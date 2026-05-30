"""Deep offline analysis for the current best defensive portfolio candidate.

This script keeps the project in research mode: it uses cached/downloaded public
historical bars, compares a candidate against simple benchmarks, and writes
machine-readable and human-readable evidence. It does not connect to brokers or
place trades.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

try:
    from scripts.strategy_optimization import DATA_SOURCE_HELP_URL, fetch_or_load_bars
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from strategy_optimization import DATA_SOURCE_HELP_URL, fetch_or_load_bars

from auto_trading_bot.domain import Bar, EquityPoint
from auto_trading_bot.metrics import max_drawdown, periodic_returns, sharpe_ratio, sortino_ratio

TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class PeriodMetrics:
    label: str
    start: str
    end: str
    candidate_return: float
    benchmark_return: float
    excess_return: float
    candidate_max_drawdown: float
    benchmark_max_drawdown: float
    candidate_sharpe: float | None
    benchmark_sharpe: float | None
    candidate_sortino: float | None
    benchmark_sortino: float | None


@dataclass(frozen=True)
class RollingMetrics:
    label: str
    windows: int
    win_rate: float
    median_excess: float
    worst_excess: float
    best_excess: float
    median_candidate_return: float
    median_benchmark_return: float
    worst_candidate_drawdown: float


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deep-analyze the QQQ/GLD research candidate.")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--data-dir", default="data/external")
    parser.add_argument("--output", default=".omx/reports/strategy-deep-analysis-latest.json")
    parser.add_argument("--markdown", default=".omx/reports/strategy-deep-analysis-latest.md")
    parser.add_argument("--candidate-qqq-weight", type=float, default=0.36)
    parser.add_argument("--candidate-gld-weight", type=float, default=0.64)
    parser.add_argument("--force-refresh", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    output = Path(args.output)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(markdown, report)
    print(
        "deep_analysis status={status} full_excess={full_excess:.2%} "
        "stress_pass={stress_pass}".format(
            status=report["status"],
            full_excess=report["full_period"]["excess_return"],
            stress_pass=report["stress_summary"]["all_stress_excess_positive"],
        )
    )
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0 if report["status"] == "pass" else 1


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    symbols = ("SPY", "QQQ", "DIA", "GLD")
    data_dir = Path(args.data_dir)
    data_metadata: list[dict[str, Any]] = []
    data: dict[str, tuple[Bar, ...]] = {}
    for symbol in symbols:
        bars, metadata = fetch_or_load_bars(
            user_symbol=symbol,
            start=start,
            end=end,
            data_dir=data_dir,
            force_refresh=args.force_refresh,
        )
        data_metadata.append(metadata)
        if bars is not None:
            data[symbol] = bars
    if set(data) != set(symbols):
        return {
            "status": "blocked",
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "data": data_metadata,
            "reason": "required symbols were not all available",
        }

    dates, aligned = align_by_date(data)
    candidate_weights = {"QQQ": args.candidate_qqq_weight, "GLD": args.candidate_gld_weight}
    benchmark_weights = {"SPY": 1 / 3, "QQQ": 1 / 3, "DIA": 1 / 3}

    full_period = evaluate_period(
        "full_period", dates, aligned, candidate_weights, benchmark_weights, 0, len(dates)
    )
    yearly = yearly_metrics(dates, aligned, candidate_weights, benchmark_weights)
    monthly = monthly_metrics(dates, aligned, candidate_weights, benchmark_weights)
    stress_periods = stress_metrics(dates, aligned, candidate_weights, benchmark_weights)
    rolling = rolling_metrics(dates, aligned, candidate_weights, benchmark_weights)

    annual_win_rate = sum(1 for row in yearly if row.excess_return > 0) / len(yearly)
    monthly_win_rate = sum(1 for row in monthly if row.excess_return > 0) / len(monthly)
    worst_stress_excess = min(row.excess_return for row in stress_periods)
    status = "pass" if full_period.excess_return > 0 and worst_stress_excess > 0 else "review"

    return {
        "status": status,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "candidate": {
            "name": "static_portfolio_qqq_0.36_gld_0.64",
            "weights": candidate_weights,
            "interpretation": "defensive static QQQ/GLD allocation; research only",
        },
        "benchmark": {
            "name": "equal_weight_spy_qqq_dia",
            "weights": benchmark_weights,
        },
        "data": data_metadata,
        "full_period": asdict(full_period),
        "yearly": [asdict(row) for row in yearly],
        "monthly_summary": {
            "months": len(monthly),
            "candidate_win_rate_vs_benchmark": monthly_win_rate,
            "best_month_excess": max(row.excess_return for row in monthly),
            "worst_month_excess": min(row.excess_return for row in monthly),
        },
        "stress_periods": [asdict(row) for row in stress_periods],
        "stress_summary": {
            "all_stress_excess_positive": all(row.excess_return > 0 for row in stress_periods),
            "worst_stress_excess": worst_stress_excess,
        },
        "rolling": [asdict(row) for row in rolling],
        "stability_summary": {
            "annual_win_rate_vs_benchmark": annual_win_rate,
            "monthly_win_rate_vs_benchmark": monthly_win_rate,
            "minimum_next_gate": (
                "paper trade only after independent data-source validation and daily signal dry-run"
            ),
        },
        "sources": {
            "yahoo_finance_help": DATA_SOURCE_HELP_URL,
            "note": "Yahoo chart endpoint URLs are captured in data metadata when refreshed.",
        },
    }


def align_by_date(
    data: dict[str, tuple[Bar, ...]],
) -> tuple[tuple[date, ...], dict[str, tuple[Bar, ...]]]:
    lookup = {symbol: {bar.timestamp.date(): bar for bar in bars} for symbol, bars in data.items()}
    dates = tuple(sorted(set.intersection(*(set(rows) for rows in lookup.values()))))
    aligned = {
        symbol: tuple(lookup[symbol][active_date] for active_date in dates) for symbol in data
    }
    return dates, aligned


def yearly_metrics(
    dates: tuple[date, ...],
    data: dict[str, tuple[Bar, ...]],
    candidate_weights: dict[str, float],
    benchmark_weights: dict[str, float],
) -> list[PeriodMetrics]:
    rows: list[PeriodMetrics] = []
    years = sorted({active_date.year for active_date in dates})
    for year in years:
        indices = [index for index, active_date in enumerate(dates) if active_date.year == year]
        if len(indices) < 2:
            continue
        rows.append(
            evaluate_period(
                str(year),
                dates,
                data,
                candidate_weights,
                benchmark_weights,
                indices[0],
                indices[-1] + 1,
            )
        )
    return rows


def monthly_metrics(
    dates: tuple[date, ...],
    data: dict[str, tuple[Bar, ...]],
    candidate_weights: dict[str, float],
    benchmark_weights: dict[str, float],
) -> list[PeriodMetrics]:
    rows: list[PeriodMetrics] = []
    months = sorted({(active_date.year, active_date.month) for active_date in dates})
    for year, month in months:
        indices = [
            index
            for index, active_date in enumerate(dates)
            if active_date.year == year and active_date.month == month
        ]
        if len(indices) < 2:
            continue
        rows.append(
            evaluate_period(
                f"{year}-{month:02d}",
                dates,
                data,
                candidate_weights,
                benchmark_weights,
                indices[0],
                indices[-1] + 1,
            )
        )
    return rows


def stress_metrics(
    dates: tuple[date, ...],
    data: dict[str, tuple[Bar, ...]],
    candidate_weights: dict[str, float],
    benchmark_weights: dict[str, float],
) -> list[PeriodMetrics]:
    periods = {
        "covid_crash_2020": (date(2020, 2, 19), date(2020, 3, 23)),
        "inflation_bear_2022": (date(2022, 1, 3), date(2022, 10, 14)),
        "rate_rebound_2023": (date(2023, 1, 3), date(2023, 12, 29)),
        "recent_holdout_2024_2026": (date(2024, 1, 2), dates[-1]),
    }
    rows: list[PeriodMetrics] = []
    for label, (start, end) in periods.items():
        selected = [index for index, active_date in enumerate(dates) if start <= active_date <= end]
        if len(selected) < 2:
            continue
        rows.append(
            evaluate_period(
                label,
                dates,
                data,
                candidate_weights,
                benchmark_weights,
                selected[0],
                selected[-1] + 1,
            )
        )
    return rows


def rolling_metrics(
    dates: tuple[date, ...],
    data: dict[str, tuple[Bar, ...]],
    candidate_weights: dict[str, float],
    benchmark_weights: dict[str, float],
) -> list[RollingMetrics]:
    rows: list[RollingMetrics] = []
    for label, size in (("rolling_63d", 63), ("rolling_126d", 126), ("rolling_252d", 252)):
        periods: list[PeriodMetrics] = []
        for start in range(0, len(dates) - size + 1, 21):
            periods.append(
                evaluate_period(
                    f"{label}_{start}",
                    dates,
                    data,
                    candidate_weights,
                    benchmark_weights,
                    start,
                    start + size,
                )
            )
        rows.append(summarize_rolling(label, periods))
    return rows


def summarize_rolling(label: str, periods: Sequence[PeriodMetrics]) -> RollingMetrics:
    excesses = [row.excess_return for row in periods]
    candidate_returns = [row.candidate_return for row in periods]
    benchmark_returns = [row.benchmark_return for row in periods]
    return RollingMetrics(
        label=label,
        windows=len(periods),
        win_rate=sum(1 for value in excesses if value > 0) / len(excesses),
        median_excess=median(excesses),
        worst_excess=min(excesses),
        best_excess=max(excesses),
        median_candidate_return=median(candidate_returns),
        median_benchmark_return=median(benchmark_returns),
        worst_candidate_drawdown=min(row.candidate_max_drawdown for row in periods),
    )


def median(values: Sequence[float]) -> float:
    sorted_values = sorted(values)
    midpoint = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return sorted_values[midpoint]
    return (sorted_values[midpoint - 1] + sorted_values[midpoint]) / 2


def evaluate_period(
    label: str,
    dates: tuple[date, ...],
    data: dict[str, tuple[Bar, ...]],
    candidate_weights: dict[str, float],
    benchmark_weights: dict[str, float],
    start: int,
    end: int,
) -> PeriodMetrics:
    candidate_curve = portfolio_curve(dates, data, candidate_weights, start, end)
    benchmark_curve = portfolio_curve(dates, data, benchmark_weights, start, end)
    candidate_return = total_return(candidate_curve)
    benchmark_return = total_return(benchmark_curve)
    candidate_returns = periodic_returns(candidate_curve)
    benchmark_returns = periodic_returns(benchmark_curve)
    return PeriodMetrics(
        label=label,
        start=dates[start].isoformat(),
        end=dates[end - 1].isoformat(),
        candidate_return=candidate_return,
        benchmark_return=benchmark_return,
        excess_return=candidate_return - benchmark_return,
        candidate_max_drawdown=max_drawdown(candidate_curve),
        benchmark_max_drawdown=max_drawdown(benchmark_curve),
        candidate_sharpe=sharpe_ratio(candidate_returns),
        benchmark_sharpe=sharpe_ratio(benchmark_returns),
        candidate_sortino=sortino_ratio(candidate_returns),
        benchmark_sortino=sortino_ratio(benchmark_returns),
    )


def portfolio_curve(
    dates: tuple[date, ...],
    data: dict[str, tuple[Bar, ...]],
    weights: dict[str, float],
    start: int,
    end: int,
    initial_cash: float = 10_000.0,
) -> tuple[EquityPoint, ...]:
    cash = 0.0
    positions: dict[str, int] = {}
    for symbol, weight in weights.items():
        allocation = initial_cash * weight
        shares = int(allocation / data[symbol][start].open)
        cash += allocation - shares * data[symbol][start].open
        positions[symbol] = shares
    return tuple(
        EquityPoint(
            timestamp=datetime.combine(dates[index], time()),
            cash=cash,
            position=sum(positions.values()),
            close_price=1.0,
            equity=cash
            + sum(quantity * data[symbol][index].close for symbol, quantity in positions.items()),
        )
        for index in range(start, end)
    )


def total_return(curve: tuple[EquityPoint, ...]) -> float:
    return (curve[-1].equity / curve[0].equity) - 1.0


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    full = report["full_period"]
    lines = [
        "# Strategy deep analysis report",
        "",
        f"Status: **{report['status'].upper()}**",
        "",
        "Safety: offline research only; no live trading, no broker integration, "
        "no investment advice.",
        "",
        "## Candidate",
        "",
        f"- Candidate: `{report['candidate']['name']}`",
        f"- Weights: {report['candidate']['weights']}",
        f"- Benchmark: `{report['benchmark']['name']}` {report['benchmark']['weights']}",
        "",
        "## Full period",
        "",
        "| Candidate return | Benchmark return | Excess | Candidate MDD | Benchmark MDD |",
        "| ---: | ---: | ---: | ---: | ---: |",
        (
            "| {candidate_return} | {benchmark_return} | {excess} | "
            "{candidate_mdd} | {benchmark_mdd} |"
        ).format(
            candidate_return=percent(full["candidate_return"]),
            benchmark_return=percent(full["benchmark_return"]),
            excess=percent(full["excess_return"]),
            candidate_mdd=percent(full["candidate_max_drawdown"]),
            benchmark_mdd=percent(full["benchmark_max_drawdown"]),
        ),
        "",
        "## Stress periods",
        "",
        "| Period | Candidate | Benchmark | Excess | Candidate MDD | Benchmark MDD |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["stress_periods"]:
        lines.append(
            (
                "| {label} | {candidate} | {benchmark} | {excess} | "
                "{candidate_mdd} | {benchmark_mdd} |"
            ).format(
                label=row["label"],
                candidate=percent(row["candidate_return"]),
                benchmark=percent(row["benchmark_return"]),
                excess=percent(row["excess_return"]),
                candidate_mdd=percent(row["candidate_max_drawdown"]),
                benchmark_mdd=percent(row["benchmark_max_drawdown"]),
            )
        )
    lines.extend(
        [
            "",
            "## Yearly results",
            "",
            "| Year | Candidate | Benchmark | Excess | Candidate MDD | Benchmark MDD |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["yearly"]:
        lines.append(
            (
                "| {label} | {candidate} | {benchmark} | {excess} | "
                "{candidate_mdd} | {benchmark_mdd} |"
            ).format(
                label=row["label"],
                candidate=percent(row["candidate_return"]),
                benchmark=percent(row["benchmark_return"]),
                excess=percent(row["excess_return"]),
                candidate_mdd=percent(row["candidate_max_drawdown"]),
                benchmark_mdd=percent(row["benchmark_max_drawdown"]),
            )
        )
    lines.extend(
        [
            "",
            "## Rolling summary",
            "",
            "| Window | Count | Win rate | Median excess | Worst excess | "
            "Best excess | Worst candidate MDD |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["rolling"]:
        lines.append(
            (
                "| {label} | {count} | {win_rate} | {median_excess} | "
                "{worst_excess} | {best_excess} | {worst_mdd} |"
            ).format(
                label=row["label"],
                count=row["windows"],
                win_rate=percent(row["win_rate"]),
                median_excess=percent(row["median_excess"]),
                worst_excess=percent(row["worst_excess"]),
                best_excess=percent(row["best_excess"]),
                worst_mdd=percent(row["worst_candidate_drawdown"]),
            )
        )
    lines.extend(
        [
            "",
            "## Next gate",
            "",
            "- This candidate is promoted only to paper-trading research, not live capital.",
            "- Next required checks: independent data source, daily dry-run, and drift monitoring.",
            "",
            "## Sources",
            "",
            f"- Yahoo Finance historical-data help: {DATA_SOURCE_HELP_URL}",
            "- Yahoo chart endpoint URLs are recorded in data metadata when refreshed.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


if __name__ == "__main__":
    raise SystemExit(main())
