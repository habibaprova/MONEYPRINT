# MONEYPRINT final handover — interactivity enhancement

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

`VISUAL_QA_REPORT.md` contains exact values, results and the pressed-state verification limitation. `UX_VERIFICATION.json` and `PBIX_VERIFICATION.json` contain current file/integrity results. Public report images are `screenshots/overview.png`, `screenshots/investigation.png` and `screenshots/reliability.png`. These were rendered from the delivered report through Power BI Desktop's native PDF export on 2026-10-13 and inspected for cursor overlays, desktop notifications and readability. The original desktop and interaction captures are retained in local, Git-ignored backups. `SCREENSHOT_VERIFICATION.json` records the current public images and integrity checks.

## Backups and maintenance

Current pre-enhancement PBIX: `backups/interactivity_before_20261012/MONEYPRINT.pbix`, SHA-256 `01c40259c075dbb0fbaa8357e48725b94f1020c2ec7f9c91b639d4c7a9604f6c`. Subsequent original Desktop save before replacement is also retained. Current original project exported from PBIX is in `backups/interactivity_current_project/`; previous handover/QA files and earlier repair backups remain.

Desktop authoring buttons require Ctrl+click (keyboard activation was used in QA). The long queue retains necessary vertical scrolling. Refresh uses existing local export paths. Do not run the old build/repair scripts over this final project; development scripts are retained as change records, not an idempotent rebuild command.

Only remaining manual check: held mouse-down pressed appearance. Hover, selected page, actions and core data interactions were confirmed. PaySim is synthetic; later evaluation is exploratory; scores are uncalibrated and contributions do not establish causality or production performance.
