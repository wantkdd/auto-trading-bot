# Broker API comparison for future paper trading

This comparison is the result of the deep-interview choice `Broker compare`. It intentionally stops before account connection, API-key handling, broker SDK installation, or order submission.

Safety boundary: no broker credentials, no account access, no order routing, no live trading authorization, no margin, no leverage, no shorting, no options, and no personalized investment advice.

## Decision

Do not connect a broker yet. The next safe implementation, if approved later, is a broker-neutral **no-order adapter contract** with fixtures and safety tests.

Current recommendation:

1. **Alpaca** is the simplest first candidate for future paper-only US equities API work if account availability and data limits are acceptable.
2. **Tradier** is a viable second candidate if account eligibility is confirmed; sandbox/live base URL separation is clear, but sandbox uses delayed market data.
3. **IBKR** is powerful and globally relevant, but operationally heavier because Web API/TWS gateway, paper credentials, account type, data subscriptions, session resets, and local gateway uptime require more engineering.

## Why not connect now?

The current bot is still validating signal quality. Connecting any broker, even paper, adds a new failure class:

- credential leakage;
- live/paper endpoint mixups;
- stale/delayed data treated as real time;
- duplicate orders;
- partial fills and rejects;
- account reconciliation drift;
- market-hours and corporate-action errors;
- day-trading/margin rule violations.

So the next build step should be adapter design and tests, not keys.

## Candidate notes

### Alpaca

Official docs describe a Trading API and free paper trading. Alpaca market-data docs state the Basic plan is free but limited for equities to IEX real-time coverage, 30 websocket symbols, historical data since 2016, and a latest-15-minute historical limitation; broader stock-exchange coverage requires Algo Trader Plus.

User checks before implementation:

- Can the user create an Alpaca account from their residency/KYC situation?
- Is paper-only access enough for the next phase?
- Is IEX-only Basic data acceptable for no-order paper observation?

### Interactive Brokers

IBKR Web API docs say individual Web API use requires an IBKR username/password and that live or simulated paper access requires a fully open and funded IBKR Pro account. Client Portal API docs describe unique paper usernames/passwords and local gateway authentication.

User checks before implementation:

- Is the account IBKR Pro and fully open/funded if Web API paper access is desired?
- Can market-data subscriptions be shared to paper?
- Is a local Client Portal/TWS gateway acceptable for cloud automation?

### Tradier

Tradier docs describe production and sandbox environments. Trading docs require a Brokerage account, account ID, and API token. The sandbox base URL is for paper trading and delayed market data.

User checks before implementation:

- Can the user open/maintain a Tradier Brokerage account?
- Can sandbox token/account access be created?
- Are delayed sandbox data constraints acceptable?

## Preconditions before any future paper-order adapter

- Human approval for paper API only, not live.
- Separate paper and live base URLs.
- No live credentials stored in repo or CI.
- Order preview/dry-run mode first.
- Idempotency keys for every hypothetical order.
- Max notional and max daily loss checks.
- Kill-switch file/env gate that defaults to disabled.
- Full order-state reconciliation logs.
- Tests proving live endpoint strings cannot be used unless an explicit later gate is passed.

## References

- Alpaca Trading API: https://docs.alpaca.markets/v1.3/docs/trading-api
- Alpaca Market Data API: https://docs.alpaca.markets/us/docs/about-market-data-api
- Alpaca account requirements: https://alpaca.markets/support/requirements-alpaca-brokerage-account
- IBKR API home: https://www.interactivebrokers.com/campus/ibkr-api-page/
- IBKR Web API: https://www.interactivebrokers.com/campus/ibkr-api-page/webapi-doc/
- IBKR Client Portal API v1: https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/
- Tradier Trading API: https://docs.tradier.com/docs/trading
- Tradier endpoints: https://docs.tradier.com/docs/endpoints
- FINRA day trading: https://www.finra.org/investors/investing/investment-products/stocks/day-trading
