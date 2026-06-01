"""Append dry-run observations for a paper-only strategy candidate.

The observation log is a local research artifact. It never connects to a broker,
never reads credentials, and never creates orders.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from auto_trading_bot.domain import EquityPoint
from auto_trading_bot.metrics import max_drawdown


@dataclass(frozen=True)
class ObservationResult:
    observation: dict[str, Any]
    summary: dict[str, Any]
    appended: bool


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append a paper-only observation log entry.")
    parser.add_argument("--signal", default="reports/paper-dry-run-signal-latest.json")
    parser.add_argument("--log", default="reports/paper-observation-log.jsonl")
    parser.add_argument("--summary", default=".omx/reports/paper-observation-summary-latest.json")
    parser.add_argument("--markdown", default=".omx/reports/paper-observation-summary-latest.md")
    parser.add_argument("--initial-equity", type=float, default=10_000.0)
    parser.add_argument("--required-days", type=int, default=22)
    parser.add_argument("--early-checkpoint-days", type=int, default=5)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    signal = read_json(Path(args.signal))
    result = append_observation(
        signal=signal,
        log_path=Path(args.log),
        initial_equity=args.initial_equity,
        required_days=args.required_days,
        early_checkpoint_days=args.early_checkpoint_days,
    )
    summary_path = Path(args.summary)
    markdown_path = Path(args.markdown)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(result.summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_markdown(markdown_path, result.summary)
    action = "appended" if result.appended else "updated_existing_date"
    status_line = (
        "paper observation {action} as_of={as_of} days={days}/{required} equity={equity:.2f}"
    )
    print(
        status_line.format(
            action=action,
            as_of=result.observation["as_of_date"],
            days=result.summary["observed_days"],
            required=result.summary["required_days"],
            equity=result.observation["virtual_equity"],
        )
    )
    print(f"log={args.log}")
    print(f"summary={summary_path}")
    print(f"markdown={markdown_path}")
    return 0


def append_observation(
    *,
    signal: Mapping[str, Any],
    log_path: Path,
    initial_equity: float,
    required_days: int,
    early_checkpoint_days: int,
) -> ObservationResult:
    if initial_equity <= 0:
        raise SystemExit("initial equity must be positive")
    if required_days <= 0 or early_checkpoint_days <= 0:
        raise SystemExit("observation day thresholds must be positive")
    observations = read_jsonl(log_path)
    observation = build_observation(signal, observations, initial_equity)
    same_date = [row for row in observations if row.get("as_of_date") == observation["as_of_date"]]
    remaining = [row for row in observations if row.get("as_of_date") != observation["as_of_date"]]
    updated = sorted([*remaining, observation], key=lambda row: str(row["as_of_date"]))
    write_jsonl(log_path, updated)
    summary = build_summary(
        updated,
        required_days=required_days,
        early_checkpoint_days=early_checkpoint_days,
        log_path=log_path,
    )
    return ObservationResult(observation=observation, summary=summary, appended=not same_date)


def build_observation(
    signal: Mapping[str, Any], observations: Sequence[Mapping[str, Any]], initial_equity: float
) -> dict[str, Any]:
    as_of = str(signal.get("as_of_date") or "")
    date.fromisoformat(as_of)
    weights = normalized_weights(signal.get("target_weights"))
    prices = close_prices(signal.get("source_bars"))
    missing_prices = sorted(set(weights) - set(prices))
    if missing_prices:
        raise SystemExit(f"missing close prices for: {', '.join(missing_prices)}")
    previous = latest_observation_before(observations, as_of)
    previous_equity = float(previous["virtual_equity"]) if previous else initial_equity
    daily_return = 0.0 if previous is None else weighted_return(previous, prices)
    virtual_equity = previous_equity * (1.0 + daily_return)
    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "as_of_date": as_of,
        "strategy": signal.get("strategy"),
        "target_weights": weights,
        "close_prices": {symbol: prices[symbol] for symbol in sorted(weights)},
        "daily_return": daily_return,
        "virtual_equity": virtual_equity,
        "warnings": tuple(build_observation_warnings(signal, previous)),
        "safety": "paper observation only; no orders; no broker; no credentials; no advice",
    }


def weighted_return(previous: Mapping[str, Any], current_prices: Mapping[str, float]) -> float:
    previous_weights = normalized_weights(previous.get("target_weights"))
    previous_prices = close_prices(previous.get("close_prices"))
    returns = []
    for symbol, weight in previous_weights.items():
        if symbol not in current_prices or symbol not in previous_prices:
            raise SystemExit(f"missing price continuity for {symbol}")
        returns.append(weight * ((current_prices[symbol] / previous_prices[symbol]) - 1.0))
    return sum(returns)


def normalized_weights(raw: Any) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        raise SystemExit("target weights must be a mapping")
    weights = {str(symbol).upper(): float(weight) for symbol, weight in raw.items()}
    if any(weight < 0 for weight in weights.values()):
        raise SystemExit("target weights must be nonnegative")
    total = sum(weights.values())
    if total <= 0:
        raise SystemExit("target weights must include a positive weight")
    return {symbol: weight / total for symbol, weight in sorted(weights.items()) if weight > 0}


def close_prices(raw: Any) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        raise SystemExit("source bars or close prices must be a mapping")
    prices: dict[str, float] = {}
    for symbol, payload in raw.items():
        value = payload.get("close") if isinstance(payload, Mapping) else payload
        close = float(value)
        if close <= 0:
            raise SystemExit(f"invalid close price for {symbol}")
        prices[str(symbol).upper()] = close
    return prices


def latest_observation_before(
    observations: Sequence[Mapping[str, Any]], as_of: str
) -> Mapping[str, Any] | None:
    previous = [row for row in observations if str(row.get("as_of_date", "")) < as_of]
    if not previous:
        return None
    return sorted(previous, key=lambda row: str(row["as_of_date"]))[-1]


def build_observation_warnings(
    signal: Mapping[str, Any], previous: Mapping[str, Any] | None
) -> list[str]:
    warnings = [
        "Paper observation only; do not place orders from this log.",
        "Live trading remains unauthorized until readiness blockers are closed.",
    ]
    if previous is None:
        warnings.append(
            "First observation initializes virtual equity; no realized performance yet."
        )
    signal_warnings = signal.get("warnings", [])
    if isinstance(signal_warnings, list | tuple):
        warnings.extend(str(item) for item in signal_warnings)
    return warnings


def build_summary(
    observations: Sequence[Mapping[str, Any]],
    *,
    required_days: int,
    early_checkpoint_days: int,
    log_path: Path,
) -> dict[str, Any]:
    if not observations:
        return {
            "status": "empty",
            "observed_days": 0,
            "required_days": required_days,
            "live_trading_authorized": False,
        }
    ordered = sorted(observations, key=lambda row: str(row["as_of_date"]))
    equities = [float(row["virtual_equity"]) for row in ordered]
    first_equity = equities[0]
    latest_equity = equities[-1]
    total_return = (latest_equity / first_equity) - 1.0 if first_equity > 0 else 0.0
    curve = tuple(
        EquityPoint(
            timestamp=datetime.fromisoformat(str(row["as_of_date"])),
            cash=0.0,
            position=0,
            close_price=1.0,
            equity=float(row["virtual_equity"]),
        )
        for row in ordered
    )
    observed_days = len(ordered)
    status = "collecting"
    if observed_days >= required_days:
        status = "observation_window_complete"
    elif observed_days >= early_checkpoint_days:
        status = "early_checkpoint_ready"
    return {
        "status": status,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "log_path": str(log_path),
        "observed_days": observed_days,
        "required_days": required_days,
        "early_checkpoint_days": early_checkpoint_days,
        "first_as_of_date": ordered[0]["as_of_date"],
        "latest_as_of_date": ordered[-1]["as_of_date"],
        "latest_strategy": ordered[-1].get("strategy"),
        "latest_target_weights": ordered[-1].get("target_weights"),
        "latest_virtual_equity": latest_equity,
        "total_return_since_first_observation": total_return,
        "max_drawdown_since_first_observation": max_drawdown(curve),
        "live_trading_authorized": False,
        "promotion_level": "paper_observation_collecting",
        "remaining_days_to_required_window": max(required_days - observed_days, 0),
        "warnings": [
            "This is not investment advice and does not authorize live trading.",
            "A short observation window cannot prove stable profitability.",
        ],
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
    )


def write_markdown(path: Path, summary: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total_return_pct = float(summary.get("total_return_since_first_observation", 0.0)) * 100
    max_drawdown_pct = float(summary.get("max_drawdown_since_first_observation", 0.0)) * 100
    lines = [
        "# Paper observation summary",
        "",
        "Safety: paper observation only; no orders, no broker, no credentials, no advice.",
        "",
        f"- Status: {summary['status']}",
        f"- Observed days: {summary['observed_days']} / {summary['required_days']}",
        f"- Latest date: {summary.get('latest_as_of_date')}",
        f"- Latest strategy: {summary.get('latest_strategy')}",
        f"- Latest virtual equity: {float(summary.get('latest_virtual_equity', 0.0)):.2f}",
        f"- Total return since first observation: {total_return_pct:.2f}%",
        f"- Max drawdown since first observation: {max_drawdown_pct:.2f}%",
        f"- Live trading authorized: {summary['live_trading_authorized']}",
        "",
        "## Warnings",
        "",
    ]
    for warning in summary.get("warnings", []):
        lines.append(f"- {warning}")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
