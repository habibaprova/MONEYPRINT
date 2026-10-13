# MONEYPRINT Walk-Forward Evaluation

**Protocol:** expanding-window validation with four contiguous chronological folds. The 632–743 period is reserved from the new selection process but has already been accessed by previous experiments; it is not a pristine holdout. No raw data or prior experiment artifacts are overwritten.

## Method Audit

- The Phase 3 primary split used equal shares of distinct steps, not rows: 95.59% / 3.00% / 1.41% of transactions fell in train/validation/test.
- Phase 3 compared logistic models with validation metrics and selected a feature set/budget; some prior validation and test results were examined. The Phase 3 robustness analysis added another overlapping, previously accessed alternate test.
- Current predictors exclude labels, flagged-fraud, post-event balances, IDs, and split metadata. Numeric imputation/scaling and one-hot categories are re-fit independently on each fold's training range.
- Recipient history is computed at recipient-step grain with a window ending at `1 PRECEDING`; no current-step or future-step receipt contributes. This temporal property is tested on a fixture and rechecked against the SQL definition.
- Sender pre-balance is decision-time available but strongly artifact-sensitive. Simulated hour (`step % 24`) is not real clock time and may encode simulator schedules.

## Fold Plan and Support

Windows were fixed by chronological coverage and minimum support, not model performance. Training expands from step 1; validation windows are disjoint and adjacent to the training cutoff.

| Fold | Train steps | Train rows | Train fraud | Validation steps | Validation rows | Validation fraud | Prevalence |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |
| fold_1 | 1–250 | 3,248,292 | 2,841 | 251–350 | 1,695,623 | 1,060 | 0.0625% |
| fold_2 | 1–350 | 4,943,915 | 3,901 | 351–450 | 1,070,802 | 1,156 | 0.1080% |
| fold_3 | 1–450 | 6,014,717 | 5,057 | 451–540 | 112,722 | 934 | 0.8286% |
| fold_4 | 1–540 | 6,127,439 | 5,991 | 541–631 | 145,715 | 970 | 0.6657% |

Reserved final period: steps 632–743, 89,466 rows, 1,252 fraud (1.3994%). It was previously accessed; this protocol does not use it for selection.

## Walk-Forward Validation Results

Primary population is TRANSFER/CASH_OUT; all-transactions metrics are included in JSON. PR-AUC is average precision. Alert@0.5% selects the highest-scored 0.5% independently within each evaluation period as a capacity metric, not a threshold tuned on labels.

| Fold | Method | Prevalence | PR-AUC | ROC-AUC | P@100 | R@100 | P@500 | R@500 | P@0.5% | R@0.5% |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fold_1 | logistic_amount_type_balanced | 0.1436% | 0.003562 | 0.742616 | 0.00% | 0.00% | 0.00% | 0.00% | 0.27% | 0.94% |
| fold_1 | logistic_plus_hour_balanced | 0.1436% | 0.183704 | 0.848205 | 69.00% | 6.51% | 44.60% | 21.04% | 9.24% | 32.17% |
| fold_1 | logistic_plus_balance_balanced | 0.1436% | 0.437155 | 0.996921 | 68.00% | 6.42% | 64.20% | 30.28% | 23.11% | 80.47% |
| fold_1 | logistic_full_context_balanced | 0.1436% | 0.491880 | 0.995505 | 83.00% | 7.83% | 72.20% | 34.06% | 20.81% | 72.45% |
| fold_1 | amount_raw | 0.1436% | 0.004943 | 0.678326 | 0.00% | 0.00% | 0.00% | 0.00% | 0.54% | 1.89% |
| fold_1 | amount_type_train_percentile | 0.1436% | 0.006513 | 0.610660 | 8.00% | 0.75% | 2.80% | 1.32% | 0.60% | 2.08% |
| fold_2 | logistic_amount_type_balanced | 0.2485% | 0.019902 | 0.761111 | 5.00% | 0.43% | 10.60% | 4.58% | 4.13% | 8.30% |
| fold_2 | logistic_plus_hour_balanced | 0.2485% | 0.228677 | 0.845693 | 75.00% | 6.49% | 55.40% | 23.96% | 18.09% | 36.42% |
| fold_2 | logistic_plus_balance_balanced | 0.2485% | 0.638218 | 0.997451 | 92.00% | 7.96% | 82.60% | 35.73% | 39.75% | 80.02% |
| fold_2 | logistic_full_context_balanced | 0.2485% | 0.656935 | 0.996499 | 94.00% | 8.13% | 85.20% | 36.85% | 38.12% | 76.73% |
| fold_2 | amount_raw | 0.2485% | 0.053154 | 0.716490 | 10.00% | 0.87% | 20.80% | 9.00% | 8.12% | 16.35% |
| fold_2 | amount_type_train_percentile | 0.2485% | 0.225452 | 0.650431 | 100.00% | 8.65% | 50.20% | 21.71% | 13.15% | 26.47% |
| fold_3 | logistic_amount_type_balanced | 2.0382% | 0.066144 | 0.729829 | 31.00% | 3.32% | 11.20% | 6.00% | 17.39% | 4.28% |
| fold_3 | logistic_plus_hour_balanced | 2.0382% | 0.195212 | 0.822244 | 43.00% | 4.60% | 33.60% | 17.99% | 48.26% | 11.88% |
| fold_3 | logistic_plus_balance_balanced | 2.0382% | 0.842007 | 0.996520 | 97.00% | 10.39% | 87.20% | 46.68% | 93.04% | 22.91% |
| fold_3 | logistic_full_context_balanced | 2.0382% | 0.855064 | 0.996139 | 98.00% | 10.49% | 91.80% | 49.14% | 98.70% | 24.30% |
| fold_3 | amount_raw | 2.0382% | 0.118358 | 0.688759 | 54.00% | 5.78% | 20.80% | 11.13% | 31.30% | 7.71% |
| fold_3 | amount_type_train_percentile | 2.0382% | 0.278672 | 0.625867 | 100.00% | 10.71% | 46.80% | 25.05% | 83.04% | 20.45% |
| fold_4 | logistic_amount_type_balanced | 1.6046% | 0.063340 | 0.743581 | 29.00% | 2.99% | 16.60% | 8.56% | 18.15% | 5.67% |
| fold_4 | logistic_plus_hour_balanced | 1.6046% | 0.290495 | 0.847017 | 69.00% | 7.11% | 50.60% | 26.08% | 60.73% | 18.97% |
| fold_4 | logistic_plus_balance_balanced | 1.6046% | 0.843715 | 0.997064 | 100.00% | 10.31% | 86.40% | 44.54% | 96.37% | 30.10% |
| fold_4 | logistic_full_context_balanced | 1.6046% | 0.862563 | 0.996628 | 100.00% | 10.31% | 93.00% | 47.94% | 98.68% | 30.82% |
| fold_4 | amount_raw | 1.6046% | 0.132474 | 0.708089 | 48.00% | 4.95% | 30.00% | 15.46% | 32.01% | 10.00% |
| fold_4 | amount_type_train_percentile | 1.6046% | 0.271684 | 0.640725 | 100.00% | 10.31% | 47.40% | 24.43% | 67.99% | 21.24% |

