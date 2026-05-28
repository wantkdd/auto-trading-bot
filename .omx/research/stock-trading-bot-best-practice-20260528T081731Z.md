# Best-Practice Research: Stock Auto-Trading Bot MVP (KR vs US)

Date: 2026-05-28
Scope: source-backed planning evidence for a greenfield MVP that excludes live auto-orders and focuses on robust validation/paper trading.

## Direct Recommendation

Build the MVP as a **broker-agnostic Python validation system** first, with hard safety boundaries:

1. **No live automatic orders in MVP.** Implement only backtesting, validation reports, and paper-trading adapters behind explicit dry-run interfaces.
2. **Prefer US/Alpaca for the first end-to-end paper-trading path** if the user can open/use Alpaca, because official docs provide a paper endpoint, Python SDK, historical/real-time data, and paper/live API parity. Caveat: Basic plan US equity data is limited to IEX real-time and 15-minute-restricted historical access; full SIP coverage is paid.
3. **For Korea, treat KRX/FSC/KIS as a serious candidate but do a research-first adapter.** KRX and the Korean public data portal provide official market data paths; KIS provides official sample code and Open API examples including strategy builder/backtester references. However, account/API-key requirements, terms, request limits, and mock-vs-real endpoints must be validated before any production adapter.
4. **Use simple, explainable baseline strategies first** (moving-average crossover, momentum, volatility breakout) and disqualify quickly if performance depends on unrealistic assumptions.
5. **Use a conservative validation protocol**: data integrity checks, cost/slippage assumptions, train/test or walk-forward splits, benchmark comparison, drawdown/turnover stress, and paper trading after backtest.

## Evidence Used

### Korea / KRX / KIS
- KRX Open API service introduces an official interface for using statistical information from KRX Information Data System in web/mobile apps: https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO001.jsp
- KRX Open API terms require authentication-key application and note terms/limits; the terms mention request caps, non-commercial restrictions, and that KRX does not guarantee accuracy/completeness or continuous provision: https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO005.jsp
- KRX data products include real-time and end-of-day market information for securities/derivatives and list stock real-time fields such as trade price and 10-level quotes: https://openapi.krx.co.kr/contents/OPP/DATA/OPPDATA002.jsp
- Korean public data portal page for FSC stock-price information says listed stock prices are KRX-provided, REST JSON/XML, free, and daily-updated with business-day lag caveats: https://www.data.go.kr/en/data/15094808/openapi.do
- Korea Investment & Securities official GitHub sample repository states it provides Python/LLM-friendly sample code for KIS Open API, with examples, strategy_builder, and backtester folders: https://github.com/koreainvestment/open-trading-api
- Korea Investment eFriend Expert Open API page states API usage requires Korean Investment account/HTS service, has no separate API use fee beyond HTS commission, and recommends sufficient mock-investment testing before use: https://www.trueetn.com/main/customer/systemdown/OpenAPI.jsp

### US / Alpaca / IBKR
- Alpaca Market Data API docs describe HTTP/WebSocket historical and real-time data and SDKs for Python/Go/Node/C#: https://docs.alpaca.markets/us/docs/about-market-data-api
- Alpaca Trading API Basic plan is free for paper/live users but US equities real-time coverage is IEX-only; Algo Trader Plus provides all US exchanges at a paid tier: https://docs.alpaca.markets/us/docs/about-market-data-api
- Alpaca paper trading docs state paper trading is free, uses a separate paper endpoint/key, has a default paper balance, and is only a simulation with fill/liquidity differences from live: https://github.com/alpacahq/alpaca-docs/blob/master/content/trading/paper-trading.md
- IBKR paper trading docs say paper accounts simulate trading with real market conditions, can share real-time market data, and help test strategies without risking capital: https://www.ibkrguides.com/clientportal/papertradingaccount.htm?Highlight=paper+trading+account
- IBKR API docs/support warn API/code use carries no liability for trading losses and market-data redistribution is restricted: https://interactivebrokers.github.io/

### Risk / Regulatory Caution
- SEC investor guidance warns day trading can cause substantial losses and is risky for inexperienced traders: https://www.sec.gov/about/reports-publications/investorpubsdaytipshtm
- FINRA day-trading guidance should be checked before US intraday/margin behavior; current rules and upcoming margin changes can affect live trading assumptions: https://www.finra.org/investors/investing/investment-products/stocks/day-trading

### Backtesting Engine Candidate
- QuantConnect LEAN is an open-source algorithmic trading engine for research, backtesting, and live trading, but it may be overkill for a small MVP and needs data plumbing: https://www.quantconnect.com/docs/v2/lean-engine/getting-started
- Backtrader is a Python backtesting framework focused on reusable strategies, indicators, and analyzers; useful as a future dependency candidate but not required for an initial pure-Python validation core: https://www.backtrader.com/

## Version / Date Context
- Research date: 2026-05-28.
- API plans, limits, terms, market-data entitlements, fees, and regulatory constraints can change; implementation must re-check official docs before enabling paper/live broker adapters.

## Boundaries / Non-goals
- This research does not decide a live broker or authorize live trading.
- It does not guarantee profitability.
- It does not provide legal/tax/investment advice.

## Handoff
- Ralplan should produce a PRD and test-spec that hard-block live order pathways in MVP.
- Implementation should start with broker-agnostic interfaces, CSV/offline backtesting, robust metrics, and an explicit `PaperBroker` simulator.
- External broker/data adapters should remain disabled/stubbed until credentials, terms, and test sandbox behavior are verified.
