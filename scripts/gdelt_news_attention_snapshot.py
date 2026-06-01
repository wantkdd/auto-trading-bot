"""Collect GDELT news-attention snapshots for no-order research.

This collector records article counts/samples for ticker queries. It is a text
feature precursor, not a trading signal. It never creates orders, connects to a
broker, or reads credentials.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.market_universe_candidate_scan import read_symbols_file
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from market_universe_candidate_scan import read_symbols_file  # type: ignore[no-redef]

GDELT_DOC_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
DEFAULT_SYMBOLS_FILE = "data/universe/us_large_liquid_watchlist.txt"
DEFAULT_OUTPUT = ".omx/reports/gdelt-news-attention-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/gdelt-news-attention-latest.md"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect GDELT news-attention snapshot.")
    parser.add_argument("--symbols", nargs="+", default=None)
    parser.add_argument("--symbols-file", default=DEFAULT_SYMBOLS_FILE)
    parser.add_argument("--max-symbols", type=int, default=5)
    parser.add_argument("--max-records", type=int, default=5)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    write_json(Path(args.output), report)
    write_markdown(Path(args.markdown), report)
    print(
        "gdelt news status={status} symbols={symbols} articles={article_samples}".format(
            **report["summary"]
        )
    )
    print(f"json={args.output}")
    print(f"markdown={args.markdown}")
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    symbols = resolve_symbols(args.symbols, Path(args.symbols_file))[: args.max_symbols]
    rows: list[dict[str, Any]] = []
    rate_limited = False
    errors: list[str] = []
    for index, symbol in enumerate(symbols):
        if index and args.sleep_seconds > 0:
            time.sleep(float(args.sleep_seconds))
        try:
            rows.append(fetch_symbol(symbol, max_records=args.max_records, timeout=args.timeout))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                rate_limited = True
                rows.append(empty_symbol(symbol, status="rate_limited"))
                break
            errors.append(f"{symbol}:HTTPError:{exc.code}")
            rows.append(empty_symbol(symbol, status="error"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{symbol}:{type(exc).__name__}")
            rows.append(empty_symbol(symbol, status="error"))
    completed = [row for row in rows if row["status"] == "ok"]
    status = "rate_limited" if rate_limited else "ok"
    if errors and not completed:
        status = "error"
    return {
        "status": status,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": "GDELT news attention only; no broker; no credentials; no orders; no advice",
        "summary": {
            "status": status,
            "symbols": len(symbols),
            "completed_symbols": len(completed),
            "article_samples": sum(len(row.get("articles", [])) for row in rows),
            "rate_limited": rate_limited,
            "errors": len(errors),
            "order_created": False,
            "live_trading_authorized": False,
        },
        "source": {
            "endpoint": GDELT_DOC_ENDPOINT,
            "docs": "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/",
        },
        "rows": rows,
        "errors": errors,
        "point_in_time_rule": "Use GDELT article seen/published time as a feature timestamp.",
        "live_trading_authorized": False,
        "paper_api_authorized": False,
    }


def fetch_symbol(symbol: str, *, max_records: int, timeout: float) -> dict[str, Any]:
    query = f'"{symbol}" stock OR "{symbol}" shares'
    params = urllib.parse.urlencode(
        {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": str(max_records),
            "sort": "datedesc",
        }
    )
    request = urllib.request.Request(
        f"{GDELT_DOC_ENDPOINT}?{params}",
        headers={"User-Agent": "auto-trading-bot-research/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 public API
        payload = json.loads(response.read().decode("utf-8"))
    articles = payload.get("articles", []) if isinstance(payload, Mapping) else []
    if not isinstance(articles, list):
        articles = []
    return {
        "symbol": symbol,
        "status": "ok",
        "query": query,
        "article_count": len(articles),
        "articles": [
            compact_article(article) for article in articles if isinstance(article, Mapping)
        ],
    }


def compact_article(article: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": article.get("title"),
        "url": article.get("url"),
        "source_country": article.get("sourcecountry"),
        "domain": article.get("domain"),
        "seendate": article.get("seendate"),
        "language": article.get("language"),
    }


def empty_symbol(symbol: str, *, status: str) -> dict[str, Any]:
    return {"symbol": symbol, "status": status, "article_count": 0, "articles": []}


def resolve_symbols(cli_symbols: Sequence[str] | None, symbols_file: Path) -> tuple[str, ...]:
    raw = list(cli_symbols) if cli_symbols else read_symbols_file(symbols_file)
    normalized: list[str] = []
    for symbol in raw:
        clean = symbol.strip().upper()
        if clean and clean not in normalized:
            normalized.append(clean)
    return tuple(normalized)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    lines = [
        "# GDELT news-attention snapshot",
        "",
        "Safety: news attention only; no broker, no credentials, no orders, no advice.",
        "",
        "## Summary",
        "",
        f"- Status: `{summary['status']}`",
        f"- Symbols: `{summary['symbols']}`",
        f"- Completed symbols: `{summary['completed_symbols']}`",
        f"- Article samples: `{summary['article_samples']}`",
        f"- Rate limited: `{summary['rate_limited']}`",
        f"- Order created: `{summary['order_created']}`",
        f"- Live trading authorized: `{summary['live_trading_authorized']}`",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
