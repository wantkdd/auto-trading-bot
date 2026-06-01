"""Scan a broader non-leveraged universe for paper-trading candidates.

The scanner expands beyond a single candidate. It is still research-only: it may
fetch public market/SEC data for local reports, but it has no broker,
credentials, live orders, or investment-advice path.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.fundamental_macro_recent_gate import build_report as build_gate_report
    from scripts.non_leveraged_universe_analysis import DEFAULT_SYMBOLS, looks_leveraged, percent
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from fundamental_macro_recent_gate import (
        build_report as build_gate_report,  # type: ignore[no-redef]
    )
    from non_leveraged_universe_analysis import (  # type: ignore[no-redef]
        DEFAULT_SYMBOLS,
        looks_leveraged,
        percent,
    )

DEFAULT_SYMBOLS_FILE = "data/universe/us_large_liquid_watchlist.txt"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan broad universe for paper candidates.")
    parser.add_argument("--symbols", nargs="+", default=None)
    parser.add_argument("--symbols-file", default=DEFAULT_SYMBOLS_FILE)
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--data-dir", default="data/external")
    parser.add_argument("--sec-cache-dir", default="data/external/sec")
    parser.add_argument("--top-candidates", type=int, default=20)
    parser.add_argument("--output", default=".omx/reports/market-universe-scan-latest.json")
    parser.add_argument("--markdown", default=".omx/reports/market-universe-scan-latest.md")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--skip-sec-refresh", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_scan_report(args)
    output = Path(args.output)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(markdown, report)
    print(
        "market scan status={status} symbols={symbols} pass={passed} review={review}".format(
            **report["summary"]
        )
    )
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0


def build_scan_report(args: argparse.Namespace) -> dict[str, Any]:
    symbols = resolve_symbols(args.symbols, Path(args.symbols_file))
    blocked = [symbol for symbol in symbols if looks_leveraged(symbol)]
    allowed = [symbol for symbol in symbols if symbol not in blocked]
    gate_args = argparse.Namespace(
        symbols=allowed,
        start=args.start,
        end=args.end,
        data_dir=args.data_dir,
        sec_cache_dir=args.sec_cache_dir,
        output=".omx/reports/fundamental-macro-recent-gate-latest.json",
        markdown=".omx/reports/fundamental-macro-recent-gate-latest.md",
        top_candidates=args.top_candidates,
        force_refresh=args.force_refresh,
        skip_sec_refresh=args.skip_sec_refresh,
    )
    gate_report = build_gate_report(gate_args)
    universe_summary = gate_report.get("universe_summary", {})
    price_metadata = gate_report.get("price_data", [])
    if not isinstance(universe_summary, Mapping):
        universe_summary = {}
    if not isinstance(price_metadata, list):
        price_metadata = []
    missing_price_data = [
        str(row.get("symbol"))
        for row in price_metadata
        if isinstance(row, Mapping) and row.get("status") != "ok"
    ]
    valid_assets = int(universe_summary.get("valid_assets", 0) or 0)
    candidates = tuple(gate_report.get("candidate_gates", ()))
    passed = [row for row in candidates if row.get("status") == "pass"]
    review = [row for row in candidates if row.get("status") != "pass"]
    return {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": "market-wide paper candidate scan only; no orders; no broker; no advice",
        "universe_policy": {
            "requested_symbols": len(symbols),
            "allowed_symbols": len(allowed),
            "blocked_symbols": blocked,
            "note": (
                "This is a broad liquid-universe seed, not literally every tradable security. "
                "Candidates must pass gates before paper intent tracking."
            ),
        },
        "summary": {
            "status": "ok",
            "symbols": valid_assets,
            "requested_symbols": len(symbols),
            "allowed_symbols": len(allowed),
            "valid_assets": valid_assets,
            "missing_price_data": len(missing_price_data),
            "passed": len(passed),
            "review": len(review),
            "top_candidate": passed[0].get("name") if passed else None,
        },
        "passed_candidates": [compact_candidate(row) for row in passed],
        "review_candidates": [compact_candidate(row) for row in review[: args.top_candidates]],
        "source_gate_summary": gate_report.get("summary", {}),
        "source_universe_summary": universe_summary,
        "missing_price_data_symbols": missing_price_data,
        "live_trading_authorized": False,
    }


def resolve_symbols(cli_symbols: Sequence[str] | None, symbols_file: Path) -> tuple[str, ...]:
    raw = list(cli_symbols) if cli_symbols else read_symbols_file(symbols_file)
    if not raw:
        raw = list(DEFAULT_SYMBOLS)
    normalized = []
    for symbol in raw:
        clean = symbol.strip().upper()
        if clean and clean not in normalized:
            normalized.append(clean)
    return tuple(normalized)


def read_symbols_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    symbols: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.split("#", 1)[0].strip()
        if clean:
            symbols.append(clean)
    return symbols


def compact_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": row.get("name"),
        "symbols": row.get("symbols"),
        "weights": row.get("weights"),
        "status": row.get("status"),
        "base_median_excess": row.get("base_median_excess"),
        "base_worst_mdd": row.get("base_worst_mdd"),
        "fundamental_status": row.get("fundamental_status"),
        "recent_regime_status": row.get("recent_regime_status"),
        "failure_reasons": row.get("failure_reasons", []),
    }


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Market universe candidate scan",
        "",
        "Safety: paper candidate scan only; no orders, no broker, no investment advice.",
        "",
        "## Summary",
        "",
        f"- Requested symbols: {report['summary']['requested_symbols']}",
        f"- Allowed symbols after leverage filter: {report['summary']['allowed_symbols']}",
        f"- Valid scanned assets: {report['summary']['valid_assets']}",
        f"- Missing/failed price data: {report['summary']['missing_price_data']}",
        f"- Passing candidates: {report['summary']['passed']}",
        f"- Review candidates: {report['summary']['review']}",
        f"- Top candidate: {report['summary']['top_candidate']}",
        f"- Live trading authorized: {report['live_trading_authorized']}",
        "",
        "## Passing candidates",
        "",
        "| Candidate | Symbols | Weights | Median excess | Worst MDD | Fundamentals | Recent |",
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in report["passed_candidates"]:
        lines.append(
            "| {name} | {symbols} | {weights} | {excess} | {mdd} | {fund} | {recent} |".format(
                name=row["name"],
                symbols=row["symbols"],
                weights=row["weights"],
                excess=percent(row["base_median_excess"]),
                mdd=percent(row["base_worst_mdd"]),
                fund=row["fundamental_status"],
                recent=row["recent_regime_status"],
            )
        )
    lines.extend(
        [
            "",
            "## Review candidates",
            "",
            "| Candidate | Symbols | Weights | Median excess | Worst MDD | Reasons |",
            "| --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for row in report["review_candidates"]:
        lines.append(
            "| {name} | {symbols} | {weights} | {excess} | {mdd} | {reasons} |".format(
                name=row["name"],
                symbols=row["symbols"],
                weights=row["weights"],
                excess=percent(row["base_median_excess"]),
                mdd=percent(row["base_worst_mdd"]),
                reasons=", ".join(row["failure_reasons"]) or "-",
            )
        )
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
