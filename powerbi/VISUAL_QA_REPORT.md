# MONEYPRINT interactivity and UX QA

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

Public report images are `screenshots/overview.png`, `screenshots/investigation.png` and `screenshots/reliability.png`. On 2026-10-13 these replaced the desktop screenshots after cursor overlays were found in the published captures. The replacements are rendered from Power BI Desktop's native PDF export of the delivered PBIX and were visually reviewed on all three pages. They show the default report context, with no selected case on Investigation Desk. No chart values or report content were retouched. Original interaction evidence is retained locally under `backups/public_screenshots_before_20261013/screenshots/`, outside Git. The original functional QA results above are unchanged; static exported images do not independently demonstrate hover or filtering behavior. `SCREENSHOT_VERIFICATION.json` records the replacement image hashes and unchanged report/data integrity.

Native tooltips were chosen to preserve exactly three pages. The metric switch uses a supported disconnected selector + numeric SWITCH method, with dynamic format strings; no field parameter was necessary. All is a documented count fallback for the metric selector and exploratory Top 500 fallback for cleared capacity controls.

One manual visual check remains: hold the mouse down on a navigation/reset button to inspect its transient pressed appearance. Live hover, persistent page indication and button actions passed. The automation has no held mouse-down screenshot operation; native state fields were checked in Desktop, but this transient rendering is not claimed as captured/verified. No other functional failures were found in the focused checks.

Automatic approval review rejected applying external changes while Desktop might have unsaved state. Cancelled the overwrite, preserved file copies, saved application state, then closed/reopened a saved isolated candidate. No application edits were discarded. Original byte-exact PBIX and subsequently saved original state are retained in `backups/interactivity_before_20261012/`.

Synthetic PaySim findings remain exploratory; risk scores are not calibrated probabilities and contributions are associational.
