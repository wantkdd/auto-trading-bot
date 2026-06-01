"""Tests for dynamic liquid US universe builder."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from scripts.build_us_liquid_universe import (
    RankedSymbol,
    TableParser,
    build_report,
    collect_source_symbols,
    normalize_symbol,
    rank_symbols,
    select_symbols,
)

from auto_trading_bot.domain import Bar


def test_table_parser_extracts_wikipedia_style_rows() -> None:
    html = """
    <table><tr><th>Symbol</th><th>Name</th></tr>
    <tr><td>AAPL</td><td>Apple</td></tr><tr><td>BRK.B</td><td>Berkshire</td></tr></table>
    """

    assert TableParser().parse(html)[0] == [
        ["Symbol", "Name"],
        ["AAPL", "Apple"],
        ["BRK.B", "Berkshire"],
    ]


def test_normalize_symbol_allows_valid_suffixes_and_normalizes_class_dot() -> None:
    assert normalize_symbol("brk.b") == "BRK-B"
    assert normalize_symbol("LULU") == "LULU"
    assert normalize_symbol("bad/symbol") == ""


def test_collect_source_symbols_uses_seed_when_remote_skipped(tmp_path: Path) -> None:
    seed = tmp_path / "seed.txt"
    seed.write_text("AAPL\nGLD\nTQQQ\n", encoding="utf-8")

    symbols = collect_source_symbols(seed, skip_remote=True)

    assert "AAPL" in symbols
    assert "GLD" in symbols
    assert "SPY" in symbols


def test_rank_symbols_orders_by_recent_dollar_volume(tmp_path: Path) -> None:
    def fake_fetch(**kwargs):
        symbol = kwargs["user_symbol"]
        volume = {"AAPL": 10.0, "MSFT": 100.0}[symbol]
        return (
            (
                Bar(datetime(2026, 1, 1), 10.0, 10.0, 10.0, 10.0, volume),
                Bar(datetime(2026, 1, 2), 20.0, 20.0, 20.0, 20.0, volume),
            ),
            {"status": "ok"},
        )

    with patch("scripts.build_us_liquid_universe.fetch_or_load_bars", side_effect=fake_fetch):
        ranked = rank_symbols(
            ["AAPL", "MSFT"],
            start=datetime(2026, 1, 1).date(),
            end=datetime(2026, 1, 2).date(),
            data_dir=tmp_path,
            force_refresh=False,
        )

    assert [item.symbol for item in ranked] == ["MSFT", "AAPL"]


def test_select_symbols_keeps_always_include_then_top_ranked() -> None:
    ranked = [
        RankedSymbol("MSFT", "test", "ok", 100.0, 10.0, 10.0),
        RankedSymbol("NVDA", "test", "ok", 90.0, 10.0, 9.0),
    ]

    assert select_symbols(ranked, max_output_symbols=3, always_include=["AAPL", "GLD"]) == [
        "AAPL",
        "GLD",
        "MSFT",
    ]


def test_build_report_requires_minimum_10_selected_symbols(tmp_path: Path) -> None:
    seed = tmp_path / "seed.txt"
    seed.write_text("AAPL\nMSFT\nNVDA\n", encoding="utf-8")

    with patch("scripts.build_us_liquid_universe.rank_symbols", return_value=[]):
        report = build_report(
            argparse.Namespace(
                seed=str(seed),
                output=str(tmp_path / "out.txt"),
                report=str(tmp_path / "out.json"),
                markdown=str(tmp_path / "out.md"),
                data_dir=str(tmp_path),
                end="2026-01-02",
                lookback_days=45,
                max_rank_candidates=300,
                max_output_symbols=150,
                min_selected_symbols=10,
                always_include=["AAPL", "GLD"],
                force_refresh=False,
                skip_remote=True,
            )
        )

    assert report["summary"]["min_selected_symbols"] == 10
    assert report["summary"]["selected"] < 10
    assert report["summary"]["status"] == "blocked"
    assert "dynamic_universe_below_minimum_10_symbols" in report["blockers"]
