# Phase 2 Exploratory Analysis

- **Dataset:** `PS_20174392719_1491204439457_log.csv`
- **Transactions:** 6,362,620
- **Fraud labels:** 8,213

## Type and Amount Summary

| Type | Transactions | Total amount | Mean | Median | P90 | P95 | P99 | Fraud | Fraud rate | Flagged |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CASH_IN | 1,399,284 | 236,367,391,912.46 | 168,920.24 | 143,427.71 | 343,358.14 | 412,005.13 | 550,870.86 | 0 | 0.000000% | 0 |
| CASH_OUT | 2,237,500 | 394,412,995,224.49 | 176,273.96 | 147,072.18 | 355,191.98 | 427,877.16 | 579,654.07 | 4,116 | 0.183955% | 0 |
| DEBIT | 41,432 | 227,199,221.28 | 5,483.67 | 3,048.99 | 9,500.11 | 14,795.35 | 50,817.98 | 0 | 0.000000% | 0 |
| PAYMENT | 2,151,495 | 28,093,371,138.37 | 13,057.60 | 9,482.19 | 28,810.73 | 37,835.66 | 59,500.11 | 0 | 0.000000% | 0 |
| TRANSFER | 532,909 | 485,291,987,263.17 | 910,647.01 | 486,308.39 | 1,782,296.64 | 2,674,586.94 | 10,000,000.00 | 4,097 | 0.768799% | 16 |

## Fraud and Amount: TRANSFER and CASH_OUT

| Type | Fraud label | Transactions | Mean amount | Median | P95 | Max | Sender pre-balance zero | Amount > sender pre-balance |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CASH_OUT | 0 | 2,233,384 | 173,917.16 | 146,946.56 | 426,154.64 | 2,847,566.62 | 1,025,762 | 1,981,098 |
| CASH_OUT | 1 | 4,116 | 1,455,102.59 | 435,516.91 | 7,841,465.04 | 10,000,000.00 | 37 | 24 |
| TRANSFER | 0 | 528,812 | 906,229.01 | 486,521.91 | 2,646,555.80 | 92,445,516.64 | 282,779 | 507,507 |
| TRANSFER | 1 | 4,097 | 1,480,891.67 | 445,705.76 | 8,098,658.15 | 10,000,000.00 | 4 | 5 |

## Chronological Split

Distinct steps: 743; training ends at step 520; validation ends at step 631.

| Split | Steps | Transactions | Fraud labels | Label rate |
| --- | ---: | ---: | ---: | ---: |
| train | 520 | 6,082,007 | 5,781 | 0.095051% |
| validation | 111 | 191,147 | 1,180 | 0.617326% |
| test | 112 | 89,466 | 1,252 | 1.399414% |

## Hourly-Step Trend

`simulated_hour = step % 24`; this wraps the simulated hourly step index and is not a wall-clock hour.

| Simulated hour | Transactions | Fraud labels | Fraud rate | Total amount |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 71,587 | 300 | 0.419071% | 9,133,130,823.00 |
| 1 | 27,111 | 358 | 1.320497% | 3,200,401,133.58 |
| 2 | 9,018 | 372 | 4.125083% | 1,555,136,461.33 |
| 3 | 2,007 | 326 | 16.243149% | 917,807,529.16 |
| 4 | 1,241 | 274 | 22.078969% | 452,670,433.94 |
| 5 | 1,641 | 366 | 22.303473% | 637,355,461.27 |
| 6 | 3,420 | 358 | 10.467836% | 733,140,777.32 |
| 7 | 8,988 | 328 | 3.649310% | 1,342,656,886.21 |
| 8 | 26,915 | 368 | 1.367267% | 4,771,771,726.72 |
| 9 | 283,518 | 341 | 0.120275% | 57,230,312,371.27 |
| 10 | 425,729 | 375 | 0.088084% | 90,728,860,570.56 |
| 11 | 445,992 | 324 | 0.072647% | 86,836,289,140.77 |
| 12 | 483,418 | 339 | 0.070126% | 95,365,234,623.53 |
| 13 | 468,474 | 346 | 0.073857% | 89,606,322,363.92 |
| 14 | 439,653 | 353 | 0.080291% | 83,019,857,921.19 |
| 15 | 416,686 | 341 | 0.081836% | 88,134,439,201.48 |
| 16 | 441,612 | 345 | 0.078123% | 103,510,274,373.14 |
| 17 | 439,941 | 353 | 0.080238% | 86,449,998,969.93 |
| 18 | 580,509 | 343 | 0.059086% | 90,907,288,926.90 |
| 19 | 647,814 | 342 | 0.052793% | 96,483,920,076.50 |
| 20 | 553,728 | 340 | 0.061402% | 74,928,896,033.23 |
| 21 | 247,806 | 347 | 0.140029% | 33,951,419,898.48 |
| 22 | 194,555 | 351 | 0.180412% | 26,461,247,101.59 |
| 23 | 141,257 | 323 | 0.228661% | 18,034,511,954.75 |

