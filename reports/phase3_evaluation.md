# Phase 3: Explainable Risk Ranking

Evaluation population: all transactions, with a separately reported TRANSFER/CASH_OUT-only population because the other PaySim types contain no fraud labels. PR-AUC is average precision. All baselines and ablations are compared on validation; model/policy and the investigation budget are frozen before the single test evaluation.

## Split Audit

| Split | Steps | Transactions | Fraud | Prevalence | Mean amount | Median | P95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 520 | 6,082,007 | 5,781 | 0.095051% | 180,413.05 | 75,131.44 | 519,726.71 |
| validation | 111 | 191,147 | 1,180 | 0.617326% | 160,710.94 | 67,312.03 | 485,733.64 |
| test | 112 | 89,466 | 1,252 | 1.399414% | 183,310.91 | 74,786.96 | 516,514.64 |

The split keeps contiguous steps (train 1–520, validation 521–631, test 632–743). It is approximately 70/15/15 by steps, not by transactions. The sharp prevalence and volume shift is reported, not corrected by resampling.

### Type Mix and Amounts by Split

| Split | Type | Rows | Split share | Fraud | Type prevalence | Mean amount | Median | P95 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| train | CASH_IN | 1,335,450 | 21.96% | 0 | 0.000000% | 168,983.93 | 143,413.16 | 412,481.43 |
| train | CASH_OUT | 2,147,137 | 35.30% | 2,900 | 0.135064% | 176,040.31 | 147,386.92 | 428,516.85 |
| train | DEBIT | 39,138 | 0.64% | 0 | 0.000000% | 5,599.65 | 3,088.81 | 15,184.87 |
| train | PAYMENT | 2,053,690 | 33.77% | 0 | 0.000000% | 13,104.31 | 9,525.74 | 37,954.64 |
| train | TRANSFER | 506,592 | 8.33% | 2,881 | 0.568702% | 920,839.31 | 491,598.35 | 2,690,003.42 |
| validation | CASH_IN | 43,121 | 22.56% | 0 | 0.000000% | 167,869.81 | 143,951.92 | 405,700.55 |
| validation | CASH_OUT | 61,211 | 32.02% | 590 | 0.963879% | 171,287.41 | 137,282.48 | 401,013.45 |
| validation | DEBIT | 1,582 | 0.83% | 0 | 0.000000% | 3,564.48 | 2,423.95 | 10,083.96 |
| validation | PAYMENT | 67,743 | 35.44% | 0 | 0.000000% | 12,153.31 | 8,394.03 | 36,506.23 |
| validation | TRANSFER | 17,490 | 9.15% | 590 | 3.373356% | 695,659.57 | 395,987.55 | 2,266,664.33 |
| test | CASH_IN | 20,713 | 23.15% | 0 | 0.000000% | 167,000.91 | 143,254.70 | 400,692.32 |
| test | CASH_OUT | 29,152 | 32.58% | 626 | 2.147366% | 203,953.76 | 147,037.80 | 436,128.91 |
| test | DEBIT | 712 | 0.80% | 0 | 0.000000% | 3,372.19 | 2,544.55 | 9,238.68 |
| test | PAYMENT | 30,062 | 33.60% | 0 | 0.000000% | 11,904.41 | 9,196.04 | 32,292.40 |
| test | TRANSFER | 8,827 | 9.87% | 626 | 7.091877% | 751,679.28 | 392,478.94 | 2,457,893.72 |

### Hour Patterns by Split

