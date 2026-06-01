"""Tests for market-wide no-order challenger selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from scripts.paper_challenger_signal import build_report, select_challenger
from scripts.paper_signal_dry_run import DryRunSignal


def test_select_challenger_uses_first_safe_passed_market_candidate() -> None:
    market_scan = {
        "passed_candidates": [
            {
                "name": "TQQQ_0.4_GLD_0.6",
                "symbols": ["TQQQ", "GLD"],
                "weights": [0.4, 0.6],
                "status": "pass",
            },
            {
                "name": "LLY_0.4_GLD_0.6",
                "symbols": ["LLY", "GLD"],
                "weights": [0.4, 0.6],
                "status": "pass",
            },
        ]
    }

    selected = select_challenger(market_scan)

    assert selected is not None
    assert selected["name"] == "LLY_0.4_GLD_0.6"
    assert selected["symbols"] == ["LLY", "GLD"]


def test_build_report_writes_challenger_without_changing_primary(tmp_path: Path) -> None:
    market_scan = tmp_path / "market.json"
    output = tmp_path / "challenger.json"
    market_scan.write_text(
        json.dumps(
            {
                "passed_candidates": [
                    {
                        "name": "LLY_0.4_GLD_0.6",
                        "symbols": ["LLY", "GLD"],
                        "weights": [0.4, 0.6],
                        "status": "pass",
                        "base_median_excess": 0.2,
                        "base_worst_mdd": -0.17,
                        "fundamental_status": "pass",
                        "recent_regime_status": "pass",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fake_signal = DryRunSignal(
        generated_at="2026-06-01T00:00:00+00:00",
        as_of_date="2026-05-29",
        strategy="LLY_0.4_GLD_0.6",
        target_weights={"LLY": 0.4, "GLD": 0.6},
        source_bars={},
        warnings=("do not place orders",),
    )

    with patch("scripts.paper_challenger_signal.build_signal", return_value=fake_signal):
        report = build_report(
            argparse.Namespace(
                market_scan=str(market_scan),
                output=str(output),
                report=str(tmp_path / "report.json"),
                markdown=str(tmp_path / "report.md"),
                start="2015-01-01",
                end="2026-05-29",
                data_dir="data/external",
                force_refresh=False,
            )
        )

    assert report["summary"]["status"] == "pass"
    assert report["summary"]["challenger_strategy"] == "LLY_0.4_GLD_0.6"
    assert report["summary"]["primary_strategy_changed"] is False
    assert report["live_trading_authorized"] is False
    assert json.loads(output.read_text(encoding="utf-8"))["strategy"] == "LLY_0.4_GLD_0.6"


def test_build_report_blocks_missing_market_scan(tmp_path: Path) -> None:
    report = build_report(
        argparse.Namespace(
            market_scan=str(tmp_path / "missing.json"),
            output=str(tmp_path / "challenger.json"),
            report=str(tmp_path / "report.json"),
            markdown=str(tmp_path / "report.md"),
            start="2015-01-01",
            end="2026-05-29",
            data_dir="data/external",
            force_refresh=False,
        )
    )

    assert report["summary"]["status"] == "blocked"
    assert report["blockers"] == ["market_scan_report_missing_for_challenger"]
