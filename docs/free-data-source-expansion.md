# Free data-source expansion plan

Safety boundary: this is research/paper infrastructure only. It does not approve broker connection, credentials, account access, live orders, leverage, shorting, derivatives, or personalized investment advice.

## Current implementation status

- US symbol universe: implemented with `scripts/us_symbol_universe_refresh.py` using Nasdaq Trader public symbol directories.
- Current refresh output: `data/universe/us_nasdaqtrader_symbols.csv` and `data/universe/us_nasdaqtrader_common_symbols.txt`.
- Latest local refresh: 12,708 listed rows and 5,386 common-equity candidates.
- Data-source registry: expanded with 13 free/free-key sources via `scripts/modeling_data_source_registry.py`.

## Free / free-key source queue

| Priority | Source | Cost/key | Use | Implementation status |
| --- | --- | --- | --- | --- |
| 1 | Nasdaq Trader symbol directories | Free, no key | Broad US listed-symbol universe, ETF/test issue filtering | Implemented |
| 2 | SEC EDGAR APIs | Free, no key | US filings, company facts, 8-K/10-Q/10-K events | Partially implemented |
| 3 | Stooq historical data | Free, no key | Independent daily OHLCV replication | Planned |
| 4 | GDELT DOC API | Free, no key | Global news attention/article-count features | Planned |
| 5 | BLS Public Data API | Free, no key for low volume; registration key for higher limits | Labor/CPI/PPI macro features | Planned |
| 6 | OpenDART | Free key | Korean filings and financial statements | Planned; key required |
| 7 | KRX data portal | Free public portal | Korean listed-symbol/reference data | Planned; access behavior needs validation |
| 8 | Bank of Korea ECOS | Free key | Korean macro regime features | Planned; key required |
| 9 | FRED/ALFRED | Free key | US macro/vintage-aware regime features | Planned; key required |
| 10 | Alpha Vantage free tier | Free key with limits | Independent price/news/fundamental cross-checks | Planned; key required |

## Why not fine-tune immediately

Fine-tuning comes after data maturity. First the bot needs dated, auditable examples where every feature existed before the decision time and every label is computed only after the fact. Until then, fine-tuning can learn hindsight stories, survivorship bias, or future-data leakage.

## Next collector order

1. Archive dated Nasdaq Trader symbol snapshots on every research refresh.
2. Add Stooq daily OHLCV replication for a small validation subset, then broaden if stable.
3. Extend SEC companyfacts/submissions into point-in-time fundamental features.
4. Add GDELT article-count features with publication-time filtering and deduplication.
5. Add Korean data only after free-key setup for OpenDART/ECOS or a no-key KRX path is confirmed.

## Source references

- Nasdaq Trader symbol directory definitions: https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs
- Nasdaq listed directory: https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt
- Other listed directory: https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt
- SEC EDGAR APIs: https://www.sec.gov/edgar/sec-api-documentation
- SEC fair access: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- Stooq historical data: https://stooq.com/db/h/
- GDELT DOC API: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
- BLS Public Data API: https://www.bls.gov/developers/
- OpenDART guide: https://opendart.fss.or.kr/guide/main.do
- KRX data portal: https://data.krx.co.kr/
- Bank of Korea ECOS API: https://ecos.bok.or.kr/api/
- FRED API: https://fred.stlouisfed.org/docs/api/fred/
