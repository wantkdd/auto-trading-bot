# Training data and modeling roadmap

This roadmap answers the key question: if years of price, filings, macro, and news data exist on the web, how should the bot collect and use them before becoming a stronger no-order paper trading system?

Safety boundary: this repository remains research/paper-only. It must not add broker credentials, account access, live orders, margin, leverage, shorting, derivatives, or personalized investment advice.

## Decision

Do **not** fine-tune first. Build a point-in-time dataset and evaluate simple, auditable models before any LLM fine-tuning.

The final bot should be a layered decision system:

1. Data collectors create auditable raw caches.
2. Feature builders convert raw data into point-in-time features.
3. Label builders calculate forward outcomes only for training/evaluation, never as decision-time inputs.
4. Baseline models prove whether the data adds signal after costs.
5. Paper observers log `would_buy`, `would_sell`, and `would_hold` without orders.
6. LLMs summarize news/filings and produce reason codes; they do not directly route orders.

## What to collect

| Group | Data | Purpose | Current status |
| --- | --- | --- | --- |
| Price/volume | Daily and later intraday OHLCV, corporate-action-adjusted prices, volume | trend, volatility, drawdown, relative strength, labels | daily Yahoo cache exists; point-in-time dataset builder exists; Nasdaq Trader universe refresh exists; independent OHLCV source still needed |
| Fundamentals | SEC companyfacts and submissions | quality, profitability, balance-sheet, filing-event gates | partially implemented |
| Macro regime | FRED/ALFRED rates, yield curve, inflation, labor, credit proxies | market regime and risk throttle | planned; API key may be required |
| News/events | News API, SEC 8-K/10-Q/10-K, earnings calendar | event risk, sentiment/attention, thesis-break flags | SEC event count exists; news not collected yet |
| Portfolio state | paper positions, target weights, drift, drawdown | convert scores into buy/sell/hold with risk caps | paper intent logging exists |

## How to use the data

### Point-in-time rule

Every training row must represent one decision timestamp. A feature is allowed only if it was publicly available at or before that timestamp.

Examples:

- SEC revenue growth: allowed only after the SEC `filed` date.
- News: allowed only after article publication time.
- Macro: use release/vintage timing; revised final values cannot be backfilled into earlier decisions.
- Price: use only completed bars available before the decision.

### Labels

Labels are for training/evaluation only:

- forward 1-day, 5-day, 20-day return
- forward excess return vs benchmark
- forward max drawdown
- whether a buy/sell/hold rule would have improved risk-adjusted return after costs

The label window must never leak into features.

### Model ladder

1. Scorecard/rules: transparent first baseline.
2. Logistic/regularized models: check whether features have stable directional value.
3. Tree models: only if baselines pass, with calibration and feature-importance audit.
4. LLM extraction: summarize filings/news into structured flags and reason codes.
5. Fine-tuning: only after a large labeled decision/outcome corpus exists and proves uplift over retrieval + baseline models.

## Why fine-tuning is later

Fine-tuning without a clean labeled dataset usually teaches hindsight stories, not tradable signal. A fine-tuned model can look impressive while learning data leakage, survivorship bias, vendor quirks, or market-regime coincidences.

Fine-tuning becomes reasonable only when:

- many decision-time examples exist across different regimes;
- every example has source timestamps and outcome labels;
- simple baselines are already beaten out-of-sample;
- the fine-tuned model is used for event classification or explanation, not direct order routing.

## Next implementation sequence

1. Generate a data-source registry report. **Expanded to 13 free/free-key sources and a broad Nasdaq Trader US universe refresh.**
2. Build a point-in-time feature dataset for daily decisions over the existing 90-symbol universe. **Done for cached daily price/volume via `scripts/point_in_time_dataset.py`.**
3. Add forward-label generation with no-lookahead tests. **Done for 1/5/20-day returns, 20-day benchmark excess return, and 20-day forward max drawdown.**
4. Compare scorecard/logistic baselines against current static defensive pairs. **Scorecard baseline evaluator exists via `scripts/scorecard_baseline_report.py`; logistic/regularized models remain later.**
5. Add news/event collection only after source/API constraints are explicit.
6. Add intraday no-order observer only after market-data source freshness and cost are known.
