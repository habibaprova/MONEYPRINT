# Phase 3 Chronological Robustness Audit

**Secondary exploratory robustness analysis; not a pristine holdout.** The original Phase 3 split, model bundle, reports, and selection file were preserved. Original validation/test classifier metrics below are reused from the saved Phase 3 report; the original test was not rescored by this audit. The original test had already been accessed twice (the discarded non-converged SAGA run and the corrected Phase 3 run).

## Why the Original Row Shares Skewed

The primary split assigned equal proportions of the 743 distinct step values, implicitly treating each step as equal in volume. Transaction counts per step are highly nonuniform: the original training period averaged 11,696 rows/step, validation 1,722, and test 799. Thus the row shares are train 95.59% (6,082,007 rows), validation 3.00% (191,147 rows), test 1.41% (89,466 rows), although the step shares were approximately 70/15/15. The full per-step cumulative transaction and fraud series is provided in the companion CSV/Parquet files.

| Original split | Steps | Transactions | Row share | Mean transactions/step | Fraud | Prevalence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 520 | 6,082,007 | 95.5897% | 11,696.2 | 5,781 | 0.0951% |
| validation | 111 | 191,147 | 3.0042% | 1,722.0 | 1,180 | 0.6173% |
| test | 112 | 89,466 | 1.4061% | 798.8 | 1,252 | 1.3994% |

| Original boundary | Through step | Cumulative transactions | Row share | Cumulative fraud labels | Fraud share |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 520 | 6,082,007 | 95.5897% | 5,781 | 70.3884% |
| validation | 631 | 6,273,154 | 98.5939% | 6,961 | 84.7559% |
| test | 743 | 6,362,620 | 100.0000% | 8,213 | 100.0000% |

The largest individual steps are also tens of thousands of rows (the top step contains 51,352 transactions), which is why step-count proportions are not transaction-count proportions.

## Alternative Whole-Step Split

Boundaries minimize absolute row-count error to cumulative 70% and 85%, using transaction counts only and never cutting a step: train through step 323; validation through step 377.

| Split | Steps | Transactions | Row share | Fraud | Prevalence | Mean amount | Median | P95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 323 (1–323) | 4,463,587 | 70.15% | 3,643 | 0.0816% | 174,802.27 | 75,005.95 | 510,208.41 |
| validation | 54 (324–377) | 943,289 | 14.83% | 560 | 0.0594% | 215,741.35 | 78,086.45 | 589,498.81 |
| test | 366 (378–743) | 955,744 | 15.02% | 4,010 | 0.4196% | 168,079.89 | 71,421.32 | 506,100.04 |

### Type Mix and Fraud by Type

| Split | Type | Transactions | Split share | Fraud | Type prevalence | Mean amount | Median | P95 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| train | CASH_IN | 977,376 | 21.90% | 0 | 0.0000% | 168,084.56 | 142,371.95 | 411,096.82 |
| train | CASH_OUT | 1,582,647 | 35.46% | 1,831 | 0.1157% | 176,456.19 | 147,771.68 | 430,992.35 |
| train | DEBIT | 27,764 | 0.62% | 0 | 0.0000% | 5,658.58 | 3,117.78 | 15,404.28 |
| train | PAYMENT | 1,506,552 | 33.75% | 0 | 0.0000% | 12,447.27 | 9,008.53 | 36,274.95 |
| train | TRANSFER | 369,248 | 8.27% | 1,812 | 0.4907% | 860,630.03 | 466,151.54 | 2,290,544.03 |
| validation | CASH_IN | 209,945 | 22.26% | 0 | 0.0000% | 173,112.16 | 147,411.19 | 419,948.19 |
| validation | CASH_OUT | 329,968 | 34.98% | 280 | 0.0849% | 177,689.63 | 150,685.22 | 430,509.85 |
| validation | DEBIT | 6,903 | 0.73% | 0 | 0.0000% | 5,145.86 | 3,404.79 | 16,035.86 |
| validation | PAYMENT | 316,004 | 33.50% | 0 | 0.0000% | 15,131.60 | 11,702.16 | 40,960.99 |
| validation | TRANSFER | 80,469 | 8.53% | 280 | 0.3480% | 1,288,860.96 | 658,541.39 | 4,834,902.49 |
| test | CASH_IN | 211,963 | 22.18% | 0 | 0.0000% | 168,621.62 | 144,164.46 | 408,219.54 |
| test | CASH_OUT | 324,885 | 33.99% | 2,005 | 0.6171% | 173,948.46 | 140,446.86 | 408,871.71 |
| test | DEBIT | 6,765 | 0.71% | 0 | 0.0000% | 5,110.48 | 2,496.95 | 10,481.14 |
| test | PAYMENT | 328,939 | 34.42% | 0 | 0.0000% | 13,860.53 | 9,912.19 | 40,631.95 |
| test | TRANSFER | 83,192 | 8.70% | 2,005 | 2.4101% | 766,813.11 | 455,177.16 | 2,524,591.71 |

