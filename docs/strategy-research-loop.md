# Strategy research loop

This project remains an offline research simulator. No result in this document
authorizes live trading, broker integration, credential use, or investment advice.

## Current promoted research candidate

- Candidate: `static_portfolio_qqq_0.36_gld_0.64`
- Allocation: 36% QQQ / 64% GLD
- Evidence source: `.omx/reports/strategy-optimization-latest.{json,md}`
- Promotion level: **paper-trading research candidate only**

## Evidence gates

A candidate must pass all of these before moving from research to paper-trading
simulation:

1. Positive median out-of-sample excess return versus equal-weight SPY/QQQ/DIA.
2. No holdout excess return below -5 percentage points.
3. Worst out-of-sample max drawdown no worse than -20%.
4. Enough trades/windows to avoid a one-shot artifact.
5. Deep analysis report generated with yearly, monthly, stress-period, and rolling
   summaries.
6. SEC fundamentals and recent-regime validation generated from cached/public SEC
   data, with no leverage, no broker access, and no live-trading authorization.
7. Macro/news risk notes remain conservative: FRED macro automation requires a user
   API key, and public RSS/news checks are event-risk alerts rather than complete
   sentiment coverage.

A candidate may not move to any live-capital process until additional external
requirements exist outside this MVP: independent data-source validation, a dry-run
paper-trading service, drift monitoring, tax/cost review, and explicit human
approval.

## Latest deep-analysis finding

`static_portfolio_qqq_0.36_gld_0.64` passed the first optimizer gate, but the deep
analysis marked it as `review` rather than final pass:

- Full-period excess return was positive.
- COVID 2020 and inflation-bear 2022 stress periods outperformed the benchmark.
- Strong rebound years such as 2021 and 2023 underperformed because the defensive
  GLD allocation reduced upside capture.
- Rolling windows still include negative-excess intervals.

## Next experiments

Prioritize experiments that preserve drawdown control while improving upside
capture:

1. Adaptive QQQ/GLD allocation using QQQ trend and momentum state.
2. Monthly or quarterly rebalance variants with explicit cost assumptions.
3. Independent data-source replication for QQQ, GLD, SPY, DIA.
4. Daily dry-run signal generation that records target weights without placing
   orders.
5. Drift monitor that compares live dry-run behavior against historical rolling
   distributions.
6. Fundamental/macro/news-risk gate that records SEC filing metadata, recent 8-K
   counts, recent-regime windows after 2020/2022/2023, and explicit no-leverage
   constraints before any paper-trading promotion.

## Stop rules

Stop promoting a candidate if any of these are true:

- It requires live broker access to validate.
- It only passes by weakening the benchmark or drawdown gate.
- It has a single fragile window responsible for most excess return.
- It fails independent data-source replication.
