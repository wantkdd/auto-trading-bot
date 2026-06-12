# Market universe candidate scan

Safety: paper candidate scan only; no orders, no broker, no investment advice.

## Summary

- Requested symbols: 150
- Allowed symbols after leverage filter: 150
- Valid scanned assets: 150
- Missing/failed price data: 0
- Passing candidates: 0
- Review candidates: 30
- Top candidate: None
- Live trading authorized: False

## Passing candidates

| Candidate | Symbols | Weights | Median excess | Worst MDD | Fundamentals | Recent |
| --- | --- | --- | ---: | ---: | --- | --- |

## Review candidates

| Candidate | Symbols | Weights | Median excess | Worst MDD | Reasons |
| --- | --- | --- | ---: | ---: | --- |
| SATS_0.5_GLD_0.5 | ('SATS', 'GLD') | (0.5, 0.5) | 177.09% | -18.31% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct, trailing_504d:recent_mdd_worse_than_minus_20pct |
| MU_0.3_IEF_0.7 | ('MU', 'IEF') | (0.3, 0.7) | 152.26% | -19.98% | MU:revenue_decline_worse_than_minus_10pct, post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct |
| SATS_0.4_GLD_0.6 | ('SATS', 'GLD') | (0.4, 0.6) | 150.49% | -16.12% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct |
| SATS_0.36_GLD_0.64 | ('SATS', 'GLD') | (0.36, 0.64) | 139.92% | -16.16% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct |
| AMD_0.6_GLD_0.4 | ('AMD', 'GLD') | (0.6, 0.4) | 134.55% | -19.98% | AMD:revenue_decline_worse_than_minus_10pct, post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct, trailing_504d:recent_mdd_worse_than_minus_20pct, trailing_252d:recent_mdd_worse_than_minus_20pct |
| FIX_0.5_GLD_0.5 | ('FIX', 'GLD') | (0.5, 0.5) | 125.79% | -18.92% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct, trailing_504d:recent_mdd_worse_than_minus_20pct |
| INTC_0.5_GLD_0.5 | ('INTC', 'GLD') | (0.5, 0.5) | 124.05% | -19.96% | INTC:net_income_not_positive, post_2020:recent_excess_below_minus_5pp, post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct, trailing_504d:recent_mdd_worse_than_minus_20pct, trailing_252d:recent_mdd_worse_than_minus_20pct |
| SATS_0.3_GLD_0.7 | ('SATS', 'GLD') | (0.3, 0.7) | 123.76% | -16.93% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct |
| AMD_0.5_GLD_0.5 | ('AMD', 'GLD') | (0.5, 0.5) | 119.02% | -19.38% | AMD:revenue_decline_worse_than_minus_10pct, post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct, trailing_504d:recent_mdd_worse_than_minus_20pct |
| FIX_0.4_GLD_0.6 | ('FIX', 'GLD') | (0.4, 0.6) | 111.97% | -14.84% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct |
| INTC_0.4_GLD_0.6 | ('INTC', 'GLD') | (0.4, 0.6) | 108.71% | -18.78% | INTC:net_income_not_positive, post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct, trailing_504d:recent_mdd_worse_than_minus_20pct |
| AMD_0.4_GLD_0.6 | ('AMD', 'GLD') | (0.4, 0.6) | 105.36% | -19.13% | AMD:revenue_decline_worse_than_minus_10pct, post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct |
| FIX_0.36_GLD_0.64 | ('FIX', 'GLD') | (0.36, 0.64) | 104.49% | -14.72% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct |
| INTC_0.36_GLD_0.64 | ('INTC', 'GLD') | (0.36, 0.64) | 102.72% | -18.22% | INTC:net_income_not_positive, post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct |
| SATS_0.36_IEF_0.64 | ('SATS', 'IEF') | (0.36, 0.64) | 102.31% | -19.33% | post_2020:recent_excess_below_minus_5pp, post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct, trailing_504d:recent_mdd_worse_than_minus_20pct |
| GLW_0.6_GLD_0.4 | ('GLW', 'GLD') | (0.6, 0.4) | 98.48% | -19.57% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct |
| AMD_0.36_GLD_0.64 | ('AMD', 'GLD') | (0.36, 0.64) | 97.97% | -18.95% | AMD:revenue_decline_worse_than_minus_10pct, post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct |
| INTC_0.5_IEF_0.5 | ('INTC', 'IEF') | (0.5, 0.5) | 95.66% | -19.76% | INTC:net_income_not_positive, post_2020:recent_excess_below_minus_5pp, post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct, trailing_504d:recent_mdd_worse_than_minus_20pct, trailing_252d:recent_mdd_worse_than_minus_20pct |
| INTC_0.3_GLD_0.7 | ('INTC', 'GLD') | (0.3, 0.7) | 92.51% | -17.24% | INTC:net_income_not_positive, post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct |
| AMAT_0.6_GLD_0.4 | ('AMAT', 'GLD') | (0.6, 0.4) | 91.92% | -16.40% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct, trailing_504d:recent_mdd_worse_than_minus_20pct |
| FIX_0.3_GLD_0.7 | ('FIX', 'GLD') | (0.3, 0.7) | 90.39% | -14.43% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct |
| AMD_0.5_IEF_0.5 | ('AMD', 'IEF') | (0.5, 0.5) | 90.21% | -18.91% | AMD:revenue_decline_worse_than_minus_10pct, post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct, trailing_504d:recent_mdd_worse_than_minus_20pct |
| GLW_0.5_GLD_0.5 | ('GLW', 'GLD') | (0.5, 0.5) | 89.54% | -18.92% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct |
| AMD_0.3_GLD_0.7 | ('AMD', 'GLD') | (0.3, 0.7) | 89.28% | -18.91% | AMD:revenue_decline_worse_than_minus_10pct, post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct |
| AMAT_0.5_GLD_0.5 | ('AMAT', 'GLD') | (0.5, 0.5) | 85.51% | -15.60% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct |
| SATS_0.3_IEF_0.7 | ('SATS', 'IEF') | (0.3, 0.7) | 83.07% | -16.47% | post_2020:recent_excess_below_minus_5pp, post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct, trailing_504d:recent_mdd_worse_than_minus_20pct |
| GLW_0.4_GLD_0.6 | ('GLW', 'GLD') | (0.4, 0.6) | 80.41% | -18.41% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct |
| FIX_0.4_IEF_0.6 | ('FIX', 'IEF') | (0.4, 0.6) | 77.03% | -14.72% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct, ai_proxy_post_2023:recent_mdd_worse_than_minus_20pct, trailing_504d:recent_mdd_worse_than_minus_20pct |
| GLW_0.36_GLD_0.64 | ('GLW', 'GLD') | (0.36, 0.64) | 76.71% | -18.07% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct |
| AMAT_0.4_GLD_0.6 | ('AMAT', 'GLD') | (0.4, 0.6) | 76.52% | -15.02% | post_2020:recent_mdd_worse_than_minus_20pct, post_2022:recent_mdd_worse_than_minus_20pct |