Validation has 560 fraud cases overall (280 per labeled transaction type); alternative test has 4,010 (2,005 each in CASH_OUT and TRANSFER). These counts support exploratory ranking estimates, but test prevalence is 0.4196% and remains subject to temporal and project-level reuse. No confidence interval is claimed.

## Feature-Set Comparison

All four feature sets use balanced logistic regression for comparability. Feature sets match the Phase 3 hierarchy: amount+type; add simulated hour; add sender pre-balance/ratio/coverage to amount+type+hour; then add strictly historical recipient count/amount. The balance ablation therefore includes hour, as in the original Phase 3 saved specification.
PR-AUC is average precision. Every row reports prevalence to make the period mix visible; PR-AUC and precision depend on prevalence and must not be naively compared across periods.

| Protocol | Split | Feature set | Population | Fraud prevalence | PR-AUC | ROC-AUC | P@100 | R@100 | P@500 | R@500 |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| original_step_split | train | amount_type | all_transactions | 0.0951% | 0.007175 | 0.888526 | 0.00% | 0.00% | 0.00% | 0.00% |
| original_step_split | train | amount_type | transfer_cash_out | 0.2178% | 0.007175 | 0.744201 | 0.00% | 0.00% | 0.00% | 0.00% |
| original_step_split | train | plus_hour | all_transactions | 0.0951% | 0.153056 | 0.930757 | 89.00% | 1.54% | 56.80% | 4.91% |
| original_step_split | train | plus_hour | transfer_cash_out | 0.2178% | 0.153056 | 0.841109 | 89.00% | 1.54% | 56.80% | 4.91% |
| original_step_split | train | plus_balance | all_transactions | 0.0951% | 0.517482 | 0.997940 | 5.00% | 0.09% | 67.80% | 5.86% |
| original_step_split | train | plus_balance | transfer_cash_out | 0.2178% | 0.517483 | 0.995710 | 5.00% | 0.09% | 67.80% | 5.86% |
| original_step_split | train | full_context | all_transactions | 0.0951% | 0.559144 | 0.997752 | 32.00% | 0.55% | 78.80% | 6.82% |
| original_step_split | train | full_context | transfer_cash_out | 0.2178% | 0.559146 | 0.995313 | 32.00% | 0.55% | 78.80% | 6.82% |
| cumulative_row_split | train | amount_type | all_transactions | 0.0816% | 0.006322 | 0.886231 | 0.00% | 0.00% | 0.00% | 0.00% |
| cumulative_row_split | train | amount_type | transfer_cash_out | 0.1866% | 0.006322 | 0.739559 | 0.00% | 0.00% | 0.00% | 0.00% |
| cumulative_row_split | train | plus_hour | all_transactions | 0.0816% | 0.133475 | 0.928964 | 82.00% | 2.25% | 52.20% | 7.16% |
| cumulative_row_split | train | plus_hour | transfer_cash_out | 0.1866% | 0.133475 | 0.837384 | 82.00% | 2.25% | 52.20% | 7.16% |
| cumulative_row_split | train | plus_balance | all_transactions | 0.0816% | 0.496740 | 0.997161 | 71.00% | 1.95% | 84.20% | 11.56% |
| cumulative_row_split | train | plus_balance | transfer_cash_out | 0.1866% | 0.496741 | 0.994000 | 71.00% | 1.95% | 84.20% | 11.56% |
| cumulative_row_split | train | full_context | all_transactions | 0.0816% | 0.529375 | 0.996922 | 82.00% | 2.25% | 89.00% | 12.22% |
| cumulative_row_split | train | full_context | transfer_cash_out | 0.1866% | 0.529376 | 0.993556 | 82.00% | 2.25% | 89.00% | 12.22% |
| original_step_split | validation | amount_type | all_transactions | 0.6173% | 0.052194 | 0.893379 | 28.00% | 2.37% | 12.20% | 5.17% |
| original_step_split | validation | amount_type | transfer_cash_out | 1.4993% | 0.052194 | 0.738722 | 28.00% | 2.37% | 12.20% | 5.17% |
| original_step_split | validation | plus_hour | all_transactions | 0.6173% | 0.240152 | 0.933675 | 66.00% | 5.59% | 45.40% | 19.24% |
| original_step_split | validation | plus_hour | transfer_cash_out | 1.4993% | 0.240152 | 0.837468 | 66.00% | 5.59% | 45.40% | 19.24% |
| original_step_split | validation | plus_balance | all_transactions | 0.6173% | 0.823030 | 0.998762 | 97.00% | 8.22% | 91.00% | 38.56% |
| original_step_split | validation | plus_balance | transfer_cash_out | 1.4993% | 0.823030 | 0.996966 | 97.00% | 8.22% | 91.00% | 38.56% |
| original_step_split | validation | full_context | all_transactions | 0.6173% | 0.840292 | 0.998562 | 98.00% | 8.31% | 94.00% | 39.83% |
| original_step_split | validation | full_context | transfer_cash_out | 1.4993% | 0.840292 | 0.996475 | 98.00% | 8.31% | 94.00% | 39.83% |
| cumulative_row_split | validation | amount_type | all_transactions | 0.0594% | 0.003308 | 0.883559 | 0.00% | 0.00% | 0.00% | 0.00% |
| cumulative_row_split | validation | amount_type | transfer_cash_out | 0.1364% | 0.003308 | 0.732182 | 0.00% | 0.00% | 0.00% | 0.00% |
| cumulative_row_split | validation | plus_hour | all_transactions | 0.0594% | 0.234314 | 0.928088 | 80.00% | 14.29% | 32.60% | 29.11% |
| cumulative_row_split | validation | plus_hour | transfer_cash_out | 0.1364% | 0.234314 | 0.834601 | 80.00% | 14.29% | 32.60% | 29.11% |
| cumulative_row_split | validation | plus_balance | all_transactions | 0.0594% | 0.444340 | 0.998894 | 68.00% | 12.14% | 50.00% | 44.64% |
| cumulative_row_split | validation | plus_balance | transfer_cash_out | 0.1364% | 0.444340 | 0.997456 | 68.00% | 12.14% | 50.00% | 44.64% |
| cumulative_row_split | validation | full_context | all_transactions | 0.0594% | 0.474395 | 0.998288 | 75.00% | 13.39% | 56.20% | 50.18% |
| cumulative_row_split | validation | full_context | transfer_cash_out | 0.1364% | 0.474395 | 0.996062 | 75.00% | 13.39% | 56.20% | 50.18% |
| original_step_split | test | amount_type | all_transactions | 1.3994% | 0.120391 | 0.886063 | 51.00% | 4.07% | 25.60% | 10.22% |
| original_step_split | test | amount_type | transfer_cash_out | 3.2966% | 0.120391 | 0.726338 | 51.00% | 4.07% | 25.60% | 10.22% |
| original_step_split | test | plus_hour | all_transactions | 1.3994% | 0.325979 | 0.920995 | 87.00% | 6.95% | 59.60% | 23.80% |
| original_step_split | test | plus_hour | transfer_cash_out | 3.2966% | 0.325979 | 0.810238 | 87.00% | 6.95% | 59.60% | 23.80% |
| original_step_split | test | plus_balance | all_transactions | 1.3994% | 0.870886 | 0.998361 | 94.00% | 7.51% | 91.00% | 36.34% |
| original_step_split | test | plus_balance | transfer_cash_out | 3.2966% | 0.870886 | 0.996062 | 94.00% | 7.51% | 91.00% | 36.34% |
| original_step_split | test | full_context | all_transactions | 1.3994% | 0.889085 | 0.998293 | 95.00% | 7.59% | 95.20% | 38.02% |
| original_step_split | test | full_context | transfer_cash_out | 3.2966% | 0.889085 | 0.995901 | 95.00% | 7.59% | 95.20% | 38.02% |
| cumulative_row_split | test | amount_type | all_transactions | 0.4196% | 0.058069 | 0.893170 | 68.00% | 1.70% | 34.80% | 4.34% |
| cumulative_row_split | test | amount_type | transfer_cash_out | 0.9827% | 0.058069 | 0.748374 | 68.00% | 1.70% | 34.80% | 4.34% |
| cumulative_row_split | test | plus_hour | all_transactions | 0.4196% | 0.229174 | 0.931047 | 68.00% | 1.70% | 67.80% | 8.45% |
| cumulative_row_split | test | plus_hour | transfer_cash_out | 0.9827% | 0.229174 | 0.837589 | 68.00% | 1.70% | 67.80% | 8.45% |
| cumulative_row_split | test | plus_balance | all_transactions | 0.4196% | 0.787881 | 0.998660 | 95.00% | 2.37% | 97.00% | 12.09% |
| cumulative_row_split | test | plus_balance | transfer_cash_out | 0.9827% | 0.787881 | 0.996843 | 95.00% | 2.37% | 97.00% | 12.09% |
| cumulative_row_split | test | full_context | all_transactions | 0.4196% | 0.794706 | 0.998296 | 96.00% | 2.39% | 99.00% | 12.34% |
| cumulative_row_split | test | full_context | transfer_cash_out | 0.9827% | 0.794706 | 0.995987 | 96.00% | 2.39% | 99.00% | 12.34% |

