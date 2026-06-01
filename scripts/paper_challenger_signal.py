"""Generate a no-order challenger signal from the market-wide candidate scan.

The challenger is observational only. It does not replace the frozen primary paper
strategy, connect to brokers, read trading credentials, or create orders.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.non_leveraged_universe_analysis import looks_leveraged
    from scripts.paper_signal_dry_run import build_signal
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from non_leveraged_universe_analysis import looks_leveraged  # type: ignore[no-redef]
    from paper_signal_dry_run import build_signal  # type: ignore[no-redef]

DEFAULT_MARKET_SCAN = ".omx/reports/market-universe-scan-latest.json"
DEFAULT_OUTPUT = "reports/paper-challenger-signal-latest.json"
DEFAULT_REPORT = ".omx/reports/paper-challenger-selection-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/paper-challenger-selection-latest.md"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write no-order market-scan challenger signal.")
    parser.add_argument("--market-scan", default=DEFAULT_MARKET_SCAN)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--data-dir", default="data/external")
    parser.add_argument("--force-refresh", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    report_path = Path(args.report)
    markdown_path = Path(args.markdown)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(markdown_path, report)
    print(
        "paper challenger status={status} strategy={strategy} blockers={blockers}".format(
            status=report["summary"]["status"],
            strategy=report["summary"].get("challenger_strategy"),
            blockers=len(report["blockers"]),
        )
    )
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = datetime.now(tz=UTC)
    market_scan = read_json_if_exists(Path(args.market_scan))
    blockers: list[str] = []
    selected = select_challenger(market_scan)
    signal_payload: dict[str, Any] | None = None
    if market_scan is None:
        blockers.append("market_scan_report_missing_for_challenger")
    elif selected is None:
        blockers.append("market_scan_has_no_safe_passed_challenger")
    else:
        signal = build_signal(
            argparse.Namespace(
                start=args.start,
                end=args.end,
                data_dir=args.data_dir,
                output=args.output,
                strategy=selected["name"],
                weights=[
                    f"{symbol}={weight}"
                    for symbol, weight in zip(
                        selected["symbols"], selected["weights"], strict=True
                    )
                ],
                qqq_weight=0.36,
                gld_weight=0.64,
                force_refresh=args.force_refresh,
            )
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        signal_payload = asdict(signal)
        output.write_text(
            json.dumps(signal_payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    status = "pass" if not blockers else "blocked"
    return {
        "status": "ok",
        "generated_at": generated_at.isoformat(),
        "safety": "challenger observation only; no orders; no broker; no credentials; no advice",
        "live_trading_authorized": False,
        "paper_api_authorized": False,
        "summary": {
            "status": status,
            "challenger_strategy": selected.get("name") if selected else None,
            "challenger_symbols": selected.get("symbols") if selected else [],
            "challenger_weights": selected.get("weights") if selected else [],
            "primary_strategy_changed": False,
            "output": str(args.output) if signal_payload else None,
            "order_created": False,
            "live_trading_authorized": False,
        },
        "selected_candidate": selected,
        "signal": compact_signal(signal_payload),
        "blockers": blockers,
        "required_next_evidence": [
            "Track challenger separately from the frozen primary observation strategy.",
            "Promote a challenger only after forward no-order evidence and explicit human review.",
            "Do not connect a broker or place paper/live API orders from challenger output.",
        ],
    }


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def select_challenger(market_scan: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if market_scan is None:
        return None
    candidates = market_scan.get("passed_candidates", [])
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        symbols = [str(symbol).upper() for symbol in candidate.get("symbols", [])]
        weights = [float(weight) for weight in candidate.get("weights", [])]
        if not symbols or len(symbols) != len(weights):
            continue
        if candidate.get("status") != "pass":
            continue
        if any(looks_leveraged(symbol) for symbol in symbols):
            continue
        if max(weights) > 0.75:
            continue
        return {
            "name": str(candidate.get("name") or "_".join(symbols)),
            "symbols": symbols,
            "weights": weights,
            "base_median_excess": candidate.get("base_median_excess"),
            "base_worst_mdd": candidate.get("base_worst_mdd"),
            "fundamental_status": candidate.get("fundamental_status"),
            "recent_regime_status": candidate.get("recent_regime_status"),
        }
    return None


def compact_signal(signal: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if signal is None:
        return None
    return {
        "as_of_date": signal.get("as_of_date"),
        "strategy": signal.get("strategy"),
        "target_weights": signal.get("target_weights"),
        "safety": signal.get("safety"),
        "warnings": signal.get("warnings"),
    }


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    lines = [
        "# Paper challenger signal",
        "",
        "Safety: challenger observation only; no orders, no broker, no credentials, no advice.",
        "",
        "## Summary",
        "",
        f"- Status: `{summary['status']}`",
        f"- Challenger strategy: `{summary['challenger_strategy']}`",
        f"- Challenger symbols: `{summary['challenger_symbols']}`",
        f"- Challenger weights: `{summary['challenger_weights']}`",
        f"- Primary strategy changed: `{summary['primary_strategy_changed']}`",
        f"- Order created: `{summary['order_created']}`",
        f"- Live trading authorized: `{summary['live_trading_authorized']}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- {blocker}" for blocker in report["blockers"] or ["none"])
    lines.extend(["", "## Required next evidence", ""])
    lines.extend(f"- {item}" for item in report["required_next_evidence"])
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
