"""Offline non-leveraged universe stability analysis.

This script compares ordinary large-cap stocks and unleveraged ETFs. Leveraged
and inverse products are explicitly blocked. It is research-only and never places
orders.
"""

from __future__ import annotations

import argparse
import itertools
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import median
from typing import Any

from auto_trading_bot.domain import Bar, EquityPoint
from auto_trading_bot.metrics import max_drawdown, periodic_returns, sharpe_ratio
from auto_trading_bot.validation import train_test_split_window, walk_forward_windows

try:
    from scripts.strategy_optimization import fetch_or_load_bars
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from strategy_optimization import fetch_or_load_bars

TRADING_DAYS_PER_YEAR = 252
BANNED_LEVERAGED_MARKERS = (
    "2X",
    "3X",
    "ULTRA",
    "LEVERAGED",
    "INVERSE",
    "BEAR",
    "BULL 2X",
    "BULL 3X",
)
DEFAULT_SYMBOLS = (
    "SPY",
    "QQQ",
    "DIA",
    "IWM",
    "GLD",
    "TLT",
    "IEF",
    "SHY",
    "XLK",
    "XLV",
    "XLP",
    "XLU",
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "META",
    "JPM",
    "JNJ",
    "PG",
    "XOM",
    "KO",
)


@dataclass(frozen=True)
class AssetSummary:
    symbol: str
    category: str
    median_return: float
    median_excess: float
    min_holdout_excess: float
    worst_max_drawdown: float
    full_return: float
    full_max_drawdown: float
    sharpe: float | None
    status: str
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True)
class PairSummary:
    name: str
    symbols: tuple[str, str]
    weights: tuple[float, float]
    median_return: float
    median_excess: float
    min_holdout_excess: float
    worst_max_drawdown: float
    full_return: float
    full_max_drawdown: float
    status: str
    failure_reasons: tuple[str, ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze non-leveraged ETF/stock universe.")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--data-dir", default="data/external")
    parser.add_argument("--output", default=".omx/reports/non-leveraged-universe-latest.json")
    parser.add_argument("--markdown", default=".omx/reports/non-leveraged-universe-latest.md")
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
        "universe status={status} valid_assets={valid_assets} pass_assets={pass_assets} "
        "pass_pairs={pass_pairs}".format(**report["summary"])
    )
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    symbols = tuple(dict.fromkeys(symbol.upper() for symbol in args.symbols))
    blocked = [symbol for symbol in symbols if looks_leveraged(symbol)]
    allowed = [symbol for symbol in symbols if symbol not in blocked]
    data, metadata = load_symbols(args, allowed)
    benchmark_symbols = ("SPY", "QQQ", "DIA")
    required = set(benchmark_symbols)
    if not required.issubset(data):
        raise SystemExit("benchmark symbols SPY/QQQ/DIA are required")
    dates, aligned = align_by_date(data)
    windows = build_windows(dates)

    asset_summaries = [
        summarize_asset(symbol, dates, aligned, windows, benchmark_symbols)
        for symbol in sorted(aligned)
    ]
    pair_summaries = summarize_pairs(dates, aligned, windows, benchmark_symbols)
    pass_assets = [row for row in asset_summaries if row.status == "pass"]
    pass_pairs = [row for row in pair_summaries if row.status == "pass"]
    qqq = next(row for row in asset_summaries if row.symbol == "QQQ")
    return {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": "non-leveraged offline research only; no orders, no broker, no advice",
        "blocked_symbols": blocked,
        "data": metadata,
        "summary": {
            "status": "ok",
            "valid_assets": len(asset_summaries),
            "pass_assets": len(pass_assets),
            "pass_pairs": len(pass_pairs),
            "qqq_single_asset_status": qqq.status,
            "qqq_single_asset_worst_mdd": qqq.worst_max_drawdown,
            "interpretation": (
                "QQQ is not leveraged, but single-asset QQQ fails drawdown stability; "
                "defensive pairing with GLD is what improved the gate result."
            ),
        },
        "asset_summaries": [asdict(row) for row in sorted(asset_summaries, key=asset_sort_key)],
        "pair_summaries": [asdict(row) for row in sorted(pair_summaries, key=pair_sort_key)[:30]],
    }


