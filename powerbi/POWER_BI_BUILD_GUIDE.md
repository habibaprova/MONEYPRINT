# MONEYPRINT Power BI maintenance guide

The report is built and delivered as `MONEYPRINT.pbix`. The editable `MONEYPRINT.pbip` project is synchronized with the final visual repair. The previous planning guide is preserved in `backups/documents_before_visual_QA/`. Use `FINAL_HANDOVER.md` and `VISUAL_QA_REPORT.md` for delivered behavior and actual QA.

## Open and present

Open `C:/Users/user4/Desktop/MONEYPRINT/powerbi/MONEYPRINT.pbix` in Power BI Desktop. Use Fit to Page. All three 1280 × 720 pages were also inspected at 100%. In authoring mode, native sidebar and Clear all slicers buttons require Ctrl+click; keyboard button activation was tested.

Executive headline cards always describe the full dataset. Type filters change descriptive charts; simulated-step filters affect the trend only. Click a chart category to cross-highlight related charts, and click it again to clear.

Investigation capacity selectors compare saved evaluation metrics. The compact Window Label and Budget Label fields are on `phase4_investigation_capacity`; keep them there so they do not filter the fixed exploratory queue through the evaluation-window dimension. Both are single-select. Clearing selects All/All and the measures resolve to `reserved_final_exploratory` + `top_500`. The page explains this fallback. The separate rank range selects saved queue ranks 1–K and does not recalculate capacity metrics. Selecting one row populates case context/contributions; zero or multiple ranks show prompts.

Behind the Score shows four walk-forward folds, prevalence, feature ablation, five step definitions, and historical split diagnostics. Fold selection filters its saved curve and step definition. Historical split diagnostics remain disconnected and use ALL rows only.

## Authoritative bindings and formats

| Visual | Final source/format |
| --- | --- |
| Transactions card | `[Transactions Display] = FORMAT([Total Transactions], "#,0")`; visual display units None. |
| Fraud-label card | `[Fraud Labels]`; `#,0`, display units None. |
| Prevalence card | `[Fraud Label Prevalence]`; `0.0000%`. |
| Synthetic amount card | `[Amount Display] = FORMAT([Total Synthetic Amount] / 1000000000000, "0.000") & " T"`; title identifies trillion synthetic units. |
| Volume by type | SUM of `transaction_type_overview[transaction_count]`, not the global Transactions measure. Exact count data labels. |
| Amount by type | SUM of `transaction_type_overview[total_synthetic_amount]`; axis/labels billions; native tooltip unscaled `#,0.00`. |
| Fraud by type | SUM of `fraud_by_transaction_type[fraud_count]`; exact count labels. |
| Amount bands | `transaction_amount_distribution[Amount Band Label]`, sorted by original `amount_band`; SUM transaction count. Tooltip retains original band. |
| Activity trend | `dim_simulated_step[simulated_step]`; SUM of step transaction count. |
| Capacity cards | `[Capacity Precision]`, `[Capacity Recall]`, `[Capacity False Positives]`; two-decimal percentages / exact count. |
| Case queue | Saved case rank, step, type, amount (`#,0.00`), score (`0.0000`), retrospective label. Rank ascending. |
| Case panels | `[Selected Case Context]`, `[Selected Contributions]`; HASONEVALUE rank guard. Contribution text is parsed from saved JSON during import. |
| Fold curves | `[Validation ROC-AUC]` and `[Validation PR-AUC]`, selected model + validation + transfer_cash_out population. |
| Ablation | MAX of repeated saved mean fold metrics, not SUM. |
| Historical split | `[Historical Split Share]`, ALL rows only; compact protocol legend. |

The complete 17 measure definitions are in `MONEYPRINT.SemanticModel/definition/tables/executive_kpi_summary.tmdl`. Actual field bindings and positions are in `MONEYPRINT.Report/definition/pages/`; `VISUAL_QA_LAYOUT.json` records repaired rectangles. The original `build_report.py` is an earlier build script; do not rerun it over final repairs. `visual_repair.py` targets the isolated QA project and still requires Desktop application/refresh/verification.

## Refresh and evidence lock

Home → Refresh reads the 16 existing CSVs from `C:/Users/user4/Desktop/MONEYPRINT/powerbi/exports/`. Sources use UTF-8 and CSV quoting. Display-only text transformations retain original fields and values, including nullable ratios and original contribution JSON. Moving folders requires adjusting File.Contents paths. Refreshing does not retrain or regenerate evidence.

Keep the 15 active single-direction dimension-to-fact relationships in `definition/relationships.tmdl`. Keep executive summary and historical mixed-grain split diagnostics disconnected. No bidirectional filters or fact-to-fact joins are needed.

Frozen evidence: `phase4_walkforward_v1_plus_balance`, trained through step 631. Steps 632–743 were previously accessed and are exploratory, not pristine. Scores are ranking scores, not calibrated probabilities. The queue has 500 risk-selected eligible examples with 456 retrospective labels; that fraction is not population prevalence. Synthetic PaySim amounts/time and balance artifacts do not establish real banking performance.

`verify_visual_qa.py` performs read-only evidence/archive checks and writes `PBIX_VERIFICATION.json`. The backup inventory is `QA_PROTECTED_HASHES.json`. No training, export regeneration, dependency installation, or cloud publication is part of maintenance QA.


## Final interactivity update

The current deliverable includes nine UX measures, a disconnected three-row selector, native visual tooltips, budget tiles and selection labels. See FINAL_HANDOVER.md and VISUAL_QA_REPORT.md for the final definitions and validation. Use the synchronized main PBIP or the interactivity candidate for future work; the old builder/repair scripts are historical and must not be run over the final report. One manual held mouse-down pressed-state visual check remains.