| Split | Simulated hour | Rows | Fraud | Prevalence |
| --- | ---: | ---: | ---: | ---: |
| test | 0 | 183 | 38 | 20.765027% |
| test | 1 | 724 | 38 | 5.248619% |
| test | 2 | 105 | 56 | 53.333333% |
| test | 3 | 109 | 50 | 45.871560% |
| test | 4 | 42 | 42 | 100.000000% |
| test | 5 | 38 | 38 | 100.000000% |
| test | 6 | 50 | 50 | 100.000000% |
| test | 7 | 96 | 30 | 31.250000% |
| test | 8 | 2,021 | 72 | 3.562593% |
| test | 9 | 7,087 | 36 | 0.507972% |
| test | 10 | 62 | 62 | 100.000000% |
| test | 11 | 5,033 | 60 | 1.192132% |
| test | 12 | 4,600 | 46 | 1.000000% |
| test | 13 | 10,604 | 52 | 0.490381% |
| test | 14 | 6,501 | 54 | 0.830641% |
| test | 15 | 8,084 | 52 | 0.643246% |
| test | 16 | 10,445 | 68 | 0.651029% |
| test | 17 | 52 | 52 | 100.000000% |
| test | 18 | 6,810 | 50 | 0.734214% |
| test | 19 | 8,112 | 52 | 0.641026% |
| test | 20 | 9,319 | 52 | 0.558000% |
| test | 21 | 990 | 56 | 5.656566% |
| test | 22 | 5,522 | 86 | 1.557407% |
| test | 23 | 2,877 | 60 | 2.085506% |
| train | 0 | 68,045 | 196 | 0.288045% |
| train | 1 | 25,093 | 260 | 1.036146% |
| train | 2 | 8,203 | 256 | 3.120809% |
| train | 3 | 1,476 | 228 | 15.447154% |
| train | 4 | 1,026 | 196 | 19.103314% |
| train | 5 | 1,525 | 250 | 16.393443% |
| train | 6 | 1,886 | 248 | 13.149523% |
| train | 7 | 8,840 | 246 | 2.782805% |
| train | 8 | 23,509 | 250 | 1.063423% |
| train | 9 | 274,342 | 257 | 0.093679% |
| train | 10 | 419,757 | 269 | 0.064085% |
| train | 11 | 434,917 | 222 | 0.051044% |
| train | 12 | 462,225 | 247 | 0.053437% |
| train | 13 | 446,143 | 248 | 0.055588% |
| train | 14 | 419,394 | 259 | 0.061756% |
| train | 15 | 404,175 | 253 | 0.062597% |
| train | 16 | 416,416 | 241 | 0.057875% |
| train | 17 | 432,447 | 253 | 0.058504% |
| train | 18 | 538,788 | 241 | 0.044730% |
| train | 19 | 624,921 | 216 | 0.034564% |
| train | 20 | 526,711 | 248 | 0.047085% |
| train | 21 | 231,057 | 245 | 0.106034% |
| train | 22 | 178,207 | 233 | 0.130747% |
| train | 23 | 132,904 | 219 | 0.164781% |
| validation | 0 | 3,359 | 66 | 1.964870% |
| validation | 1 | 1,294 | 60 | 4.636785% |
| validation | 2 | 710 | 60 | 8.450704% |
| validation | 3 | 422 | 48 | 11.374408% |
| validation | 4 | 173 | 36 | 20.809249% |
| validation | 5 | 78 | 78 | 100.000000% |
| validation | 6 | 1,484 | 60 | 4.043127% |
| validation | 7 | 52 | 52 | 100.000000% |
| validation | 8 | 1,385 | 46 | 3.321300% |
| validation | 9 | 2,089 | 48 | 2.297750% |
| validation | 10 | 5,910 | 44 | 0.744501% |
| validation | 11 | 6,042 | 42 | 0.695134% |
| validation | 12 | 16,593 | 46 | 0.277225% |
| validation | 13 | 11,727 | 46 | 0.392257% |
| validation | 14 | 13,758 | 40 | 0.290740% |
| validation | 15 | 4,427 | 36 | 0.813192% |
| validation | 16 | 14,751 | 36 | 0.244051% |
| validation | 17 | 7,442 | 48 | 0.644988% |
| validation | 18 | 34,911 | 52 | 0.148950% |
| validation | 19 | 14,781 | 74 | 0.500643% |
| validation | 20 | 17,698 | 40 | 0.226014% |
| validation | 21 | 15,759 | 46 | 0.291897% |
| validation | 22 | 10,826 | 32 | 0.295585% |
| validation | 23 | 5,476 | 44 | 0.803506% |

## Validation Results