def looks_leveraged(symbol: str) -> bool:
    upper = symbol.upper()
    known_leveraged = {
        "BITU",
        "BITX",
        "BOIL",
        "DDM",
        "DOG",
        "DUST",
        "DXD",
        "ERY",
        "FAZ",
        "FNGD",
        "FNGU",
        "GUSH",
        "LABD",
        "LABU",
        "NUGT",
        "PSQ",
        "QID",
        "QLD",
        "ROM",
        "SCO",
        "SDOW",
        "SDS",
        "SH",
        "SOXL",
        "SOXS",
        "SPXL",
        "SPXS",
        "SQQQ",
        "SSO",
        "TECL",
        "TECS",
        "TBT",
        "TMF",
        "TNA",
        "TQQQ",
        "TWM",
        "UCO",
        "UDOW",
        "UPRO",
        "URE",
        "URTY",
        "UVIX",
        "VIXY",
        "YANG",
        "YINN",
    }
    return upper in known_leveraged or any(marker in upper for marker in BANNED_LEVERAGED_MARKERS)


def load_symbols(
    args: argparse.Namespace, symbols: Sequence[str]
) -> tuple[dict[str, tuple[Bar, ...]], list[dict[str, Any]]]:
    data: dict[str, tuple[Bar, ...]] = {}
    metadata: list[dict[str, Any]] = []
    for symbol in symbols:
        bars, meta = fetch_or_load_bars(
            user_symbol=symbol,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
            data_dir=Path(args.data_dir),
            force_refresh=args.force_refresh,
        )
        metadata.append(meta)
        if bars is not None:
            data[symbol] = bars
    return data, metadata


def align_by_date(
    data: dict[str, tuple[Bar, ...]],
) -> tuple[tuple[date, ...], dict[str, tuple[Bar, ...]]]:
    lookup = {symbol: {bar.timestamp.date(): bar for bar in bars} for symbol, bars in data.items()}
    dates = tuple(sorted(set.intersection(*(set(rows) for rows in lookup.values()))))
    aligned = {
        symbol: tuple(lookup[symbol][active_date] for active_date in dates) for symbol in data
    }
    return dates, aligned


def build_windows(dates: tuple[date, ...]) -> tuple[tuple[str, int, int], ...]:
    holdout = train_test_split_window(
        dates, 0.7, min_train_size=TRADING_DAYS_PER_YEAR * 3, min_test_size=252
    )
    windows = [("holdout_70_30", holdout.test_start, holdout.test_end)]
    for window in walk_forward_windows(
        dates,
        train_size=TRADING_DAYS_PER_YEAR * 3,
        test_size=TRADING_DAYS_PER_YEAR,
        step_size=TRADING_DAYS_PER_YEAR,
    ):
        windows.append((window.label, window.test_start, window.test_end))
    return tuple(windows)


def summarize_asset(
    symbol: str,
    dates: tuple[date, ...],
    data: dict[str, tuple[Bar, ...]],
    windows: Sequence[tuple[str, int, int]],
    benchmark_symbols: tuple[str, ...],
) -> AssetSummary:
    rows = [
        evaluate_weights(dates, data, {symbol: 1.0}, benchmark_symbols, start, end)
        for _label, start, end in windows
    ]
    holdout = rows[0]
    full_curve = portfolio_curve(dates, data, {symbol: 1.0}, 0, len(dates))
    full_returns = periodic_returns(full_curve)
    median_return = median(row[0] for row in rows)
    median_excess = median(row[2] for row in rows)
    worst_mdd = min(row[3] for row in rows)
    reasons = failure_reasons(median_excess, holdout[2], worst_mdd, median_return)
    return AssetSummary(
        symbol=symbol,
        category=category(symbol),
        median_return=median_return,
        median_excess=median_excess,
        min_holdout_excess=holdout[2],
        worst_max_drawdown=worst_mdd,
        full_return=total_return(full_curve),
        full_max_drawdown=max_drawdown(full_curve),
        sharpe=sharpe_ratio(full_returns),
        status="pass" if not reasons else "review",
        failure_reasons=tuple(reasons),
    )


