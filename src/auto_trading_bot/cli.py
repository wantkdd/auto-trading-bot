"""Command line entrypoints for local/offline MVP validation runs."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .reports import ReportInputs, SAFETY_STATEMENT, write_report_bundle
from .validation import DisqualificationRules, evaluate_disqualification, train_test_split_window


@dataclass(frozen=True)
class _CliBar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auto-trading-bot",
        description="Run offline backtest validation and write markdown/JSON reports.",
    )
    subparsers = parser.add_subparsers(dest="command")
    _add_backtest_parser(
        subparsers.add_parser("backtest", help="run an offline fixture backtest"),
        required_paths=True,
    )
    _add_backtest_parser(parser, required_paths=False)
    return parser


def _add_backtest_parser(parser: argparse.ArgumentParser, *, required_paths: bool) -> None:
    if getattr(parser, "_auto_trading_backtest_args", False):
        return
    parser._auto_trading_backtest_args = True  # type: ignore[attr-defined]
    parser.add_argument("--csv", required=required_paths, help="Local OHLCV CSV fixture path")
    parser.add_argument("--output-dir", required=required_paths, help="Local directory for generated reports")
    parser.add_argument("--strategy", choices=("moving-average", "momentum"), default="moving-average")
    parser.add_argument("--symbol", default="fixture")
    parser.add_argument("--market", default="offline-fixture")
    parser.add_argument("--initial-cash", type=float, default=10_000.0)
    parser.add_argument("--commission", type=float, default=0.0)
    parser.add_argument("--slippage", type=float, default=0.0)
    parser.add_argument("--short-window", type=int, default=5)
    parser.add_argument("--long-window", type=int, default=20)
    parser.add_argument("--lookback", type=int, default=10)
    parser.add_argument("--train-fraction", type=float, default=0.7)
    parser.add_argument("--max-drawdown-limit", type=float, default=-0.20)
    parser.add_argument("--min-trades", type=int, default=5)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command not in (None, "backtest"):
        parser.error(f"unsupported command: {args.command}")
    if args.command is None and (not args.csv or not args.output_dir):
        parser.error("--csv and --output-dir are required unless using a subcommand")
    report_paths = run_backtest_cli(args)
    print(f"{SAFETY_STATEMENT}")
    print(f"Wrote markdown report: {report_paths['markdown']}")
    print(f"Wrote JSON report: {report_paths['json']}")
    return 0


def run_backtest_cli(args: argparse.Namespace) -> dict[str, Path]:
    csv_path = Path(args.csv)
    output_dir = Path(args.output_dir)
    bars = _load_bars(csv_path)
    if len(bars) < 2:
        raise SystemExit("at least two bars are required for next-bar execution")

    signals = _signals(args.strategy, bars, args)
    result = _run_local_backtest(
        bars,
        signals,
        initial_cash=args.initial_cash,
        commission=args.commission,
        slippage=args.slippage,
    )
    metrics = _calculate_metrics(result["equity_curve"], result["trades"], initial_cash=args.initial_cash)
    benchmark_metrics = _benchmark_metrics(bars, args.initial_cash)
    metrics["costs_included"] = True
    metrics["trade_count"] = len(result["trades"])

    split = train_test_split_window(bars, args.train_fraction).to_dict()
    flags = evaluate_disqualification(
        metrics,
        benchmark_metrics=benchmark_metrics,
        rules=DisqualificationRules(
            max_drawdown_limit=args.max_drawdown_limit,
            min_trades=args.min_trades,
        ),
    )
    report = ReportInputs(
        strategy=args.strategy,
        market=args.market,
        symbol=args.symbol,
        data_period=f"{bars[0].timestamp} to {bars[-1].timestamp}",
        assumptions={
            "initial_cash": args.initial_cash,
            "commission": args.commission,
            "slippage": args.slippage,
            "execution": "signals execute at next bar open",
            "positioning": "long-only cash-only local simulation",
            "data_source": str(csv_path),
        },
        metrics=metrics,
        benchmark_metrics=benchmark_metrics,
        validation={"train_test_split": split, "rows": len(bars)},
        disqualification_flags=flags,
        warnings=result["warnings"],
    )
    return write_report_bundle(report, output_dir, stem=f"{args.strategy}-report")


def _load_bars(path: Path) -> list[_CliBar]:
    if not path.exists():
        raise SystemExit(f"CSV fixture does not exist: {path}")
    rows: list[_CliBar] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp", "open", "high", "low", "close"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"CSV missing required columns: {', '.join(sorted(missing))}")
        for raw in reader:
            try:
                bar = _CliBar(
                    timestamp=str(raw["timestamp"]),
                    open=float(raw["open"]),
                    high=float(raw["high"]),
                    low=float(raw["low"]),
                    close=float(raw["close"]),
                    volume=float(raw.get("volume") or 0.0),
                )
            except (TypeError, ValueError) as exc:
                raise SystemExit(f"malformed CSV row: {raw}") from exc
            if min(bar.open, bar.high, bar.low, bar.close) <= 0 or bar.volume < 0:
                raise SystemExit(f"invalid OHLCV values at {bar.timestamp}")
            rows.append(bar)
    _validate_sorted_unique(rows)
    return rows


def _validate_sorted_unique(bars: Sequence[_CliBar]) -> None:
    previous: str | None = None
    seen: set[str] = set()
    for bar in bars:
        if bar.timestamp in seen:
            raise SystemExit(f"duplicate timestamp: {bar.timestamp}")
        if previous is not None and bar.timestamp <= previous:
            raise SystemExit("CSV timestamps must be strictly increasing")
        seen.add(bar.timestamp)
        previous = bar.timestamp


def _signals(strategy: str, bars: Sequence[_CliBar], args: argparse.Namespace) -> list[int]:
    if strategy == "moving-average":
        return _moving_average_signals(bars, args.short_window, args.long_window)
    return _momentum_signals(bars, args.lookback)


def _moving_average_signals(bars: Sequence[_CliBar], short_window: int, long_window: int) -> list[int]:
    if short_window < 1 or long_window <= short_window:
        raise SystemExit("moving-average requires 1 <= short_window < long_window")
    signals = [0] * len(bars)
    closes = [bar.close for bar in bars]
    previous_state = 0
    for idx in range(long_window - 1, len(bars)):
        short_avg = sum(closes[idx - short_window + 1 : idx + 1]) / short_window
        long_avg = sum(closes[idx - long_window + 1 : idx + 1]) / long_window
        state = 1 if short_avg > long_avg else 0
        if state != previous_state:
            signals[idx] = 1 if state else -1
        previous_state = state
    return signals


def _momentum_signals(bars: Sequence[_CliBar], lookback: int) -> list[int]:
    if lookback < 1:
        raise SystemExit("momentum lookback must be positive")
    signals = [0] * len(bars)
    in_position = False
    for idx in range(lookback, len(bars)):
        positive = bars[idx].close > bars[idx - lookback].close
        if positive and not in_position:
            signals[idx] = 1
            in_position = True
        elif not positive and in_position:
            signals[idx] = -1
            in_position = False
    return signals


def _run_local_backtest(
    bars: Sequence[_CliBar],
    signals: Sequence[int],
    *,
    initial_cash: float,
    commission: float,
    slippage: float,
) -> dict[str, Any]:
    cash = initial_cash
    shares = 0
    trades: list[dict[str, Any]] = []
    equity_curve: list[float] = [initial_cash]
    warnings: list[str] = []

    for signal_index, signal in enumerate(signals[:-1]):
        execution_bar = bars[signal_index + 1]
        if signal > 0 and shares == 0:
            execution_price = execution_bar.open * (1 + slippage)
            affordable = int((cash - commission) // execution_price)
            if affordable <= 0:
                warnings.append(f"buy signal at {bars[signal_index].timestamp} skipped: insufficient cash")
            else:
                cost = affordable * execution_price + commission
                cash -= cost
                shares += affordable
                trades.append(
                    {
                        "side": "buy",
                        "signal_timestamp": bars[signal_index].timestamp,
                        "execution_timestamp": execution_bar.timestamp,
                        "price": execution_price,
                        "quantity": affordable,
                        "commission": commission,
                    }
                )
        elif signal < 0 and shares > 0:
            execution_price = execution_bar.open * (1 - slippage)
            proceeds = shares * execution_price - commission
            trades.append(
                {
                    "side": "sell",
                    "signal_timestamp": bars[signal_index].timestamp,
                    "execution_timestamp": execution_bar.timestamp,
                    "price": execution_price,
                    "quantity": shares,
                    "commission": commission,
                }
            )
            cash += proceeds
            shares = 0
        equity_curve.append(cash + shares * execution_bar.close)

    if shares > 0:
        final_bar = bars[-1]
        final_price = final_bar.close * (1 - slippage)
        cash += shares * final_price - commission
        trades.append(
            {
                "side": "sell",
                "signal_timestamp": final_bar.timestamp,
                "execution_timestamp": final_bar.timestamp,
                "price": final_price,
                "quantity": shares,
                "commission": commission,
                "reason": "end_of_data_flatten",
            }
        )
        shares = 0
        equity_curve[-1] = cash

    return {"cash": cash, "trades": trades, "equity_curve": equity_curve, "warnings": warnings}


def _calculate_metrics(equity_curve: Sequence[float], trades: Sequence[dict[str, Any]], *, initial_cash: float) -> dict[str, Any]:
    final_equity = equity_curve[-1]
    returns = [equity_curve[i] / equity_curve[i - 1] - 1 for i in range(1, len(equity_curve)) if equity_curve[i - 1]]
    total_return = final_equity / initial_cash - 1 if initial_cash else 0.0
    volatility = _sample_std(returns) * math.sqrt(252) if len(returns) > 1 else 0.0
    avg_return = sum(returns) / len(returns) if returns else 0.0
    sharpe = (avg_return / _sample_std(returns) * math.sqrt(252)) if len(returns) > 1 and _sample_std(returns) else 0.0
    wins = _winning_round_trips(trades)
    round_trips = max(1, len([t for t in trades if t.get("side") == "sell"]))
    return {
        "initial_equity": initial_cash,
        "final_equity": final_equity,
        "total_return": total_return,
        "volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": _max_drawdown(equity_curve),
        "win_rate": wins / round_trips,
        "turnover": len(trades) / max(1, len(equity_curve)),
    }


def _benchmark_metrics(bars: Sequence[_CliBar], initial_cash: float) -> dict[str, Any]:
    shares = int(initial_cash // bars[0].open)
    cash = initial_cash - shares * bars[0].open
    final_equity = cash + shares * bars[-1].close
    return {"strategy": "buy_and_hold", "total_return": final_equity / initial_cash - 1 if initial_cash else 0.0}


def _max_drawdown(equity_curve: Sequence[float]) -> float:
    peak = equity_curve[0]
    worst = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak:
            worst = min(worst, equity / peak - 1)
    return worst


def _sample_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _winning_round_trips(trades: Sequence[dict[str, Any]]) -> int:
    wins = 0
    open_trade: dict[str, Any] | None = None
    for trade in trades:
        if trade.get("side") == "buy":
            open_trade = trade
        elif trade.get("side") == "sell" and open_trade:
            if float(trade["price"]) > float(open_trade["price"]):
                wins += 1
            open_trade = None
    return wins


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
