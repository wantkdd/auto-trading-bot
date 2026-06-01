"""Tests for independent price replication gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from scripts.independent_price_replication_gate import (
    build_report,
    compare_provider_to_signal,
    stooq_symbol,
)


def paper_signal() -> dict[str, object]:
    return {
        "as_of_date": "2026-05-29",
        "source_bars": {
            "AAPL": {"close": 100.0, "timestamp": "2026-05-29T13:30:00"},
            "GLD": {"close": 200.0, "timestamp": "2026-05-29T13:30:00"},
        },
    }


def test_missing_independent_key_blocks_without_fetching(tmp_path: Path) -> None:
    signal = tmp_path / "signal.json"
    signal.write_text(json.dumps(paper_signal()), encoding="utf-8")
    args = argparse.Namespace(
        paper_signal=str(signal),
        output=str(tmp_path / "out.json"),
        markdown=str(tmp_path / "out.md"),
        provider="auto",
        stooq_api_key="",
        alpha_vantage_api_key="",
        max_close_diff_bps=100.0,
        timeout_seconds=1.0,
    )

    report = build_report(args)

    assert report["summary"]["status"] == "blocked"
    assert report["summary"]["symbols_checked"] == 0
    assert report["blockers"] == ["independent_price_api_key_missing"]
    assert report["live_trading_authorized"] is False


def test_compare_provider_to_signal_passes_within_tolerance() -> None:
    with patch(
        "scripts.independent_price_replication_gate.fetch_provider_daily_row",
        side_effect=[{"close": 100.2}, {"close": 199.0}],
    ):
        comparisons, blockers = compare_provider_to_signal(
            paper_signal(),
            provider="alpha_vantage",
            api_key="demo-key",
            max_close_diff_bps=100.0,
            timeout_seconds=1.0,
        )

    assert blockers == []
    assert [row["status"] for row in comparisons] == ["pass", "pass"]
    assert comparisons[0]["close_diff_bps"] == 20.000000000000018


def test_compare_provider_to_signal_blocks_large_difference() -> None:
    with patch(
        "scripts.independent_price_replication_gate.fetch_provider_daily_row",
        return_value={"close": 110.0},
    ):
        comparisons, blockers = compare_provider_to_signal(
            {"as_of_date": "2026-05-29", "source_bars": {"AAPL": {"close": 100.0}}},
            provider="alpha_vantage",
            api_key="demo-key",
            max_close_diff_bps=100.0,
            timeout_seconds=1.0,
        )

    assert comparisons[0]["status"] == "blocked"
    assert blockers == ["independent_close_diff_above_limit:AAPL"]


def test_compare_provider_to_signal_blocks_malformed_signal_date() -> None:
    comparisons, blockers = compare_provider_to_signal(
        {"as_of_date": "not-a-date", "source_bars": {"AAPL": {"close": 100.0}}},
        provider="alpha_vantage",
        api_key="demo-key",
        max_close_diff_bps=100.0,
        timeout_seconds=1.0,
    )

    assert comparisons == []
    assert blockers == ["paper_signal_as_of_date_invalid_for_independent_price_replication"]


def test_compare_provider_to_signal_blocks_invalid_source_bar_close() -> None:
    comparisons, blockers = compare_provider_to_signal(
        {"as_of_date": "2026-05-29", "source_bars": {"AAPL": {"close": "bad"}}},
        provider="alpha_vantage",
        api_key="demo-key",
        max_close_diff_bps=100.0,
        timeout_seconds=1.0,
    )

    assert comparisons == []
    assert blockers == ["source_bar_close_invalid:AAPL"]


def test_build_report_blocks_invalid_paper_signal_json(tmp_path: Path) -> None:
    signal = tmp_path / "signal.json"
    signal.write_text("{not valid json", encoding="utf-8")
    args = argparse.Namespace(
        paper_signal=str(signal),
        output=str(tmp_path / "out.json"),
        markdown=str(tmp_path / "out.md"),
        provider="alpha_vantage",
        stooq_api_key="",
        alpha_vantage_api_key="demo-key",
        max_close_diff_bps=100.0,
        timeout_seconds=1.0,
        request_delay_seconds=0.0,
    )

    report = build_report(args)

    assert report["summary"]["status"] == "blocked"
    assert report["blockers"] == [
        "paper_signal_json_invalid_for_independent_price_replication"
    ]


def test_stooq_symbol_normalizes_us_symbols() -> None:
    assert stooq_symbol("AAPL") == "aapl.us"
    assert stooq_symbol("BRK-B") == "brk.b"
