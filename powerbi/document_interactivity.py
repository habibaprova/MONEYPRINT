from pathlib import Path
import json,hashlib,shutil
from PIL import Image
R=Path(__file__).parent
record=json.loads((R/'UX_VERIFICATION.json').read_text())
record['desktop_pbix_reopen_verified']=True
record['desktop_checks_passed']=['All five native type tooltips reconciled to population summary','All three metrics, dynamic title and number formats','All/single/multiple selection indicators and slicer reset','Three navigation destinations, rose hover and persistent current page','Top 100/500 single selection; Fold 1/2; default reset; queue unaffected','Rank 8 context and contributions, repeated in reopened PBIX','Reliability Fold 3 selection and clearing; all pages reopened']
for n in ['UX_VERIFICATION.json','PBIX_VERIFICATION.json']:
 if n=='PBIX_VERIFICATION.json':shutil.copy2(R/n,R/'backups/interactivity_before_20261012'/n)
 (R/n).write_text(json.dumps(record,indent=2),encoding='utf-8')
for n,label in [('overview','01_overview'),('investigation','02_investigation'),('reliability','03_reliability')]:
 p=R/'screenshots'/('UX_reopened_'+n+'.jpg')
 Image.open(p).crop((54,160,1129,765)).resize((1280,720),Image.Resampling.LANCZOS).save(R/'screenshots'/('UX_'+label+'.png'))

