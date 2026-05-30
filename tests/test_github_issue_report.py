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

    body = build_issue_body(
        argparse.Namespace(
            summary=str(summary),
            readiness=str(readiness),
            run_url="https://example.test/run",
            repo="wantkdd/auto-trading-bot",
            mode="success",
        )
    )

    assert "5 / 30" in body
    assert "live trading authorized: `False`" in body
    assert "human_approval_missing" in body
    assert "실주문" in body
