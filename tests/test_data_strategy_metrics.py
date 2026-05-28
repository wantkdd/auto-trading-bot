"""Data validation, strategy, and metric regression tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from helpers import make_bars


def test_bar_rejects_invalid_ohlcv_values() -> None:
    from auto_trading_bot.domain import Bar, DomainValidationError

    with pytest.raises(DomainValidationError):
        Bar(datetime(2024, 1, 1), open=10, high=9, low=8, close=10, volume=100)
    with pytest.raises(DomainValidationError):
        Bar(datetime(2024, 1, 1), open=10, high=11, low=9, close=10, volume=-1)


def test_validate_bars_rejects_duplicates_and_unsorted_rows() -> None:
    from auto_trading_bot.data import DataValidationError, validate_bars

    bars = make_bars([10, 11, 12])
    duplicate = (bars[0], bars[0])
    unsorted_rows = (bars[1], bars[0])

    with pytest.raises(DataValidationError, match="duplicate"):
        validate_bars(duplicate)
    with pytest.raises(DataValidationError, match="sorted"):
        validate_bars(unsorted_rows)


def test_load_csv_bars_rejects_invalid_prices(tmp_path: Path) -> None:
    from auto_trading_bot.data import DataValidationError, load_csv_bars

    csv_path = tmp_path / "bad.csv"
    csv_path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2024-01-01T09:00:00,10,11,9,10,100\n"
        "2024-01-02T09:00:00,0,11,9,10,100\n",
        encoding="utf-8",
    )

    with pytest.raises(DataValidationError, match="invalid bar"):
        load_csv_bars(csv_path)


def test_momentum_strategy_waits_for_lookback_then_emits_directional_signals() -> None:
    from auto_trading_bot.domain import SignalAction
    from auto_trading_bot.strategies import MomentumStrategy

    bars = make_bars([100, 101, 103, 102])
    signals = MomentumStrategy(lookback=2, threshold=0.0).generate_signals(bars)

    assert [signal.action for signal in signals[:2]] == [SignalAction.HOLD, SignalAction.HOLD]
    assert signals[2].action is SignalAction.BUY
    assert signals[3].action is SignalAction.BUY


def test_moving_average_crossover_generates_expected_baseline_sequence() -> None:
    from auto_trading_bot.domain import SignalAction
    from auto_trading_bot.strategies import MovingAverageCrossoverStrategy

    bars = make_bars([10, 9, 8, 9, 10, 11, 9, 8])
    signals = MovingAverageCrossoverStrategy(short_window=2, long_window=3).generate_signals(bars)

    assert len(signals) == len(bars)
    assert [signal.action for signal in signals[:2]] == [SignalAction.HOLD, SignalAction.HOLD]
    assert SignalAction.BUY in [signal.action for signal in signals]
    assert SignalAction.SELL in [signal.action for signal in signals]


def test_max_drawdown_and_total_return_match_known_curve() -> None:
    from auto_trading_bot.domain import EquityPoint
    from auto_trading_bot.metrics import max_drawdown, total_return

    bars = make_bars([100, 110, 88, 132])
    curve = tuple(
        EquityPoint(
            timestamp=bar.timestamp,
            cash=equity,
            position=0,
            close_price=bar.close,
            equity=equity,
        )
        for bar, equity in zip(bars, [100.0, 120.0, 90.0, 135.0], strict=True)
    )

    assert total_return(curve, initial_cash=100.0) == pytest.approx(0.35)
    assert max_drawdown(curve) == pytest.approx(-0.25)
