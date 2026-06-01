"""Tests for public US symbol-universe refresh."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.us_symbol_universe_refresh import (
    build_report,
    is_common_equity_candidate,
    merge_rows,
    parse_nasdaq_listed,
    parse_other_listed,
    write_csv,
    write_symbols,
)

NASDAQ_SAMPLE = "\n".join(
    [
        (
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|"
            "Round Lot Size|ETF|NextShares"
        ),
        "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N",
        "TQQQ|ProShares UltraPro QQQ|G|N|N|100|Y|N",
        "ZTEST|Test Company|S|Y|N|100|N|N",
        "File Creation Time: 0601202612:00|||||||",
    ]
)

OTHER_SAMPLE = "\n".join(
    [
        "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol",
        "IBM|International Business Machines Corporation Common Stock|N|IBM|N|100|N|IBM",
        "BRK.B|Berkshire Hathaway Inc. Common Stock|N|BRK.B|N|100|N|BRK.B",
        "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY",
        "ABC.W|ABC Corp Warrant|A|ABC.W|N|100|N|ABC.W",
        "File Creation Time: 0601202612:00|||||||",
    ]
)


def test_parse_and_filter_symbol_directory_samples() -> None:
    rows = merge_rows(parse_nasdaq_listed(NASDAQ_SAMPLE), parse_other_listed(OTHER_SAMPLE))
    common = [row.symbol for row in rows if is_common_equity_candidate(row)]

    assert "AAPL" in common
    assert "IBM" in common
    assert "BRK.B" in common
    assert "TQQQ" not in common
    assert "SPY" not in common
    assert "ABC.W" not in common
    assert "ZTEST" not in common


def test_report_preserves_no_order_safety() -> None:
    rows = merge_rows(parse_nasdaq_listed(NASDAQ_SAMPLE), parse_other_listed(OTHER_SAMPLE))
    common = [row.symbol for row in rows if is_common_equity_candidate(row)]
    report = build_report(rows, common)

    assert report["summary"]["symbols"] == 7
    assert report["summary"]["common_equity_candidates"] == 3
    assert report["summary"]["order_created"] is False
    assert report["live_trading_authorized"] is False
    assert "no broker" in report["safety"]


def test_writes_csv_symbols_and_report_payload(tmp_path: Path) -> None:
    rows = merge_rows(parse_nasdaq_listed(NASDAQ_SAMPLE), parse_other_listed(OTHER_SAMPLE))
    common = [row.symbol for row in rows if is_common_equity_candidate(row)]
    csv_path = tmp_path / "symbols.csv"
    symbols_path = tmp_path / "common.txt"
    report = build_report(rows, common)

    write_csv(csv_path, rows)
    write_symbols(symbols_path, common)
    loaded_rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8", newline="")))
    payload = json.dumps(report)

    assert loaded_rows[0]["symbol"] == "AAPL"
    assert symbols_path.read_text(encoding="utf-8").splitlines() == ["AAPL", "BRK.B", "IBM"]
    assert "nasdaqtrader" in payload
