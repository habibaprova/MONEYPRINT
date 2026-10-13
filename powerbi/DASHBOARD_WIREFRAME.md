# MONEYPRINT Dashboard Wireframes

Canvas: 1280 x 720 (16:9). Page background `#F0EDCF`. Keep a persistent 184 px left rail on all pages. Main content starts at x=208. Use 12 px gutters, flat rectangular panels, 1 px `#D8D5BD` dividers, and no shadows.

```text
PAGE 1 | EXECUTIVE OVERVIEW                         1280 x 720
┌──────────────────────┬──────────────────────────────────────────────────────────┐
│ MONEYPRINT           │ MONEYPRINT | Transaction Intelligence                    │
│                      │ Synthetic PaySim · 6,362,620 transactions · 1–743 steps   │
│ 01 Overview          ├──────────────────────────────────────────────────────────┤
│ 02 Investigation     │ Total transactions │ Fraud labels │ Label prevalence │ Value│
│ 03 Reliability       ├──────────────────────────┬───────────────────────────────┤
│                      │ Volume by type           │ Activity by simulated step    │
│ Data: PaySim         ├──────────────────────────┼───────────────────────────────┤
│ Synthetic · offline │ Synthetic value by type  │ Fraud prevalence by type       │
│                      ├──────────────────────────┼───────────────────────────────┤
│                      │ Amount distribution      │ Evidence note / split insight  │
└──────────────────────┴──────────────────────────┴───────────────────────────────┘

PAGE 2 | INVESTIGATION DESK                         1280 x 720
┌──────────────────────┬──────────────────────────────────────────────────────────┐
│ MONEYPRINT           │ MONEYPRINT | Investigation Desk                          │
│                      │ Phase 4 plus_balance · exploratory later-period cases   │
│ 01 Overview          ├──────────────────────────────────────────────────────────┤
│ 02 Investigation     │ Period slicer │ Capacity 100/500/0.5% │ P@500 │ R@500     │
│ 03 Reliability       ├─────────────────────────────────┬────────────────────────┤
│                      │ Ranked selected-model cases      │ Selected case details    │
│                      │ Rank · step · type · amount      │ Score · pre-balance      │
│                      │ Score · label · top contributions│ Coverage · contribution  │
│                      │                                  │ Label (retrospective)    │
│                      ├─────────────────────────────────┴────────────────────────┤
│                      │ Label is historical review outcome; queue is risk-selected│
└──────────────────────┴──────────────────────────────────────────────────────────┘

PAGE 3 | MODEL RELIABILITY & DATA QUALITY               1280 x 720
┌──────────────────────┬──────────────────────────────────────────────────────────┐
│ MONEYPRINT           │ MONEYPRINT | Model Reliability & Data Quality             │
│                      │ Four expanding folds · prevalence shifts across periods  │
│ 01 Overview          ├────────────────────────────┬─────────────────────────────┤
│ 02 Investigation     │ Fold ROC-AUC / PR-AUC      │ Fraud prevalence by fold     │
│ 03 Reliability       ├────────────────────────────┼─────────────────────────────┤
│                      │ Feature ablation           │ Split distribution comparison│
│                      ├────────────────────────────┴─────────────────────────────┤
│                      │ PaySim caveat and selected configuration                  │
│                      │ Balance/hour artifacts · previously accessed evaluation  │
└──────────────────────┴──────────────────────────────────────────────────────────┘
```

## Page Placement Coordinates

Coordinates are pixels from the upper-left of a 1280 x 720 page. Per-visual rectangles are specified in `POWER_BI_BUILD_GUIDE.md`.

| Page element | Page 1 | Page 2 | Page 3 |
| --- | --- | --- | --- |
| Sidebar | x0 y0 w184 h720 | x0 y0 w184 h720 | x0 y0 w184 h720 |
| Heading/subtitle | x208 y20 w1048 h60 | x208 y20 w1048 h60 | x208 y20 w1048 h60 |
| KPI / selector row | KPI row x208 y90 through x1256 h76 | selectors/cards x208 y88 through x1256 h60 | n/a |
| Top analytical row | x208 y178 w510 h145; x730 y178 w526 h145 | queue x208 y164 w690 h420; detail x910 y164 w346 h420 | x208 y82 w510 h205; x730 y82 w526 h205 |
| Middle row | x208 y335 w510 h145; x730 y335 w526 h145 | same queue/detail region | x208 y299 w510 h185; x730 y299 w526 h185 |
| Lower row | x208 y492 w510 h145; x730 y492 w526 h145 | note x208 y600 w1048 h62 | x208 y496 w510 h140; x730 y496 w526 h140 |
| Page 1 slicers | type x208 y646 w510 h30; step x730 y646 w526 h30 | n/a | n/a |
| Footer | x208 y690 w1048 h18 | x208 y680 w1048 h20 | x208 y680 w1048 h20 |

## Shared Visual Rules

- Sidebar: x=0, y=0, w=184, h=720, fill `#D5CE91`. Brand at y=28. Three page-navigation buttons at y=104, 150, 196. Active page uses `#BC858A`; inactive labels use `#474538`.
- Main header: x=208, y=20, w=1048, h=44. Page title 22 pt, subtitle 10 pt.
- Panel surfaces: `#FAF9EF`; headings `#474538`; primary data `#9D9D78`; comparison/highlight `#BC858A`; dividers `#D8D5BD`.
- Footer at x=208, y=694, w=1048, h=16: “Synthetic PaySim · Offline analysis · Simulated time, not calendar time”.
- Do not display a currency symbol; exported amounts are synthetic amount units.