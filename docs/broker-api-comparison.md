# Broker API comparison for future paper trading

This comparison is the result of the deep-interview choice `Broker compare`. It intentionally stops before account connection, API-key handling, broker SDK installation, paper-order submission, or live-order submission.

Safety boundary: no broker credentials, no account access, no order routing, no paper API authorization, no live trading authorization, no margin, no leverage, no shorting, no options, no crypto, and no personalized investment advice.

## Decision

Do not connect a broker yet. The next safe implementation, if approved later, is still a broker-neutral **no-order adapter contract** with fixtures and safety tests.

Current recommendation:

1. **Alpaca** is the safest first future paper-only US equities API candidate after the no-order adapter exists. Official docs describe paper-only accounts, separate paper API keys, a separate paper endpoint, and documented simulation limitations.
2. **tastytrade** and **TradeStation** are strong second-phase sandbox/SIM candidates. They both document separated test environments, but tastytrade sandbox resets daily with delayed quotes, while TradeStation SIM/live switching requires strict base-URL guards and account/API-key eligibility checks.
3. **Tradier** and **E*TRADE** are viable only after heavier account/token plumbing is approved. Both document sandbox URLs; Tradier explicitly recommends sandbox order testing and preview, and E*TRADE requires preview-before-place semantics.
4. **Interactive Brokers** is powerful but operationally heavier because TWS/IB Gateway, GUI/session handling, paper/live username separation, data subscriptions, and daily/server reset behavior add risk.
5. **Charles Schwab Trader API** is not a safe first candidate until official public paper/sandbox documentation is available and reviewed. The official portal pages were accessible as URLs but did not expose crawlable details in this review.

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

Official docs describe free paper trading, paper-only accounts, a separate paper endpoint (`https://paper-api.alpaca.markets`), and different paper keys from live keys. Docs also warn that paper trading omits real-world effects such as market impact, information leakage, slippage, queue position, price improvement, regulatory fees, and dividends; paper accounts have fill/partial-fill assumptions and PDT-like checks.

User checks before implementation:

- Can the user create the intended Alpaca paper/live account from their residency/KYC situation?
- Is paper-only access enough for the next phase?
- Are IEX/data-plan limitations acceptable for no-order paper observation?

### tastytrade

Official sandbox docs describe a controlled open-API sandbox, separate REST and websocket hosts (`api.cert.tastyworks.com`, `streamer.cert.tastyworks.com`), daily reset of trades/transactions/positions/balances, and quotes that are always 15 minutes delayed.

User checks before implementation:

- Can sandbox credentials be created under the API terms?
- Are delayed quotes acceptable?
- Will daily reset behavior corrupt observation metrics or reconciliation logs?

### TradeStation

Official SIM docs describe a simulator API for paper trading with fake funded accounts, simulated executions, and a separate SIM base URL (`https://sim-api.tradestation.com/v3`) from live (`https://api.tradestation.com/v3`). Docs explicitly warn about mistakes in applications that switch between SIM and live.

User checks before implementation:

- Can the user obtain a TradeStation account/API key and SIM access?
- Is the standard auth flow acceptable for local/cloud development?
- Are rate limits and streaming quotas compatible with the planned polling cadence?

### Tradier

Tradier docs describe production and sandbox environments. Trading docs require a Brokerage account, account ID, and API token. The sandbox base URL is for paper trading, supports the full trading API with paper money and delayed market data, and docs recommend previewing orders before submission.

User checks before implementation:

- Can the user open/maintain a Tradier Brokerage account?
- Can sandbox token/account access be created?
- Are delayed sandbox data constraints acceptable?

### E*TRADE

Official docs publish live and sandbox URLs for accounts and orders. The Order API documents preview, place, change-preview, change-place, cancel, and list endpoints; place order is submitted after a successful preview, and preview IDs must match and be used promptly. OAuth access-token handling is required.

User checks before implementation:

- Can developer/sandbox access be obtained?
- Can OAuth callback and token handling be completed without storing secrets in repo or CI?
- Are market-data agreement and delayed-data constraints acceptable?

### Interactive Brokers

IBKR TWS API docs say the API requires a running TWS or IB Gateway session; headless operation without a GUI is not supported. Paper trading is available after a regular account has been approved and funded. Setup docs also warn about paper/live username interactions, market-data subscription separation, daily restarts, and ensuring clients connect to the correct paper vs live port.

User checks before implementation:

- Is the account approved/funded and eligible for paper trading?
- Can market-data subscriptions be shared or separately configured for paper?
- Is a GUI/gateway session acceptable for cloud automation?

### Charles Schwab Trader API

The official Trader API portal URL was reachable, but the public pages accessed during this review did not expose crawlable paper/sandbox details. Do not choose Schwab for a first paper/sandbox path until official docs confirm sandbox availability, app approval, auth, market-data, and order-preview constraints.

User checks before implementation:

- Confirm from Schwab official docs whether an individual paper/sandbox environment exists.
- Confirm app approval and OAuth requirements.
- Confirm market-data and order-preview behavior.

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

- Alpaca Paper Trading: https://docs.alpaca.markets/us/v1.4.2/docs/paper-trading
- Alpaca Trading API: https://docs.alpaca.markets/v1.3/docs/trading-api
- Alpaca Market Data API: https://docs.alpaca.markets/us/docs/about-market-data-api
- Alpaca account requirements: https://alpaca.markets/support/requirements-alpaca-brokerage-account
- tastytrade sandbox: https://developer.tastytrade.com/sandbox/
- TradeStation SIM vs. LIVE: https://api.tradestation.com/docs/fundamentals/sim-vs-live/
- TradeStation authentication overview: https://api.tradestation.com/docs/fundamentals/authentication/auth-overview/
- Tradier Trading API: https://docs.tradier.com/docs/trading
- Tradier endpoints: https://docs.tradier.com/docs/endpoints
- E*TRADE Order API: https://apisb.etrade.com/docs/api/order/api-order-v1.html
- E*TRADE authorization: https://apisb.etrade.com/docs/api/authorization/get_access_token.html
- IBKR TWS API introduction: https://interactivebrokers.github.io/tws-api/introduction.html
- IBKR TWS API setup: https://interactivebrokers.github.io/tws-api/initial_setup.html
- Schwab Trader API portal: https://developer.schwab.com/products/trader-api--individual
- FINRA day trading: https://www.finra.org/investors/investing/investment-products/stocks/day-trading
