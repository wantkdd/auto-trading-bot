"""Tests for broader market universe candidate scanning helpers."""

from __future__ import annotations

import argparse

import scripts.market_universe_candidate_scan as market_scan
from scripts.fundamental_macro_recent_gate import STOCK_SYMBOLS
from scripts.market_universe_candidate_scan import (
    build_scan_report,
    compact_candidate,
    resolve_symbols,
)

from conftest import PROJECT_ROOT


def test_resolve_symbols_deduplicates_and_uppercases_cli_symbols(tmp_path) -> None:
    assert resolve_symbols(["aapl", "AAPL", "gld"], tmp_path / "missing.txt") == (
        "AAPL",
        "GLD",
    )


def test_resolve_symbols_reads_commentable_symbol_file(tmp_path) -> None:
    path = tmp_path / "symbols.txt"
    path.write_text("# comment\naapl\n\nGLD # defensive\n", encoding="utf-8")

    assert resolve_symbols(None, path) == ("AAPL", "GLD")


def test_watchlist_is_deduplicated_and_core_stocks_have_fundamental_gates() -> None:
    symbols = resolve_symbols(None, PROJECT_ROOT / "data/universe/us_large_liquid_watchlist.txt")

    assert len(symbols) == len(set(symbols))
    assert "BRK-B" in symbols
    assert all(" " not in symbol for symbol in symbols)
    assert {"AAPL", "NVDA", "JPM", "PLD"}.issubset(STOCK_SYMBOLS)


def test_compact_candidate_preserves_gate_status() -> None:
    row = {
        "name": "AAPL_0.3_GLD_0.7",
        "symbols": ["AAPL", "GLD"],
        "weights": [0.3, 0.7],
        "status": "pass",
        "base_median_excess": 0.12,
        "base_worst_mdd": -0.18,
        "fundamental_status": "pass",
        "recent_regime_status": "pass",
    }

    assert compact_candidate(row)["status"] == "pass"


def test_build_scan_report_distinguishes_requested_allowed_and_valid_assets(
    monkeypatch, tmp_path
) -> None:
    def fake_gate_report(args):
        assert "TQQQ" not in args.symbols
        return {
            "summary": {"candidates": 2},
            "universe_summary": {"valid_assets": 2},
            "price_data": [
                {"symbol": "AAPL", "status": "ok"},
                {"symbol": "GLD", "status": "ok"},
                {"symbol": "MISSING", "status": "fetch_failed"},
            ],
            "candidate_gates": [
                {
                    "name": "AAPL_0.3_GLD_0.7",
                    "symbols": ["AAPL", "GLD"],
                    "weights": [0.3, 0.7],
                    "status": "pass",
                    "base_median_excess": 0.12,
                    "base_worst_mdd": -0.18,
                    "fundamental_status": "pass",
                    "recent_regime_status": "pass",
                    "failure_reasons": [],
                },
                {
                    "name": "MISSING_0.3_GLD_0.7",
                    "symbols": ["MISSING", "GLD"],
                    "weights": [0.3, 0.7],
                    "status": "review",
                    "base_median_excess": None,
                    "base_worst_mdd": None,
                    "fundamental_status": "review",
                    "recent_regime_status": "review",
                    "failure_reasons": ["missing_price_data"],
                },
            ],
        }

    monkeypatch.setattr(market_scan, "build_gate_report", fake_gate_report)

    report = build_scan_report(
        argparse.Namespace(
            symbols=["AAPL", "GLD", "TQQQ", "MISSING"],
            symbols_file=str(tmp_path / "unused.txt"),
            start="2020-01-01",
            end="2026-01-01",
            data_dir=str(tmp_path),
            sec_cache_dir=str(tmp_path / "sec"),
            top_candidates=10,
            force_refresh=False,
            skip_sec_refresh=True,
        )
    )

    assert report["summary"]["requested_symbols"] == 4
    assert report["summary"]["allowed_symbols"] == 3
    assert report["summary"]["valid_assets"] == 2
    assert report["summary"]["missing_price_data"] == 1
    assert report["universe_policy"]["blocked_symbols"] == ["TQQQ"]
    assert report["live_trading_authorized"] is False