| Method | Population | PR-AUC | ROC-AUC | P@100 | R@100 | FP@100 | P@500 | R@500 | FP@500 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| amount_raw | all_transactions | 0.099997 | 0.803988 | 46.0000% | 3.8983% | 54 | 23.0000% | 9.7458% | 385 |
| amount_raw | transfer_cash_out | 0.104039 | 0.698996 | 46.0000% | 3.8983% | 54 | 23.0000% | 9.7458% | 385 |
| amount_type_train_percentile | all_transactions | 0.143082 | 0.626529 | 63.0000% | 5.3390% | 37 | 44.2000% | 18.7288% | 279 |
| amount_type_train_percentile | transfer_cash_out | 0.258271 | 0.631383 | 100.0000% | 8.4746% | 0 | 54.4000% | 23.0508% | 228 |
| logistic_amount_type_balanced | all_transactions | 0.052194 | 0.893379 | 28.0000% | 2.3729% | 72 | 12.2000% | 5.1695% | 439 |
| logistic_amount_type_balanced | transfer_cash_out | 0.052194 | 0.738722 | 28.0000% | 2.3729% | 72 | 12.2000% | 5.1695% | 439 |
| logistic_plus_hour_balanced | all_transactions | 0.240152 | 0.933675 | 66.0000% | 5.5932% | 34 | 45.4000% | 19.2373% | 273 |
| logistic_plus_hour_balanced | transfer_cash_out | 0.240152 | 0.837468 | 66.0000% | 5.5932% | 34 | 45.4000% | 19.2373% | 273 |
| logistic_plus_balance_balanced | all_transactions | 0.823030 | 0.998762 | 97.0000% | 8.2203% | 3 | 91.0000% | 38.5593% | 45 |
| logistic_plus_balance_balanced | transfer_cash_out | 0.823030 | 0.996966 | 97.0000% | 8.2203% | 3 | 91.0000% | 38.5593% | 45 |
| logistic_full_context_balanced | all_transactions | 0.840292 | 0.998562 | 98.0000% | 8.3051% | 2 | 94.0000% | 39.8305% | 30 |
| logistic_full_context_balanced | transfer_cash_out | 0.840292 | 0.996475 | 98.0000% | 8.3051% | 2 | 94.0000% | 39.8305% | 30 |
| logistic_full_context_unweighted | all_transactions | 0.913765 | 0.999127 | 100.0000% | 8.4746% | 0 | 99.0000% | 41.9492% | 5 |
| logistic_full_context_unweighted | transfer_cash_out | 0.914020 | 0.997880 | 100.0000% | 8.4746% | 0 | 99.0000% | 41.9492% | 5 |

### Feature Ablation (Validation PR-AUC)

| Model | All transactions | TRANSFER/CASH_OUT |
| --- | ---: | ---: |
| logistic_amount_type_balanced | 0.052194 | 0.052194 |
| logistic_plus_hour_balanced | 0.240152 | 0.240152 |
| logistic_plus_balance_balanced | 0.823030 | 0.823030 |
| logistic_full_context_balanced | 0.840292 | 0.840292 |
| logistic_full_context_unweighted | 0.913765 | 0.914020 |

### Frozen Decision

Selected policy: **logistic_full_context_unweighted**; chosen on validation eligible-population PR-AUC. Selected budget: **top 500 eligible transactions**, chosen from K=100/500 by validation F1. Validation precision/recall at that budget: 99.0000% / 41.9492%; false positives: 5.

## Final Frozen Test Evaluation