## Stability Summary

The ordering is directionally stable: amount/type alone is weak, adding simulated hour improves ranking, and adding balance features accounts for most of the lift under both protocols. Full context edges the balance ablation on eligible-population PR-AUC by 0.0173 / 0.0182 on original validation/test and 0.0301 / 0.0068 on row-based validation/test. This is a relatively small added increment beyond balance features, not evidence of a causal recipient-history effect.
Top-budget recall is less stable: full-context recall@500 is 38.02% on the original test and 12.34% on the exploratory row-based test. Period prevalence and transaction mix differ, and the latter overlaps prior analysis.

## Alternative Protocol Selection

Validation-only selected feature set: **full_context**; budget: **top 500 TRANSFER/CASH_OUT transactions**, by validation F1. Test labels were not used in this selection. The alternative test is exploratory: steps 378–520 were in the original Phase 3 training period, and later steps were in its validation/test periods.

## Methodological Checks and Limitations

- The alternate cutoffs use step transaction counts only; fraud counts are not used to place boundaries.
- Every model's imputer, scaler, and one-hot encoder is fit on that protocol's training period only. The alternative models are newly fit; original models are loaded read-only.
- Recipient histories were precomputed at recipient-step grain from all transactions, then restricted to strictly earlier steps. Same-step activity does not contribute to another transaction's history; validation/test historical state may legitimately include earlier-period observations.
- Predictor inputs exclude fraud labels, flagged-fraud indicators, post-event balances, account IDs, and split metadata.
- Sender pre-balance and balance ratios sharply improve scores and may encode PaySim balance-generation shortcuts. Simulated hour is not wall-clock time and exhibits period-dependent label patterns. These are associations, not causal effects.
- The alternate test is not pristine because the same dataset and overlapping periods were previously examined in Phase 3. Original primary test results are copied from the saved report, not recomputed here.
- All results are synthetic-data research diagnostics, not claims of real-world fraud-detection performance.

## Reproduction

```powershell
.\.venv\Scripts\python.exe -m src.phase3_robustness
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
