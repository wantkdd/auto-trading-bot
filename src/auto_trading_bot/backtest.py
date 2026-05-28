"""Offline, long-only, cash-only backtest engine with next-bar execution."""

from __future__ import annotations

from auto_trading_bot.data import validate_bars
from auto_trading_bot.domain import (
    BacktestConfig,
    BacktestResult,
    Bar,
    EquityPoint,
    SignalAction,
    StrategySignal,
    Trade,
    TradeSide,
)
from auto_trading_bot.metrics import summarize_metrics, total_return
from auto_trading_bot.strategies import Strategy

SAFETY_CAVEAT = "This MVP cannot place orders and is not approval for live trading."


def run_backtest(
    bars: tuple[Bar, ...],
    strategy: Strategy,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Run a deterministic local backtest.

    Signals generated from bar t are evaluated at bar t+1 open, preventing same-bar
    close-to-open look-ahead execution.
    """

    validated_bars = validate_bars(bars)
    active_config = config or BacktestConfig()
    signals = strategy.generate_signals(validated_bars)
    if len(signals) != len(validated_bars):
        raise ValueError("strategy must return exactly one signal per bar")

    cash = active_config.initial_cash
    position = 0
    trades: list[Trade] = []
    equity_curve: list[EquityPoint] = []

    for index, bar in enumerate(validated_bars):
        if index > 0:
            signal = signals[index - 1]
            cash, position, maybe_trade = _execute_signal(
                signal=signal,
                execution_bar=bar,
                cash=cash,
                position=position,
                config=active_config,
            )
            if maybe_trade is not None:
                trades.append(maybe_trade)

        equity_curve.append(
            EquityPoint(
                timestamp=bar.timestamp,
                cash=cash,
                position=position,
                close_price=bar.close,
                equity=cash + position * bar.close,
            )
        )

    curve = tuple(equity_curve)
    trade_tuple = tuple(trades)
    strategy_metrics = summarize_metrics(
        equity_curve=curve,
        trades=trade_tuple,
        initial_cash=active_config.initial_cash,
    )
    benchmark = _benchmark_metrics(validated_bars, active_config.initial_cash)

    warnings = (SAFETY_CAVEAT,)
    return BacktestResult(
        strategy_name=strategy.name,
        config=active_config,
        bars=validated_bars,
        signals=signals,
        trades=trade_tuple,
        equity_curve=curve,
        metrics=strategy_metrics,
        benchmark_metrics=benchmark,
        warnings=warnings,
    )


def _execute_signal(
    *,
    signal: StrategySignal,
    execution_bar: Bar,
    cash: float,
    position: int,
    config: BacktestConfig,
) -> tuple[float, int, Trade | None]:
    slippage_rate = config.slippage_bps / 10_000

    if signal.action is SignalAction.BUY and position == 0:
        price = execution_bar.open * (1 + slippage_rate)
        quantity = int(cash / (price * (1 + config.commission_rate)))
        if quantity < config.min_trade_quantity:
            return cash, position, None
        notional = quantity * price
        commission = notional * config.commission_rate
        slippage = quantity * execution_bar.open * slippage_rate
        updated_cash = cash - notional - commission
        updated_position = position + quantity
        return (
            updated_cash,
            updated_position,
            Trade(
                timestamp=execution_bar.timestamp,
                side=TradeSide.BUY,
                quantity=quantity,
                price=price,
                commission=commission,
                slippage=slippage,
                cash_after=updated_cash,
                position_after=updated_position,
                source_signal_at=signal.timestamp,
            ),
        )

    if signal.action is SignalAction.SELL and position > 0:
        price = execution_bar.open * (1 - slippage_rate)
        quantity = position
        notional = quantity * price
        commission = notional * config.commission_rate
        slippage = quantity * execution_bar.open * slippage_rate
        updated_cash = cash + notional - commission
        updated_position = 0
        return (
            updated_cash,
            updated_position,
            Trade(
                timestamp=execution_bar.timestamp,
                side=TradeSide.SELL,
                quantity=quantity,
                price=price,
                commission=commission,
                slippage=slippage,
                cash_after=updated_cash,
                position_after=updated_position,
                source_signal_at=signal.timestamp,
            ),
        )

    return cash, position, None


def _benchmark_metrics(bars: tuple[Bar, ...], initial_cash: float) -> dict[str, float | int | None]:
    first_open = bars[0].open
    shares = int(initial_cash / first_open)
    residual_cash = initial_cash - shares * first_open
    curve = tuple(
        EquityPoint(
            timestamp=bar.timestamp,
            cash=residual_cash,
            position=shares,
            close_price=bar.close,
            equity=residual_cash + shares * bar.close,
        )
        for bar in bars
    )
    return {
        "total_return": total_return(curve, initial_cash),
        "trade_count": 1 if shares > 0 else 0,
        "final_equity": curve[-1].equity,
    }
