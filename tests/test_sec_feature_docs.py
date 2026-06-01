"""Documentation checks for SEC fundamental feature snapshots."""

from __future__ import annotations

from conftest import PROJECT_ROOT


def test_readme_documents_sec_feature_snapshot_command() -> None:
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "sec_fundamental_feature_snapshot.py" in text
    assert "sec-fundamental-snapshot.csv" in text
    assert "local cache-only" in text


def test_free_data_plan_mentions_sec_feature_snapshot() -> None:
    text = (PROJECT_ROOT / "docs" / "free-data-source-expansion.md").read_text(encoding="utf-8")

    assert "SEC feature snapshot script" in text
    assert "sec_fundamental_feature_snapshot.py" in text
