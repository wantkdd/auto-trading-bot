"""Offline strategy optimization evaluator for real historical OHLCV data.

This script is intentionally outside ``src/`` so the production MVP remains
broker-free and network-free. It fetches/cache-validates market data for local
research, then evaluates fixed, explainable long-only strategy families with
chronological holdout and walk-forward tests.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time
from functools import partial
from pathlib import Path
from statistics import fmean
from typing import Any

from auto_trading_bot.backtest import run_backtest
from auto_trading_bot.data import DataValidationError, load_csv_bars
from auto_trading_bot.domain import BacktestConfig, Bar, EquityPoint, SignalAction, StrategySignal
from auto_trading_bot.metrics import summarize_metrics
from auto_trading_bot.strategies import MomentumStrategy, MovingAverageCrossoverStrategy, Strategy
from auto_trading_bot.validation import train_test_split_window, walk_forward_windows

YAHOO_CHART_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
DATA_SOURCE_HELP_URL = (
    "https://help.yahoo.com/kb/finance-for-web/download-historical-data-yahoo-finance-sln2311.html"
)
TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class StrategySpec:
    family: str
    name: str
    params: dict[str, float | int]
    build: Callable[[], Strategy]


@dataclass(frozen=True)
class StaticPortfolioSpec:
    family: str
    name: str
    params: dict[str, float | int]
    weights: dict[str, float]


@dataclass(frozen=True)
class WindowEvaluation:
    symbol: str
    strategy: str
    family: str
    window: str
    start: str
    end: str
    bars: int
    total_return: float
    benchmark_return: float
    excess_return: float
    max_drawdown: float
    sharpe: float | None
    sortino: float | None
    trade_count: int
    final_equity: float


@dataclass(frozen=True)
class CandidateSummary:
    strategy: str
    family: str
    params: dict[str, float | int]
    status: str
    score: float
    median_excess: float
    mean_excess: float
    min_holdout_excess: float
    worst_max_drawdown: float
    median_total_return: float
    median_benchmark_return: float
    total_trades: int
    traded_window_ratio: float
    evaluated_windows: int
    failure_reasons: tuple[str, ...]


class SmaTrendFilterStrategy(Strategy):
    """Buy when price is above an SMA band; exit when it loses the band."""

    def __init__(self, window: int, entry_buffer: float = 0.0, exit_buffer: float = 0.0) -> None:
        if window <= 1:
            raise ValueError("window must be greater than one")
        if entry_buffer < 0 or exit_buffer < 0:
            raise ValueError("buffers must be nonnegative")
        self.window = window
        self.entry_buffer = entry_buffer
        self.exit_buffer = exit_buffer
        self.name = f"sma_trend_filter_{window}_{entry_buffer:g}_{exit_buffer:g}"

    def generate_signals(self, bars: tuple[Bar, ...]) -> tuple[StrategySignal, ...]:
        closes = [bar.close for bar in bars]
        signals: list[StrategySignal] = []
        for index, bar in enumerate(bars):
            if index + 1 < self.window:
                signals.append(StrategySignal(bar.timestamp, SignalAction.HOLD, "warming up"))
                continue
            average = fmean(closes[index + 1 - self.window : index + 1])
            if bar.close > average * (1 + self.entry_buffer):
                action = SignalAction.BUY
                reason = "close above SMA entry band"
            elif bar.close < average * (1 - self.exit_buffer):
                action = SignalAction.SELL
                reason = "close below SMA exit band"
            else:
                action = SignalAction.HOLD
                reason = "inside SMA band"
            signals.append(
                StrategySignal(bar.timestamp, action, reason, strength=(bar.close / average) - 1.0)
            )
        return tuple(signals)


class DonchianChannelStrategy(Strategy):
    """Buy breakouts above prior highs and exit on prior low-channel breaks."""

    def __init__(self, entry_window: int, exit_window: int) -> None:
        if entry_window <= 1 or exit_window <= 1:
            raise ValueError("channel windows must be greater than one")
        self.entry_window = entry_window
        self.exit_window = exit_window
        self.name = f"donchian_channel_{entry_window}_{exit_window}"

    def generate_signals(self, bars: tuple[Bar, ...]) -> tuple[StrategySignal, ...]:
        closes = [bar.close for bar in bars]
        signals: list[StrategySignal] = []
        warmup = max(self.entry_window, self.exit_window)
        for index, bar in enumerate(bars):
            if index < warmup:
                signals.append(StrategySignal(bar.timestamp, SignalAction.HOLD, "warming up"))
                continue
            prior_entry_high = max(closes[index - self.entry_window : index])
            prior_exit_low = min(closes[index - self.exit_window : index])
            if bar.close > prior_entry_high:
                action = SignalAction.BUY
                reason = "close broke above prior channel high"
                strength = (bar.close / prior_entry_high) - 1.0
            elif bar.close < prior_exit_low:
                action = SignalAction.SELL
                reason = "close broke below prior channel low"
                strength = (bar.close / prior_exit_low) - 1.0
            else:
                action = SignalAction.HOLD
                reason = "inside price channel"
                strength = 0.0
            signals.append(StrategySignal(bar.timestamp, action, reason, strength=strength))
        return tuple(signals)


class TrendMomentumStrategy(Strategy):
    """Require both long trend and lookback momentum to be positive."""

    def __init__(self, ma_window: int, lookback: int, threshold: float = 0.0) -> None:
        if ma_window <= 1 or lookback <= 0:
            raise ValueError("windows must be positive")
        if threshold < 0:
            raise ValueError("threshold must be nonnegative")
        self.ma_window = ma_window
        self.lookback = lookback
        self.threshold = threshold
        self.name = f"trend_momentum_{ma_window}_{lookback}_{threshold:g}"

    def generate_signals(self, bars: tuple[Bar, ...]) -> tuple[StrategySignal, ...]:
        closes = [bar.close for bar in bars]
        signals: list[StrategySignal] = []
        warmup = max(self.ma_window, self.lookback)
        for index, bar in enumerate(bars):
            if index < warmup:
                signals.append(StrategySignal(bar.timestamp, SignalAction.HOLD, "warming up"))
                continue
            average = fmean(closes[index + 1 - self.ma_window : index + 1])
            momentum = (bar.close / bars[index - self.lookback].close) - 1.0
            above_trend = bar.close > average
            if above_trend and momentum > self.threshold:
                action = SignalAction.BUY
                reason = "trend and momentum positive"
            elif (not above_trend) or momentum < -self.threshold:
                action = SignalAction.SELL
                reason = "trend or momentum failed"
            else:
                action = SignalAction.HOLD
                reason = "mixed trend and momentum"
            signals.append(StrategySignal(bar.timestamp, action, reason, strength=momentum))
        return tuple(signals)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch/cache real OHLCV data and evaluate offline strategy stability."
    )
    parser.add_argument("--symbols", nargs="+", default=["SPY", "QQQ", "DIA"])
    parser.add_argument(
        "--aux-symbols",
        nargs="+",
        default=["GLD"],
        help="Auxiliary assets available to portfolio-level defensive strategies.",
    )
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--data-dir", default="data/external")
    parser.add_argument("--output", default=".omx/reports/strategy-optimization-latest.json")
    parser.add_argument("--markdown", default=".omx/reports/strategy-optimization-latest.md")
    parser.add_argument("--initial-cash", type=float, default=10_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--top", type=int, default=12)
    return parser.parse_args(argv)


def yahoo_symbol(user_symbol: str) -> str:
    normalized = user_symbol.upper()
    aliases = {"005930": "005930.KS", "SAMSUNG": "005930.KS"}
    return aliases.get(normalized, user_symbol)


def fetch_or_load_bars(
    *,
    user_symbol: str,
    start: date,
    end: date,
    data_dir: Path,
    force_refresh: bool,
) -> tuple[tuple[Bar, ...] | None, dict[str, Any]]:
    query_symbol = yahoo_symbol(user_symbol)
    cache_path = data_dir / f"{safe_name(query_symbol)}_yahoo_daily_{start.year}_{end.year}.csv"
    metadata: dict[str, Any] = {
        "symbol": user_symbol,
        "query_symbol": query_symbol,
        "cache_path": str(cache_path),
        "source": "Yahoo Finance chart endpoint",
        "source_help_url": DATA_SOURCE_HELP_URL,
    }

    if force_refresh or not cache_path.exists():
        try:
            rows, url = fetch_yahoo_rows(query_symbol, start, end)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            write_rows(cache_path, rows)
            metadata["fetched_url"] = url
            metadata["refreshed"] = True
        except (OSError, urllib.error.URLError, ValueError, KeyError, IndexError) as exc:
            metadata["status"] = "fetch_failed"
            metadata["error"] = str(exc)
            return None, metadata
    else:
        metadata["refreshed"] = False

    try:
        bars = load_csv_bars(cache_path)
    except (DataValidationError, ValueError) as exc:
        metadata["status"] = "validation_failed"
        metadata["error"] = str(exc)
        return None, metadata

    metadata.update(
        {
            "status": "ok",
            "rows": len(bars),
            "first_bar": bars[0].timestamp.isoformat() if bars else None,
            "last_bar": bars[-1].timestamp.isoformat() if bars else None,
        }
    )
    return bars, metadata


def fetch_yahoo_rows(symbol: str, start: date, end: date) -> tuple[list[dict[str, Any]], str]:
    period1 = int(datetime.combine(start, time.min, tzinfo=UTC).timestamp())
    # Yahoo period2 is exclusive. Add one day so the requested end date can appear.
    period2 = int(datetime.combine(end, time.min, tzinfo=UTC).timestamp()) + 86_400
    query = urllib.parse.urlencode(
        {
            "period1": period1,
            "period2": period2,
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
    )
    url = f"{YAHOO_CHART_ENDPOINT.format(symbol=urllib.parse.quote(symbol))}?{query}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "auto-trading-bot-offline-research/0.1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - research script only
        payload = json.loads(response.read().decode("utf-8"))

    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    rows: list[dict[str, Any]] = []
    for index, raw_ts in enumerate(timestamps):
        row = {
            "timestamp": datetime.fromtimestamp(raw_ts, tz=UTC).replace(tzinfo=None).isoformat(),
            "open": value_at(quote, "open", index),
            "high": value_at(quote, "high", index),
            "low": value_at(quote, "low", index),
            "close": value_at(quote, "close", index),
            "volume": value_at(quote, "volume", index),
        }
        if any(row[key] is None for key in ("open", "high", "low", "close", "volume")):
            continue
        rows.append(row)
    if len(rows) < 2:
        raise ValueError(f"not enough rows returned for {symbol}")
    return rows, url


def value_at(quote: dict[str, list[Any]], key: str, index: int) -> Any:
    values = quote.get(key) or []
    if index >= len(values):
        return None
    return values[index]


def write_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"]
        )
        writer.writeheader()
        writer.writerows(rows)


def safe_name(symbol: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in symbol).strip("_")


def build_static_portfolio_specs() -> tuple[StaticPortfolioSpec, ...]:
    specs: list[StaticPortfolioSpec] = []
    for qqq_weight in (0.30, 0.31, 0.32, 0.35, 0.36, 0.38, 0.39, 0.40):
        gld_weight = round(1.0 - qqq_weight, 2)
        specs.append(
            StaticPortfolioSpec(
                family="static_portfolio",
                name=f"static_portfolio_qqq_{qqq_weight:g}_gld_{gld_weight:g}",
                params={
                    "qqq_weight": qqq_weight,
                    "gld_weight": gld_weight,
                    "rebalance": 0,
                },
                weights={"QQQ": qqq_weight, "GLD": gld_weight},
            )
        )
    return tuple(specs)


def build_strategy_specs() -> tuple[StrategySpec, ...]:
    specs: list[StrategySpec] = []
    for short in (5, 10, 20, 30, 50, 75, 100):
        for long in (50, 100, 150, 200, 250):
            if short >= long:
                continue
            specs.append(
                StrategySpec(
                    family="moving_average",
                    name=f"moving_average_crossover_{short}_{long}",
                    params={"short_window": short, "long_window": long},
                    build=lambda short=short, long=long: MovingAverageCrossoverStrategy(
                        short, long
                    ),
                )
            )
    for lookback in (20, 40, 60, 90, 120, 180, 252):
        for threshold in (0.0, 0.01, 0.02, 0.05, 0.08, 0.12):
            specs.append(
                StrategySpec(
                    family="momentum",
                    name=f"momentum_{lookback}_{threshold:g}",
                    params={"lookback": lookback, "threshold": threshold},
                    build=lambda lookback=lookback, threshold=threshold: MomentumStrategy(
                        lookback, threshold
                    ),
                )
            )
    for window in (50, 100, 150, 200, 250):
        for entry_buffer in (0.0, 0.01, 0.02):
            for exit_buffer in (0.0, 0.01, 0.02):
                specs.append(
                    StrategySpec(
                        family="sma_trend_filter",
                        name=f"sma_trend_filter_{window}_{entry_buffer:g}_{exit_buffer:g}",
                        params={
                            "window": window,
                            "entry_buffer": entry_buffer,
                            "exit_buffer": exit_buffer,
                        },
                        build=partial(SmaTrendFilterStrategy, window, entry_buffer, exit_buffer),
                    )
                )
    for entry_window in (40, 60, 90, 120, 180, 252):
        for exit_window in (20, 40, 60, 90):
            if exit_window >= entry_window:
                continue
            specs.append(
                StrategySpec(
                    family="donchian_channel",
                    name=f"donchian_channel_{entry_window}_{exit_window}",
                    params={"entry_window": entry_window, "exit_window": exit_window},
                    build=partial(DonchianChannelStrategy, entry_window, exit_window),
                )
            )
    for ma_window in (100, 150, 200, 250):
        for lookback in (60, 90, 120, 180):
            for threshold in (0.0, 0.02, 0.05):
                specs.append(
                    StrategySpec(
                        family="trend_momentum",
                        name=f"trend_momentum_{ma_window}_{lookback}_{threshold:g}",
                        params={
                            "ma_window": ma_window,
                            "lookback": lookback,
                            "threshold": threshold,
                        },
                        build=partial(TrendMomentumStrategy, ma_window, lookback, threshold),
                    )
                )
    return tuple(specs)


def evaluate_all(
    data_by_symbol: dict[str, tuple[Bar, ...]],
    specs: Sequence[StrategySpec],
    config: BacktestConfig,
) -> tuple[list[WindowEvaluation], list[CandidateSummary]]:
    evaluations: list[WindowEvaluation] = []
    grouped: dict[str, list[WindowEvaluation]] = defaultdict(list)

    primary_symbols = {"SPY", "QQQ", "DIA"}
    for symbol, bars in sorted(data_by_symbol.items()):
        if symbol not in primary_symbols:
            continue
        windows = evaluation_windows(bars)
        for spec in specs:
            for window_name, start_index, test_start, test_end in windows:
                eval_row = evaluate_window(
                    symbol=symbol,
                    bars=bars,
                    spec=spec,
                    config=config,
                    window_name=window_name,
                    start_index=start_index,
                    test_start=test_start,
                    test_end=test_end,
                )
                evaluations.append(eval_row)
                grouped[spec.name].append(eval_row)

    portfolio_evaluations, portfolio_summaries = evaluate_static_portfolios(data_by_symbol, config)
    evaluations.extend(portfolio_evaluations)

    summaries = [summarize_candidate(spec, grouped[spec.name]) for spec in specs]
    summaries.extend(portfolio_summaries)
    summaries.sort(key=lambda row: row.score, reverse=True)
    return evaluations, summaries


def evaluate_static_portfolios(
    data_by_symbol: dict[str, tuple[Bar, ...]],
    config: BacktestConfig,
) -> tuple[list[WindowEvaluation], list[CandidateSummary]]:
    specs = build_static_portfolio_specs()
    required = {"SPY", "QQQ", "DIA", "GLD"}
    if not required.issubset(data_by_symbol):
        return [], []

    dates, bars_by_symbol = align_bars_by_date(data_by_symbol, required)
    windows = evaluation_windows(tuple(bars_by_symbol["SPY"]))
    evaluations: list[WindowEvaluation] = []
    grouped: dict[str, list[WindowEvaluation]] = defaultdict(list)
    for spec in specs:
        for window_name, _start_index, test_start, test_end in windows:
            eval_row = evaluate_static_portfolio_window(
                dates=dates,
                bars_by_symbol=bars_by_symbol,
                spec=spec,
                config=config,
                window_name=window_name,
                test_start=test_start,
                test_end=test_end,
            )
            evaluations.append(eval_row)
            grouped[spec.name].append(eval_row)
    summaries = [summarize_static_portfolio(spec, grouped[spec.name]) for spec in specs]
    return evaluations, summaries


def align_bars_by_date(
    data_by_symbol: dict[str, tuple[Bar, ...]], symbols: set[str]
) -> tuple[tuple[Any, ...], dict[str, tuple[Bar, ...]]]:
    lookup = {
        symbol: {bar.timestamp.date(): bar for bar in data_by_symbol[symbol]} for symbol in symbols
    }
    common_dates = tuple(sorted(set.intersection(*(set(rows) for rows in lookup.values()))))
    aligned = {
        symbol: tuple(lookup[symbol][active_date] for active_date in common_dates)
        for symbol in symbols
    }
    return common_dates, aligned


def evaluate_static_portfolio_window(
    *,
    dates: tuple[Any, ...],
    bars_by_symbol: dict[str, tuple[Bar, ...]],
    spec: StaticPortfolioSpec,
    config: BacktestConfig,
    window_name: str,
    test_start: int,
    test_end: int,
) -> WindowEvaluation:
    cash = config.initial_cash
    positions: dict[str, int] = {}
    slippage_rate = config.slippage_bps / 10_000
    trade_count = 0
    for symbol, weight in spec.weights.items():
        execution_price = bars_by_symbol[symbol][test_start].open * (1 + slippage_rate)
        allocated_cash = config.initial_cash * weight
        quantity = int(allocated_cash / (execution_price * (1 + config.commission_rate)))
        if quantity <= 0:
            continue
        notional = quantity * execution_price
        cash -= notional + (notional * config.commission_rate)
        positions[symbol] = quantity
        trade_count += 1

    curve = tuple(
        EquityPoint(
            timestamp=bars_by_symbol["SPY"][index].timestamp,
            cash=cash,
            position=sum(positions.values()),
            close_price=1.0,
            equity=cash
            + sum(
                quantity * bars_by_symbol[symbol][index].close
                for symbol, quantity in positions.items()
            ),
        )
        for index in range(test_start, test_end)
    )
    first_equity = curve[0].equity
    metrics = summarize_metrics(equity_curve=curve, trades=tuple(), initial_cash=first_equity)
    benchmark_return, _benchmark_final = equal_weight_benchmark_return(
        bars_by_symbol,
        test_start,
        test_end,
        first_equity,
        symbols=("SPY", "QQQ", "DIA"),
    )
    total = float(metrics["total_return"] or 0.0)
    return WindowEvaluation(
        symbol="PORTFOLIO",
        strategy=spec.name,
        family=spec.family,
        window=window_name,
        start=dates[test_start].isoformat(),
        end=dates[test_end - 1].isoformat(),
        bars=test_end - test_start,
        total_return=total,
        benchmark_return=benchmark_return,
        excess_return=total - benchmark_return,
        max_drawdown=float(metrics["max_drawdown"] or 0.0),
        sharpe=float(metrics["sharpe"]) if metrics["sharpe"] is not None else None,
        sortino=float(metrics["sortino"]) if metrics["sortino"] is not None else None,
        trade_count=trade_count,
        final_equity=float(metrics["final_equity"] or first_equity),
    )


def equal_weight_benchmark_return(
    bars_by_symbol: dict[str, tuple[Bar, ...]],
    test_start: int,
    test_end: int,
    initial_equity: float,
    *,
    symbols: tuple[str, ...],
) -> tuple[float, float]:
    allocation = initial_equity / len(symbols)
    final_equity = 0.0
    for symbol in symbols:
        first_open = bars_by_symbol[symbol][test_start].open
        shares = int(allocation / first_open)
        residual = allocation - shares * first_open
        final_equity += residual + shares * bars_by_symbol[symbol][test_end - 1].close
    return (final_equity / initial_equity) - 1.0, final_equity


def summarize_static_portfolio(
    spec: StaticPortfolioSpec, rows: Sequence[WindowEvaluation]
) -> CandidateSummary:
    return summarize_candidate(
        StrategySpec(
            family=spec.family,
            name=spec.name,
            params=spec.params,
            build=lambda: MomentumStrategy(1),
        ),
        rows,
    )


def evaluation_windows(bars: tuple[Bar, ...]) -> tuple[tuple[str, int, int, int], ...]:
    holdout = train_test_split_window(
        bars, 0.7, min_train_size=TRADING_DAYS_PER_YEAR * 3, min_test_size=252
    )
    windows: list[tuple[str, int, int, int]] = [
        ("holdout_70_30", holdout.train_start, holdout.test_start, holdout.test_end)
    ]
    for wf_window in walk_forward_windows(
        bars,
        train_size=TRADING_DAYS_PER_YEAR * 3,
        test_size=TRADING_DAYS_PER_YEAR,
        step_size=TRADING_DAYS_PER_YEAR,
    ):
        windows.append(
            (wf_window.label, wf_window.train_start, wf_window.test_start, wf_window.test_end)
        )
    return tuple(windows)


def evaluate_window(
    *,
    symbol: str,
    bars: tuple[Bar, ...],
    spec: StrategySpec,
    config: BacktestConfig,
    window_name: str,
    start_index: int,
    test_start: int,
    test_end: int,
) -> WindowEvaluation:
    run_bars = bars[start_index:test_end]
    result = run_backtest(run_bars, spec.build(), config)
    relative_test_start = test_start - start_index
    test_curve = result.equity_curve[relative_test_start:]
    first_test_equity = test_curve[0].equity
    first_test_timestamp = bars[test_start].timestamp
    test_trades = tuple(trade for trade in result.trades if trade.timestamp >= first_test_timestamp)
    metrics = summarize_metrics(
        equity_curve=test_curve,
        trades=test_trades,
        initial_cash=first_test_equity,
    )
    benchmark_return, benchmark_final = benchmark_total_return(
        bars[test_start:test_end], first_test_equity
    )
    total = float(metrics["total_return"] or 0.0)
    return WindowEvaluation(
        symbol=symbol,
        strategy=spec.name,
        family=spec.family,
        window=window_name,
        start=bars[test_start].timestamp.date().isoformat(),
        end=bars[test_end - 1].timestamp.date().isoformat(),
        bars=test_end - test_start,
        total_return=total,
        benchmark_return=benchmark_return,
        excess_return=total - benchmark_return,
        max_drawdown=float(metrics["max_drawdown"] or 0.0),
        sharpe=float(metrics["sharpe"]) if metrics["sharpe"] is not None else None,
        sortino=float(metrics["sortino"]) if metrics["sortino"] is not None else None,
        trade_count=int(metrics["trade_count"] or 0),
        final_equity=float(metrics["final_equity"] or first_test_equity),
    )


def benchmark_total_return(bars: tuple[Bar, ...], initial_equity: float) -> tuple[float, float]:
    first_open = bars[0].open
    shares = int(initial_equity / first_open)
    residual = initial_equity - shares * first_open
    final_equity = residual + shares * bars[-1].close
    return (final_equity / initial_equity) - 1.0, final_equity


def summarize_candidate(spec: StrategySpec, rows: Sequence[WindowEvaluation]) -> CandidateSummary:
    if not rows:
        return CandidateSummary(
            strategy=spec.name,
            family=spec.family,
            params=spec.params,
            status="fail",
            score=-math.inf,
            median_excess=0.0,
            mean_excess=0.0,
            min_holdout_excess=0.0,
            worst_max_drawdown=0.0,
            median_total_return=0.0,
            median_benchmark_return=0.0,
            total_trades=0,
            traded_window_ratio=0.0,
            evaluated_windows=0,
            failure_reasons=("no_evaluations",),
        )

    excesses = [row.excess_return for row in rows]
    total_returns = [row.total_return for row in rows]
    benchmark_returns = [row.benchmark_return for row in rows]
    holdout_excesses = [row.excess_return for row in rows if row.window == "holdout_70_30"]
    worst_max_drawdown = min(row.max_drawdown for row in rows)
    total_trades = sum(row.trade_count for row in rows)
    traded_window_ratio = sum(1 for row in rows if row.trade_count > 0) / len(rows)
    median_excess = statistics.median(excesses)
    mean_excess = statistics.fmean(excesses)
    min_holdout_excess = min(holdout_excesses) if holdout_excesses else min(excesses)
    median_total_return = statistics.median(total_returns)
    median_benchmark_return = statistics.median(benchmark_returns)

    failure_reasons: list[str] = []
    if median_excess <= 0:
        failure_reasons.append("median_excess_not_positive")
    if min_holdout_excess < -0.05:
        failure_reasons.append("holdout_symbol_excess_below_minus_5pp")
    if worst_max_drawdown < -0.20:
        failure_reasons.append("max_drawdown_worse_than_minus_20pct")
    min_total_trades = max(18, len({row.symbol for row in rows}) * 6)
    if total_trades < min_total_trades:
        failure_reasons.append("insufficient_trade_count")
    if traded_window_ratio < 0.50:
        failure_reasons.append("too_few_windows_with_trades")
    if median_total_return <= 0:
        failure_reasons.append("median_total_return_not_positive")

    # Conservative score: reward excess, punish tail holdout loss and drawdown breach.
    drawdown_penalty = max(0.0, abs(worst_max_drawdown) - 0.20)
    trade_penalty = 0.01 if total_trades < min_total_trades else 0.0
    score = (
        median_excess
        + (0.35 * mean_excess)
        + (0.5 * min_holdout_excess)
        - drawdown_penalty
        - trade_penalty
    )
    status = "pass" if not failure_reasons else "fail"
    return CandidateSummary(
        strategy=spec.name,
        family=spec.family,
        params=spec.params,
        status=status,
        score=score,
        median_excess=median_excess,
        mean_excess=mean_excess,
        min_holdout_excess=min_holdout_excess,
        worst_max_drawdown=worst_max_drawdown,
        median_total_return=median_total_return,
        median_benchmark_return=median_benchmark_return,
        total_trades=total_trades,
        traded_window_ratio=traded_window_ratio,
        evaluated_windows=len(rows),
        failure_reasons=tuple(failure_reasons),
    )


def percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"cannot serialize {type(obj)!r}")


def write_markdown(path: Path, report: dict[str, Any], top: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summaries = report["candidate_summaries"][:top]
    lines = [
        "# Strategy stability optimization report",
        "",
        f"Status: **{report['status'].upper()}**",
        "",
        "Safety: offline historical backtest only; no live trading, no broker integration, "
        "no credentials, no investment advice.",
        "",
        "## Criteria",
        "",
    ]
    for item in report["criteria"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Data",
            "",
            "| Symbol | Status | Rows | First | Last | Note |",
            "| --- | --- | ---: | --- | --- | --- |",
        ]
    )
    for item in report["data"]:
        lines.append(
            "| {symbol} | {status} | {rows} | {first} | {last} | {note} |".format(
                symbol=item.get("symbol"),
                status=item.get("status"),
                rows=item.get("rows", ""),
                first=item.get("first_bar", ""),
                last=item.get("last_bar", ""),
                note=(item.get("error") or "").replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "## Top candidates",
            "",
            "| Rank | Status | Strategy | Median excess | Mean excess | Min holdout excess | "
            "Worst MDD | Median return | Median benchmark | Trades | Traded win. | Reasons |",
            "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for index, row in enumerate(summaries, start=1):
        reasons = ", ".join(row["failure_reasons"]) or "-"
        lines.append(
            (
                "| {rank} | {status} | `{strategy}` | {median_excess} | {mean_excess} | "
                "{min_holdout_excess} | {worst_mdd} | {median_total} | "
                "{median_benchmark} | {trades} | {traded_windows:.0%} | {reasons} |"
            ).format(
                rank=index,
                status=row["status"],
                strategy=row["strategy"],
                median_excess=percent(row["median_excess"]),
                mean_excess=percent(row["mean_excess"]),
                min_holdout_excess=percent(row["min_holdout_excess"]),
                worst_mdd=percent(row["worst_max_drawdown"]),
                median_total=percent(row["median_total_return"]),
                median_benchmark=percent(row["median_benchmark_return"]),
                trades=row["total_trades"],
                traded_windows=row["traded_window_ratio"],
                reasons=reasons,
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            report["interpretation"],
            "",
            "## Sources",
            "",
            f"- Yahoo Finance historical-data help: {DATA_SOURCE_HELP_URL}",
            "- Yahoo Finance chart endpoint URLs are recorded per symbol in the JSON report.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    data_dir = Path(args.data_dir)
    data_by_symbol: dict[str, tuple[Bar, ...]] = {}
    data_metadata: list[dict[str, Any]] = []

    requested_symbols = list(dict.fromkeys([*args.symbols, *args.aux_symbols]))
    for symbol in requested_symbols:
        bars, metadata = fetch_or_load_bars(
            user_symbol=symbol,
            start=start,
            end=end,
            data_dir=data_dir,
            force_refresh=args.force_refresh,
        )
        metadata["role"] = "primary" if symbol in args.symbols else "auxiliary"
        data_metadata.append(metadata)
        if bars is not None:
            data_by_symbol[symbol.upper()] = bars

    if not data_by_symbol:
        return {
            "status": "blocked",
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "criteria": criteria_lines(),
            "data": data_metadata,
            "candidate_summaries": [],
            "interpretation": (
                "No valid market data was available, so no strategy can be evaluated."
            ),
        }

    config = BacktestConfig(
        initial_cash=args.initial_cash,
        commission_rate=args.commission_rate,
        slippage_bps=args.slippage_bps,
    )
    evaluations, summaries = evaluate_all(data_by_symbol, build_strategy_specs(), config)
    pass_count = sum(1 for row in summaries if row.status == "pass")
    status = "pass" if pass_count else "fail"
    best = summaries[0]
    interpretation = (
        "At least one candidate passed the conservative stability gate. This is still only a "
        "research signal for additional paper trading, not authorization for live capital."
        if status == "pass"
        else "No candidate passed the conservative stability gate. The current strategy families "
        "should not be promoted to paper-money or live-money delegation without new research, "
        "additional strategy design, and independent data validation."
    )
    return {
        "status": status,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "request": {
            "symbols": args.symbols,
            "start": args.start,
            "end": args.end,
            "initial_cash": args.initial_cash,
            "commission_rate": args.commission_rate,
            "slippage_bps": args.slippage_bps,
        },
        "criteria": criteria_lines(),
        "data": data_metadata,
        "best_candidate": asdict(best),
        "pass_candidate_count": pass_count,
        "candidate_summaries": [asdict(row) for row in summaries],
        "evaluations": [asdict(row) for row in evaluations],
        "interpretation": interpretation,
    }


def criteria_lines() -> list[str]:
    return [
        "median out-of-sample excess return versus buy-and-hold must be positive",
        "no symbol may have holdout excess return below -5 percentage points",
        "worst out-of-sample max drawdown must be no worse than -20%",
        "aggregate trade count and traded-window ratio must be high enough "
        "to avoid one-shot artifacts",
        "median out-of-sample total return must be positive after 0.1% "
        "commission and 5 bps slippage",
    ]


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    output = Path(args.output)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=to_jsonable), encoding="utf-8"
    )
    write_markdown(markdown, report, args.top)
    print(f"status={report['status']} pass_candidates={report.get('pass_candidate_count', 0)}")
    if report.get("best_candidate"):
        best = report["best_candidate"]
        print(
            (
                "best={strategy} median_excess={median_excess:.2%} "
                "min_holdout_excess={min_holdout_excess:.2%} "
                "worst_mdd={worst_max_drawdown:.2%}"
            ).format(**best)
        )
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
