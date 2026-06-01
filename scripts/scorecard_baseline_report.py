"""Evaluate an auditable scorecard baseline on point-in-time labels.

This is a no-order research evaluator. It ranks symbols using feature columns
only, then evaluates forward labels offline. It never creates orders, connects
to a broker, or reads credentials.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

DEFAULT_DATASET = ".omx/datasets/point-in-time-daily.csv"
DEFAULT_OUTPUT = ".omx/reports/scorecard-baseline-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/scorecard-baseline-latest.md"
FEATURE_WEIGHTS = {
    "trailing_return_20d": 0.35,
    "close_to_sma_50": 0.25,
    "trailing_return_5d": 0.15,
    "volume_to_sma_20": 0.10,
    "benchmark_trailing_return_20d": 0.05,
    "trailing_volatility_20d": -0.30,
}


@dataclass(frozen=True)
class ScoredRow:
    as_of_date: date
    symbol: str
    score: float
    forward_return_20d: float
    forward_excess_return_20d: float
    forward_max_drawdown_20d: float
    bls_macro_points_available: int | None = None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate point-in-time scorecard baseline.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--validation-start", default="2023-01-01")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    write_json(Path(args.output), report)
    write_markdown(Path(args.markdown), report)
    summary = report["summary"]
    print(
        (
            "scorecard baseline status={status} dates={validation_dates} "
            "selected_avg={selected_avg_forward_return_20d}"
        ).format(**summary)
    )
    print(f"json={args.output}")
    print(f"markdown={args.markdown}")
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    if args.top_n <= 0:
        raise SystemExit("top-n must be positive")
    validation_start = date.fromisoformat(str(args.validation_start))
    rows = [
        row for row in read_scored_rows(Path(args.dataset)) if row.as_of_date >= validation_start
    ]
    if not rows:
        raise SystemExit("no validation rows available")
    by_date: dict[date, list[ScoredRow]] = defaultdict(list)
    for row in rows:
        by_date[row.as_of_date].append(row)
    date_metrics = [
        evaluate_date(day, day_rows, args.top_n) for day, day_rows in sorted(by_date.items())
    ]
    selected_returns = [metric["selected_forward_return_20d"] for metric in date_metrics]
    universe_returns = [metric["universe_forward_return_20d"] for metric in date_metrics]
    selected_excess = [metric["selected_excess_return_20d"] for metric in date_metrics]
    drawdowns = [metric["selected_forward_max_drawdown_20d"] for metric in date_metrics]
    macro_regime_metrics = build_macro_regime_metrics(date_metrics)
    macro_dates = [
        metric
        for metric in date_metrics
        if isinstance(metric.get("bls_macro_points_available"), int)
        and int(metric["bls_macro_points_available"]) > 0
    ]
    summary = {
        "status": "ok",
        "validation_start": validation_start.isoformat(),
        "validation_dates": len(date_metrics),
        "validation_rows": len(rows),
        "top_n": args.top_n,
        "selected_avg_forward_return_20d": mean(selected_returns),
        "universe_avg_forward_return_20d": mean(universe_returns),
        "selected_minus_universe_forward_return_20d": mean(selected_returns)
        - mean(universe_returns),
        "selected_avg_forward_excess_return_20d": mean(selected_excess),
        "selected_hit_rate_20d": mean([1.0 if value > 0 else 0.0 for value in selected_returns]),
        "selected_avg_forward_max_drawdown_20d": mean(drawdowns),
        "bls_macro_dates_with_points": len(macro_dates),
        "bls_macro_coverage_ratio": len(macro_dates) / len(date_metrics),
        "macro_regime_groups": len(macro_regime_metrics),
        "order_created": False,
        "live_trading_authorized": False,
    }
    return {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": (
            "scorecard baseline evaluation only; no orders; no broker; no credentials; no advice"
        ),
        "summary": summary,
        "feature_weights": FEATURE_WEIGHTS,
        "macro_regime_metrics": macro_regime_metrics,
        "date_metrics_sample": date_metrics[:5],
        "date_metrics_tail": date_metrics[-5:],
        "live_trading_authorized": False,
        "paper_api_authorized": False,
    }


def read_scored_rows(path: Path) -> list[ScoredRow]:
    if not path.exists():
        raise SystemExit(f"dataset does not exist: {path}")
    rows: list[ScoredRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            rows.append(
                ScoredRow(
                    as_of_date=date.fromisoformat(str(raw["as_of_date"])),
                    symbol=str(raw["symbol"]),
                    score=score_row(raw),
                    forward_return_20d=float(raw["forward_return_20d"]),
                    forward_excess_return_20d=float(raw["forward_excess_return_20d"]),
                    forward_max_drawdown_20d=float(raw["forward_max_drawdown_20d"]),
                    bls_macro_points_available=parse_optional_int(
                        raw.get("bls_macro_points_available")
                    ),
                )
            )
    return rows


def score_row(row: Mapping[str, str]) -> float:
    return sum(float(row[column]) * weight for column, weight in FEATURE_WEIGHTS.items())


def evaluate_date(day: date, rows: Sequence[ScoredRow], top_n: int) -> dict[str, Any]:
    ranked = sorted(rows, key=lambda row: row.score, reverse=True)
    selected = ranked[: min(top_n, len(ranked))]
    macro_points = [
        row.bls_macro_points_available
        for row in rows
        if row.bls_macro_points_available is not None
    ]
    return {
        "as_of_date": day.isoformat(),
        "symbols_available": len(rows),
        "selected_symbols": [row.symbol for row in selected],
        "selected_forward_return_20d": mean([row.forward_return_20d for row in selected]),
        "universe_forward_return_20d": mean([row.forward_return_20d for row in rows]),
        "selected_excess_return_20d": mean([row.forward_excess_return_20d for row in selected]),
        "selected_forward_max_drawdown_20d": mean(
            [row.forward_max_drawdown_20d for row in selected]
        ),
        "bls_macro_points_available": max(macro_points) if macro_points else None,
        "top_score": selected[0].score if selected else 0.0,
    }


def build_macro_regime_metrics(date_metrics: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for metric in date_metrics:
        raw_points = metric.get("bls_macro_points_available")
        group_key = "missing" if raw_points is None else str(int(raw_points))
        grouped[group_key].append(metric)

    regimes: list[dict[str, Any]] = []
    for group_key, metrics in sorted(grouped.items(), key=macro_group_sort_key):
        selected_returns = [float(metric["selected_forward_return_20d"]) for metric in metrics]
        universe_returns = [float(metric["universe_forward_return_20d"]) for metric in metrics]
        selected_excess = [float(metric["selected_excess_return_20d"]) for metric in metrics]
        regimes.append(
            {
                "bls_macro_points_available": group_key,
                "validation_dates": len(metrics),
                "selected_avg_forward_return_20d": mean(selected_returns),
                "universe_avg_forward_return_20d": mean(universe_returns),
                "selected_minus_universe_forward_return_20d": mean(selected_returns)
                - mean(universe_returns),
                "selected_avg_forward_excess_return_20d": mean(selected_excess),
                "selected_hit_rate_20d": mean(
                    [1.0 if value > 0 else 0.0 for value in selected_returns]
                ),
            }
        )
    return regimes


def macro_group_sort_key(item: tuple[str, list[Mapping[str, Any]]]) -> tuple[int, str]:
    key = item[0]
    if key == "missing":
        return (1_000_000, key)
    return (int(key), key)


def parse_optional_int(value: str | None) -> int | None:
    if value in (None, "", "None"):
        return None
    return int(float(value))


def mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    lines = [
        "# Scorecard baseline report",
        "",
        "Safety: offline evaluation only; no orders, no broker, no credentials, no advice.",
        "",
        "## Summary",
        "",
        f"- Validation dates: `{summary['validation_dates']}`",
        f"- Validation rows: `{summary['validation_rows']}`",
        f"- Top N: `{summary['top_n']}`",
        f"- Selected avg 20d return: `{percent(summary['selected_avg_forward_return_20d'])}`",
        f"- Universe avg 20d return: `{percent(summary['universe_avg_forward_return_20d'])}`",
        (
            "- Selected minus universe 20d return: "
            f"`{percent(summary['selected_minus_universe_forward_return_20d'])}`"
        ),
        (
            "- Selected avg 20d excess return: "
            f"`{percent(summary['selected_avg_forward_excess_return_20d'])}`"
        ),
        f"- Selected hit rate: `{percent(summary['selected_hit_rate_20d'])}`",
        (
            "- Selected avg 20d max drawdown: "
            f"`{percent(summary['selected_avg_forward_max_drawdown_20d'])}`"
        ),
        f"- BLS macro dates with points: `{summary['bls_macro_dates_with_points']}`",
        f"- BLS macro coverage ratio: `{percent(summary['bls_macro_coverage_ratio'])}`",
        f"- Macro regime groups: `{summary['macro_regime_groups']}`",
        f"- Order created: `{summary['order_created']}`",
        f"- Live trading authorized: `{summary['live_trading_authorized']}`",
    ]
    macro_regimes = report.get("macro_regime_metrics", [])
    if macro_regimes:
        lines.extend(["", "## BLS macro availability regimes", ""])
        for regime in macro_regimes:
            lines.append(
                
                    "- points="
                    f"`{regime['bls_macro_points_available']}` dates="
                    f"`{regime['validation_dates']}` selected-minus-universe="
                    f"`{percent(regime['selected_minus_universe_forward_return_20d'])}` "
                    f"hit-rate=`{percent(regime['selected_hit_rate_20d'])}`"
                
            )
    path.write_text("\n".join(lines), encoding="utf-8")


def percent(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{value * 100:.2f}%"
    return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