## Receiver Concentration

Unique receivers: 2,722,362; maximum transactions to one receiver: 113.
Top receiver share of transactions: 0.0018%; top 10 share by transaction count: 0.0161%; top 10 share of amount (ranked by count): 0.0558%; top 10 amount share (ranked by amount): 0.2286%.

## Repeated-Account Frequency

| Role | Unique accounts | Repeated accounts | Rows in repeated accounts | Median tx/account | P90 | P99 | Max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| receiver | 2,722,362 | 459,658 | 4,099,916 | 1 | 5 | 25 | 113 |
| sender | 6,353,307 | 9,298 | 18,611 | 1 | 1 | 1 | 3 |

### Account-frequency bins

| Role | Transactions/account | Accounts | Transaction rows |
| --- | ---: | ---: | ---: |
| receiver | 1 | 2,262,704 | 2,262,704 |
| receiver | 2 | 77,054 | 154,108 |
| receiver | 3-5 | 139,225 | 536,432 |
| receiver | 6-10 | 113,093 | 869,418 |
| receiver | 11-25 | 104,706 | 1,668,167 |
| receiver | 26+ | 25,580 | 871,791 |
| sender | 1 | 6,344,009 | 6,344,009 |
| sender | 2 | 9,283 | 18,566 |
| sender | 3-5 | 15 | 45 |

## Balance Investigation

The signed sender comparison is only a diagnostic hypothesis: `CASH_IN` is compared with +amount and the other transaction types with -amount. Receiver deltas are classified empirically by transaction type and destination-ID prefix, without asserting a universal accounting rule. Mismatches are not fraud findings.
Balance residuals are rounded to cents before applying a one-cent tolerance to avoid binary floating-point boundary artifacts.

### Sender deltas by type

| Type | Rows | Pre zero | Post zero | Amount > pre | Delta = +amount | Delta = -amount | Unchanged | Other delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CASH_IN | 1,399,284 | 13,464 | 0 | 477,536 | 1,399,251 | 0 | 33 | 0 |
| CASH_OUT | 2,237,500 | 1,025,799 | 1,985,211 | 1,981,122 | 17 | 256,377 | 1,025,801 | 955,339 |
| DEBIT | 41,432 | 6,158 | 11,786 | 11,786 | 0 | 29,646 | 6,158 | 5,628 |
| PAYMENT | 2,151,495 | 774,245 | 1,101,124 | 1,101,124 | 0 | 1,050,371 | 774,245 | 326,879 |
| TRANSFER | 532,909 | 282,783 | 511,445 | 507,512 | 0 | 25,380 | 282,800 | 224,729 |

### Zero-balance patterns

| Type | Rows | Sender pre zero | Sender post zero | Sender both zero | Receiver pre zero | Receiver post zero | Receiver both zero |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CASH_IN | 1,399,284 | 13,464 | 0 | 0 | 163,573 | 270,871 | 160,005 |
| CASH_OUT | 2,237,500 | 1,025,799 | 1,985,211 | 1,025,799 | 324,187 | 11,425 | 1,608 |
| DEBIT | 41,432 | 6,158 | 11,786 | 6,158 | 0 | 468 | 0 |
| PAYMENT | 2,151,495 | 774,245 | 1,101,124 | 774,245 | 2,151,495 | 2,151,495 | 2,151,495 |
| TRANSFER | 532,909 | 282,783 | 511,445 | 282,783 | 65,133 | 5,174 | 4,174 |

### Receiver deltas by type and account-ID prefix

