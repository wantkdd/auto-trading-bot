# Market Comparison: Korea vs US for the Offline MVP

## Decision for this MVP

Start with a broker-agnostic, offline validation core and local CSV fixtures. Do **not** authorize live trading, broker credentials, or remote paper-trading adapters in this MVP.

The first implementation path should use US-style OHLCV fixtures because the data shape is simple and widely available, while keeping symbols/markets generic so Korean equities can be evaluated later with the same validation pipeline.

## Korea considerations

- Official market-data paths exist through KRX information services and Korean public-data stock-price APIs.
- Korea Investment & Securities publishes Open API samples, but any account, mock-investment, endpoint, request-limit, and terms requirements must be rechecked before a future adapter.
- Korea remains a serious candidate if the user prioritizes Korean-market access, local tax/account fit, or KRX/KIS data availability.

## US considerations

- US paper-trading and market-data ecosystems such as Alpaca and IBKR are well documented for future research.
- Free/basic data plans can have exchange coverage, delay, and entitlement constraints, so results must not assume full-depth real-time data.
- US remains a practical first paper-trading candidate only after a separate approval-gated adapter story.

## MVP safety boundary

This MVP cannot place orders and is not approval for live trading.

Backtests, local simulations, and paper trading are not live-trading proof. No report in this repository should be read as investment advice or a profit guarantee.

## Sources to re-check before future adapters

- KRX Open API / KRX information data services.
- Korean public data portal stock-price information sourced from KRX.
- Korea Investment & Securities Open API samples and account/mock-investment terms.
- Alpaca market-data and paper-trading documentation.
- Interactive Brokers paper-trading and API documentation.
- SEC and FINRA investor guidance on day-trading and margin risks.