## Fold Variation and Train–Validation Gap

| Feature set | Mean validation PR-AUC | SD across folds | Mean validation ROC-AUC | Mean train PR-AUC | Mean val minus train PR-AUC |
| --- | ---: | ---: | ---: | ---: | ---: |
| amount_type | 0.038237 | 0.031345 | 0.744284 | 0.015769 | +0.022467 |
| plus_hour | 0.224522 | 0.047941 | 0.840790 | 0.141096 | +0.083426 |
| plus_balance | 0.690274 | 0.194376 | 0.996989 | 0.510244 | +0.180029 |
| full_context | 0.716611 | 0.177517 | 0.996193 | 0.543705 | +0.172906 |

The in-sample training scores are diagnostics and optimistically biased; fold validation metrics are the generalization estimates. Prevalence varies materially across folds, so PR-AUC and precision variation mixes prevalence shift with ranking change. ROC-AUC and the per-fold ranking metrics help separate those effects but do not remove period shift.

## Simulation-Artifact Ablation

The report compares the amount+type baseline, adding simulated hour, then adding sender pre-balance/ratio/coverage, then strictly historical recipient aggregates. A large balance-feature lift is consistent with a PaySim shortcut risk; it does not establish causality. Hour performance is also subject to step-period and simulation schedule shifts.

## Validation-Selected Configuration

Selected feature set: **plus_balance**, chosen by highest mean eligible-population validation ROC-AUC across the four walk-forward folds (0.996989). ROC-AUC is the primary selection criterion because fold prevalence shifts substantially; PR-AUC remains fully reported per fold. Configuration is fixed balanced logistic regression, Newton-Cholesky, C=1.0; no hyperparameter search was performed. The final model preprocessing was refit on steps 1–631 only.

## Reserved Previously Accessed Evaluation

| Method | Prevalence | PR-AUC | ROC-AUC | P@100 | R@100 | P@500 | R@500 | P@0.5% | R@0.5% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| amount_raw | 3.2966% | 0.218453 | 0.678718 | 80.00% | 6.39% | 44.00% | 17.57% | 61.05% | 9.27% |
| amount_type_train_percentile | 3.2966% | 0.298478 | 0.614011 | 100.00% | 7.99% | 61.00% | 24.36% | 100.00% | 15.18% |
| logistic_plus_balance_balanced | 3.2966% | 0.873142 | 0.996395 | 90.00% | 7.19% | 91.20% | 36.42% | 94.21% | 14.30% |

This period has been read in prior Phase 3 experiments, including test scoring, and was also scored in preliminary Phase 4 implementation runs before the final protocol revision. The final code computes selection from walk-forward validation folds only; however, because earlier reserved-period metrics were visible during protocol iteration, zero influence cannot be claimed. Treat these values as exploratory diagnostics, not a fresh confirmatory estimate.

## Caveats

- The folds share expanding training history; fold scores are correlated, not independent replications.
- PR-AUC and precision depend on prevalence. Fold-to-fold changes cannot be called ranking deterioration without accounting for the changing fraud prevalence and mix.
- Sender balance fields may encode simulator balance clipping; the hour field is a synthetic step index. Neither supports causal interpretation.
- All experiments reuse one synthetic dataset and prior exploration has accessed the reserved period. No real-world fraud performance claim is warranted.

## Reproduction

```powershell
.\.venv\Scripts\python.exe -m src.phase4_walkforward --plan-only
.\.venv\Scripts\python.exe -m src.phase4_walkforward
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
