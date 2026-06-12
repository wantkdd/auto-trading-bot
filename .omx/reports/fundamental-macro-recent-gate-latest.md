# Fundamental, macro-proxy, and recent-regime gate

Safety: offline research only; non-leveraged; no orders, no broker, no investment advice.

## Summary

- Candidates checked: 8
- Passing full gate: 4
- Review required: 4
- Top candidate: AAPL_0.3_GLD_0.7 (pass)

## Data-source limits

- SEC fundamentals cover companies, not ETFs such as QQQ or GLD.
- FRED macro series are documented but require an API key, so this run uses price-based macro proxies only.
- Public news sentiment is not treated as a reliable free data source; SEC 8-K counts are used only as event-risk flags, not sentiment or prediction.
- Passing this research gate is still not approval for real-money trading.

## Candidate gates

| Candidate | Status | Base excess | Holdout excess | Worst MDD | Fundamentals | Recent regimes | Reasons |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| AAPL_0.3_GLD_0.7 | pass | 12.09% | 26.51% | -18.29% | pass | pass | - |
| AAPL_0.36_GLD_0.64 | pass | 10.35% | 26.06% | -17.63% | pass | pass | - |
| AAPL_0.4_GLD_0.6 | pass | 9.34% | 26.64% | -17.79% | pass | pass | - |
| AAPL_0.5_GLD_0.5 | review | 9.28% | 25.15% | -19.83% | pass | review | post_2020:recent_mdd_worse_than_minus_20pct |
| QQQ_0.36_GLD_0.64 | review | 8.53% | 38.31% | -19.32% | not_applicable | review | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct |
| QQQ_0.4_GLD_0.6 | review | 8.48% | 42.91% | -19.66% | not_applicable | review | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct |
| QQQ_0.3_GLD_0.7 | review | 8.06% | 38.02% | -19.93% | not_applicable | review | post_2020:recent_mdd_worse_than_minus_20pct |
| XLK_0.3_GLD_0.7 | pass | 7.56% | 46.49% | -19.74% | not_applicable | pass | - |

## Top candidate recent-regime detail

Candidate: `AAPL_0.3_GLD_0.7`

| Window | Status | Return | Benchmark | Excess | MDD | Reasons |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| post_2020 | pass | 203.63% | 139.82% | 63.81% | -18.54% | - |
| post_2022 | pass | 107.07% | 53.55% | 53.52% | -18.15% | - |
| ai_proxy_post_2023 | pass | 126.99% | 101.60% | 25.38% | -15.76% | - |
| trailing_504d | pass | 71.27% | 39.69% | 31.58% | -16.96% | - |
| trailing_252d | pass | 30.85% | 23.57% | 7.28% | -14.77% | - |