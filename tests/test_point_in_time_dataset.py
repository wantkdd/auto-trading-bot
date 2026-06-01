"""Tests for point-in-time daily modeling dataset generation."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from scripts.point_in_time_dataset import build_dataset, main


def write_prices(path: Path, closes: list[float], *, start: date = date(2024, 1, 2)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["timestamp,open,high,low,close,volume"]
    for offset, close in enumerate(closes):
        day = start + timedelta(days=offset)
        rows.append(f"{day.isoformat()}T09:30:00,{close},{close},{close},{close},{1000 + offset}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def args(tmp_path: Path, **overrides) -> argparse.Namespace:
    values = {
        "symbols": ["AAA"],
        "symbols_file": str(tmp_path / "symbols.txt"),
        "data_dir": str(tmp_path),
        "benchmark": "SPY",
        "start": "2024-01-02",
        "end": "2024-04-30",
        "min_history": 50,
        "output": str(tmp_path / "dataset.csv"),
        "summary": str(tmp_path / "summary.json"),
        "markdown": str(tmp_path / "summary.md"),
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_build_dataset_uses_past_features_and_future_labels(tmp_path: Path) -> None:
    closes = [100 + offset for offset in range(90)]
    benchmark = [200 + offset for offset in range(90)]
    write_prices(tmp_path / "aaa_yahoo_daily_2015_2026.csv", closes)
    write_prices(tmp_path / "spy_yahoo_daily_2015_2026.csv", benchmark)

    result = build_dataset(args(tmp_path))

    assert result.summary["summary"]["rows"] == 20
    first = result.rows[0]
    assert first["symbol"] == "AAA"
    assert first["as_of_date"] == "2024-02-21"
    assert first["trailing_return_5d"] == pytest.approx(150 / 145 - 1)
    assert first["forward_return_5d"] == pytest.approx(155 / 150 - 1)
    assert result.summary["summary"]["order_created"] is False
    assert result.summary["live_trading_authorized"] is False


def test_future_price_changes_do_not_change_same_date_features(tmp_path: Path) -> None:
    original = [100 + offset for offset in range(90)]
    changed = list(original)
    changed[55] = 500.0
    benchmark = [200 + offset for offset in range(90)]
    left = tmp_path / "left"
    right = tmp_path / "right"
    write_prices(left / "aaa_yahoo_daily_2015_2026.csv", original)
    write_prices(left / "spy_yahoo_daily_2015_2026.csv", benchmark)
    write_prices(right / "aaa_yahoo_daily_2015_2026.csv", changed)
    write_prices(right / "spy_yahoo_daily_2015_2026.csv", benchmark)

    left_result = build_dataset(args(left, data_dir=str(left)))
    right_result = build_dataset(args(right, data_dir=str(right)))
    left_first = left_result.rows[0]
    right_first = right_result.rows[0]

    feature_columns = [
        "trailing_return_1d",
        "trailing_return_5d",
        "trailing_return_20d",
        "trailing_volatility_20d",
        "close_to_sma_20",
        "close_to_sma_50",
        "volume_to_sma_20",
        "benchmark_trailing_return_20d",
    ]
    for column in feature_columns:
        assert right_first[column] == pytest.approx(left_first[column])
    assert right_first["forward_return_5d"] != pytest.approx(left_first["forward_return_5d"])


def test_missing_and_leveraged_symbols_are_reported_without_rows(tmp_path: Path) -> None:
    closes = [100 + offset for offset in range(90)]
    write_prices(tmp_path / "spy_yahoo_daily_2015_2026.csv", closes)

    result = build_dataset(args(tmp_path, symbols=["MISSING", "TQQQ"]))

    assert result.summary["summary"]["rows"] == 0
    assert result.summary["summary"]["blocked_leveraged_symbols"] == 1
    assert result.summary["summary"]["missing_price_data"] == 1
    assert result.summary["blocked_leveraged_symbols"] == ["TQQQ"]
    assert result.summary["missing_price_data_symbols"] == ["MISSING"]


def test_script_writes_dataset_summary_and_markdown(tmp_path: Path) -> None:
    closes = [100 + offset for offset in range(90)]
    benchmark = [200 + offset for offset in range(90)]
    write_prices(tmp_path / "aaa_yahoo_daily_2015_2026.csv", closes)
    write_prices(tmp_path / "spy_yahoo_daily_2015_2026.csv", benchmark)
    output = tmp_path / "dataset.csv"
    summary = tmp_path / "summary.json"
    markdown = tmp_path / "summary.md"

    assert (
        main(
            [
                "--symbols",
                "AAA",
                "--data-dir",
                str(tmp_path),
                "--benchmark",
                "SPY",
                "--start",
                "2024-01-02",
                "--end",
                "2024-04-30",
                "--min-history",
                "50",
                "--output",
                str(output),
                "--summary",
                str(summary),
                "--markdown",
                str(markdown),
            ]
        )
        == 0
    )

    rows = read_rows(output)
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert len(rows) == 20
    assert payload["summary"]["symbols_written"] == 1
    assert "Point-in-time daily" in markdown.read_text(encoding="utf-8")
