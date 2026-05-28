"""Command line entrypoints for local/offline MVP validation runs."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from auto_trading_bot.backtest import run_backtest
from auto_trading_bot.data import DataValidationError, load_csv_bars
from auto_trading_bot.domain import BacktestConfig, BacktestResult, Bar
from auto_trading_bot.reports import SAFETY_STATEMENT, ReportInputs, write_report_bundle
from auto_trading_bot.strategies import MomentumStrategy, MovingAverageCrossoverStrategy, Strategy
from auto_trading_bot.validation import (
    DisqualificationRules,
    evaluate_disqualification,
    train_test_split_window,
)


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
    parser.add_argument(
        "--output-dir",
        required=required_paths,
        help="Local directory for generated reports",
    )
    parser.add_argument(
        "--strategy",
        choices=("moving-average", "momentum"),
        default="moving-average",
    )
    parser.add_argument("--symbol", default="fixture")
    parser.add_argument("--market", default="offline-fixture")
    parser.add_argument("--initial-cash", type=float, default=10_000.0)
    parser.add_argument(
        "--commission-rate",
        type=float,
        default=0.001,
        help="Per-trade commission rate, e.g. 0.001 for 0.1%%.",
    )
    parser.add_argument(
        "--slippage-bps",
        type=float,
        default=5.0,
        help="Per-trade slippage in basis points.",
    )
    parser.add_argument("--short-window", type=int, default=5)
    parser.add_argument("--long-window", type=int, default=20)
    parser.add_argument("--lookback", type=int, default=10)
    parser.add_argument("--train-fraction", type=float, default=0.7)
    parser.add_argument("--validation-mode", choices=("holdout", "none"), default="holdout")
    parser.add_argument("--max-drawdown-limit", type=float, default=-0.20)
    parser.add_argument("--min-trades", type=int, default=5)
    parser.add_argument("--min-trade-quantity", type=int, default=1)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command not in (None, "backtest"):
        parser.error(f"unsupported command: {args.command}")
    if args.command is None and (not args.csv or not args.output_dir):
        parser.error("--csv and --output-dir are required unless using a subcommand")
    try:
        report_paths = run_backtest_cli(args)
    except (DataValidationError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(SAFETY_STATEMENT)
    print(f"Wrote markdown report: {report_paths['markdown']}")
    print(f"Wrote JSON report: {report_paths['json']}")
    return 0


def run_backtest_cli(args: argparse.Namespace) -> dict[str, Path]:
    csv_path = Path(args.csv)
    output_dir = Path(args.output_dir)
    bars = load_csv_bars(csv_path)
    if len(bars) < 2:
        raise SystemExit("at least two bars are required for next-bar execution")

    config = BacktestConfig(
        initial_cash=args.initial_cash,
        commission_rate=args.commission_rate,
        slippage_bps=args.slippage_bps,
        min_trade_quantity=args.min_trade_quantity,
    )

    if args.validation_mode == "holdout":
        report = _build_holdout_report(args, bars, config, csv_path)
    else:
        result = run_backtest(bars, _build_strategy(args), config)
        report = _report_from_result(
            args,
            csv_path=csv_path,
            result=result,
            metrics_label="full_period_not_validation",
            validation={
                "mode": "none",
                "headline_metrics": "full_period_not_validation",
                "warning": "No train/test split was requested; do not treat this as validation.",
                "rows": len(bars),
            },
        )
    return write_report_bundle(report, output_dir, stem=f"{args.strategy}-report")


def _build_strategy(args: argparse.Namespace) -> Strategy:
    if args.strategy == "moving-average":
        return MovingAverageCrossoverStrategy(
            short_window=args.short_window,
            long_window=args.long_window,
        )
    return MomentumStrategy(lookback=args.lookback)


def _build_holdout_report(
    args: argparse.Namespace,
    bars: tuple[Bar, ...],
    config: BacktestConfig,
    csv_path: Path,
) -> ReportInputs:
    window = train_test_split_window(
        bars,
        args.train_fraction,
        min_train_size=1,
        min_test_size=2,
    )
    train_bars = bars[window.train_slice]
    test_bars = bars[window.test_slice]
    # Build separate strategy instances so future mutable strategies cannot leak
    # train-run state into the out-of-sample test run.
    train_result = run_backtest(train_bars, _build_strategy(args), config)
    test_result = run_backtest(test_bars, _build_strategy(args), config)

    validation: dict[str, Any] = {
        "mode": "holdout",
        "headline_metrics": "out_of_sample_test",
        "train_test_split": window.to_dict(),
        "rows": len(bars),
        "train_rows": len(train_bars),
        "test_rows": len(test_bars),
        "train_metrics": dict(train_result.metrics),
        "test_metrics": dict(test_result.metrics),
        "strategy_selection": (
            "Strategy parameters are supplied before the split; train metrics are "
            "diagnostic only and report headline metrics use the test slice."
        ),
    }
    return _report_from_result(
        args,
        csv_path=csv_path,
        result=test_result,
        metrics_label="out_of_sample_test",
        validation=validation,
    )


def _report_from_result(
    args: argparse.Namespace,
    *,
    csv_path: Path,
    result: BacktestResult,
    metrics_label: str,
    validation: dict[str, Any],
) -> ReportInputs:
    metrics: dict[str, Any] = dict(result.metrics)
    metrics["costs_included"] = True
    metrics["metrics_label"] = metrics_label
    flags = evaluate_disqualification(
        metrics,
        benchmark_metrics=result.benchmark_metrics,
        rules=DisqualificationRules(
            max_drawdown_limit=args.max_drawdown_limit,
            min_trades=args.min_trades,
        ),
    )
    return ReportInputs(
        strategy=result.strategy_name,
        market=args.market,
        symbol=args.symbol,
        data_period=(
            f"{result.bars[0].timestamp.isoformat()} "
            f"to {result.bars[-1].timestamp.isoformat()}"
        ),
        assumptions={
            "initial_cash": args.initial_cash,
            "commission_rate": args.commission_rate,
            "slippage_bps": args.slippage_bps,
            "min_trade_quantity": args.min_trade_quantity,
            "execution": "signals execute at next bar open",
            "positioning": "long-only cash-only local simulation",
            "data_source": str(csv_path),
            "engine": "auto_trading_bot.backtest.run_backtest",
            "metrics_label": metrics_label,
        },
        metrics=metrics,
        benchmark_metrics=result.benchmark_metrics,
        validation=validation,
        disqualification_flags=tuple(flags),
        warnings=list(result.warnings),
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
