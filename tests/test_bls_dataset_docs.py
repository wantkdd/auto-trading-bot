"""Documentation checks for BLS macro joins into modeling datasets."""

from __future__ import annotations

from conftest import PROJECT_ROOT


def test_readme_documents_bls_macro_dataset_join() -> None:
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "cached OHLCV plus BLS macro context" in text
    assert "conservatively lagged" in text


def test_training_roadmap_marks_bls_join_implemented() -> None:
    text = (PROJECT_ROOT / "docs" / "training-data-and-modeling-roadmap.md").read_text(
        encoding="utf-8"
    )

    assert "BLS no-key snapshot and point-in-time join implemented" in text
    assert "cached daily price/volume plus conservative BLS macro joins" in text
