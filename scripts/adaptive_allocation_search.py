"""Offline adaptive QQQ/GLD policy search.

This is an offline policy-search / contextual-bandit style experiment, not live
trading and not investment advice. It learns simple state-conditioned target
weights on each training window and evaluates the chosen policy only on future
out-of-sample windows.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from statistics import fmean, median
from typing import Any

from auto_trading_bot.domain import Bar, EquityPoint
from auto_trading_bot.metrics import max_drawdown, periodic_returns, sharpe_ratio, sortino_ratio
from auto_trading_bot.validation import train_test_split_window, walk_forward_windows

try:
    from scripts.strategy_optimization import fetch_or_load_bars
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from strategy_optimization import fetch_or_load_bars

TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class AdaptivePolicy:
    name: str
    sma_window: int
    momentum_window: int
    momentum_threshold: float
    risk_on_qqq_weight: float
    risk_off_qqq_weight: float
    rebalance_days: int

    @property
    def params(self) -> dict[str, float | int]:
        return {
            "sma_window": self.sma_window,
            "momentum_window": self.momentum_window,
            "momentum_threshold": self.momentum_threshold,
            "risk_on_qqq_weight": self.risk_on_qqq_weight,
            "risk_off_qqq_weight": self.risk_off_qqq_weight,
            "rebalance_days": self.rebalance_days,
        }


@dataclass(frozen=True)
class PolicyEvaluation:
    window: str
    phase: str
    policy: str
    start: str
    end: str
    candidate_return: float
    benchmark_return: float
    excess_return: float
    candidate_max_drawdown: float
    benchmark_max_drawdown: float
    sharpe: float | None
    sortino: float | None
    rebalances: int


@dataclass(frozen=True)
class SearchSummary:
    status: str
    median_excess: float
    mean_excess: float
    min_holdout_excess: float
    worst_max_drawdown: float
    median_candidate_return: float
    median_benchmark_return: float
    selected_policy_count: int
    failure_reasons: tuple[str, ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline adaptive QQQ/GLD policy search.")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--data-dir", default="data/external")
    parser.add_argument("--output", default=".omx/reports/adaptive-allocation-search-latest.json")
    parser.add_argument("--markdown", default=".omx/reports/adaptive-allocation-search-latest.md")
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
    summary = report["summary"]
    print(
        "adaptive_search status={status} median_excess={median_excess:.2%} "
        "worst_mdd={worst_max_drawdown:.2%}".format(**summary)
    )
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0 if summary["status"] == "pass" else 1


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    symbols = ("SPY", "QQQ", "DIA", "GLD")
    data, metadata = load_or_fetch_symbols(args, symbols)
    dates, aligned = align_by_date(data)
    windows = build_windows(dates)
    policies = build_policy_grid()
    evaluations: list[PolicyEvaluation] = []
    chosen_policies: list[AdaptivePolicy] = []

    for label, train_start, train_end, test_start, test_end in windows:
        chosen = choose_policy_on_train(
            policies=policies,
            dates=dates,
            data=aligned,
            start=train_start,
            end=train_end,
        )
        chosen_policies.append(chosen)
        evaluations.append(
            evaluate_policy(
                label=label,
                phase="train_selected_oos_test",
                policy=chosen,
                dates=dates,
                data=aligned,
                start=test_start,
                end=test_end,
            )
        )

    static_policy = AdaptivePolicy(
        name="static_qqq_0.36_gld_0.64",
        sma_window=200,
        momentum_window=180,
        momentum_threshold=0.0,
        risk_on_qqq_weight=0.36,
        risk_off_qqq_weight=0.36,
        rebalance_days=21,
    )
    static_evaluations = [
        evaluate_policy(
            label=label,
            phase="static_baseline_oos_test",
            policy=static_policy,
            dates=dates,
            data=aligned,
            start=test_start,
            end=test_end,
        )
        for label, _train_start, _train_end, test_start, test_end in windows
    ]
    summary = summarize_evaluations(evaluations)
    static_summary = summarize_evaluations(static_evaluations)
    return {
        "status": summary.status,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": "offline research only; no orders, no broker, no investment advice",
        "data": metadata,
        "summary": asdict(summary),
        "static_baseline_summary": asdict(static_summary),
        "selected_policy_frequency": selected_policy_frequency(chosen_policies),
        "evaluations": [asdict(row) for row in evaluations],
        "static_baseline_evaluations": [asdict(row) for row in static_evaluations],
        "policy_grid_size": len(policies),
        "next_gate": (
            "Only consider paper dry-run if adaptive policy beats or matches static baseline "
            "without worse drawdown, and then replicate with independent data."
        ),
    }


def load_or_fetch_symbols(
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
        if bars is None:
            raise SystemExit(f"missing bars for {symbol}: {meta.get('error')}")
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


def build_windows(dates: tuple[date, ...]) -> tuple[tuple[str, int, int, int, int], ...]:
    holdout = train_test_split_window(
        dates, 0.7, min_train_size=TRADING_DAYS_PER_YEAR * 3, min_test_size=252
    )
    windows = [
        (
            "holdout_70_30",
            holdout.train_start,
            holdout.train_end,
            holdout.test_start,
            holdout.test_end,
        )
    ]
    for window in walk_forward_windows(
        dates,
        train_size=TRADING_DAYS_PER_YEAR * 3,
        test_size=TRADING_DAYS_PER_YEAR,
        step_size=TRADING_DAYS_PER_YEAR,
    ):
        windows.append(
            (window.label, window.train_start, window.train_end, window.test_start, window.test_end)
        )
    return tuple(windows)


def build_policy_grid() -> tuple[AdaptivePolicy, ...]:
    policies: list[AdaptivePolicy] = []
    for sma in (150, 200):
        for momentum_window in (90, 180, 252):
            for threshold in (0.0, 0.03):
                for risk_on in (0.55, 0.65, 0.75):
                    for risk_off in (0.20, 0.30, 0.36):
                        if risk_off >= risk_on:
                            continue
                        for rebalance_days in (21, 63):
                            policies.append(
                                AdaptivePolicy(
                                    name=(
                                        f"adaptive_sma{sma}_mom{momentum_window}_th{threshold:g}_"
                                        f"on{risk_on:g}_off{risk_off:g}_r{rebalance_days}"
                                    ),
                                    sma_window=sma,
                                    momentum_window=momentum_window,
                                    momentum_threshold=threshold,
                                    risk_on_qqq_weight=risk_on,
                                    risk_off_qqq_weight=risk_off,
                                    rebalance_days=rebalance_days,
                                )
                            )
    return tuple(policies)


def choose_policy_on_train(
    *,
    policies: Sequence[AdaptivePolicy],
    dates: tuple[date, ...],
    data: dict[str, tuple[Bar, ...]],
    start: int,
    end: int,
) -> AdaptivePolicy:
    scored: list[tuple[float, AdaptivePolicy]] = []
    for policy in policies:
        evaluation = evaluate_policy(
            label="train",
            phase="train_selection",
            policy=policy,
            dates=dates,
            data=data,
            start=start,
            end=end,
        )
        drawdown_penalty = max(0.0, abs(evaluation.candidate_max_drawdown) - 0.20)
        turnover_penalty = max(0, evaluation.rebalances - 48) * 0.0005
        score = evaluation.excess_return - drawdown_penalty - turnover_penalty
        scored.append((score, policy))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def evaluate_policy(
    *,
    label: str,
    phase: str,
    policy: AdaptivePolicy,
    dates: tuple[date, ...],
    data: dict[str, tuple[Bar, ...]],
    start: int,
    end: int,
) -> PolicyEvaluation:
    candidate_curve, rebalances = adaptive_curve(policy, dates, data, start, end)
    benchmark_curve = benchmark_curve_equal_weight(dates, data, start, end)
    candidate_return = total_return(candidate_curve)
    benchmark_return = total_return(benchmark_curve)
    returns = periodic_returns(candidate_curve)
    return PolicyEvaluation(
        window=label,
        phase=phase,
        policy=policy.name,
        start=dates[start].isoformat(),
        end=dates[end - 1].isoformat(),
        candidate_return=candidate_return,
        benchmark_return=benchmark_return,
        excess_return=candidate_return - benchmark_return,
        candidate_max_drawdown=max_drawdown(candidate_curve),
        benchmark_max_drawdown=max_drawdown(benchmark_curve),
        sharpe=sharpe_ratio(returns),
        sortino=sortino_ratio(returns),
        rebalances=rebalances,
    )


def adaptive_curve(
    policy: AdaptivePolicy,
    dates: tuple[date, ...],
    data: dict[str, tuple[Bar, ...]],
    start: int,
    end: int,
) -> tuple[tuple[EquityPoint, ...], int]:
    cash = 10_000.0
    positions = {"QQQ": 0, "GLD": 0}
    last_weight: float | None = None
    rebalances = 0
    curve: list[EquityPoint] = []
    qqq_closes = [bar.close for bar in data["QQQ"]]
    warmup = max(policy.sma_window, policy.momentum_window)
    for index in range(start, end):
        if index == start or (index - start) % policy.rebalance_days == 0:
            target_qqq = target_weight(policy, qqq_closes, index, warmup)
            if target_qqq != last_weight:
                cash = liquidate(cash, positions, data, index)
                positions = buy_targets(cash, target_qqq, data, index)
                cash -= invested_cash(positions, target_qqq, data, index)
                last_weight = target_qqq
                rebalances += 1
        equity = cash + sum(positions[symbol] * data[symbol][index].close for symbol in positions)
        curve.append(
            EquityPoint(
                timestamp=datetime.combine(dates[index], time()),
                cash=cash,
                position=sum(positions.values()),
                close_price=1.0,
                equity=equity,
            )
        )
    return tuple(curve), rebalances


def target_weight(
    policy: AdaptivePolicy, qqq_closes: Sequence[float], index: int, warmup: int
) -> float:
    if index <= warmup:
        return policy.risk_off_qqq_weight
    average = fmean(qqq_closes[index - policy.sma_window : index])
    momentum = (qqq_closes[index - 1] / qqq_closes[index - 1 - policy.momentum_window]) - 1.0
    risk_on = qqq_closes[index - 1] > average and momentum > policy.momentum_threshold
    return policy.risk_on_qqq_weight if risk_on else policy.risk_off_qqq_weight


def liquidate(
    cash: float, positions: dict[str, int], data: dict[str, tuple[Bar, ...]], index: int
) -> float:
    for symbol, quantity in positions.items():
        if quantity:
            cash += quantity * data[symbol][index].open
    return cash


def buy_targets(
    cash: float, qqq_weight: float, data: dict[str, tuple[Bar, ...]], index: int
) -> dict[str, int]:
    weights = {"QQQ": qqq_weight, "GLD": 1.0 - qqq_weight}
    return {
        symbol: int((cash * weight) / data[symbol][index].open)
        for symbol, weight in weights.items()
        if weight > 0
    }


def invested_cash(
    positions: dict[str, int], qqq_weight: float, data: dict[str, tuple[Bar, ...]], index: int
) -> float:
    del qqq_weight
    return sum(quantity * data[symbol][index].open for symbol, quantity in positions.items())


def benchmark_curve_equal_weight(
    dates: tuple[date, ...],
    data: dict[str, tuple[Bar, ...]],
    start: int,
    end: int,
) -> tuple[EquityPoint, ...]:
    cash = 0.0
    allocation = 10_000.0 / 3
    positions: dict[str, int] = {}
    for symbol in ("SPY", "QQQ", "DIA"):
        quantity = int(allocation / data[symbol][start].open)
        positions[symbol] = quantity
        cash += allocation - quantity * data[symbol][start].open
    return tuple(
        EquityPoint(
            timestamp=datetime.combine(dates[index], time()),
            cash=cash,
            position=sum(positions.values()),
            close_price=1.0,
            equity=cash
            + sum(positions[symbol] * data[symbol][index].close for symbol in positions),
        )
        for index in range(start, end)
    )


def total_return(curve: tuple[EquityPoint, ...]) -> float:
    return (curve[-1].equity / curve[0].equity) - 1.0


def summarize_evaluations(rows: Sequence[PolicyEvaluation]) -> SearchSummary:
    excesses = [row.excess_return for row in rows]
    candidate_returns = [row.candidate_return for row in rows]
    benchmark_returns = [row.benchmark_return for row in rows]
    holdout_excesses = [row.excess_return for row in rows if row.window == "holdout_70_30"]
    worst_drawdown = min(row.candidate_max_drawdown for row in rows)
    median_excess = median(excesses)
    mean_excess = fmean(excesses)
    min_holdout_excess = min(holdout_excesses) if holdout_excesses else min(excesses)
    failure_reasons: list[str] = []
    if median_excess <= 0:
        failure_reasons.append("median_excess_not_positive")
    if min_holdout_excess < -0.05:
        failure_reasons.append("holdout_excess_below_minus_5pp")
    if worst_drawdown < -0.20:
        failure_reasons.append("max_drawdown_worse_than_minus_20pct")
    if median(candidate_returns) <= 0:
        failure_reasons.append("median_candidate_return_not_positive")
    return SearchSummary(
        status="pass" if not failure_reasons else "review",
        median_excess=median_excess,
        mean_excess=mean_excess,
        min_holdout_excess=min_holdout_excess,
        worst_max_drawdown=worst_drawdown,
        median_candidate_return=median(candidate_returns),
        median_benchmark_return=median(benchmark_returns),
        selected_policy_count=len({row.policy for row in rows}),
        failure_reasons=tuple(failure_reasons),
    )


def selected_policy_frequency(policies: Sequence[AdaptivePolicy]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for policy in policies:
        counts[policy.name] = counts.get(policy.name, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    static = report["static_baseline_summary"]
    lines = [
        "# Adaptive allocation search report",
        "",
        f"Status: **{summary['status'].upper()}**",
        "",
        "Safety: offline policy-search research only; no orders, no broker, no investment advice.",
        "",
        "## Summary",
        "",
        "| Model | Median excess | Mean excess | Holdout min excess | "
        "Worst MDD | Median return | Median benchmark |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        summary_row("adaptive_train_selected", summary),
        summary_row("static_36_64_baseline", static),
        "",
        "## Selected policy frequency",
        "",
    ]
    for name, count in report["selected_policy_frequency"].items():
        lines.append(f"- `{name}`: {count}")
    lines.extend(
        [
            "",
            "## OOS evaluations",
            "",
            "| Window | Policy | Candidate | Benchmark | Excess | MDD | Rebalances |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["evaluations"]:
        lines.append(
            (
                "| {window} | `{policy}` | {candidate} | {benchmark} | "
                "{excess} | {mdd} | {rebalance} |"
            ).format(
                window=row["window"],
                policy=row["policy"],
                candidate=percent(row["candidate_return"]),
                benchmark=percent(row["benchmark_return"]),
                excess=percent(row["excess_return"]),
                mdd=percent(row["candidate_max_drawdown"]),
                rebalance=row["rebalances"],
            )
        )
    lines.extend(
        [
            "",
            "## Next gate",
            "",
            f"- {report['next_gate']}",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def summary_row(name: str, summary: dict[str, Any]) -> str:
    return (
        f"| {name} | {percent(summary['median_excess'])} | "
        f"{percent(summary['mean_excess'])} | {percent(summary['min_holdout_excess'])} | "
        f"{percent(summary['worst_max_drawdown'])} | "
        f"{percent(summary['median_candidate_return'])} | "
        f"{percent(summary['median_benchmark_return'])} |"
    )


def percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


if __name__ == "__main__":
    raise SystemExit(main())
