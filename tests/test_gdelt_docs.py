"""Documentation checks for GDELT news-attention collection."""

from __future__ import annotations

from conftest import PROJECT_ROOT


def test_readme_mentions_gdelt_collector() -> None:
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "gdelt_news_attention_snapshot.py" in text
    assert "rate_limited" in text


def test_free_data_plan_marks_gdelt_collector_implemented() -> None:
    text = (PROJECT_ROOT / "docs" / "free-data-source-expansion.md").read_text(encoding="utf-8")

    assert "Rate-limit-safe collector implemented" in text
    assert "GDELT collector script" in text