| Type | Prefix | Rows | Pre zero | Post zero | Delta = +amount | Delta = -amount | Unchanged | Other delta |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CASH_IN | C-prefix | 1,399,284 | 163,573 | 270,871 | 0 | 1,032,039 | 160,005 | 207,240 |
| CASH_OUT | C-prefix | 2,237,500 | 324,187 | 11,425 | 2,025,840 | 16 | 1,619 | 210,058 |
| DEBIT | C-prefix | 41,432 | 0 | 468 | 37,987 | 0 | 0 | 3,445 |
| PAYMENT | M-prefix | 2,151,495 | 2,151,495 | 2,151,495 | 0 | 0 | 2,151,495 | 0 |
| TRANSFER | C-prefix | 532,909 | 65,133 | 5,174 | 474,846 | 0 | 4,174 | 53,889 |

### Balance deltas by fraud label

| Type | isFraud label | Rows | Sender candidate mismatch | Sender unchanged | Receiver unchanged |
| --- | ---: | ---: | ---: | ---: | ---: |
| CASH_IN | 0 | 1,399,284 | 33 | 33 | 160,005 |
| CASH_OUT | 0 | 2,233,384 | 1,981,099 | 1,025,764 | 1,600 |
| CASH_OUT | 1 | 4,116 | 24 | 37 | 18 |
| DEBIT | 0 | 41,432 | 11,786 | 6,158 | 0 |
| PAYMENT | 0 | 2,151,495 | 1,101,124 | 774,245 | 2,151,495 |
| TRANSFER | 0 | 528,812 | 507,508 | 282,780 | 106 |
| TRANSFER | 1 | 4,097 | 21 | 20 | 4,068 |

### Representative non-zero sender exceptions

- `CASH_OUT` at step 1: amount 23,261.30; sender balance 20,411.53 -> 0.00 (delta -20,411.53); amount exceeds starting balance: true; fraud label: 0.
- `CASH_OUT` at step 1: amount 32,282.57; sender balance 14,375.74 -> 0.00 (delta -14,375.74); amount exceeds starting balance: true; fraud label: 0.
- `DEBIT` at step 1: amount 1,668.11; sender balance 1,080.00 -> 0.00 (delta -1,080.00); amount exceeds starting balance: true; fraud label: 0.
- `DEBIT` at step 1: amount 1,939.39; sender balance 1,029.00 -> 0.00 (delta -1,029.00); amount exceeds starting balance: true; fraud label: 0.
- `PAYMENT` at step 1: amount 353.90; sender balance 3.00 -> 0.00 (delta -3.00); amount exceeds starting balance: true; fraud label: 0.
- `PAYMENT` at step 1: amount 365.00; sender balance 319.00 -> 0.00 (delta -319.00); amount exceeds starting balance: true; fraud label: 0.
- `TRANSFER` at step 1: amount 7,276.69; sender balance 93.00 -> 0.00 (delta -93.00); amount exceeds starting balance: true; fraud label: 0.
- `TRANSFER` at step 1: amount 17,488.56; sender balance 14,180.00 -> 0.00 (delta -14,180.00); amount exceeds starting balance: true; fraud label: 0.

## Candidate Feature Policy

| Candidate predictor | Definition |
| --- | --- |
| amount | Transaction amount known at decision time |
| transaction_type | Transaction category known at decision time |
| simulated_hour | `step % 24`; simulated index, not clock time |
| sender_pre_balance | `oldbalanceOrg`; available before the transaction, but artifact-sensitive |
| amount_to_sender_pre_balance | Amount / old sender balance; null when old balance is zero |
| sender_balance_covers_amount | Whether old sender balance is at least amount |
| recipient_prior_transaction_count | Count of receipts at strictly earlier steps |
| recipient_prior_received_amount | Sum of receipt amounts at strictly earlier steps |

The feature Parquet includes `split_step` and `split` as evaluation metadata and `label_is_fraud` as the target, not as predictors. Raw sender/receiver IDs, `isFlaggedFraud`, post-transaction balances, and future-derived fields are absent. Same-step receipts never contribute to one another's historical features. No model was trained and no Power BI CSV was exported.

## Leakage and Simulation Limitations

- Balance differences are descriptive diagnostics, not evidence of fraud.
- The signed sender equation (CASH_IN positive, other types negative) is a candidate comparison only; high deviations require simulator-specific context.
- The receiver account prefix and balance fields do not establish the real-world economic role of a transaction.
- PaySim labels fraud only in selected transaction types and its balance generation may make classification artificially easy.
- All test-split label summaries are descriptive; test labels were not used to design features, thresholds, or models.
