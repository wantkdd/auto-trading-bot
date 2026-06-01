"""Build a broad, liquid, non-leveraged US candidate universe.

The builder refreshes a broad index-derived symbol pool, ranks candidates by
recent dollar volume, and writes a daily watchlist for no-order paper scanning.
It does not connect to brokers, read trading credentials, or create orders.
"""

from __future__ import annotations

import argparse
import html.parser
import json
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from scripts.non_leveraged_universe_analysis import looks_leveraged
    from scripts.strategy_optimization import fetch_or_load_bars
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from non_leveraged_universe_analysis import looks_leveraged  # type: ignore[no-redef]
    from strategy_optimization import fetch_or_load_bars  # type: ignore[no-redef]

DEFAULT_SEED = "data/universe/us_large_liquid_watchlist.txt"
DEFAULT_OUTPUT = "data/universe/us_dynamic_liquid_watchlist.txt"
DEFAULT_REPORT = ".omx/reports/us-dynamic-liquid-universe-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/us-dynamic-liquid-universe-latest.md"
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
CORE_ETFS = (
    "SPY",
    "QQQ",
    "DIA",
    "IWM",
    "GLD",
    "TLT",
    "IEF",
    "SHY",
    "XLK",
    "XLV",
    "XLP",
    "XLU",
    "XLF",
    "XLE",
    "XLI",
    "XLY",
    "XLC",
    "XLRE",
    "XLB",
    "VNQ",
)


@dataclass(frozen=True)
class RankedSymbol:
    symbol: str
    source: str
    status: str
    average_dollar_volume: float
    latest_close: float | None
    latest_volume: float | None
    error: str = ""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build dynamic US liquid watchlist.")
    parser.add_argument("--seed", default=DEFAULT_SEED)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    parser.add_argument("--data-dir", default="data/external")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--lookback-days", type=int, default=45)
    parser.add_argument("--max-rank-candidates", type=int, default=300)
    parser.add_argument("--max-output-symbols", type=int, default=150)
    parser.add_argument("--min-selected-symbols", type=int, default=10)
    parser.add_argument("--always-include", nargs="*", default=["AAPL", "GLD"])
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--skip-remote", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    write_watchlist(Path(args.output), report)
    write_report(Path(args.report), Path(args.markdown), report)
    print(
        (
            "dynamic universe status={status} selected={selected} "
            "ranked={ranked} sources={sources}"
        ).format(**report["summary"])
    )
    print(f"watchlist={args.output}")
    print(f"report={args.report}")
    return 0 if report["status"] == "ok" else 1


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    end = date.fromisoformat(args.end)
    start = end - timedelta(days=int(args.lookback_days))
    source_symbols = collect_source_symbols(Path(args.seed), skip_remote=bool(args.skip_remote))
    candidate_symbols = [symbol for symbol in source_symbols if not looks_leveraged(symbol)]
    ranked = rank_symbols(
        candidate_symbols[: int(args.max_rank_candidates)],
        start=start,
        end=end,
        data_dir=Path(args.data_dir),
        force_refresh=bool(args.force_refresh),
    )
    selected = select_symbols(
        ranked,
        max_output_symbols=int(args.max_output_symbols),
        always_include=tuple(str(symbol).upper() for symbol in args.always_include),
    )
    blocked = [symbol for symbol in source_symbols if looks_leveraged(symbol)]
    ok_ranked = [item for item in ranked if item.status == "ok"]
    min_selected_symbols = int(args.min_selected_symbols)
    status = "ok" if len(selected) >= min_selected_symbols else "blocked"
    return {
        "status": status,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": "dynamic universe builder only; no orders; no broker; no credentials; no advice",
        "live_trading_authorized": False,
        "summary": {
            "status": status,
            "sources": len(source_symbols),
            "rank_candidates": min(len(candidate_symbols), int(args.max_rank_candidates)),
            "ranked": len(ok_ranked),
            "selected": len(selected),
            "min_selected_symbols": min_selected_symbols,
            "blocked_leveraged_or_inverse": len(blocked),
            "lookback_days": int(args.lookback_days),
            "max_output_symbols": int(args.max_output_symbols),
        },
        "source_counts": source_counts(source_symbols),
        "selected_symbols": selected,
        "top_selected_symbols": selected[:10],
        "ranked_symbols": [item.__dict__ for item in ranked],
        "blocked_symbols": blocked,
        "blockers": [] if status == "ok" else ["dynamic_universe_below_minimum_10_symbols"],
        "source_urls": {
            "sp500": SP500_URL,
            "nasdaq100": NASDAQ100_URL,
        },
    }


def collect_source_symbols(seed: Path, *, skip_remote: bool) -> tuple[str, ...]:
    symbols: list[str] = []
    symbols.extend(CORE_ETFS)
    symbols.extend(read_seed_symbols(seed))
    if not skip_remote:
        symbols.extend(fetch_wikipedia_table_symbols(SP500_URL, symbol_headers={"Symbol"}))
        symbols.extend(fetch_wikipedia_table_symbols(NASDAQ100_URL, symbol_headers={"Ticker"}))
    return dedupe_symbols(symbols)


