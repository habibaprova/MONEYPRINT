CREATE OR REPLACE TEMP VIEW robustness_source AS
SELECT
    split_step,
    split,
    label_is_fraud,
    amount,
    transaction_type,
    simulated_hour,
    sender_pre_balance,
    amount_to_sender_pre_balance,
    sender_balance_covers_amount,
    recipient_prior_transaction_count,
    recipient_prior_received_amount
FROM read_parquet('__PARQUET_PATH__');

CREATE OR REPLACE TEMP VIEW robustness_step_counts AS
SELECT split_step AS step, COUNT(*) AS transaction_count
FROM robustness_source
GROUP BY split_step;

CREATE OR REPLACE TEMP VIEW robustness_step_cumulative AS
SELECT
    step,
    transaction_count,
    SUM(transaction_count) OVER (ORDER BY step) AS cumulative_transactions,
    SUM(transaction_count) OVER () AS total_transactions,
    cumulative_transactions::DOUBLE / total_transactions AS cumulative_transaction_share
FROM robustness_step_counts;