"""Tests for no-order paper trade intent logging."""

from __future__ import annotations

import pytest
from scripts.paper_trade_intent_log import build_intent, build_trade_intents, normalized_weights


def signal(as_of: str, aapl: float = 100.0, gld: float = 200.0) -> dict[str, object]:
    return {
        "as_of_date": as_of,
        "strategy": "AAPL_0.3_GLD_0.7",
        "target_weights": {"AAPL": 0.3, "GLD": 0.7},
        "source_bars": {"AAPL": {"close": aapl}, "GLD": {"close": gld}},
    }


def test_first_intent_logs_would_buy_without_creating_orders() -> None:
    intent = build_intent(
        signal=signal("2026-05-29"),
        previous_intents=[],
        initial_equity=10_000.0,
        rebalance_threshold=0.02,
    )

    assert intent["decision"] == "would_rebalance"
    assert intent["hypothetical_positions_after_intent"] == {"AAPL": 30, "GLD": 35}
    assert all(row["order_created"] is False for row in intent["trade_intents"])
    assert "no orders" in intent["safety"]


def test_second_intent_holds_when_drift_is_small() -> None:
    first = build_intent(
        signal=signal("2026-05-29"),
        previous_intents=[],
        initial_equity=10_000.0,
        rebalance_threshold=0.02,
    )
    second = build_intent(
        signal=signal("2026-06-01", aapl=101.0, gld=200.0),
        previous_intents=[first],
        initial_equity=10_000.0,
        rebalance_threshold=0.02,
    )

    assert second["decision"] == "would_hold"
    assert second["trade_intents"] == []


def test_build_trade_intents_uses_would_buy_and_would_sell_language() -> None:
    rows = build_trade_intents(
        {"AAPL": 10, "GLD": 10}, {"AAPL": 12, "GLD": 8}, {"AAPL": 100.0, "GLD": 200.0}
    )

    assert [row["side"] for row in rows] == ["would_buy", "would_sell"]


def test_normalized_weights_rejects_leverage_like_negative_weight() -> None:
    with pytest.raises(SystemExit):
        normalized_weights({"AAPL": 1.2, "GLD": -0.2})