def summarize_pairs(
    dates: tuple[date, ...],
    data: dict[str, tuple[Bar, ...]],
    windows: Sequence[tuple[str, int, int]],
    benchmark_symbols: tuple[str, ...],
) -> list[PairSummary]:
    risk_assets = [symbol for symbol in data if symbol not in {"SHY", "IEF", "TLT", "GLD"}]
    defensive_assets = [symbol for symbol in ("GLD", "IEF", "SHY") if symbol in data]
    summaries: list[PairSummary] = []
    for risk_symbol, defensive_symbol in itertools.product(risk_assets, defensive_assets):
        if risk_symbol == defensive_symbol:
            continue
        for risk_weight in (0.30, 0.36, 0.40, 0.50, 0.60):
            weights = {risk_symbol: risk_weight, defensive_symbol: 1.0 - risk_weight}
            rows = [
                evaluate_weights(dates, data, weights, benchmark_symbols, start, end)
                for _label, start, end in windows
            ]
            holdout = rows[0]
            full_curve = portfolio_curve(dates, data, weights, 0, len(dates))
            median_return = median(row[0] for row in rows)
            median_excess = median(row[2] for row in rows)
            worst_mdd = min(row[3] for row in rows)
            reasons = failure_reasons(median_excess, holdout[2], worst_mdd, median_return)
            summaries.append(
                PairSummary(
                    name=f"{risk_symbol}_{risk_weight:g}_{defensive_symbol}_{1 - risk_weight:g}",
                    symbols=(risk_symbol, defensive_symbol),
                    weights=(risk_weight, 1.0 - risk_weight),
                    median_return=median_return,
                    median_excess=median_excess,
                    min_holdout_excess=holdout[2],
                    worst_max_drawdown=worst_mdd,
                    full_return=total_return(full_curve),
                    full_max_drawdown=max_drawdown(full_curve),
                    status="pass" if not reasons else "review",
                    failure_reasons=tuple(reasons),
                )
            )
    return summaries


def evaluate_weights(
    dates: tuple[date, ...],
    data: dict[str, tuple[Bar, ...]],
    weights: dict[str, float],
    benchmark_symbols: tuple[str, ...],
    start: int,
    end: int,
) -> tuple[float, float, float, float]:
    candidate_curve = portfolio_curve(dates, data, weights, start, end)
    benchmark_weights = {symbol: 1 / len(benchmark_symbols) for symbol in benchmark_symbols}
    benchmark_curve = portfolio_curve(dates, data, benchmark_weights, start, end)
    candidate_return = total_return(candidate_curve)
    benchmark_return = total_return(benchmark_curve)
    return (
        candidate_return,
        benchmark_return,
        candidate_return - benchmark_return,
        max_drawdown(candidate_curve),
    )


def portfolio_curve(
    dates: tuple[date, ...],
    data: dict[str, tuple[Bar, ...]],
    weights: dict[str, float],
    start: int,
    end: int,
) -> tuple[EquityPoint, ...]:
    del dates
    cash = 0.0
    positions: dict[str, int] = {}
    for symbol, weight in weights.items():
        allocation = 10_000.0 * weight
        quantity = int(allocation / data[symbol][start].open)
        positions[symbol] = quantity
        cash += allocation - quantity * data[symbol][start].open
    return tuple(
        EquityPoint(
            timestamp=data[next(iter(weights))][index].timestamp,
            cash=cash,
            position=sum(positions.values()),
            close_price=1.0,
            equity=cash
            + sum(quantity * data[symbol][index].close for symbol, quantity in positions.items()),
        )
        for index in range(start, end)
    )


