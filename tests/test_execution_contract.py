"""Tests for broker execution preflight contract."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from auto_trading_bot.execution_contract import (
    BrokerOrderSide,
    ExecutionApproval,
    ExecutionContractError,
    ExecutionPreflightPolicy,
    ExecutionPreflightStatus,
    ExecutionVenue,
    NullBrokerExecutionAdapter,
    build_tickets_from_no_order_plan,
    evaluate_execution_preflight,
)


def accepted_plan():
    return {
        "accepted": [
            {
                "symbol": "aapl",
                "side": "would_buy",
                "quantity": 2,
                "reference_price": 300.0,
                "created_at": "2026-06-01T13:30:00+00:00",
                "reason": "rebalance",
            }
        ]
    }


def test_build_tickets_from_no_order_plan_creates_idempotent_broker_shape() -> None:
    created_at = datetime(2026, 6, 1, 14, 0, tzinfo=UTC)

    first = build_tickets_from_no_order_plan(accepted_plan(), created_at=created_at)
    second = build_tickets_from_no_order_plan(accepted_plan(), created_at=created_at)

    assert len(first) == 1
    assert first[0].symbol == "AAPL"
    assert first[0].side is BrokerOrderSide.BUY
    assert first[0].estimated_notional == pytest.approx(600.0)
    assert first[0].client_order_id == second[0].client_order_id
    assert first[0].to_dict()["order_created"] is False


def test_build_tickets_rejects_non_no_order_sides() -> None:
    with pytest.raises(ExecutionContractError, match="unsupported no-order side"):
        build_tickets_from_no_order_plan(
            {"accepted": [{"symbol": "AAPL", "side": "buy", "quantity": 1, "reference_price": 1}]}
        )


def test_preflight_blocks_until_api_approvals_and_observation_exist() -> None:
    tickets = build_tickets_from_no_order_plan(accepted_plan())

    report = evaluate_execution_preflight(
        tickets,
        approval=ExecutionApproval(paper_observation_days=1),
        policy=ExecutionPreflightPolicy(allowed_symbols=frozenset({"AAPL"})),
    )

    assert report.status is ExecutionPreflightStatus.BLOCKED
    assert "human_approval_missing" in report.blockers
    assert "broker_api_adapter_not_connected" in report.blockers
    assert "minimum_paper_observation_days_missing" in report.blockers
    assert report.to_dict()["submit_attempted"] is False


def test_preflight_can_reach_paper_adapter_ready_without_submitting() -> None:
    tickets = build_tickets_from_no_order_plan(accepted_plan())

    report = evaluate_execution_preflight(
        tickets,
        approval=ExecutionApproval(
            venue=ExecutionVenue.PAPER,
            human_approved=True,
            broker_api_connected=True,
            account_reconciled=True,
            market_data_fresh=True,
            kill_switch_armed=True,
            paper_observation_days=30,
        ),
        policy=ExecutionPreflightPolicy(allowed_symbols=frozenset({"AAPL"})),
    )

    assert report.status is ExecutionPreflightStatus.READY_FOR_PAPER_API_ADAPTER
    assert report.blockers == ()
    assert report.order_created is False


def test_live_preflight_requires_live_and_legal_approval() -> None:
    tickets = build_tickets_from_no_order_plan(accepted_plan())

    report = evaluate_execution_preflight(
        tickets,
        approval=ExecutionApproval(
            venue=ExecutionVenue.LIVE,
            human_approved=True,
            broker_api_connected=True,
            account_reconciled=True,
            market_data_fresh=True,
            kill_switch_armed=True,
            paper_observation_days=30,
        ),
        policy=ExecutionPreflightPolicy(allowed_symbols=frozenset({"AAPL"})),
    )

    assert "live_trading_authorization_missing" in report.blockers
    assert "legal_tax_review_missing_for_live" in report.blockers


def test_null_adapter_never_creates_orders() -> None:
    ticket = build_tickets_from_no_order_plan(accepted_plan())[0]

    result = NullBrokerExecutionAdapter().route_ticket(ticket)

    assert result.order_created is False
    assert result.status == "broker_api_adapter_not_configured"
