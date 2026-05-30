"""Safety and pure-function checks for paper dry-run signal generation."""

from __future__ import annotations

from datetime import datetime

import pytest
from scripts.paper_signal_dry_run import (
    build_warnings,
    constrain_bars_to_window,
    normalize_weights,
    parse_weight_pairs,
)

from auto_trading_bot.domain import Bar


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


def test_parse_weight_pairs_uppercases_and_parses_symbols() -> None:
    assert parse_weight_pairs(["aapl=30", "GLD=70"]) == {"AAPL": 30.0, "GLD": 70.0}


def test_normalize_weights_rejects_negative_values() -> None:
    with pytest.raises(SystemExit):
        normalize_weights({"AAPL": 0.3, "GLD": -0.1})


def test_constrain_bars_to_requested_window_prevents_cache_lookahead() -> None:
    bars = (
        Bar(datetime(2026, 5, 28), 1.0, 1.0, 1.0, 1.0, 1.0),
        Bar(datetime(2026, 5, 29), 1.0, 1.0, 1.0, 1.0, 1.0),
    )

    filtered = constrain_bars_to_window(
        bars, start=datetime(2026, 1, 1).date(), end=datetime(2026, 5, 28).date()
    )

    assert [bar.timestamp.date().isoformat() for bar in filtered] == ["2026-05-28"]
