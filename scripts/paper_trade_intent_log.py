"""Append hypothetical paper trade intents without placing orders.

This script answers: "If this strategy were connected to a trading system, what
would it intend to do today?" It is still research-only. It creates no broker
orders, reads no credentials, and does not authorize trading.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.non_leveraged_universe_analysis import looks_leveraged
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from non_leveraged_universe_analysis import looks_leveraged  # type: ignore[no-redef]


@dataclass(frozen=True)
class IntentResult:
    intent: dict[str, Any]
    appended: bool


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append no-order hypothetical trade intents.")
    parser.add_argument("--signal", default="reports/paper-dry-run-signal-latest.json")
    parser.add_argument("--log", default="reports/paper-trade-intent-log.jsonl")
    parser.add_argument("--initial-equity", type=float, default=10_000.0)
    parser.add_argument("--rebalance-threshold", type=float, default=0.02)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = append_intent(
        signal=read_json(Path(args.signal)),
        log_path=Path(args.log),
        initial_equity=args.initial_equity,
        rebalance_threshold=args.rebalance_threshold,
    )
    action = "appended" if result.appended else "updated_existing_date"
    status_line = (
        "paper trade intent {action} as_of={as_of} decision={decision} notional={notional:.2f}"
    )
    print(
        status_line.format(
            action=action,
            as_of=result.intent["as_of_date"],
            decision=result.intent["decision"],
            notional=result.intent["total_hypothetical_trade_notional"],
        )
    )
    print(f"log={args.log}")
    return 0


def append_intent(
    *,
    signal: Mapping[str, Any],
    log_path: Path,
    initial_equity: float,
    rebalance_threshold: float,
) -> IntentResult:
    if initial_equity <= 0:
        raise SystemExit("initial equity must be positive")
    if rebalance_threshold < 0:
        raise SystemExit("rebalance threshold must be nonnegative")
    previous_intents = read_jsonl(log_path)
    intent = build_intent(
        signal=signal,
        previous_intents=previous_intents,
        initial_equity=initial_equity,
        rebalance_threshold=rebalance_threshold,
    )
    same_date = [row for row in previous_intents if row.get("as_of_date") == intent["as_of_date"]]
    remaining = [row for row in previous_intents if row.get("as_of_date") != intent["as_of_date"]]
    updated = sorted([*remaining, intent], key=lambda row: str(row["as_of_date"]))
    write_jsonl(log_path, updated)
    return IntentResult(intent=intent, appended=not same_date)


def build_intent(
    *,
    signal: Mapping[str, Any],
    previous_intents: Sequence[Mapping[str, Any]],
    initial_equity: float,
    rebalance_threshold: float,
) -> dict[str, Any]:
    as_of = str(signal.get("as_of_date") or "")
    date.fromisoformat(as_of)
    target_weights = normalized_weights(signal.get("target_weights"))
    blocked = [symbol for symbol in target_weights if looks_leveraged(symbol)]
    if blocked:
        raise SystemExit(f"leveraged/inverse symbols are blocked: {', '.join(blocked)}")
    prices = close_prices(signal.get("source_bars"))
    missing_prices = sorted(set(target_weights) - set(prices))
    if missing_prices:
        raise SystemExit(f"missing close prices for: {', '.join(missing_prices)}")
    previous = latest_intent_before(previous_intents, as_of)
    current_positions = positions_from_previous(previous, prices)
    current_equity = portfolio_equity(current_positions, prices, previous, initial_equity)
    current_weights = position_weights(current_positions, prices, current_equity)
    target_positions = target_share_positions(target_weights, prices, current_equity)
    trade_intents = build_trade_intents(current_positions, target_positions, prices)
    max_drift = max_weight_drift(target_weights, current_weights)
    should_rebalance = previous is None or max_drift >= rebalance_threshold
    decision = "would_rebalance" if should_rebalance else "would_hold"
    applied_positions = target_positions if should_rebalance else current_positions
    total_notional = sum(abs(row["notional"]) for row in trade_intents if should_rebalance)
    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "as_of_date": as_of,
        "strategy": signal.get("strategy"),
        "decision": decision,
        "target_weights": target_weights,
        "current_weights_before_intent": current_weights,
        "max_weight_drift": max_drift,
        "rebalance_threshold": rebalance_threshold,
        "reference_prices": {symbol: prices[symbol] for symbol in sorted(target_weights)},
        "hypothetical_positions_before_intent": current_positions,
        "hypothetical_positions_after_intent": applied_positions,
        "hypothetical_equity_after_intent": current_equity,
        "trade_intents": trade_intents if should_rebalance else [],
        "total_hypothetical_trade_notional": total_notional,
        "fill_assumption": (
            "research-only reference close; not executable; no order is created or routed"
        ),
        "safety": (
            "hypothetical paper trade intent only; no orders; no broker; no credentials; no advice"
        ),
        "warnings": [
            "This is not an order and must not be sent to a broker.",
            "Reference close prices are used for research accounting, not executable fill claims.",
        ],
    }


def build_trade_intents(
    current: Mapping[str, int], target: Mapping[str, int], prices: Mapping[str, float]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol in sorted(set(current) | set(target)):
        delta = int(target.get(symbol, 0)) - int(current.get(symbol, 0))
        if delta == 0:
            continue
        side = "would_buy" if delta > 0 else "would_sell"
        quantity = abs(delta)
        rows.append(
            {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "reference_price": prices[symbol],
                "notional": quantity * prices[symbol],
                "order_created": False,
            }
        )
    return rows


def target_share_positions(
    weights: Mapping[str, float], prices: Mapping[str, float], equity: float
) -> dict[str, int]:
    return {
        symbol: int((equity * weight) / prices[symbol])
        for symbol, weight in sorted(weights.items())
    }


def positions_from_previous(
    previous: Mapping[str, Any] | None, current_prices: Mapping[str, float]
) -> dict[str, int]:
    if previous is None:
        return {symbol: 0 for symbol in sorted(current_prices)}
    raw = previous.get("hypothetical_positions_after_intent", {})
    if not isinstance(raw, Mapping):
        raise SystemExit("previous intent positions are invalid")
    positions = {symbol: int(raw.get(symbol, 0)) for symbol in sorted(current_prices)}
    return positions


def portfolio_equity(
    positions: Mapping[str, int],
    prices: Mapping[str, float],
    previous: Mapping[str, Any] | None,
    initial_equity: float,
) -> float:
    if previous is None:
        return initial_equity
    previous_prices = close_prices(previous.get("reference_prices"))
    previous_positions = positions_from_previous(previous, previous_prices)
    previous_cash = implied_cash(previous, previous_positions, previous_prices, initial_equity)
    return previous_cash + sum(positions[symbol] * prices[symbol] for symbol in positions)


def implied_cash(
    previous: Mapping[str, Any],
    positions: Mapping[str, int],
    prices: Mapping[str, float],
    initial: float,
) -> float:
    previous_equity = float(previous.get("hypothetical_equity_after_intent", initial))
    invested = sum(positions[symbol] * prices[symbol] for symbol in positions)
    return previous_equity - invested


def position_weights(
    positions: Mapping[str, int], prices: Mapping[str, float], equity: float
) -> dict[str, float]:
    if equity <= 0:
        return {symbol: 0.0 for symbol in sorted(positions)}
    return {symbol: (positions[symbol] * prices[symbol]) / equity for symbol in sorted(positions)}


def max_weight_drift(target: Mapping[str, float], current: Mapping[str, float]) -> float:
    return max(
        abs(float(target.get(symbol, 0.0)) - float(current.get(symbol, 0.0))) for symbol in target
    )


def latest_intent_before(
    intents: Sequence[Mapping[str, Any]], as_of: str
) -> Mapping[str, Any] | None:
    previous = [row for row in intents if str(row.get("as_of_date", "")) < as_of]
    if not previous:
        return None
    return sorted(previous, key=lambda row: str(row["as_of_date"]))[-1]


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
        raise SystemExit("prices must be a mapping")
    prices: dict[str, float] = {}
    for symbol, payload in raw.items():
        value = payload.get("close") if isinstance(payload, Mapping) else payload
        price = float(value)
        if price <= 0:
            raise SystemExit(f"invalid price for {symbol}")
        prices[str(symbol).upper()] = price
    return prices


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


if __name__ == "__main__":
    raise SystemExit(main())
