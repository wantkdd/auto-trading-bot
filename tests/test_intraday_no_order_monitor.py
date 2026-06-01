"""Tests for intraday no-order monitor."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.intraday_no_order_monitor import (
    QuoteSnapshot,
    build_report,
    classify_judgement,
    is_us_market_open,
    main,
    resolve_symbols,
)


def test_market_hours_use_new_york_time() -> None:
    assert is_us_market_open(datetime(2026, 6, 1, 14, 0, tzinfo=ZoneInfo("UTC"))) is True
    assert is_us_market_open(datetime(2026, 6, 1, 22, 0, tzinfo=ZoneInfo("UTC"))) is False


def test_classify_judgement_never_creates_order_language() -> None:
    assert (
        classify_judgement(QuoteSnapshot("NVDA", "ok", 102.0, 100.0, 0.02, 1))
        == "would_review_buy_strength"
    )
    assert (
        classify_judgement(QuoteSnapshot("NVDA", "ok", 97.0, 100.0, -0.03, 1))
        == "would_review_sell_risk"
    )
    assert classify_judgement(QuoteSnapshot("NVDA", "ok", 100.5, 100.0, 0.005, 1)) == "would_hold"


def test_resolve_symbols_limits_to_ten_by_default(tmp_path: Path) -> None:
    symbols_file = tmp_path / "symbols.txt"
    symbols_file.write_text(
        "AAPL\nMSFT\nNVDA\nAMZN\nMETA\nTSLA\nGOOGL\nAVGO\nLLY\nJPM\nUNH\n",
        encoding="utf-8",
    )

    assert resolve_symbols(None, symbols_file, max_symbols=10) == (
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "META",
        "TSLA",
        "GOOGL",
        "AVGO",
        "LLY",
        "JPM",
    )


def test_build_report_records_intraday_changes_without_orders(tmp_path: Path) -> None:
    log = tmp_path / "intraday.jsonl"
    previous = {
        "quotes": [
            {"symbol": "AAPL", "judgement": "would_hold"},
            {"symbol": "NVDA", "judgement": "would_hold"},
        ]
    }
    log.write_text(json.dumps(previous) + "\n", encoding="utf-8")

    def fake_fetch(symbol: str, _token: str) -> QuoteSnapshot:
        return {
            "AAPL": QuoteSnapshot("AAPL", "ok", 101.0, 100.0, 0.01, 1),
            "NVDA": QuoteSnapshot("NVDA", "ok", 103.0, 100.0, 0.03, 1),
        }[symbol]

    report = build_report(
        argparse.Namespace(
            symbols=["AAPL", "NVDA"],
            symbols_file=str(tmp_path / "missing.txt"),
            max_symbols=10,
            log=str(log),
            finnhub_api_key="token",
            force_market_open=True,
        ),
        now=datetime(2026, 6, 1, 14, 0, tzinfo=ZoneInfo("UTC")),
        quote_fetcher=fake_fetch,
    )

    assert report["summary"]["status"] == "ok"
    assert report["summary"]["symbols"] == 2
    assert report["summary"]["changes"] == 1
    assert report["summary"]["notable"] == 1
    assert report["order_created"] is False


def test_main_skips_closed_market_without_requiring_api_key(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    markdown = tmp_path / "latest.md"
    log = tmp_path / "log.jsonl"

    assert (
        main(
            [
                "--now",
                "2026-06-01T22:00:00+00:00",
                "--output",
                str(output),
                "--markdown",
                str(markdown),
                "--log",
                str(log),
            ]
        )
        == 0
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "skipped_market_closed"
    assert not log.exists()
