# Broad Market Data Feature Gate

This gate lets the bot pull and summarize a much wider US market context without automatically changing strategy code or placing orders. It is intentionally diagnostic-first: if the data is thin, stale, contradictory, or not validated, the output becomes `review` and must not be used for strategy promotion.

Safety boundary: no broker, no credentials, no submitted orders, no live-trading authorization, no automatic code rewriting, no leverage/margin/shorting/options/inverse or leveraged ETFs.

## What it adds

`scripts/market_data_feature_gate.py` reads the dynamic US liquid watchlist plus core cross-asset and sector ETFs, then writes:

- `.omx/reports/market-data-feature-gate-latest.json`
- `.omx/reports/market-data-feature-gate-latest.md`

The feature gate aggregates:

- breadth: usable asset coverage, percentage above 50/200-day moving averages, positive 20-day return ratio;
- momentum: 5/20/63/126-day returns;
- risk: 20-day realized volatility and 63-day max drawdown;
- sector leadership: best/worst sector ETF over 20 days and cyclical/defensive comparison;
- cross-asset context: SPY, QQQ, IWM, GLD, TLT, SHY, VNQ relationships;
- quality blockers: too few usable assets, low feature coverage, or stale/uneven latest dates.

## How the bot should use it

Use this report as a **gate and warning layer**, not as an automatic trading signal.

- `summary.status = pass`: data quality is good enough to consider as research context after walk-forward validation.
- `summary.status = review`: data is insufficient or market signals are conflicted; do not promote or increase exposure from this feature pack.
- `summary.use_for_strategy_promotion = false`: the bot should not use these features to promote a challenger or live pilot.
- Any `quality_gate.blockers`: stop using the broad data pack for strategy changes until fixed.

## Workflow integration

The daily paper-observation workflow runs the feature gate after building the dynamic liquid universe and before adaptive allocation review. The Discord report includes a compact summary so the operator can see whether the broad data pack is useful or should be ignored.

## Why this is safer than blindly adding data

More data can make a strategy worse through stale prices, survivorship bias, inconsistent vendor adjustments, data snooping, and regime overfitting. This gate therefore records broad features but refuses to treat them as actionable when coverage/freshness or signal agreement is poor.

