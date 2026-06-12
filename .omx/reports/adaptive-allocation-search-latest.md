# Adaptive allocation search report

Status: **REVIEW**

Safety: offline policy-search research only; no orders, no broker, no investment advice.

## Summary

| Model | Median excess | Mean excess | Holdout min excess | Worst MDD | Median return | Median benchmark |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive_train_selected | 5.40% | 6.49% | 29.92% | -23.20% | 27.16% | 20.42% |
| static_36_64_baseline | 8.53% | 8.83% | 38.31% | -19.32% | 25.78% | 20.42% |

## Selected policy frequency

- `adaptive_sma150_mom252_th0_on0.75_off0.2_r21`: 2
- `adaptive_sma150_mom252_th0_on0.75_off0.36_r21`: 2
- `adaptive_sma150_mom90_th0_on0.75_off0.2_r21`: 2
- `adaptive_sma150_mom252_th0_on0.75_off0.36_r63`: 1
- `adaptive_sma150_mom252_th0.03_on0.75_off0.2_r21`: 1
- `adaptive_sma200_mom90_th0_on0.75_off0.2_r21`: 1

## OOS evaluations

| Window | Policy | Candidate | Benchmark | Excess | MDD | Rebalances |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| holdout_70_30 | `adaptive_sma150_mom252_th0_on0.75_off0.2_r21` | 129.72% | 99.80% | 29.92% | -10.86% | 10 |
| walk_forward_1 | `adaptive_sma150_mom252_th0_on0.75_off0.36_r63` | -5.22% | -8.14% | 2.92% | -17.29% | 1 |
| walk_forward_2 | `adaptive_sma150_mom252_th0.03_on0.75_off0.2_r21` | 19.03% | 27.99% | -8.96% | -7.51% | 6 |
| walk_forward_3 | `adaptive_sma150_mom252_th0_on0.75_off0.2_r21` | 30.13% | 20.05% | 10.08% | -23.20% | 3 |
| walk_forward_4 | `adaptive_sma150_mom252_th0_on0.75_off0.36_r21` | 19.50% | 25.14% | -5.64% | -9.96% | 1 |
| walk_forward_5 | `adaptive_sma150_mom252_th0_on0.75_off0.36_r21` | -13.96% | -19.36% | 5.40% | -21.81% | 2 |
| walk_forward_6 | `adaptive_sma150_mom90_th0_on0.75_off0.2_r21` | 30.12% | 28.03% | 2.09% | -8.30% | 2 |
| walk_forward_7 | `adaptive_sma150_mom90_th0_on0.75_off0.2_r21` | 27.16% | 20.42% | 6.74% | -9.85% | 3 |
| walk_forward_8 | `adaptive_sma200_mom90_th0_on0.75_off0.2_r21` | 32.59% | 16.72% | 15.87% | -9.28% | 3 |

## Next gate

- Only consider paper dry-run if adaptive policy beats or matches static baseline without worse drawdown, and then replicate with independent data.