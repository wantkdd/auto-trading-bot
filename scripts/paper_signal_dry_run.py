"""Generate offline paper-trading target weights without placing orders.

The output is a dry-run signal only. It never connects to a broker, never reads
credentials, and never creates live or paper orders.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.strategy_optimization import fetch_or_load_bars
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from strategy_optimization import fetch_or_load_bars


@dataclass(frozen=True)
class DryRunSignal:
    generated_at: str
    as_of_date: str
    strategy: str
    target_weights: dict[str, float]
    source_bars: dict[str, dict[str, Any]]
    warnings: tuple[str, ...]
    safety: str = "dry-run target weights only; no orders; no broker; no investment advice"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write offline paper dry-run target weights.")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--data-dir", default="data/external")
    parser.add_argument("--output", default="reports/paper-dry-run-signal-latest.json")
    parser.add_argument("--strategy", default="static_portfolio_qqq_0.36_gld_0.64")
    parser.add_argument("--qqq-weight", type=float, default=0.36)
    parser.add_argument("--gld-weight", type=float, default=0.64)
    parser.add_argument("--force-refresh", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    signal = build_signal(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(signal), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"strategy={signal.strategy} as_of={signal.as_of_date} output={output}")
    print(f"target_weights={signal.target_weights}")
    if signal.warnings:
        print("warnings=" + "; ".join(signal.warnings))
    return 0


def build_signal(args: argparse.Namespace) -> DryRunSignal:
    weights = normalize_weights({"QQQ": args.qqq_weight, "GLD": args.gld_weight})
    bars_by_symbol = {}
    metadata_by_symbol = {}
    for symbol in weights:
        bars, metadata = fetch_or_load_bars(
            user_symbol=symbol,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
            data_dir=Path(args.data_dir),
            force_refresh=args.force_refresh,
        )
        metadata_by_symbol[symbol] = metadata
        if bars is None:
            raise SystemExit(f"missing validated bars for {symbol}: {metadata.get('error')}")
        bars_by_symbol[symbol] = bars

    common_dates = sorted(
        set.intersection(
            *(set(bar.timestamp.date() for bar in bars) for bars in bars_by_symbol.values())
        )
    )
    if not common_dates:
        raise SystemExit("no common dates across dry-run symbols")
    as_of = common_dates[-1]
    source_bars = {}
    for symbol, bars in bars_by_symbol.items():
        by_date = {bar.timestamp.date(): bar for bar in bars}
        bar = by_date[as_of]
        source_bars[symbol] = {
            "timestamp": bar.timestamp.isoformat(),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "metadata": metadata_by_symbol[symbol],
        }

    warnings = tuple(build_warnings(weights, source_bars))
    return DryRunSignal(
        generated_at=datetime.now(tz=UTC).isoformat(),
        as_of_date=as_of.isoformat(),
        strategy=args.strategy,
        target_weights=weights,
        source_bars=source_bars,
        warnings=warnings,
    )


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    if any(value < 0 for value in weights.values()):
        raise SystemExit("weights must be nonnegative")
    total = sum(weights.values())
    if total <= 0:
        raise SystemExit("at least one positive target weight is required")
    return {symbol: value / total for symbol, value in weights.items() if value > 0}


def build_warnings(weights: dict[str, float], source_bars: dict[str, dict[str, Any]]) -> list[str]:
    warnings = [
        "This is a dry-run target allocation only; do not place orders from this output.",
        "Candidate remains in research review until independent data-source replication passes.",
    ]
    if max(weights.values()) > 0.75:
        warnings.append("Single-asset concentration exceeds 75%.")
    for symbol, payload in source_bars.items():
        if payload["volume"] <= 0:
            warnings.append(f"{symbol} latest bar has non-positive volume.")
    return warnings


if __name__ == "__main__":
    raise SystemExit(main())
