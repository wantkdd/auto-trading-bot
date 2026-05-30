"""Regression checks for the offline strategy optimization evaluator script."""

from __future__ import annotations

import pytest
from scripts.strategy_optimization import (
    DonchianChannelStrategy,
    SmaTrendFilterStrategy,
    TrendMomentumStrategy,
    benchmark_total_return,
    build_static_portfolio_specs,
    build_strategy_specs,
)
from tests.helpers import make_bars

from auto_trading_bot.domain import SignalAction


def test_optimizer_includes_defensive_strategy_families() -> None:
    families = {spec.family for spec in build_strategy_specs()}

    assert "moving_average" in families
    assert "momentum" in families
    assert "sma_trend_filter" in families
    assert "donchian_channel" in families
    assert "trend_momentum" in families


def test_custom_strategy_signals_are_aligned_and_past_only() -> None:
    bars = make_bars([100 + index for index in range(80)])

    for strategy in (
        SmaTrendFilterStrategy(window=20),
        DonchianChannelStrategy(entry_window=20, exit_window=10),
        TrendMomentumStrategy(ma_window=20, lookback=10),
    ):
        signals = strategy.generate_signals(bars)

        assert len(signals) == len(bars)
        assert signals[0].action is SignalAction.HOLD
        assert any(signal.action is SignalAction.BUY for signal in signals)


def test_benchmark_total_return_uses_test_window_initial_equity() -> None:
    bars = make_bars([100.0, 110.0, 120.0], opens=[100.0, 110.0, 120.0])

    total_return, final_equity = benchmark_total_return(bars, 1_000.0)

    assert final_equity == 1_200.0
    assert total_return == pytest.approx(0.2)


def test_static_portfolio_specs_are_defensive_and_weighted() -> None:
    specs = build_static_portfolio_specs()

    assert specs
    for spec in specs:
        assert spec.family == "static_portfolio"
        assert set(spec.weights) == {"QQQ", "GLD"}
        assert sum(spec.weights.values()) == pytest.approx(1.0)
        assert 0 < spec.weights["QQQ"] < spec.weights["GLD"]
