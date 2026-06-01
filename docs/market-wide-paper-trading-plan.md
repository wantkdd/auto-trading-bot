# Market-wide paper trading plan

This project now treats `AAPL_0.3_GLD_0.7` as a locked baseline, not as the only possible strategy. The broader process is still paper-only: no broker, no credentials, no orders, no investment advice, and no live-trading authorization.

## Universe policy

The market-wide scan starts from `data/universe/us_large_liquid_watchlist.txt`, a large/liquid, non-leveraged US universe seed. It intentionally does **not** mean every tradable ticker is eligible. The scanner excludes leveraged/inverse symbols and should continue to exclude illiquid, newly listed, delisting-risk, stale-data, or structurally complex products before any paper-intent tracking.

Why this boundary exists:

- FINRA warns that auto-trading services can create unique data, credential, and risk-control problems, especially where AI profitability claims are marketed without registration or supervision.
- SEC investor guidance warns that auto-trading arrangements are high risk and that promises of reliable or extraordinary profits should be treated skeptically.
- FINRA day-trading disclosures highlight short-horizon losses, cost drag, and system-failure risk; this bot must avoid high-frequency/day-trading behavior unless a separate gate is approved.
- Portfolio-management practice emphasizes diversification, correlation, and drawdown/risk control rather than single-name return chasing.
- Broker paper trading is useful for simulation, but official broker docs warn that simulated execution does not prove real-world fill behavior.

## Source-backed policy inputs

The current policy is grounded in public professional/regulatory guidance reviewed on 2026-06-01:

- FINRA auto-trading alert: auto-trading creates data, credential-sharing, and control risks, especially where providers claim AI can reliably optimize profitability.
- SEC auto-trading investor alert: arrangements that let someone else trade without asking first can be highly risky; guaranteed-profit claims are red flags.
- FINRA day-trading disclosure and Investor.gov day-trading guidance: short-horizon trading can be unsuitable for limited resources or low risk tolerance and can be harmed by system failures and transaction costs.
- CFA Institute portfolio/risk material: evaluate diversification, correlation, drawdown, and risk-adjusted return instead of relying on isolated return.
- Broker API/paper docs: paper/sandbox fills are simulated and are not proof of real-world execution quality.

Repository consequence: the bot records hypothetical intents only and requires a separate broker-sandbox/live gate before any account connection.

## Daily no-order loop

GitHub Actions runs `.github/workflows/paper-observation.yml` after the US close window. The workflow:

1. Runs tests, lint, and type checks.
2. Refreshes the existing fundamental/macro/recent gates.
3. Runs `scripts/market_universe_candidate_scan.py` over the broad non-leveraged watchlist.
4. Keeps the locked paper strategy target weights unless a future promotion gate explicitly changes it.
5. Appends paper observation and hypothetical trade-intent logs.
6. Updates the status issue with observation, live-readiness, and market-scan summary fields.

## Buy and sell behavior

`scripts/paper_trade_intent_log.py` records both sides:

- `would_buy` when the hypothetical target position is larger than the current paper position.
- `would_sell` when the hypothetical target position is smaller.
- `would_hold` when allocation drift is below the rebalance threshold.

Every row includes `order_created: false`; it is a decision log, not a routed order.

## Continuous monitoring boundary

The current safe cadence is daily close-based observation. That is enough to test swing/position-style rules without pretending to have executable intraday fills. “Always watching and able to buy/sell anytime” requires a separate intraday-data and broker-sandbox gate covering stale data, exchange calendars, quote latency, slippage, partial fills, cancel/replace, idempotency, rate limits, account reconciliation, and kill-switch behavior.

Until that gate exists, intraday or second-level trading is out of scope.

## Promotion gate for changing the tracked strategy

A new market-wide candidate can replace the locked baseline only if it passes all of these paper-only checks:

- Non-leveraged/inverse filter.
- Walk-forward and holdout performance gate.
- Recent-regime gate, including post-2020, post-2022, AI-proxy post-2023, trailing 504-day, and trailing 252-day windows when data is available.
- Stock fundamentals gate for company legs using SEC data where applicable.
- Macro proxy review for defensive legs.
- At least 30 observed paper days after promotion to a candidate watch state.
- Explicit human approval before any future broker connection. This repository still contains no live-order path.
