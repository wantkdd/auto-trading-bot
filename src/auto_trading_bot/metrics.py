"""Backtest metric calculations with deterministic pure-Python math."""

from __future__ import annotations

from math import sqrt
from statistics import fmean, pstdev

from auto_trading_bot.domain import EquityPoint, Trade, TradeSide

TRADING_DAYS_PER_YEAR = 252


def total_return(equity_curve: tuple[EquityPoint, ...], initial_cash: float) -> float:
    if not equity_curve:
        return 0.0
    return (equity_curve[-1].equity / initial_cash) - 1.0


def periodic_returns(equity_curve: tuple[EquityPoint, ...]) -> tuple[float, ...]:
    returns: list[float] = []
    for previous, current in zip(equity_curve, equity_curve[1:], strict=False):
        if previous.equity <= 0:
            returns.append(0.0)
        else:
            returns.append((current.equity / previous.equity) - 1.0)
    return tuple(returns)


def cagr(equity_curve: tuple[EquityPoint, ...], initial_cash: float) -> float | None:
    if len(equity_curve) < 2:
        return None
    elapsed_days = (equity_curve[-1].timestamp - equity_curve[0].timestamp).days
    if elapsed_days <= 0 or initial_cash <= 0:
        return None
    years = elapsed_days / 365.25
    return (equity_curve[-1].equity / initial_cash) ** (1 / years) - 1.0


def volatility(returns: tuple[float, ...], annualization: int = TRADING_DAYS_PER_YEAR) -> float | None:
    if len(returns) < 2:
        return None
    return pstdev(returns) * sqrt(annualization)


def sharpe_ratio(
    returns: tuple[float, ...],
    risk_free_rate: float = 0.0,
    annualization: int = TRADING_DAYS_PER_YEAR,
) -> float | None:
    if len(returns) < 2:
        return None
    per_period_rf = risk_free_rate / annualization
    excess = tuple(value - per_period_rf for value in returns)
    deviation = pstdev(excess)
    if deviation == 0:
        return None
    return fmean(excess) / deviation * sqrt(annualization)


def sortino_ratio(
    returns: tuple[float, ...],
    risk_free_rate: float = 0.0,
    annualization: int = TRADING_DAYS_PER_YEAR,
) -> float | None:
    if len(returns) < 2:
        return None
    per_period_rf = risk_free_rate / annualization
    excess = tuple(value - per_period_rf for value in returns)
    downside = tuple(min(0.0, value) for value in excess)
    downside_deviation = sqrt(fmean(tuple(value * value for value in downside)))
    if downside_deviation == 0:
        return None
    return fmean(excess) / downside_deviation * sqrt(annualization)


def max_drawdown(equity_curve: tuple[EquityPoint, ...]) -> float:
    peak = 0.0
    worst = 0.0
    for point in equity_curve:
        peak = max(peak, point.equity)
        if peak > 0:
            drawdown = (point.equity / peak) - 1.0
            worst = min(worst, drawdown)
    return worst


def win_rate(trades: tuple[Trade, ...]) -> float | None:
    round_trips = _round_trip_pnls(trades)
    if not round_trips:
        return None
    wins = sum(1 for pnl in round_trips if pnl > 0)
    return wins / len(round_trips)


def turnover(trades: tuple[Trade, ...], equity_curve: tuple[EquityPoint, ...]) -> float:
    if not equity_curve:
        return 0.0
    average_equity = fmean(point.equity for point in equity_curve)
    if average_equity <= 0:
        return 0.0
    traded_value = sum(trade.notional for trade in trades)
    return traded_value / average_equity


def exposure(equity_curve: tuple[EquityPoint, ...]) -> float:
    if not equity_curve:
        return 0.0
    invested = sum(1 for point in equity_curve if point.position > 0)
    return invested / len(equity_curve)


def summarize_metrics(
    *,
    equity_curve: tuple[EquityPoint, ...],
    trades: tuple[Trade, ...],
    initial_cash: float,
) -> dict[str, float | int | None]:
    returns = periodic_returns(equity_curve)
    return {
        "total_return": total_return(equity_curve, initial_cash),
        "cagr": cagr(equity_curve, initial_cash),
        "volatility": volatility(returns),
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "max_drawdown": max_drawdown(equity_curve),
        "win_rate": win_rate(trades),
        "turnover": turnover(trades, equity_curve),
        "exposure": exposure(equity_curve),
        "trade_count": len(trades),
        "final_equity": equity_curve[-1].equity if equity_curve else initial_cash,
    }


def _round_trip_pnls(trades: tuple[Trade, ...]) -> tuple[float, ...]:
    open_cost = 0.0
    open_quantity = 0
    pnls: list[float] = []

    for trade in trades:
        gross = trade.quantity * trade.price
        total_cost = gross + trade.commission + trade.slippage
        if trade.side is TradeSide.BUY:
            open_cost += total_cost
            open_quantity += trade.quantity
        elif trade.side is TradeSide.SELL and open_quantity:
            sell_proceeds = gross - trade.commission - trade.slippage
            closed_fraction = trade.quantity / open_quantity
            allocated_cost = open_cost * closed_fraction
            pnls.append(sell_proceeds - allocated_cost)
            open_cost -= allocated_cost
            open_quantity -= trade.quantity
    return tuple(pnls)
