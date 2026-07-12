# ADR 0002: Temporal Validation

Status: PROPOSED

## Decision

Use expanding-window validation with separate train, tuning, calibration and locked final test. Do not use random splits. Do not calibrate on final test.

Recommended design: `design_A_recommended` from `reports/model-contract/fold_manifest.csv`.

| Split | Season filter | V1 negotiated-fee rows | V1 discovery snapshots | Forward-MV diagnostics | Prior-performance links |
|---|---|---:|---:|---:|---:|
| train | `season <= 2018` | 1,536 | 4,650 | 4,607 | 2,269 |
| tune | `season = 2019` | 399 | 1,131 | 1,130 | 696 |
| calibration | `season between 2020 and 2021` | 526 | 2,073 | 2,073 | 1,376 |
| locked final test | `season >= 2023` | 2,690 | 12,483 | 5,403 | 0 |

Alternative: `design_B_historical_rolling`.

| Split | Season filter | V1 negotiated-fee rows | V1 discovery snapshots | Forward-MV diagnostics | Prior-performance links |
|---|---|---:|---:|---:|---:|
| train | `season <= 2017` | 1,220 | 3,701 | 3,659 | 1,681 |
| tune | `season between 2018 and 2019` | 715 | 2,080 | 2,078 | 1,284 |
| calibration | `season between 2020 and 2021` | 526 | 2,073 | 2,073 | 1,376 |
| diagnostic recent | `season >= 2023` | 2,690 | 12,483 | 5,403 | 0 |

## Rationale

Design A keeps a modern locked test for fee diagnostics while exposing that prior-performance links are absent in the recent period. Do not hide that by moving recent rows into training.

Haaland, Antony and Cristiano Ronaldo are development sanity cases. They cannot be used as untouched final-test evidence.

