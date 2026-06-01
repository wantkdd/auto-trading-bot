"""Documentation checks for BLS macro collection."""

from __future__ import annotations

from conftest import PROJECT_ROOT


def test_readme_mentions_bls_macro_snapshot() -> None:
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "bls_macro_snapshot.py" in text
    assert "bls-macro-snapshot-latest" in text


def test_free_data_plan_marks_bls_snapshot_implemented() -> None:
    text = (PROJECT_ROOT / "docs" / "free-data-source-expansion.md").read_text(encoding="utf-8")

    assert "No-key snapshot implemented" in text
    assert "BLS macro snapshot script" in text