| Method | Population | PR-AUC | ROC-AUC | P@100 | R@100 | FP@100 | P@500 | R@500 | FP@500 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| amount_raw | all_transactions | 0.210696 | 0.790335 | 80.0000% | 6.3898% | 20 | 44.0000% | 17.5719% | 280 |
| amount_raw | transfer_cash_out | 0.218453 | 0.678718 | 80.0000% | 6.3898% | 20 | 44.0000% | 17.5719% | 280 |
| amount_type_train_percentile | all_transactions | 0.250950 | 0.612005 | 100.0000% | 7.9872% | 0 | 57.6000% | 23.0032% | 212 |
| amount_type_train_percentile | transfer_cash_out | 0.298285 | 0.613769 | 100.0000% | 7.9872% | 0 | 61.0000% | 24.3610% | 195 |
| logistic_amount_type_balanced | all_transactions | 0.120391 | 0.886063 | 51.0000% | 4.0735% | 49 | 25.6000% | 10.2236% | 372 |
| logistic_amount_type_balanced | transfer_cash_out | 0.120391 | 0.726338 | 51.0000% | 4.0735% | 49 | 25.6000% | 10.2236% | 372 |
| logistic_plus_hour_balanced | all_transactions | 0.325979 | 0.920995 | 87.0000% | 6.9489% | 13 | 59.6000% | 23.8019% | 202 |
| logistic_plus_hour_balanced | transfer_cash_out | 0.325979 | 0.810238 | 87.0000% | 6.9489% | 13 | 59.6000% | 23.8019% | 202 |
| logistic_plus_balance_balanced | all_transactions | 0.870886 | 0.998361 | 94.0000% | 7.5080% | 6 | 91.0000% | 36.3419% | 45 |
| logistic_plus_balance_balanced | transfer_cash_out | 0.870886 | 0.996062 | 94.0000% | 7.5080% | 6 | 91.0000% | 36.3419% | 45 |
| logistic_full_context_balanced | all_transactions | 0.889085 | 0.998293 | 95.0000% | 7.5879% | 5 | 95.2000% | 38.0192% | 24 |
| logistic_full_context_balanced | transfer_cash_out | 0.889085 | 0.995901 | 95.0000% | 7.5879% | 5 | 95.2000% | 38.0192% | 24 |
| logistic_full_context_unweighted | all_transactions | 0.950373 | 0.998991 | 100.0000% | 7.9872% | 0 | 99.8000% | 39.8562% | 1 |
| logistic_full_context_unweighted | transfer_cash_out | 0.950486 | 0.997615 | 100.0000% | 7.9872% | 0 | 99.8000% | 39.8562% | 1 |

A preliminary SAGA run scored the test before its non-convergence was noticed; that run is discarded. The solver change was based on a train-only convergence check, not test metrics. The corrected model and validation-selected policy were frozen before this final test pass; no test result informed features, model selection, thresholds, or budgets.

## Coefficients and Artifact Risk

Full balanced logistic model coefficient extremes (standardized log1p numeric and one-hot scales):
- `numeric__sender_balance_covers_amount`: 15.64148
- `categorical__transaction_type_CASH_OUT`: 9.29616
- `categorical__transaction_type_TRANSFER`: 9.28895
- `numeric__amount`: 3.47911
- `categorical__simulated_hour_5`: 3.36221
- `categorical__simulated_hour_4`: 3.19683
- `categorical__simulated_hour_3`: 2.98303
- `categorical__simulated_hour_6`: 2.96965
- `categorical__transaction_type_PAYMENT`: -9.15506
- `numeric__sender_pre_balance`: -9.07364
- `categorical__simulated_hour_19`: -2.23353
- `categorical__simulated_hour_20`: -1.92447
- `categorical__simulated_hour_18`: -1.88053
- `categorical__simulated_hour_17`: -1.71525
- `categorical__simulated_hour_16`: -1.66302
- `categorical__simulated_hour_12`: -1.57830

Balance-feature ablations are sensitive to the simulator: many labeled nonfraud rows have amount greater than sender pre-balance and are clipped to zero after the event, while labeled fraud rows usually are not. Post-event balances are excluded from every predictor. Pre-balance and its ratios remain legitimate decision-time candidates but may still encode this synthetic rule; compare ablations and do not interpret performance as real-world fraud detection.
Simulated hour has an abrupt distribution/prevalence shift across chronological periods; its ablation should be read as a dataset-specific signal, not a validated daily-cycle effect.

## Risk Bands and Investigation Export

Risk bands use validation eligible-population score quantiles only: `{"high": 0.3755722641944885, "moderate": 3.387714605196379e-05, "very_high": 0.9968135952949524}`. The capped transaction table contains at most 500 top-ranked eligible rows per split. It is a risk-selected investigation list, not a prevalence sample. Aggregated overview and risk-band prevalence use the full population.

## Limits

- The test period contains 1,252 positives; at K=100, recall resolution is about 0.08 percentage points per captured transaction. Top-K estimates remain sensitive to the simulator and time shift.
- No confidence interval is presented because transactions are not independent and account-level dependence is not modeled.
- Evaluation is offline on synthetic PaySim labels; no real-world detection claim is supported.
- Training used all chronological training rows with sparse-compatible scikit-learn Newton-Cholesky logistic regression. Inspect iteration/convergence status in the JSON report.

## Reproduction

```powershell
.\.venv\Scripts\python.exe -m src.phase3_evaluation
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
