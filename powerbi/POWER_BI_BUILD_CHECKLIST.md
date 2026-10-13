# Power BI Completion Checklist — final visual QA verified 2026-10-12

Final repair evidence supersedes earlier file sizes/layout notes: see `VISUAL_QA_REPORT.md`, `FINAL_HANDOVER.md`, and `PBIX_VERIFICATION.json`.

- [x] Back up the current primary PBIX before visual QA.
- [x] Exact count cards, single trillion-unit amount suffix, explicit chart units and unscaled tooltip.
- [x] Five transaction categories and eight compact amount bands fit; no unwanted category scrollbars.
- [x] Bottom slicers, footer, case columns, contribution lines, and rank-bound inputs fit.
- [x] Capacity selectors retain their intended capacity-only scope and single selection.
- [x] Inspect all pages at Fit to Page and 100%.
- [x] Save corrected PBIX and synchronize editable project.
- [x] Reopen delivered PBIX; test charts, case panels, sidebar navigation, fold interaction, and full CSV refresh.
- [x] Capture updated actual screenshots of all three reopened pages.
- [x] Verify 29 protected-file hashes and manifest source model/report/parquet hashes are unchanged.

- [x] Locate original PBIX in Documents and create a matching-hash backup before editing.
- [x] Preserve the existing imported model and theme through Desktop Save As to PBIP.
- [x] Reconcile all 16 exports against the manifest; preserve exports and frozen artifacts.
- [x] Repair the malformed single-column fraud query and refresh its five CSV rows.
- [x] Replace auto-detected relationships with 15 active, single-direction dimension-to-fact links.
- [x] Add 17 scoped DAX measures, including exact KPI display and selected-case context.
- [x] Build three 1280 × 720 pages with the approved palette and consistent sidebar.
- [x] Executive Overview: four population KPIs, five descriptive charts, evidence note, type/step slicers.
- [x] Investigation Desk: capacity selectors, ranked top-500 queue, rank-range control, wrapping case context/contributions.
- [x] Behind the Score: four fold curves, prevalence, four feature ablations, window definitions, historical split diagnostics, limitations.
- [x] Validate 6,362,620 transactions, 8,213 labels, 456 labels in top 500, and saved capacity/fold metrics.
- [x] Verify capacity changes, selected-case filtering, native page navigation, and clear-slicers action in Desktop.
- [x] Capture actual rendered screenshots of all three pages.
- [x] Save `MONEYPRINT.pbix`; pass archive integrity checks and reopen all three pages in Desktop without visual errors.
- [x] Update README, executive summary, recruiter pitch, and final handover.

The default cleared capacity selectors display “All”; measures resolve that state to `reserved_final_exploratory` + `top_500`, as stated on the page. Compact selector labels are sourced from the capacity fact, preserving the exploratory queue. Rank range 1–K filters the saved queue independently. Native tooltips show unscaled values; three saved contributions fit as signed text lines. Necessary vertical scrolling remains in the 500-case queue.

See `FINAL_HANDOVER.md`, `PBIX_VERIFICATION.json`, and `QA_EXPORT_RECONCILIATION.json` for evidence.