def read_seed_symbols(path: Path) -> list[str]:
    if not path.exists():
        return []
    rows: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.split("#", 1)[0].strip()
        if clean:
            rows.append(clean)
    return rows


def dedupe_symbols(raw: Sequence[str]) -> tuple[str, ...]:
    symbols: list[str] = []
    for item in raw:
        symbol = normalize_symbol(item)
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return tuple(symbols)


def normalize_symbol(raw: str) -> str:
    symbol = raw.strip().upper().replace(".", "-")
    if not symbol or len(symbol) > 8:
        return ""
    if any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for char in symbol):
        return ""
    return symbol


def fetch_wikipedia_table_symbols(url: str, *, symbol_headers: set[str]) -> list[str]:
    request = urllib.request.Request(url, headers={"User-Agent": "paper-observer/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - public list
        html = response.read().decode("utf-8", "replace")
    tables = TableParser().parse(html)
    for table in tables:
        if not table:
            continue
        header = [cell.strip() for cell in table[0]]
        symbol_index = next(
            (index for index, cell in enumerate(header) if cell in symbol_headers), None
        )
        if symbol_index is None:
            continue
        symbols = []
        for row in table[1:]:
            if symbol_index < len(row):
                symbols.append(row[symbol_index])
        if symbols:
            return symbols
    return []


class TableParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._current_table: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []

    def parse(self, html: str) -> list[list[list[str]]]:
        self.feed(html)
        return self.tables

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._in_table = True
            self._current_table = []
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._current_row = []
        elif self._in_row and tag in {"td", "th"}:
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._in_cell:
            self._current_row.append("".join(self._current_cell).strip())
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._current_row:
                self._current_table.append(self._current_row)
            self._in_row = False
        elif tag == "table" and self._in_table:
            if self._current_table:
                self.tables.append(self._current_table)
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)


def rank_symbols(
    symbols: Sequence[str], *, start: date, end: date, data_dir: Path, force_refresh: bool
) -> list[RankedSymbol]:
    ranked: list[RankedSymbol] = []
    for symbol in symbols:
        bars, metadata = fetch_or_load_bars(
            user_symbol=symbol,
            start=start,
            end=end,
            data_dir=data_dir,
            force_refresh=force_refresh,
        )
        if not bars:
            ranked.append(
                RankedSymbol(
                    symbol=symbol,
                    source="Yahoo Finance chart endpoint",
                    status=str(metadata.get("status", "missing")),
                    average_dollar_volume=0.0,
                    latest_close=None,
                    latest_volume=None,
                    error=str(metadata.get("error", "")),
                )
            )
            continue
        recent = bars[-min(len(bars), 20) :]
        adv = sum(bar.close * bar.volume for bar in recent) / len(recent)
        ranked.append(
            RankedSymbol(
                symbol=symbol,
                source="Yahoo Finance chart endpoint",
                status="ok",
                average_dollar_volume=adv,
                latest_close=bars[-1].close,
                latest_volume=bars[-1].volume,
            )
        )
    return sorted(ranked, key=lambda item: item.average_dollar_volume, reverse=True)


def select_symbols(
    ranked: Sequence[RankedSymbol], *, max_output_symbols: int, always_include: Sequence[str]
) -> list[str]:
    selected: list[str] = []
    for symbol in always_include:
        if symbol and symbol not in selected:
            selected.append(symbol)
    for item in ranked:
        if item.status != "ok":
            continue
        if item.symbol not in selected:
            selected.append(item.symbol)
        if len(selected) >= max_output_symbols:
            break
    return selected


def source_counts(symbols: Sequence[str]) -> dict[str, int]:
    return {"unique_symbols": len(set(symbols))}


def write_watchlist(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Dynamic non-leveraged US liquid universe.",
        "# Generated from broad index sources and recent dollar-volume ranking.",
        "# No broker, no orders, no investment advice.",
        *[str(symbol) for symbol in report["selected_symbols"]],
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(output: Path, markdown: Path, report: Mapping[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Dynamic US liquid universe",
        "",
        "Safety: universe selection only; no orders, no broker, no credentials, no advice.",
        "",
        "## Summary",
        "",
        f"- Source symbols: {report['summary']['sources']}",
        f"- Ranked symbols: {report['summary']['ranked']}",
        f"- Selected symbols: {report['summary']['selected']}",
        f"- Minimum selected symbols: {report['summary']['min_selected_symbols']}",
        f"- Leveraged/inverse blocked: {report['summary']['blocked_leveraged_or_inverse']}",
        "",
        "## First 10 selected symbols",
        "",
        ", ".join(report["top_selected_symbols"]),
        "",
        "## Full selected symbols",
        "",
        ", ".join(report["selected_symbols"]),
    ]
    markdown.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
