"""No-order broker adapter contract tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from auto_trading_bot.broker_contract import (
    BrokerContractError,
    FixtureNoOrderBrokerAdapter,
    NoOrderSafetyPolicy,
    OrderIntentSide,
    PaperOrderIntent,
    build_intents_from_trade_rows,
)
from auto_trading_bot.domain import DomainValidationError


def intent(symbol: str, side: OrderIntentSide, quantity: int, price: float) -> PaperOrderIntent:
    return PaperOrderIntent(
        symbol=symbol,
        side=side,
        quantity=quantity,
        reference_price=price,
        created_at=datetime(2026, 6, 1, 13, 30),
    )


def test_fixture_adapter_accepts_valid_intents_without_creating_orders() -> None:
    adapter = FixtureNoOrderBrokerAdapter(
        NoOrderSafetyPolicy(
            max_order_notional=1_000,
            max_total_notional=2_000,
            allowed_symbols=frozenset({"AAPL", "GLD"}),
        )
    )

    plan = adapter.preview(
        [
            intent("aapl", OrderIntentSide.WOULD_BUY, 2, 300.0),
            intent("GLD", OrderIntentSide.WOULD_SELL, 1, 400.0),
        ]
    )

    assert plan.order_created is False
    assert plan.live_trading_authorized is False
    assert plan.paper_api_authorized is False
    assert [row.symbol for row in plan.accepted] == ["AAPL", "GLD"]
    assert plan.rejected == ()
    assert plan.total_notional == pytest.approx(1_000.0)
    assert plan.to_dict()["safety"] == (
        "no-order broker contract only; no broker, no credentials, no API calls"
    )


def test_fixture_adapter_rejects_blocked_symbols_and_notional_limits() -> None:
    adapter = FixtureNoOrderBrokerAdapter(
        NoOrderSafetyPolicy(
            max_order_notional=500,
            max_total_notional=700,
            allowed_symbols=frozenset({"AAPL"}),
            blocked_symbols=frozenset({"GLD"}),
        )
    )

    plan = adapter.preview(
        [
            intent("AAPL", OrderIntentSide.WOULD_BUY, 1, 600.0),
            intent("GLD", OrderIntentSide.WOULD_SELL, 1, 100.0),
            intent("MSFT", OrderIntentSide.WOULD_BUY, 1, 100.0),
        ]
    )

    assert plan.accepted == ()
    assert plan.rejection_reasons["AAPL"] == ("order_notional_limit_exceeded",)
    assert plan.rejection_reasons["GLD"] == ("symbol_not_allowed", "symbol_blocked")
    assert plan.rejection_reasons["MSFT"] == ("symbol_not_allowed",)


def test_safety_policy_refuses_any_api_authorization_flags() -> None:
    with pytest.raises(DomainValidationError, match="outside this contract"):
        NoOrderSafetyPolicy(live_trading_authorized=True)
    with pytest.raises(DomainValidationError, match="outside this contract"):
        NoOrderSafetyPolicy(paper_api_authorized=True)


def test_build_intents_from_trade_rows_preserves_would_buy_and_would_sell_only() -> None:
    rows = [
        {"symbol": "aapl", "side": "would_buy", "quantity": 3, "reference_price": 10.0},
        {"symbol": "gld", "side": "would_sell", "quantity": 2, "reference_price": 20.0},
    ]

    intents = build_intents_from_trade_rows(rows, created_at=datetime(2026, 6, 1))

    assert [row.symbol for row in intents] == ["AAPL", "GLD"]
    assert [row.side for row in intents] == [
        OrderIntentSide.WOULD_BUY,
        OrderIntentSide.WOULD_SELL,
    ]


def test_build_intents_rejects_real_order_like_side() -> None:
    with pytest.raises(BrokerContractError, match="unsupported paper side"):
        build_intents_from_trade_rows(
            [{"symbol": "AAPL", "side": "buy", "quantity": 1, "reference_price": 10.0}],
            created_at=datetime(2026, 6, 1),
        )


def test_build_intents_rejects_tainted_live_order_metadata() -> None:
    base_row = {
        "symbol": "AAPL",
        "side": "would_buy",
        "quantity": 1,
        "reference_price": 10.0,
    }

    tainted_rows = (
        {**base_row, "order_created": True},
        {**base_row, "live_trading_authorized": True},
        {**base_row, "paper_api_authorized": True},
        {**base_row, "broker_order_id": "abc123"},
    )

    for row in tainted_rows:
        with pytest.raises(BrokerContractError):
            build_intents_from_trade_rows([row], created_at=datetime(2026, 6, 1))