qa='''# MONEYPRINT interactivity and UX QA

Verified in Power BI Desktop on 2026-10-12, including the reopened delivered `MONEYPRINT.pbix`.

## Delivered file

460,982 bytes; SHA-256 `3a3284e79055001ec58e863f870ca5e13d65ed0b22569c963ceec021d8ce5bc6`. Three original 1280 × 720 pages, 54 in-bounds visual containers, ZIP integrity passed. Standalone PBIX saved in Desktop and reopened in a separate instance. All three reopened pages rendered without errors. Main PBIP/report/semantic-model files synchronized; `interactivity/` retains the verified candidate project and PBIX.

## Enhancement checks

| Feature | Actual Desktop result |
| --- | --- |
| Rich tooltips | Native visual tooltips on the three type charts. All five types tested using Desktop's Ctrl+H tooltip shortcut after selecting a data point. Exact counts, full-population shares, raw synthetic amounts, fraud labels and type-specific rates matched frozen summaries. No investigation-case denominators. |
| Navigation feedback | Dusty rose hover appeared on all three navigation targets and reset. All three destinations activated; selected page retained its cream fill and rose outline. Reset remained functional on every page. Native pressed formatting inspected; transient held mouse-down appearance was not captured. |
| Metric switch | Transaction count, synthetic amount and fraud count all changed the primary chart and its title correctly. Amount chart uses billions to two decimals; count/fraud formats remain whole numbers. All five types preserved, including zero-fraud types. Fixed population KPIs unchanged. |
| Selection indicator | All after clearing; each single bar type; single slicer type; CASH_OUT + TRANSFER showed Multiple. Related charts retained native cross-highlighting. Reset returned All. |
| Budget controls | Native tiles 0.5%, Top 100 and Top 500; single selection, active tile styling, and separate context-responsive caption. Top 100 replaced Top 500 and vice versa. Default caption explicitly says Top 500 (default) after reset. Capacity window and budget filter the capacity fact; exploratory queue unchanged. |
| Capacity values | Exploratory Top 100: 90.00% precision, 7.19% recall, 10 FP. Top 500: 91.20%, 36.42%, 44 FP. Fold 1 Top 500: 64.20%, 30.28%, 179. Fold 2 Top 500: 82.60%, 35.73%, 87. Top 100/500 switching repeated successfully after delivered PBIX reopened. |
| Case interaction | Rank 8: step 688, TRANSFER, amount 500,205.38, pre-balance 1.00, ratio 500205.375, score 1.0000. Contributions +38.01, −15.92, +11.98. Repeated after PBIX reopen. |
| Reliability | Original content definitions unchanged apart from sidebar button styling. Four folds, four ablations and five windows rendered. Fold 3 filtered to 99.65% ROC-AUC/84.20% PR-AUC; clearing restored all folds. Reopened page rendered correctly. |
| Layout | Overview checked at full desktop fit and reduced fit; three-page grid preserved. Selector occupies part of bottom slicer row; explanatory text fits above indicator/hint. Budget controls fit existing top row. No new chart/category or control scrollbars; long case queue retains necessary vertical scrolling. |
| Population | Exact 6,362,620 transactions, 8,213 labels, 0.1291% prevalence; 1.144 T synthetic units. |
| Integrity | All 29 protected hashes unchanged, including all 16 CSV exports and frozen evidence. Original 15 relationships byte-identical to current-project baseline. Disconnected selector adds only three UI metadata rows. No model training/export regeneration. |

## Exact tooltip evidence

| Type | Transactions | Population share | Synthetic amount | Fraud labels | Type fraud rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| CASH_OUT | 2,237,500 | 35.17% | 394,412,995,224.49 | 4,116 | 0.1840% |
| TRANSFER | 532,909 | 8.38% | 485,291,987,263.17 | 4,097 | 0.7688% |
| PAYMENT | 2,151,495 | 33.81% | 28,093,371,138.37 | 0 | 0.0000% |
| CASH_IN | 1,399,284 | 21.99% | 236,367,391,912.46 | 0 | 0.0000% |
| DEBIT | 41,432 | 0.65% | 227,199,221.28 | 0 | 0.0000% |

## Evidence and limitations

`screenshots/UX_01_overview.png`, `UX_02_investigation.png`, `UX_03_reliability.png` are cropped actual captures of the reopened primary PBIX. `UX_tooltip_*.jpg`, `UX_metric_amount.jpg`, `UX_metric_fraud.jpg`, `UX_selection_multiple.jpg`, `UX_navigation_hover.jpg`, and `UX_budget_Top100.jpg` retain interaction evidence.

Native tooltips were chosen to preserve exactly three pages. The metric switch uses a supported disconnected selector + numeric SWITCH method, with dynamic format strings; no field parameter was necessary. All is a documented count fallback for the metric selector and exploratory Top 500 fallback for cleared capacity controls.

One manual visual check remains: hold the mouse down on a navigation/reset button to inspect its transient pressed appearance. Live hover, persistent page indication and button actions passed. The automation has no held mouse-down screenshot operation; native state fields were checked in Desktop, but this transient rendering is not claimed as captured/verified. No other functional failures were found in the focused checks.

Automatic approval review rejected applying external changes while Desktop might have unsaved state. Cancelled the overwrite, preserved file copies, saved application state, then closed/reopened a saved isolated candidate. No application edits were discarded. Original byte-exact PBIX and subsequently saved original state are retained in `backups/interactivity_before_20261012/`.

Synthetic PaySim findings remain exploratory; risk scores are not calibrated probabilities and contributions are associational.
'''
(R/'VISUAL_QA_REPORT.md').write_text(qa,encoding='utf-8')
handover='''# MONEYPRINT final handover — interactivity enhancement

Open `C:/Users/user4/Desktop/MONEYPRINT/powerbi/MONEYPRINT.pbix`. The enhanced standalone PBIX was saved in Power BI Desktop, reopened, and inspected on all three original pages.

## Delivery

- 460,982 bytes; SHA-256 `3a3284e79055001ec58e863f870ca5e13d65ed0b22569c963ceec021d8ce5bc6`.
- Executive Overview, Investigation Desk, Behind the Score; each 1280 × 720; 54 visual containers within bounds.
- `MONEYPRINT.pbip`, `.Report/`, `.SemanticModel/` synchronized. `interactivity/MONEYPRINT_UX.pbip` and `.pbix` retain the verified source/candidate.
- Population totals unchanged: 6,362,620 transactions; 8,213 labels; 0.1291% prevalence; 1.144 trillion synthetic amount units.

## Five enhancements delivered

1. Three Overview type charts have native hover tooltips with exact transactions, population share, synthetic amount, fraud labels and type fraud rate. All five transaction types reconciled in Desktop.
2. Sidebar navigation and reset have dusty rose hover feedback. Current page retains a persistent cream fill/rose outline. Native pressed colors configured; held mouse-down appearance needs one manual visual check.
3. Compact Compare by dropdown switches the primary type chart between transactions, amount in billions, and fraud count. Title/number formats change with the metric. All means the documented count default; KPIs remain fixed.
4. Overview adds a click hint and an accurate All/single/Multiple selection indicator. Existing cross-highlighting remains functional.
5. Investigation uses native single-select budget tiles for Top 100, Top 500 and the existing 0.5% alert-rate budget. Active budget and cleared Top 500 fallback have a dynamic caption. Window selection remains independent of the exploratory queue.

## Model additions and scope

Nine DAX measures in executive_kpi_summary: Type Transactions, Type Share of Population, Type Synthetic Amount, Type Fraud Labels, Type Fraud Label Rate, Selected Type Label, Comparison Value, Comparison Title, Budget Status. Comparison Value remains numeric, with a dynamic format string. A disconnected three-row `ux_metric_selector` Power Query metadata table supports the SWITCH measure. Capacity measures add an ambiguity guard for explicitly filtered multi-budget contexts.

No new CSV/source data. Amount display divides by one billion once in the switching chart; tooltips retain raw synthetic units. Population share denominator removes type filters over the full summary; fraud rate divides each type's population fraud count by its population transaction count. The 500 selected cases are never used for these rates.

All 16 export CSVs and all 29 protected files retain original hashes. Frozen model/evidence unchanged; no training or export generation. Original 15 relationships unchanged. Reliability content unchanged apart from the requested sidebar formatting.

## Verification

Passed all five type tooltips; three metrics/title/format switching; All/single/Multiple indicators; three navigation targets; reset on every page; Top 100/500, Fold 1/2 comparisons; rank-8 details/contributions; Fold 3 reliability filtering/clearing. Delivered PBIX reopened successfully and all three pages inspected; Top 100/500 and selected case repeated after reopen.

Exploratory Top 100 = 90.00% precision, 7.19% recall, 10 FP; Top 500 = 91.20%, 36.42%, 44. Fold 1 Top 500 = 64.20%, 30.28%, 179; Fold 2 = 82.60%, 35.73%, 87. Clear controls resolves to exploratory Top 500 and ranks 1–500. A selected budget/window never rescopes the saved exploratory case queue.

`VISUAL_QA_REPORT.md` contains exact values, results, screenshots and the pressed-state verification limitation. `UX_VERIFICATION.json` and `PBIX_VERIFICATION.json` contain current file/integrity results. Real reopened-report screenshots: `screenshots/UX_01_overview.png`, `UX_02_investigation.png`, `UX_03_reliability.png`; interaction JPGs are retained beside them.

## Backups and maintenance

Current pre-enhancement PBIX: `backups/interactivity_before_20261012/MONEYPRINT.pbix`, SHA-256 `01c40259c075dbb0fbaa8357e48725b94f1020c2ec7f9c91b639d4c7a9604f6c`. Subsequent original Desktop save before replacement is also retained. Current original project exported from PBIX is in `backups/interactivity_current_project/`; previous handover/QA files and earlier repair backups remain.

Desktop authoring buttons require Ctrl+click (keyboard activation was used in QA). The long queue retains necessary vertical scrolling. Refresh uses existing local export paths. Do not run the old build/repair scripts over this final project; development scripts are retained as change records, not an idempotent rebuild command.

Only remaining manual check: held mouse-down pressed appearance. Hover, selected page, actions and core data interactions were confirmed. PaySim is synthetic; later evaluation is exploratory; scores are uncalibrated and contributions do not establish causality or production performance.
'''
(R/'FINAL_HANDOVER.md').write_text(handover,encoding='utf-8')
with (R/'POWER_BI_BUILD_GUIDE.md').open('a',encoding='utf-8') as f:
 f.write('\n\n## Final interactivity update\n\nThe current deliverable includes nine UX measures, a disconnected three-row selector, native visual tooltips, budget tiles and selection labels. See FINAL_HANDOVER.md and VISUAL_QA_REPORT.md for the final definitions and validation. Use the synchronized main PBIP or the interactivity candidate for future work; the old builder/repair scripts are historical and must not be run over the final report. One manual held mouse-down pressed-state visual check remains.\n')
assert hashlib.sha256((R/'MONEYPRINT.pbix').read_bytes()).hexdigest()==record['sha256']
print('Current handover, QA, verification records and reopened screenshots updated')
