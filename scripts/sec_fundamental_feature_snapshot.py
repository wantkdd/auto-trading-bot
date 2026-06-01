"""Build SEC fundamental feature snapshots from cached EDGAR data.

This is a no-order research feature builder. By default it reads only local SEC
cache files so it can be run safely in CI/offline loops. It never connects to a
broker, reads credentials, or creates orders.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.fundamental_macro_recent_gate import (
        build_fundamental_snapshot,
        load_sec_ticker_map,
    )
    from scripts.market_universe_candidate_scan import read_symbols_file
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from fundamental_macro_recent_gate import (  # type: ignore[no-redef]
        build_fundamental_snapshot,
        load_sec_ticker_map,
    )
    from market_universe_candidate_scan import read_symbols_file  # type: ignore[no-redef]

DEFAULT_SYMBOLS_FILE = "data/universe/us_large_liquid_watchlist.txt"
DEFAULT_OUTPUT = ".omx/features/sec-fundamental-snapshot.csv"
DEFAULT_REPORT = ".omx/reports/sec-fundamental-feature-snapshot-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/sec-fundamental-feature-snapshot-latest.md"
CSV_COLUMNS = (
    "symbol",
    "as_of_date",
    "cik",
    "company_name",
    "status",
    "revenue_growth_yoy",
    "net_income_positive",
    "operating_cash_flow_positive",
    "debt_to_equity",
    "current_ratio",
    "latest_filing_date",
    "recent_8k_count_90d",
    "failure_reasons",
    "data_warnings",
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build cached SEC fundamental feature snapshot.")
    parser.add_argument("--symbols", nargs="+", default=None)
    parser.add_argument("--symbols-file", default=DEFAULT_SYMBOLS_FILE)
    parser.add_argument("--sec-cache-dir", default="data/external/sec")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    parser.add_argument("--allow-network-refresh", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_snapshot(args)
    write_csv(Path(args.output), result["rows"])
    write_json(Path(args.report), result["report"])
    write_markdown(Path(args.markdown), result["report"])
    print(
        "sec feature snapshot status={status} rows={rows} pass={passed} review={review}".format(
            **result["report"]["summary"]
        )
    )
    print(f"csv={args.output}")
    print(f"report={args.report}")
    return 0


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    as_of = date.fromisoformat(str(args.as_of))
    cache_dir = Path(args.sec_cache_dir)
    symbols = resolve_symbols(args.symbols, Path(args.symbols_file))
    ticker_map = load_sec_ticker_map(cache_dir, force_refresh=bool(args.allow_network_refresh))
    rows = [
        snapshot_to_row(
            build_fundamental_snapshot(
                symbol=symbol,
                ticker_map=ticker_map,
                cache_dir=cache_dir,
                force_refresh=bool(args.allow_network_refresh),
                skip_refresh=not bool(args.allow_network_refresh),
                as_of=as_of,
            ),
            as_of=as_of,
        )
        for symbol in symbols
    ]
    pass_rows = [row for row in rows if row["status"] == "pass"]
    review_rows = [row for row in rows if row["status"] != "pass"]
    cached_rows = [row for row in rows if "companyfacts_cache_missing" not in row["data_warnings"]]
    report = {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "as_of_date": as_of.isoformat(),
        "safety": "cached SEC fundamental features only; no broker; no credentials; no orders",
        "summary": {
            "status": "ok",
            "symbols_requested": len(symbols),
            "rows": len(rows),
            "cached_companyfacts_rows": len(cached_rows),
            "passed": len(pass_rows),
            "review": len(review_rows),
            "network_refresh_allowed": bool(args.allow_network_refresh),
            "order_created": False,
            "live_trading_authorized": False,
        },
        "columns": list(CSV_COLUMNS),
        "rows_sample": rows[:10],
        "review_symbols": [row["symbol"] for row in review_rows[:50]],
        "point_in_time_rule": (
            "SEC facts use filed dates <= as_of_date; future filings are excluded."
        ),
        "live_trading_authorized": False,
        "paper_api_authorized": False,
    }
    return {"rows": rows, "report": report}


def resolve_symbols(cli_symbols: Sequence[str] | None, symbols_file: Path) -> tuple[str, ...]:
    raw = list(cli_symbols) if cli_symbols else read_symbols_file(symbols_file)
    normalized: list[str] = []
    for symbol in raw:
        clean = symbol.strip().upper()
        if clean and clean not in normalized:
            normalized.append(clean)
    return tuple(normalized)


def snapshot_to_row(snapshot: Any, *, as_of: date) -> dict[str, Any]:
    return {
        "symbol": snapshot.symbol,
        "as_of_date": as_of.isoformat(),
        "cik": snapshot.cik or "",
        "company_name": snapshot.company_name or "",
        "status": snapshot.status,
        "revenue_growth_yoy": snapshot.revenue_growth_yoy,
        "net_income_positive": snapshot.net_income_positive,
        "operating_cash_flow_positive": snapshot.operating_cash_flow_positive,
        "debt_to_equity": snapshot.debt_to_equity,
        "current_ratio": snapshot.current_ratio,
        "latest_filing_date": snapshot.latest_filing_date or "",
        "recent_8k_count_90d": snapshot.recent_8k_count_90d,
        "failure_reasons": ";".join(snapshot.failure_reasons),
        "data_warnings": ";".join(snapshot.data_warnings),
    }


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: format_cell(row.get(column, "")) for column in CSV_COLUMNS})


def format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return f"{value:.10f}"
    return str(value)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    lines = [
        "# SEC fundamental feature snapshot",
        "",
        "Safety: cached SEC features only; no broker, no credentials, no orders.",
        "",
        "## Summary",
        "",
        f"- As-of date: `{report['as_of_date']}`",
        f"- Symbols requested: `{summary['symbols_requested']}`",
        f"- Rows: `{summary['rows']}`",
        f"- Cached companyfacts rows: `{summary['cached_companyfacts_rows']}`",
        f"- Passed: `{summary['passed']}`",
        f"- Review: `{summary['review']}`",
        f"- Network refresh allowed: `{summary['network_refresh_allowed']}`",
        f"- Order created: `{summary['order_created']}`",
        f"- Live trading authorized: `{summary['live_trading_authorized']}`",
        "",
        "## Point-in-time rule",
        "",
        str(report["point_in_time_rule"]),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
