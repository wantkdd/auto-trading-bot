"""Docs checks for free data-source expansion."""

from __future__ import annotations

from conftest import PROJECT_ROOT


def test_free_data_source_expansion_documents_no_order_sources() -> None:
    text = (PROJECT_ROOT / "docs" / "free-data-source-expansion.md").read_text(encoding="utf-8")

    assert "Nasdaq Trader" in text
    assert "SEC EDGAR" in text
    assert "OpenDART" in text
    assert "GDELT" in text
    assert "no key" in text
    assert "Free key" in text or "free-key" in text
    assert "live orders" in text


def test_readme_mentions_broad_symbol_universe_refresh() -> None:
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "us_symbol_universe_refresh.py" in text
    assert "common-equity candidates" in text
    assert "free-data-source-expansion.md" in text
