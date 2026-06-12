# Quant paper signal

Safety: quant paper signal only; no orders, no broker, no credentials, no advice.

## Summary

- Status: `review`
- Feature quality: `review`
- Regime: `conflicted`
- Selected strategy: `quant_momentum_top5_defensive`
- Selected family: `momentum_plus_defensive`
- Max weight: `34.95%`
- Use for strategy promotion: `False`
- Order created: `False`
- Live trading authorized: `False`

## Selected weights

| Symbol | Weight |
| --- | ---: |
| SHY | 34.95% |
| IEF | 11.06% |
| AMD | 9.00% |
| DELL | 9.00% |
| FTNT | 9.00% |
| HPE | 9.00% |
| MU | 9.00% |
| TLT | 6.56% |
| GLD | 2.42% |

## Candidate ranking

| Strategy | Status | Score | Reasons |
| --- | --- | ---: | --- |
| quant_momentum_top5_defensive | review | 0.5826 | regime_conflicted_requires_review |
| quant_sector_rotation_top3_defensive | review | 0.0914 | regime_conflicted_requires_review |
| quant_core_inverse_volatility | review | 0.2660 | regime_conflicted_requires_review |
| quant_defensive_min_volatility | review | -0.0780 | regime_conflicted_requires_review |

## Blockers

- none

## Required next evidence

- Track this quant candidate separately from the locked champion baseline.
- Do not promote quant weights to live trading without forward paper evidence.
- Do not let a conflicted regime or quality blocker increase real-money exposure.