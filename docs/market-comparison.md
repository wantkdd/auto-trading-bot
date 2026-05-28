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

- KRX Open API / KRX information data services: https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO001.jsp
- KRX Open API terms and usage limits: https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO005.jsp
- Korean public data portal stock-price information sourced from KRX: https://www.data.go.kr/en/data/15094808/openapi.do
- Korea Investment & Securities Open API samples and account/mock-investment terms: https://github.com/koreainvestment/open-trading-api
- Alpaca market-data documentation: https://docs.alpaca.markets/us/docs/about-market-data-api
- Alpaca paper-trading documentation: https://github.com/alpacahq/alpaca-docs/blob/master/content/trading/paper-trading.md
- Interactive Brokers paper-trading documentation: https://www.ibkrguides.com/clientportal/papertradingaccount.htm?Highlight=paper+trading+account
- SEC day-trading investor guidance: https://www.sec.gov/about/reports-publications/investorpubsdaytipshtm
- FINRA day-trading investor guidance: https://www.finra.org/investors/investing/investment-products/stocks/day-trading
