"""Tests for GitHub paper-observation issue reporting."""

from __future__ import annotations

import argparse
import json

from scripts.github_issue_report import build_issue_body, format_percent


def test_format_percent_handles_numbers_and_missing_values() -> None:
    assert format_percent(0.1234) == "12.34%"
    assert format_percent(None) == "unknown"


def test_build_issue_body_preserves_no_live_trading_boundary(tmp_path) -> None:
    summary = tmp_path / "summary.json"
    readiness = tmp_path / "readiness.json"
    market_scan = tmp_path / "market-scan.json"
    bls_macro = tmp_path / "bls-macro.json"
    no_order_preview = tmp_path / "no-order-preview.json"
    challenger_selection = tmp_path / "challenger-selection.json"
    challenger_summary = tmp_path / "challenger-summary.json"
    operational_risk = tmp_path / "operational-risk.json"
    independent_price = tmp_path / "independent-price.json"
    summary.write_text(
        json.dumps(
            {
                "status": "collecting",
                "observed_days": 5,
                "required_days": 30,
                "latest_as_of_date": "2026-06-05",
                "latest_virtual_equity": 10_100.0,
                "total_return_since_first_observation": 0.01,
                "max_drawdown_since_first_observation": -0.02,
            }
        ),
        encoding="utf-8",
    )
    readiness.write_text(
        json.dumps(
            {
                "live_trading_authorized": False,
                "summary": {"paper_dry_run_ready": True},
                "live_blockers": ["human_approval_missing"],
            }
        ),
        encoding="utf-8",
    )
    market_scan.write_text(
        json.dumps(
            {
                "summary": {
                    "symbols": 82,
                    "passed": 3,
                    "top_candidate": "NVDA_0.3_GLD_0.7",
                }
            }
        ),
        encoding="utf-8",
    )
    bls_macro.write_text(
        json.dumps({"summary": {"status": "ok", "latest_points": 3}}),
        encoding="utf-8",
    )
    no_order_preview.write_text(
        json.dumps(
            {
                "summary": {
                    "status": "ok",
                    "accepted": 2,
                    "rejected": 0,
                    "total_notional": 9482.45,
                    "order_created": False,
                }
            }
        ),
        encoding="utf-8",
    )
    challenger_selection.write_text(
        json.dumps(
            {
                "summary": {
                    "status": "pass",
                    "challenger_strategy": "LLY_0.4_GLD_0.6",
                    "primary_strategy_changed": False,
                }
            }
        ),
        encoding="utf-8",
    )
    challenger_summary.write_text(
        json.dumps(
            {
                "status": "collecting",
                "observed_days": 5,
                "latest_virtual_equity": 10_250.0,
                "total_return_since_first_observation": 0.025,
                "max_drawdown_since_first_observation": -0.01,
            }
        ),
        encoding="utf-8",
    )
    operational_risk.write_text(
        json.dumps(
            {
                "summary": {
                    "status": "monitoring",
                    "halt_required": False,
                    "market_data_staleness_gate": "pass",
                    "drift_monitor": "pass",
                    "kill_switch": "armed",
                }
            }
        ),
        encoding="utf-8",
    )
    independent_price.write_text(
        json.dumps(
            {
                "summary": {
                    "status": "pass",
                    "provider": "alpha_vantage",
                    "symbols_checked": 2,
                }
            }
        ),
        encoding="utf-8",
    )

    body = build_issue_body(
        argparse.Namespace(
            summary=str(summary),
            readiness=str(readiness),
            market_scan=str(market_scan),
            bls_macro=str(bls_macro),
            no_order_preview=str(no_order_preview),
            challenger_selection=str(challenger_selection),
            challenger_summary=str(challenger_summary),
            operational_risk=str(operational_risk),
            independent_price=str(independent_price),
            run_url="https://example.test/run",
            repo="wantkdd/auto-trading-bot",
            mode="success",
        )
    )

    assert "5 / 30" in body
    assert "live trading authorized: `False`" in body
    assert "시장 후보군 스캔 종목수: `82`" in body
    assert "NVDA_0.3_GLD_0.7" in body
    assert "BLS macro status: `ok`" in body
    assert "BLS macro latest points: `3`" in body
    assert "no-order preview status: `ok`" in body
    assert "no-order accepted/rejected: `2 / 0`" in body
    assert "challenger status: `pass`" in body
    assert "challenger strategy: `LLY_0.4_GLD_0.6`" in body
    assert "primary strategy changed: `False`" in body
    assert "challenger observation status: `collecting`" in body
    assert "challenger observed days: `5`" in body
    assert "challenger virtual equity: `10250.0`" in body
    assert "challenger total return: `2.50%`" in body
    assert "challenger max drawdown: `-1.00%`" in body
    assert "operational risk status: `monitoring`" in body
    assert "market-data staleness gate: `pass`" in body
    assert "kill switch: `armed`" in body
    assert "independent price status: `pass`" in body
    assert "independent price provider: `alpha_vantage`" in body
    assert "order created: `False`" in body
    assert "human_approval_missing" in body
    assert "실주문" in body


def test_build_issue_body_supports_action_needed_mode(tmp_path) -> None:
    body = build_issue_body(
        argparse.Namespace(
            summary=str(tmp_path / "missing-summary.json"),
            readiness=str(tmp_path / "missing-readiness.json"),
            market_scan=str(tmp_path / "missing-market.json"),
            bls_macro=str(tmp_path / "missing-bls.json"),
            no_order_preview=str(tmp_path / "missing-preview.json"),
            challenger_selection=str(tmp_path / "missing-challenger.json"),
            challenger_summary=str(tmp_path / "missing-challenger-summary.json"),
            operational_risk=str(tmp_path / "missing-operational.json"),
            independent_price=str(tmp_path / "missing-independent.json"),
            run_url="",
            repo="wantkdd/auto-trading-bot",
            mode="action-needed",
        )
    )

    assert "게이트 확인 필요" in body
    assert "readiness_report_missing" in body
    assert "live trading authorized: `False`" in body
