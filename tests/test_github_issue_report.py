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
    operational_risk = tmp_path / "operational-risk.json"
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

    body = build_issue_body(
        argparse.Namespace(
            summary=str(summary),
            readiness=str(readiness),
            market_scan=str(market_scan),
            bls_macro=str(bls_macro),
            no_order_preview=str(no_order_preview),
            operational_risk=str(operational_risk),
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
    assert "operational risk status: `monitoring`" in body
    assert "market-data staleness gate: `pass`" in body
    assert "kill switch: `armed`" in body
    assert "order created: `False`" in body
    assert "human_approval_missing" in body
    assert "실주문" in body
