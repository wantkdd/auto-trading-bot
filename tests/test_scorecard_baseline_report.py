"""Tests for scorecard baseline evaluation."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import pytest
from scripts.scorecard_baseline_report import build_report, main, score_row

COLUMNS = [
    "symbol",
    "as_of_date",
    "close",
    "volume",
    "trailing_return_1d",
    "trailing_return_5d",
    "trailing_return_20d",
    "trailing_volatility_20d",
    "close_to_sma_20",
    "close_to_sma_50",
    "volume_to_sma_20",
    "benchmark_trailing_return_20d",
    "forward_return_1d",
    "forward_return_5d",
    "forward_return_20d",
    "forward_excess_return_20d",
    "forward_max_drawdown_20d",
    "bls_macro_points_available",
]


def write_dataset(path: Path) -> None:
    rows = [
        row("AAA", "2024-01-02", momentum=0.10, forward=0.08),
        row("BBB", "2024-01-02", momentum=-0.02, forward=-0.03),
        row("AAA", "2024-01-03", momentum=0.12, forward=0.06),
        row("BBB", "2024-01-03", momentum=-0.01, forward=-0.02),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def row(symbol: str, day: str, *, momentum: float, forward: float) -> dict[str, float | str]:
    return {
        "symbol": symbol,
        "as_of_date": day,
        "close": 100.0,
        "volume": 1000.0,
        "trailing_return_1d": momentum / 5,
        "trailing_return_5d": momentum / 2,
        "trailing_return_20d": momentum,
        "trailing_volatility_20d": 0.01,
        "close_to_sma_20": momentum / 2,
        "close_to_sma_50": momentum / 2,
        "volume_to_sma_20": 0.0,
        "benchmark_trailing_return_20d": 0.01,
        "forward_return_1d": forward / 20,
        "forward_return_5d": forward / 4,
        "forward_return_20d": forward,
        "forward_excess_return_20d": forward - 0.01,
        "forward_max_drawdown_20d": min(forward, -0.01),
        "bls_macro_points_available": 3 if day >= "2024-01-03" else "",
    }


def args(dataset: Path, **overrides) -> argparse.Namespace:
    values = {
        "dataset": str(dataset),
        "validation_start": "2024-01-01",
        "top_n": 1,
        "output": str(dataset.parent / "report.json"),
        "markdown": str(dataset.parent / "report.md"),
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_score_row_uses_feature_columns_only() -> None:
    base = row("AAA", "2024-01-02", momentum=0.10, forward=0.08)
    changed_label = dict(base)
    changed_label["forward_return_20d"] = -0.99

    assert score_row({key: str(value) for key, value in base.items()}) == pytest.approx(
        score_row({key: str(value) for key, value in changed_label.items()})
    )


def test_build_report_selects_top_score_and_compares_universe(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    write_dataset(dataset)

    report = build_report(args(dataset))

    summary = report["summary"]
    assert summary["validation_dates"] == 2
    assert summary["selected_avg_forward_return_20d"] == pytest.approx(0.07)
    assert summary["universe_avg_forward_return_20d"] == pytest.approx(0.0225)
    assert summary["selected_minus_universe_forward_return_20d"] == pytest.approx(0.0475)
    assert summary["bls_macro_dates_with_points"] == 1
    assert summary["bls_macro_coverage_ratio"] == pytest.approx(0.5)
    assert summary["macro_regime_groups"] == 2
    assert summary["order_created"] is False
    assert report["date_metrics_sample"][0]["selected_symbols"] == ["AAA"]
    assert report["macro_regime_metrics"][0]["bls_macro_points_available"] == "3"
    assert report["macro_regime_metrics"][0]["validation_dates"] == 1
    assert report["macro_regime_metrics"][1]["bls_macro_points_available"] == "missing"


def test_script_writes_json_and_markdown(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    output = tmp_path / "report.json"
    markdown = tmp_path / "report.md"
    write_dataset(dataset)

    assert (
        main(
            [
                "--dataset",
                str(dataset),
                "--validation-start",
                "2024-01-01",
                "--top-n",
                "1",
                "--output",
                str(output),
                "--markdown",
                str(markdown),
            ]
        )
        == 0
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["selected_hit_rate_20d"] == 1.0
    markdown_text = markdown.read_text(encoding="utf-8")
    assert "Scorecard baseline report" in markdown_text
    assert "BLS macro availability regimes" in markdown_text
