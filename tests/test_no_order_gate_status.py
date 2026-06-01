"""Tests for no-order gate status routing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.no_order_gate_status import build_report, main


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_gate_status_passes_when_no_order_gates_are_green(tmp_path: Path) -> None:
    operational = _write(
        tmp_path / "operational.json",
        {
            "summary": {
                "status": "monitoring",
                "halt_required": False,
                "market_data_staleness_gate": "pass",
                "trade_intent_safety": "pass",
                "order_created": False,
                "live_trading_authorized": False,
            }
        },
    )
    independent = _write(
        tmp_path / "independent.json",
        {"summary": {"status": "pass", "symbols_checked": 2}},
    )
    readiness = _write(
        tmp_path / "readiness.json",
        {
            "live_trading_authorized": False,
            "summary": {
                "live_readiness_status": "blocked_before_human_review",
                "live_trading_authorized": False,
            },
        },
    )
    args = argparse.Namespace(
        operational_risk=str(operational),
        independent_price=str(independent),
        readiness=str(readiness),
    )

    report = build_report(args)

    assert report["summary"]["status"] == "pass"
    assert report["summary"]["mode"] == "success"
    assert report["blockers"] == []


def test_gate_status_marks_action_needed_on_halt_or_missing_replication(tmp_path: Path) -> None:
    operational = _write(
        tmp_path / "operational.json",
        {
            "summary": {
                "status": "halt",
                "halt_required": True,
                "market_data_staleness_gate": "blocked",
                "trade_intent_safety": "halt",
                "order_created": False,
                "live_trading_authorized": False,
            }
        },
    )
    readiness = _write(
        tmp_path / "readiness.json",
        {"live_trading_authorized": False, "summary": {"live_trading_authorized": False}},
    )
    args = argparse.Namespace(
        operational_risk=str(operational),
        independent_price=str(tmp_path / "missing-independent.json"),
        readiness=str(readiness),
    )

    report = build_report(args)

    assert report["summary"]["status"] == "action_needed"
    assert report["summary"]["mode"] == "action-needed"
    assert "operational_risk_gate_not_monitoring" in report["blockers"]
    assert "independent_price_replication_report_missing" in report["blockers"]


def test_gate_status_writes_github_outputs(tmp_path: Path) -> None:
    output = tmp_path / "gate.json"
    markdown = tmp_path / "gate.md"
    github_output = tmp_path / "github-output.txt"

    assert (
        main(
            [
                "--operational-risk",
                str(tmp_path / "missing-operational.json"),
                "--independent-price",
                str(tmp_path / "missing-independent.json"),
                "--readiness",
                str(tmp_path / "missing-readiness.json"),
                "--output",
                str(output),
                "--markdown",
                str(markdown),
                "--github-output",
                str(github_output),
            ]
        )
        == 0
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["summary"]["mode"] == "action-needed"
    assert "mode=action-needed" in github_output.read_text(encoding="utf-8")
    assert "no orders" in markdown.read_text(encoding="utf-8")
