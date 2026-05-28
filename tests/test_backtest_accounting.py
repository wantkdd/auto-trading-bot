"""Backtest accounting and timing safety tests."""

from __future__ import annotations

import pytest

from helpers import make_bars


class ScriptedStrategy:
    name = "scripted_test_strategy"

    def __init__(self, actions):
        self._actions = actions

    def generate_signals(self, bars):
        from auto_trading_bot.domain import StrategySignal

        return tuple(
            StrategySignal(timestamp=bar.timestamp, action=action, reason="scripted")
            for bar, action in zip(bars, self._actions, strict=True)
        )


def test_signal_at_bar_t_executes_at_next_bar_open_only() -> None:
    from auto_trading_bot.backtest import run_backtest
    from auto_trading_bot.domain import BacktestConfig, SignalAction, TradeSide

    bars = make_bars([10, 20, 30], opens=[10, 20, 30])
    result = run_backtest(
        bars,
        ScriptedStrategy([SignalAction.BUY, SignalAction.HOLD, SignalAction.HOLD]),
        BacktestConfig(initial_cash=100.0, commission_rate=0.0, slippage_bps=0.0),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side is TradeSide.BUY
    assert trade.source_signal_at == bars[0].timestamp
    assert trade.timestamp == bars[1].timestamp
    assert trade.price == pytest.approx(bars[1].open)
    assert result.equity_curve[0].position == 0
    assert result.equity_curve[1].position == 5


def test_buy_accounting_includes_commission_and_slippage_without_negative_cash() -> None:
    from auto_trading_bot.backtest import run_backtest
    from auto_trading_bot.domain import BacktestConfig, SignalAction, TradeSide

    bars = make_bars([10, 10, 10], opens=[10, 10, 10])
    result = run_backtest(
        bars,
        ScriptedStrategy([SignalAction.BUY, SignalAction.HOLD, SignalAction.HOLD]),
        BacktestConfig(initial_cash=100.0, commission_rate=0.01, slippage_bps=100.0),
    )

    trade = result.trades[0]
    assert trade.side is TradeSide.BUY
    assert trade.price == pytest.approx(10.10)
    assert trade.commission == pytest.approx(trade.quantity * trade.price * 0.01)
    assert trade.slippage == pytest.approx(trade.quantity * 10.0 * 0.01)
    assert trade.cash_after >= -1e-9
    assert all(point.cash >= -1e-9 for point in result.equity_curve)


def test_sell_accounting_closes_long_position_without_shorting() -> None:
    from auto_trading_bot.backtest import run_backtest
    from auto_trading_bot.domain import BacktestConfig, SignalAction, TradeSide

    bars = make_bars([10, 10, 12, 12], opens=[10, 10, 12, 12])
    result = run_backtest(
        bars,
        ScriptedStrategy(
            [SignalAction.BUY, SignalAction.SELL, SignalAction.HOLD, SignalAction.HOLD]
        ),
        BacktestConfig(initial_cash=100.0, commission_rate=0.0, slippage_bps=0.0),
    )

    assert [trade.side for trade in result.trades] == [TradeSide.BUY, TradeSide.SELL]
    assert result.trades[1].timestamp == bars[2].timestamp
    assert result.trades[1].position_after == 0
    assert all(point.position >= 0 for point in result.equity_curve)
    assert result.final_equity == pytest.approx(120.0)


def test_initial_sell_signal_does_not_create_short_position() -> None:
    from auto_trading_bot.backtest import run_backtest
    from auto_trading_bot.domain import BacktestConfig, SignalAction

    bars = make_bars([10, 9, 8], opens=[10, 9, 8])
    result = run_backtest(
        bars,
        ScriptedStrategy([SignalAction.SELL, SignalAction.HOLD, SignalAction.HOLD]),
        BacktestConfig(initial_cash=100.0, commission_rate=0.0, slippage_bps=0.0),
    )

    assert result.trades == ()
    assert all(point.position == 0 for point in result.equity_curve)
    assert result.final_equity == pytest.approx(100.0)
