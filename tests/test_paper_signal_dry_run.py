"""Safety and pure-function checks for paper dry-run signal generation."""

from __future__ import annotations

import pytest
from scripts.paper_signal_dry_run import build_warnings, normalize_weights


def test_normalize_weights_preserves_relative_allocation() -> None:
    weights = normalize_weights({"QQQ": 36.0, "GLD": 64.0})

    assert weights == {"QQQ": pytest.approx(0.36), "GLD": pytest.approx(0.64)}


def test_dry_run_warnings_prevent_order_promotion() -> None:
    warnings = build_warnings(
        {"QQQ": 0.36, "GLD": 0.64},
        {
            "QQQ": {"volume": 100},
            "GLD": {"volume": 100},
        },
    )

    assert any("do not place orders" in warning for warning in warnings)
    assert any("research review" in warning for warning in warnings)
