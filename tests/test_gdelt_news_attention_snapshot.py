"""Tests for GDELT news-attention snapshots."""

from __future__ import annotations

import argparse
import json
import urllib.error
from pathlib import Path

from scripts import gdelt_news_attention_snapshot as gdelt


def args(tmp_path: Path, **overrides) -> argparse.Namespace:
    values = {
        "symbols": ["AAPL", "MSFT"],
        "symbols_file": str(tmp_path / "symbols.txt"),
        "max_symbols": 2,
        "max_records": 2,
        "output": str(tmp_path / "gdelt.json"),
        "markdown": str(tmp_path / "gdelt.md"),
        "timeout": 1.0,
        "sleep_seconds": 0.0,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_build_report_collects_compact_articles(monkeypatch, tmp_path: Path) -> None:
    def fake_fetch(symbol: str, *, max_records: int, timeout: float) -> dict[str, object]:
        return {
            "symbol": symbol,
            "status": "ok",
            "article_count": 1,
            "articles": [{"title": f"{symbol} news", "url": "https://example.test"}],
        }

    monkeypatch.setattr(gdelt, "fetch_symbol", fake_fetch)

    report = gdelt.build_report(args(tmp_path))

    assert report["summary"]["status"] == "ok"
    assert report["summary"]["completed_symbols"] == 2
    assert report["summary"]["article_samples"] == 2
    assert report["summary"]["order_created"] is False
    assert report["live_trading_authorized"] is False


def test_rate_limit_writes_rate_limited_status(monkeypatch, tmp_path: Path) -> None:
    def fake_fetch(symbol: str, *, max_records: int, timeout: float) -> dict[str, object]:
        raise urllib.error.HTTPError("https://example.test", 429, "Too Many", {}, None)

    monkeypatch.setattr(gdelt, "fetch_symbol", fake_fetch)

    report = gdelt.build_report(args(tmp_path))

    assert report["status"] == "rate_limited"
    assert report["summary"]["rate_limited"] is True
    assert report["rows"][0]["status"] == "rate_limited"


def test_script_writes_json_and_markdown(monkeypatch, tmp_path: Path) -> None:
    def fake_fetch(symbol: str, *, max_records: int, timeout: float) -> dict[str, object]:
        return {"symbol": symbol, "status": "ok", "article_count": 0, "articles": []}

    monkeypatch.setattr(gdelt, "fetch_symbol", fake_fetch)
    output = tmp_path / "gdelt.json"
    markdown = tmp_path / "gdelt.md"

    assert (
        gdelt.main(
            [
                "--symbols",
                "AAPL",
                "--output",
                str(output),
                "--markdown",
                str(markdown),
                "--sleep-seconds",
                "0",
            ]
        )
        == 0
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["symbols"] == 1
    assert "GDELT news-attention" in markdown.read_text(encoding="utf-8")