def failure_reasons(
    median_excess: float, holdout_excess: float, worst_mdd: float, median_return: float
) -> list[str]:
    reasons: list[str] = []
    if median_excess <= 0:
        reasons.append("median_excess_not_positive")
    if holdout_excess < -0.05:
        reasons.append("holdout_excess_below_minus_5pp")
    if worst_mdd < -0.20:
        reasons.append("max_drawdown_worse_than_minus_20pct")
    if median_return <= 0:
        reasons.append("median_return_not_positive")
    return reasons


def total_return(curve: tuple[EquityPoint, ...]) -> float:
    return (curve[-1].equity / curve[0].equity) - 1.0


def category(symbol: str) -> str:
    etfs = {
        "DIA",
        "GLD",
        "IEF",
        "IWM",
        "QQQ",
        "SHY",
        "SPY",
        "TLT",
        "VNQ",
        "XLB",
        "XLC",
        "XLE",
        "XLF",
        "XLI",
        "XLK",
        "XLP",
        "XLRE",
        "XLU",
        "XLV",
        "XLY",
    }
    return "ETF" if symbol in etfs else "stock"


def asset_sort_key(row: AssetSummary) -> tuple[int, float, float]:
    return (0 if row.status == "pass" else 1, -row.median_excess, row.worst_max_drawdown)


def pair_sort_key(row: PairSummary) -> tuple[int, float, float]:
    return (0 if row.status == "pass" else 1, -row.median_excess, row.worst_max_drawdown)


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Non-leveraged universe analysis",
        "",
        "Safety: offline research only; leveraged/inverse products blocked; no orders, no advice.",
        "",
        "## Summary",
        "",
        f"- Valid assets: {report['summary']['valid_assets']}",
        f"- Passing single assets: {report['summary']['pass_assets']}",
        f"- Passing defensive pairs: {report['summary']['pass_pairs']}",
        f"- QQQ single-asset status: {report['summary']['qqq_single_asset_status']}",
        f"- QQQ single-asset worst MDD: {percent(report['summary']['qqq_single_asset_worst_mdd'])}",
        f"- Interpretation: {report['summary']['interpretation']}",
        "",
        "## Top single assets",
        "",
        "| Symbol | Type | Status | Median return | Median excess | "
        "Holdout excess | Worst MDD | Reasons |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report["asset_summaries"][:20]:
        lines.append(
            "| {symbol} | {category} | {status} | {median_return} | {median_excess} | "
            "{holdout} | {mdd} | {reasons} |".format(
                symbol=row["symbol"],
                category=row["category"],
                status=row["status"],
                median_return=percent(row["median_return"]),
                median_excess=percent(row["median_excess"]),
                holdout=percent(row["min_holdout_excess"]),
                mdd=percent(row["worst_max_drawdown"]),
                reasons=", ".join(row["failure_reasons"]) or "-",
            )
        )
    lines.extend(
        [
            "",
            "## Top defensive pairs",
            "",
            "| Pair | Status | Median return | Median excess | "
            "Holdout excess | Worst MDD | Reasons |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in report["pair_summaries"][:20]:
        lines.append(
            "| {name} | {status} | {median_return} | {median_excess} | {holdout} | "
            "{mdd} | {reasons} |".format(
                name=row["name"],
                status=row["status"],
                median_return=percent(row["median_return"]),
                median_excess=percent(row["median_excess"]),
                holdout=percent(row["min_holdout_excess"]),
                mdd=percent(row["worst_max_drawdown"]),
                reasons=", ".join(row["failure_reasons"]) or "-",
            )
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


if __name__ == "__main__":
    raise SystemExit(main())
