"""Tests for broker execution preflight report generation."""

from __future__ import annotations

import argparse
import json

from scripts.broker_execution_preflight_report import build_report, main


def args(tmp_path, **overrides):
    values = {
        "no_order_preview": str(tmp_path / "preview.json"),
        "paper_summary": str(tmp_path / "paper.json"),
        "output": str(tmp_path / "preflight.json"),
        "markdown": str(tmp_path / "preflight.md"),
        "environment": "paper",
        "max_order_notional": 1_000.0,
        "max_total_notional": 2_000.0,
        "min_paper_observation_days": 12,
        "allowed_symbols": None,
        "blocked_symbols": [],
        "human_approved": False,
        "broker_api_connected": False,
        "account_reconciled": False,
        "market_data_fresh": False,
        "kill_switch_armed": False,
        "legal_tax_review_complete": False,
        "live_trading_authorized": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def write_inputs(tmp_path, observed_days=1):
    (tmp_path / "preview.json").write_text(
        json.dumps(
            {
                "policy": {"allowed_symbols": ["AAPL"]},
                "plan": {
                    "accepted": [
                        {
                            "symbol": "AAPL",
                            "side": "would_buy",
                            "quantity": 2,
                            "reference_price": 300.0,
                            "created_at": "2026-06-01T13:30:00+00:00",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "paper.json").write_text(
        json.dumps({"observed_days": observed_days}), encoding="utf-8"
    )


def test_build_report_blocks_without_required_approvals(tmp_path) -> None:
    write_inputs(tmp_path, observed_days=1)

    report = build_report(args(tmp_path))

    assert report["summary"]["status"] == "blocked"
    assert report["summary"]["ticket_count"] == 1
    assert report["summary"]["order_created"] is False
    assert "human_approval_missing" in report["preflight"]["blockers"]
    assert "minimum_paper_observation_days_missing" in report["preflight"]["blockers"]


def test_build_report_can_be_paper_api_attachable_after_approvals(tmp_path) -> None:
    write_inputs(tmp_path, observed_days=12)

    report = build_report(
        args(
            tmp_path,
            human_approved=True,
            broker_api_connected=True,
            account_reconciled=True,
            market_data_fresh=True,
            kill_switch_armed=True,
        )
    )

    assert report["summary"]["status"] == "ready_for_paper_api_adapter"
    assert report["summary"]["api_attachable_after_approvals"] is True
    assert report["summary"]["submit_attempted"] is False


def test_script_writes_outputs(tmp_path) -> None:
    write_inputs(tmp_path, observed_days=1)
    output = tmp_path / "preflight.json"
    markdown = tmp_path / "preflight.md"

    assert (
        main(
            [
                "--no-order-preview",
                str(tmp_path / "preview.json"),
                "--paper-summary",
                str(tmp_path / "paper.json"),
                "--output",
                str(output),
                "--markdown",
                str(markdown),
            ]
        )
        == 0
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "blocked"
    assert "Broker execution preflight" in markdown.read_text(encoding="utf-8")
