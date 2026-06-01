"""Refresh a broad no-order US symbol universe from Nasdaq Trader directories.

This script fetches public symbol-directory text files only. It does not fetch
prices, connect to a broker, read credentials, or create orders.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
DEFAULT_OUTPUT = "data/universe/us_nasdaqtrader_symbols.csv"
DEFAULT_COMMON_OUTPUT = "data/universe/us_nasdaqtrader_common_symbols.txt"
DEFAULT_REPORT = ".omx/reports/us-symbol-universe-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/us-symbol-universe-latest.md"
CSV_COLUMNS = ("symbol", "name", "listing_market", "source", "is_etf", "is_test_issue")


@dataclass(frozen=True)
class UniverseRow:
    symbol: str
    name: str
    listing_market: str
    source: str
    is_etf: bool
    is_test_issue: bool

    def as_csv_row(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "listing_market": self.listing_market,
            "source": self.source,
            "is_etf": str(self.is_etf).lower(),
            "is_test_issue": str(self.is_test_issue).lower(),
        }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh no-order US symbol universe.")
    parser.add_argument("--nasdaq-listed-url", default=NASDAQ_LISTED_URL)
    parser.add_argument("--other-listed-url", default=OTHER_LISTED_URL)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--common-output", default=DEFAULT_COMMON_OUTPUT)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    nasdaq_text = fetch_text(str(args.nasdaq_listed_url), timeout=float(args.timeout))
    other_text = fetch_text(str(args.other_listed_url), timeout=float(args.timeout))
    rows = merge_rows(parse_nasdaq_listed(nasdaq_text), parse_other_listed(other_text))
    write_csv(Path(args.output), rows)
    common_symbols = [row.symbol for row in rows if is_common_equity_candidate(row)]
    write_symbols(Path(args.common_output), common_symbols)
    report = build_report(rows, common_symbols)
    write_json(Path(args.report), report)
    write_markdown(Path(args.markdown), report)
    print(
        (
            "us symbol universe status={status} total={symbols} common={common_equity_candidates}"
        ).format(**report["summary"])
    )
    print(f"csv={args.output}")
    print(f"common={args.common_output}")
    return 0


def fetch_text(url: str, *, timeout: float) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "auto-trading-bot-research/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 public source
        raw = response.read()
    return raw.decode("utf-8-sig")


def parse_nasdaq_listed(text: str) -> list[UniverseRow]:
    rows: list[UniverseRow] = []
    for raw in csv.DictReader(_data_lines(text), delimiter="|"):
        symbol = normalize_symbol(raw.get("Symbol", ""))
        if not symbol:
            continue
        rows.append(
            UniverseRow(
                symbol=symbol,
                name=str(raw.get("Security Name", "")).strip(),
                listing_market="NASDAQ",
                source="nasdaqlisted",
                is_etf=yes(raw.get("ETF", "N")),
                is_test_issue=yes(raw.get("Test Issue", "N")),
            )
        )
    return rows


def parse_other_listed(text: str) -> list[UniverseRow]:
    rows: list[UniverseRow] = []
    for raw in csv.DictReader(_data_lines(text), delimiter="|"):
        symbol = normalize_symbol(raw.get("ACT Symbol", ""))
        if not symbol:
            continue
        rows.append(
            UniverseRow(
                symbol=symbol,
                name=str(raw.get("Security Name", "")).strip(),
                listing_market=exchange_name(str(raw.get("Exchange", "")).strip()),
                source="otherlisted",
                is_etf=yes(raw.get("ETF", "N")),
                is_test_issue=yes(raw.get("Test Issue", "N")),
            )
        )
    return rows


def _data_lines(text: str) -> io.StringIO:
    lines = [
        line for line in text.splitlines() if line and not line.startswith("File Creation Time")
    ]
    return io.StringIO("\n".join(lines))


def merge_rows(*groups: Sequence[UniverseRow]) -> list[UniverseRow]:
    by_symbol: dict[str, UniverseRow] = {}
    for group in groups:
        for row in group:
            if row.symbol not in by_symbol:
                by_symbol[row.symbol] = row
    return sorted(by_symbol.values(), key=lambda row: row.symbol)


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(" ", "")


def exchange_name(code: str) -> str:
    return {"A": "NYSE American", "N": "NYSE", "P": "NYSE Arca", "Z": "Cboe BZX"}.get(
        code, code or "unknown"
    )


def yes(value: object) -> bool:
    return str(value).strip().upper() == "Y"


def is_common_equity_candidate(row: UniverseRow) -> bool:
    if row.is_etf or row.is_test_issue:
        return False
    if any(marker in row.symbol for marker in ("$", "^", "+", "*", "=")):
        return False
    upper_name = row.name.upper()
    excluded_name_markers = (
        "WARRANT",
        "RIGHT",
        "UNIT",
        "PREFERRED",
        "PFD",
        "NOTE ",
        "NOTES ",
        "BOND",
        "DEBENTURE",
        "ETF",
        "ETN",
        "FUND",
        "TRUST",
    )
    return not any(marker in upper_name for marker in excluded_name_markers)


def build_report(rows: Sequence[UniverseRow], common_symbols: Sequence[str]) -> dict[str, Any]:
    by_exchange: dict[str, int] = {}
    for row in rows:
        by_exchange[row.listing_market] = by_exchange.get(row.listing_market, 0) + 1
    return {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": "public symbol universe only; no prices; no broker; no credentials; no orders",
        "summary": {
            "status": "ok",
            "symbols": len(rows),
            "common_equity_candidates": len(common_symbols),
            "etf_or_fund_like": sum(1 for row in rows if row.is_etf),
            "test_issues": sum(1 for row in rows if row.is_test_issue),
            "order_created": False,
            "live_trading_authorized": False,
        },
        "by_exchange": dict(sorted(by_exchange.items())),
        "source_urls": {
            "nasdaq_listed": NASDAQ_LISTED_URL,
            "other_listed": OTHER_LISTED_URL,
            "definitions": "https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs",
        },
        "live_trading_authorized": False,
        "paper_api_authorized": False,
    }


def write_csv(path: Path, rows: Sequence[UniverseRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_csv_row())


def write_symbols(path: Path, symbols: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(symbols) + "\n", encoding="utf-8")


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    lines = [
        "# US symbol universe refresh",
        "",
        "Safety: public symbol directory only; no prices, no broker, no credentials, no orders.",
        "",
        "## Summary",
        "",
        f"- Symbols: `{summary['symbols']}`",
        f"- Common equity candidates: `{summary['common_equity_candidates']}`",
        f"- ETF or fund-like rows: `{summary['etf_or_fund_like']}`",
        f"- Test issues: `{summary['test_issues']}`",
        f"- Order created: `{summary['order_created']}`",
        f"- Live trading authorized: `{summary['live_trading_authorized']}`",
        "",
        "## Source URLs",
        "",
        *[f"- {name}: {url}" for name, url in report["source_urls"].items()],
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
