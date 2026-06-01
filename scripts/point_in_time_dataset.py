"""Build point-in-time daily feature/label datasets for no-order modeling.

The dataset is local research infrastructure only. It reads cached public OHLCV
CSVs, creates features available at each decision date, and writes forward
labels for later evaluation. It never connects to a broker, reads credentials,
or creates orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from scripts.market_universe_candidate_scan import read_symbols_file
    from scripts.non_leveraged_universe_analysis import looks_leveraged
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from market_universe_candidate_scan import read_symbols_file  # type: ignore[no-redef]
    from non_leveraged_universe_analysis import looks_leveraged  # type: ignore[no-redef]

DEFAULT_SYMBOLS_FILE = "data/universe/us_large_liquid_watchlist.txt"
DEFAULT_OUTPUT = ".omx/datasets/point-in-time-daily.csv"
DEFAULT_SUMMARY = ".omx/reports/point-in-time-dataset-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/point-in-time-dataset-latest.md"
DEFAULT_BLS_MACRO = ".omx/reports/bls-macro-snapshot-latest.json"
MACRO_FEATURE_COLUMNS = (
    "bls_cpi_all_urban_consumers",
    "bls_unemployment_rate",
    "bls_nonfarm_payrolls_all_employees",
    "bls_macro_points_available",
)
FEATURE_COLUMNS = (
    "trailing_return_1d",
    "trailing_return_5d",
    "trailing_return_20d",
    "trailing_volatility_20d",
    "close_to_sma_20",
    "close_to_sma_50",
    "volume_to_sma_20",
    "benchmark_trailing_return_20d",
    *MACRO_FEATURE_COLUMNS,
)
LABEL_COLUMNS = (
    "forward_return_1d",
    "forward_return_5d",
    "forward_return_20d",
    "forward_excess_return_20d",
    "forward_max_drawdown_20d",
)
BASE_COLUMNS = ("symbol", "as_of_date", "close", "volume")
CSV_COLUMNS = (*BASE_COLUMNS, *FEATURE_COLUMNS, *LABEL_COLUMNS)


@dataclass(frozen=True)
class DailyBar:
    as_of_date: date
    close: float
    volume: float


@dataclass(frozen=True)
class MacroPoint:
    name: str
    period: date
    available_on: date
    value: float


@dataclass(frozen=True)
class MacroSnapshot:
    points_by_name: Mapping[str, tuple[MacroPoint, ...]]

    def values_as_of(self, as_of_date: date) -> dict[str, float]:
        values: dict[str, float] = {}
        available_count = 0
        for name in MACRO_FEATURE_COLUMNS[:-1]:
            raw_name = name.removeprefix("bls_")
            points = self.points_by_name.get(raw_name, ())
            eligible = [point for point in points if point.available_on <= as_of_date]
            if eligible:
                values[name] = eligible[-1].value
                available_count += 1
            else:
                values[name] = 0.0
        values["bls_macro_points_available"] = float(available_count)
        return values


@dataclass(frozen=True)
class DatasetResult:
    rows: list[dict[str, Any]]
    summary: dict[str, Any]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build point-in-time daily modeling dataset.")
    parser.add_argument("--symbols", nargs="+", default=None)
    parser.add_argument("--symbols-file", default=DEFAULT_SYMBOLS_FILE)
    parser.add_argument("--data-dir", default="data/external")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--min-history", type=int, default=60)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", default=DEFAULT_SUMMARY)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    parser.add_argument("--bls-macro", default=DEFAULT_BLS_MACRO)
    parser.add_argument("--bls-release-lag-days", type=int, default=45)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_dataset(args)
    write_csv(Path(args.output), result.rows)
    write_json(Path(args.summary), result.summary)
    write_markdown(Path(args.markdown), result.summary)
    print(
        "point-in-time dataset status={status} rows={rows} symbols={symbols_written}".format(
            **result.summary["summary"]
        )
    )
    print(f"csv={args.output}")
    print(f"summary={args.summary}")
    return 0


def build_dataset(args: argparse.Namespace) -> DatasetResult:
    start = date.fromisoformat(str(args.start))
    end = date.fromisoformat(str(args.end))
    if start > end:
        raise SystemExit("start must be on or before end")
    if args.min_history < 50:
        raise SystemExit("min-history must be at least 50 for SMA features")
    symbols = resolve_symbols(args.symbols, Path(args.symbols_file))
    blocked = [symbol for symbol in symbols if looks_leveraged(symbol)]
    allowed = [symbol for symbol in symbols if symbol not in blocked]
    data_dir = Path(args.data_dir)
    benchmark = str(args.benchmark).strip().upper()
    benchmark_bars = load_symbol_bars(data_dir, benchmark)
    benchmark_features = benchmark_feature_maps(benchmark_bars, start, end)
    macro_snapshot = load_bls_macro_snapshot(
        Path(args.bls_macro), release_lag_days=int(args.bls_release_lag_days)
    )
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    insufficient: list[str] = []
    written_symbols: set[str] = set()
    for symbol in allowed:
        bars = load_symbol_bars(data_dir, symbol)
        if not bars:
            missing.append(symbol)
            continue
        symbol_rows = build_symbol_rows(
            symbol=symbol,
            bars=bars,
            start=start,
            end=end,
            min_history=args.min_history,
            benchmark_features=benchmark_features,
            macro_snapshot=macro_snapshot,
        )
        if not symbol_rows:
            insufficient.append(symbol)
            continue
        rows.extend(symbol_rows)
        written_symbols.add(symbol)
    rows.sort(key=lambda row: (str(row["as_of_date"]), str(row["symbol"])))
    summary = {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": "point-in-time dataset only; no orders; no broker; no credentials; no advice",
        "summary": {
            "status": "ok",
            "rows": len(rows),
            "symbols_requested": len(symbols),
            "symbols_allowed": len(allowed),
            "symbols_written": len(written_symbols),
            "blocked_leveraged_symbols": len(blocked),
            "missing_price_data": len(missing),
            "insufficient_history": len(insufficient),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "benchmark": benchmark,
            "bls_macro_source": str(args.bls_macro),
            "bls_release_lag_days": int(args.bls_release_lag_days),
            "bls_macro_series": len(macro_snapshot.points_by_name),
            "rows_with_all_bls_macro_points": sum(
                1
                for row in rows
                if row.get("bls_macro_points_available") == float(len(MACRO_FEATURE_COLUMNS) - 1)
            ),
            "order_created": False,
            "live_trading_authorized": False,
        },
        "columns": list(CSV_COLUMNS),
        "feature_columns": list(FEATURE_COLUMNS),
        "label_columns": list(LABEL_COLUMNS),
        "blocked_leveraged_symbols": blocked,
        "missing_price_data_symbols": missing,
        "insufficient_history_symbols": insufficient,
        "point_in_time_rule": (
            "Features use only bars with timestamp date <= as_of_date; labels use later bars "
            "only for offline evaluation and must not be decision-time inputs."
        ),
        "live_trading_authorized": False,
        "paper_api_authorized": False,
    }
    return DatasetResult(rows=rows, summary=summary)


def resolve_symbols(cli_symbols: Sequence[str] | None, symbols_file: Path) -> tuple[str, ...]:
    raw = list(cli_symbols) if cli_symbols else read_symbols_file(symbols_file)
    normalized: list[str] = []
    for symbol in raw:
        clean = symbol.strip().upper()
        if clean and clean not in normalized:
            normalized.append(clean)
    return tuple(normalized)


def load_symbol_bars(data_dir: Path, symbol: str) -> list[DailyBar]:
    path = data_dir / f"{cache_symbol(symbol)}_yahoo_daily_2015_2026.csv"
    if not path.exists():
        return []
    rows: list[DailyBar] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            timestamp = str(raw.get("timestamp", ""))
            close = float(raw.get("close", "0") or 0)
            volume = float(raw.get("volume", "0") or 0)
            if close <= 0 or volume < 0:
                continue
            rows.append(
                DailyBar(
                    as_of_date=datetime.fromisoformat(timestamp).date(),
                    close=close,
                    volume=volume,
                )
            )
    rows.sort(key=lambda bar: bar.as_of_date)
    return rows


def cache_symbol(symbol: str) -> str:
    return symbol.lower().replace(".", "_").replace("-", "_")


def benchmark_feature_maps(
    bars: Sequence[DailyBar], start: date, end: date
) -> dict[str, dict[date, float]]:
    filtered = [bar for bar in bars if start <= bar.as_of_date <= end]
    trailing_20: dict[date, float] = {}
    forward_20: dict[date, float] = {}
    for index, bar in enumerate(filtered):
        if index >= 20:
            trailing_20[bar.as_of_date] = return_between(filtered, index - 20, index)
        if index + 20 < len(filtered):
            forward_20[bar.as_of_date] = return_between(filtered, index, index + 20)
    return {"trailing_20": trailing_20, "forward_20": forward_20}


def load_bls_macro_snapshot(path: Path, *, release_lag_days: int) -> MacroSnapshot:
    if release_lag_days < 0:
        raise SystemExit("bls-release-lag-days must be nonnegative")
    if not path.exists():
        return MacroSnapshot(points_by_name={})
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        return MacroSnapshot(points_by_name={})
    series = payload.get("series", [])
    if not isinstance(series, list):
        return MacroSnapshot(points_by_name={})
    points_by_name: dict[str, list[MacroPoint]] = {}
    for series_row in series:
        if not isinstance(series_row, Mapping):
            continue
        name = str(series_row.get("name") or series_row.get("series_id") or "")
        points = series_row.get("points", [])
        if not name or not isinstance(points, list):
            continue
        for point in points:
            parsed = parse_bls_point(name, point, release_lag_days=release_lag_days)
            if parsed is not None:
                points_by_name.setdefault(name, []).append(parsed)
    normalized = {
        name: tuple(sorted(points, key=lambda point: point.available_on))
        for name, points in points_by_name.items()
    }
    return MacroSnapshot(points_by_name=normalized)


def parse_bls_point(name: str, point: object, *, release_lag_days: int) -> MacroPoint | None:
    if not isinstance(point, Mapping):
        return None
    value = point.get("value")
    if not isinstance(value, int | float):
        return None
    year = str(point.get("year") or "")
    period = str(point.get("period") or "")
    if not year.isdigit() or not period.startswith("M") or not period[1:].isdigit():
        return None
    month = int(period[1:])
    if month < 1 or month > 12:
        return None
    period_month = date(int(year), month, 1)
    period_end = month_end(period_month)
    return MacroPoint(
        name=name,
        period=period_end,
        available_on=period_end + timedelta(days=release_lag_days),
        value=float(value),
    )


def month_end(first_day: date) -> date:
    if first_day.month == 12:
        next_month = date(first_day.year + 1, 1, 1)
    else:
        next_month = date(first_day.year, first_day.month + 1, 1)
    return next_month - timedelta(days=1)


def build_symbol_rows(
    *,
    symbol: str,
    bars: Sequence[DailyBar],
    start: date,
    end: date,
    min_history: int,
    benchmark_features: Mapping[str, Mapping[date, float]],
    macro_snapshot: MacroSnapshot,
) -> list[dict[str, Any]]:
    filtered = [bar for bar in bars if start <= bar.as_of_date <= end]
    rows: list[dict[str, Any]] = []
    benchmark_trailing = benchmark_features.get("trailing_20", {})
    benchmark_forward = benchmark_features.get("forward_20", {})
    max_horizon = 20
    for index, bar in enumerate(filtered):
        if index < min_history or index + max_horizon >= len(filtered):
            continue
        if bar.as_of_date not in benchmark_trailing or bar.as_of_date not in benchmark_forward:
            continue
        forward_20 = return_between(filtered, index, index + 20)
        macro_values = macro_snapshot.values_as_of(bar.as_of_date)
        rows.append(
            {
                "symbol": symbol,
                "as_of_date": bar.as_of_date.isoformat(),
                "close": bar.close,
                "volume": bar.volume,
                "trailing_return_1d": return_between(filtered, index - 1, index),
                "trailing_return_5d": return_between(filtered, index - 5, index),
                "trailing_return_20d": return_between(filtered, index - 20, index),
                "trailing_volatility_20d": trailing_volatility(filtered, index, 20),
                "close_to_sma_20": close_to_sma(filtered, index, 20),
                "close_to_sma_50": close_to_sma(filtered, index, 50),
                "volume_to_sma_20": volume_to_sma(filtered, index, 20),
                "benchmark_trailing_return_20d": benchmark_trailing[bar.as_of_date],
                **macro_values,
                "forward_return_1d": return_between(filtered, index, index + 1),
                "forward_return_5d": return_between(filtered, index, index + 5),
                "forward_return_20d": forward_20,
                "forward_excess_return_20d": forward_20 - benchmark_forward[bar.as_of_date],
                "forward_max_drawdown_20d": forward_max_drawdown(filtered, index, 20),
            }
        )
    return rows


def return_between(bars: Sequence[DailyBar], start_index: int, end_index: int) -> float:
    if start_index < 0 or end_index >= len(bars):
        raise IndexError("return window is outside available bars")
    return bars[end_index].close / bars[start_index].close - 1.0


def trailing_volatility(bars: Sequence[DailyBar], index: int, window: int) -> float:
    returns = [return_between(bars, idx - 1, idx) for idx in range(index - window + 1, index + 1)]
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    return math.sqrt(variance)


def close_to_sma(bars: Sequence[DailyBar], index: int, window: int) -> float:
    closes = [bar.close for bar in bars[index - window + 1 : index + 1]]
    return bars[index].close / (sum(closes) / len(closes)) - 1.0


def volume_to_sma(bars: Sequence[DailyBar], index: int, window: int) -> float:
    volumes = [bar.volume for bar in bars[index - window + 1 : index + 1]]
    average = sum(volumes) / len(volumes)
    return 0.0 if average == 0 else bars[index].volume / average - 1.0


def forward_max_drawdown(bars: Sequence[DailyBar], index: int, horizon: int) -> float:
    anchor = bars[index].close
    return min(bars[index + offset].close / anchor - 1.0 for offset in range(1, horizon + 1))


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: format_cell(row.get(column, "")) for column in CSV_COLUMNS})


def format_cell(value: Any) -> Any:
    if isinstance(value, float):
        return f"{value:.10f}"
    return value


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown(path: Path, summary: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = summary["summary"]
    lines = [
        "# Point-in-time daily modeling dataset",
        "",
        "Safety: dataset generation only; no orders, no broker, no credentials, no advice.",
        "",
        "## Summary",
        "",
        f"- Rows: `{data['rows']}`",
        f"- Symbols requested: `{data['symbols_requested']}`",
        f"- Symbols written: `{data['symbols_written']}`",
        f"- Missing price data: `{data['missing_price_data']}`",
        f"- Insufficient history: `{data['insufficient_history']}`",
        f"- Benchmark: `{data['benchmark']}`",
        f"- BLS macro series: `{data['bls_macro_series']}`",
        f"- Rows with all BLS macro points: `{data['rows_with_all_bls_macro_points']}`",
        f"- Order created: `{data['order_created']}`",
        f"- Live trading authorized: `{data['live_trading_authorized']}`",
        "",
        "## Point-in-time rule",
        "",
        str(summary["point_in_time_rule"]),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
