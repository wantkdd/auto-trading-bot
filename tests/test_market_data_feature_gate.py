"""Tests for broad no-order market feature gate."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from scripts.market_data_feature_gate import build_report, main


def write_csv(path: Path, symbol: str, start_close: float, drift: float = 0.01) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["timestamp,open,high,low,close,volume"]
    close = start_close
    start = datetime(2026, 1, 1, 14, 30)
    for index in range(230):
        close *= 1.0 + drift
        stamp = start + timedelta(days=index)
        rows.append(f"{stamp.isoformat()},{close},{close},{close},{close},{1000000 + index}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def args(tmp_path: Path, symbols: list[str]):
    data_dir = tmp_path / "data"
    core_symbols = [
        "SPY",
        "QQQ",
        "DIA",
        "IWM",
        "GLD",
        "TLT",
        "IEF",
        "SHY",
        "VNQ",
        "XLK",
        "XLV",
        "XLP",
        "XLU",
        "XLF",
        "XLE",
        "XLI",
        "XLY",
        "XLC",
        "XLRE",
        "XLB",
    ]
    for symbol in symbols + core_symbols:
        write_csv(data_dir / f"{symbol.lower()}_yahoo_daily_2026_2026.csv", symbol, 100.0)
    return argparse.Namespace(
        symbols=symbols,
        symbols_file=str(tmp_path / "missing.txt"),
        start="2026-01-01",
        end="2026-12-31",
        data_dir=str(data_dir),
        max_symbols=10,
        min_usable_assets=5,
        min_breadth_coverage=0.5,
        max_freshness_lag_days=7,
        force_refresh=False,
        output=str(tmp_path / "feature.json"),
        markdown=str(tmp_path / "feature.md"),
    )


def test_build_report_marks_features_usable_without_orders(tmp_path: Path) -> None:
    report = build_report(args(tmp_path, ["AAPL", "MSFT", "NVDA", "JPM", "LLY", "PG"]))

    assert report["summary"]["usable_assets"] >= 5
    assert report["summary"]["order_created"] is False
    assert report["live_trading_authorized"] is False
    assert "regime" in report


def test_main_writes_json_and_markdown(tmp_path: Path) -> None:
    a = args(tmp_path, ["AAPL", "MSFT", "NVDA", "JPM", "LLY", "PG"])

    assert (
        main(
            [
                "--symbols",
                *a.symbols,
                "--start",
                a.start,
                "--end",
                a.end,
                "--data-dir",
                a.data_dir,
                "--output",
                a.output,
                "--markdown",
                a.markdown,
                "--min-usable-assets",
                "5",
                "--min-breadth-coverage",
                "0.5",
            ]
        )
        == 0
    )

    payload = json.loads(Path(a.output).read_text(encoding="utf-8"))
    assert payload["summary"]["order_created"] is False
    assert "Market data feature gate" in Path(a.markdown).read_text(encoding="utf-8")
