CREATE OR REPLACE TEMP MACRO balance_matches(delta, expected) AS (
    ROUND(ABS(delta - expected), 2) <= 0.01
);

CREATE OR REPLACE TEMP MACRO balance_unchanged(delta) AS (
    ROUND(ABS(delta), 2) <= 0.01
);

CREATE OR REPLACE TEMP VIEW type_summary AS
SELECT
    type AS transaction_type,
    COUNT(*) AS transaction_count,
    SUM(amount) AS total_amount,
    AVG(amount) AS mean_amount,
    quantile_cont(amount, 0.50) AS median_amount,
    quantile_cont(amount, 0.90) AS p90_amount,
    quantile_cont(amount, 0.95) AS p95_amount,
    quantile_cont(amount, 0.99) AS p99_amount,
    MAX(amount) AS max_amount,
    COUNT(*) FILTER (WHERE isFraud = 1) AS fraud_count,
    COUNT(*) FILTER (WHERE isFraud = 1)::DOUBLE / COUNT(*) AS fraud_rate,
    COUNT(*) FILTER (WHERE isFlaggedFraud = 1) AS flagged_fraud_count
FROM transactions
GROUP BY type;

CREATE OR REPLACE TEMP VIEW fraud_amount_comparison AS
SELECT
    type AS transaction_type,
    isFraud AS is_fraud,
    COUNT(*) AS transaction_count,
    AVG(amount) AS mean_amount,
    quantile_cont(amount, 0.50) AS median_amount,
    quantile_cont(amount, 0.95) AS p95_amount,
    MAX(amount) AS max_amount,
    COUNT(*) FILTER (WHERE oldbalanceOrg = 0) AS sender_pre_balance_zero,
    COUNT(*) FILTER (WHERE amount > oldbalanceOrg) AS amount_exceeds_sender_pre_balance
FROM transactions
WHERE type IN ('TRANSFER', 'CASH_OUT')
GROUP BY type, isFraud;

CREATE OR REPLACE TEMP VIEW hourly_trends AS
SELECT
    step % 24 AS simulated_hour,
    COUNT(*) AS transaction_count,
    SUM(amount) AS total_amount,
    COUNT(*) FILTER (WHERE isFraud = 1) AS fraud_count,
    COUNT(*) FILTER (WHERE isFraud = 1)::DOUBLE / COUNT(*) AS fraud_rate
FROM transactions
GROUP BY simulated_hour;

CREATE OR REPLACE TEMP VIEW receiver_account_totals AS
SELECT
    nameDest AS receiver_id,
    COUNT(*) AS transaction_count,
    SUM(amount) AS total_transaction_amount
FROM transactions
GROUP BY nameDest;

CREATE OR REPLACE TEMP VIEW receiver_concentration AS
WITH ranked_by_count AS (
    SELECT *, ROW_NUMBER() OVER (
        ORDER BY transaction_count DESC, receiver_id
    ) AS count_rank
    FROM receiver_account_totals
),
ranked_by_amount AS (
    SELECT *, ROW_NUMBER() OVER (
        ORDER BY total_transaction_amount DESC, receiver_id
    ) AS amount_rank
    FROM receiver_account_totals
),
totals AS (
    SELECT SUM(transaction_count) AS all_transactions,
           SUM(total_transaction_amount) AS all_amount
    FROM receiver_account_totals
)
SELECT
    (SELECT COUNT(*) FROM receiver_account_totals) AS unique_receivers,
    totals.all_transactions,
    totals.all_amount,
    (SELECT MAX(transaction_count) FROM receiver_account_totals) AS max_receiver_transactions,
    (SELECT SUM(transaction_count) FROM ranked_by_count WHERE count_rank = 1)
        / totals.all_transactions AS top_receiver_transaction_share,
    (SELECT SUM(transaction_count) FROM ranked_by_count WHERE count_rank <= 10)
        / totals.all_transactions AS top_10_transaction_share,
    (SELECT SUM(total_transaction_amount) FROM ranked_by_count WHERE count_rank <= 10)
        / totals.all_amount AS top_10_by_count_amount_share,
    (SELECT SUM(total_transaction_amount) FROM ranked_by_amount WHERE amount_rank <= 10)
        / totals.all_amount AS top_10_amount_share
FROM totals;

CREATE OR REPLACE TEMP VIEW account_frequency AS
SELECT 'sender' AS account_role, nameOrig AS account_id, COUNT(*) AS transaction_count
FROM transactions
GROUP BY nameOrig
UNION ALL
SELECT 'receiver' AS account_role, nameDest AS account_id, COUNT(*) AS transaction_count
FROM transactions
GROUP BY nameDest;

CREATE OR REPLACE TEMP VIEW account_frequency_bins AS
SELECT
    account_role,
    CASE
        WHEN transaction_count = 1 THEN '1'
        WHEN transaction_count = 2 THEN '2'
        WHEN transaction_count BETWEEN 3 AND 5 THEN '3-5'
        WHEN transaction_count BETWEEN 6 AND 10 THEN '6-10'
        WHEN transaction_count BETWEEN 11 AND 25 THEN '11-25'
        ELSE '26+'
    END AS frequency_bin,
    COUNT(*) AS account_count,
    SUM(transaction_count) AS transaction_rows
FROM account_frequency
GROUP BY account_role, frequency_bin;

CREATE OR REPLACE TEMP VIEW account_frequency_summary AS
SELECT
    account_role,
    COUNT(*) AS unique_accounts,
    COUNT(*) FILTER (WHERE transaction_count > 1) AS repeated_accounts,
    SUM(transaction_count) FILTER (WHERE transaction_count > 1) AS rows_in_repeated_accounts,
    quantile_cont(transaction_count, 0.50) AS median_transactions,
    quantile_cont(transaction_count, 0.90) AS p90_transactions,
    quantile_cont(transaction_count, 0.99) AS p99_transactions,
    MAX(transaction_count) AS max_transactions
FROM account_frequency
GROUP BY account_role;

CREATE OR REPLACE TEMP VIEW sender_balance_by_type AS
WITH deltas AS (
    SELECT *, newbalanceOrig - oldbalanceOrg AS balance_delta
    FROM transactions
)
SELECT
    type AS transaction_type,
    COUNT(*) AS transaction_count,
    COUNT(*) FILTER (WHERE oldbalanceOrg = 0) AS pre_balance_zero,
    COUNT(*) FILTER (WHERE newbalanceOrig = 0) AS post_balance_zero,
    COUNT(*) FILTER (WHERE amount > oldbalanceOrg) AS amount_exceeds_pre_balance,
        COUNT(*) FILTER (WHERE balance_matches(balance_delta, amount)) AS delta_matches_positive_amount,
        COUNT(*) FILTER (WHERE balance_matches(balance_delta, -amount)) AS delta_matches_negative_amount,
        COUNT(*) FILTER (WHERE balance_unchanged(balance_delta)) AS unchanged_balance,
    COUNT(*) FILTER (
                WHERE NOT balance_matches(balance_delta, amount)
                    AND NOT balance_matches(balance_delta, -amount)
                    AND NOT balance_unchanged(balance_delta)
    ) AS other_balance_delta
FROM deltas
GROUP BY type;

CREATE OR REPLACE TEMP VIEW receiver_balance_by_type AS
WITH deltas AS (
    SELECT
        *,
        newbalanceDest - oldbalanceDest AS balance_delta,
        CASE
            WHEN nameDest LIKE 'C%' THEN 'C-prefix'
            WHEN nameDest LIKE 'M%' THEN 'M-prefix'
            ELSE 'other-prefix'
        END AS receiver_prefix
    FROM transactions
)
SELECT
    type AS transaction_type,
    receiver_prefix,
    COUNT(*) AS transaction_count,
    COUNT(*) FILTER (WHERE oldbalanceDest = 0) AS pre_balance_zero,
    COUNT(*) FILTER (WHERE newbalanceDest = 0) AS post_balance_zero,
        COUNT(*) FILTER (WHERE balance_matches(balance_delta, amount)) AS delta_matches_positive_amount,
        COUNT(*) FILTER (WHERE balance_matches(balance_delta, -amount)) AS delta_matches_negative_amount,
        COUNT(*) FILTER (WHERE balance_unchanged(balance_delta)) AS unchanged_balance,
    COUNT(*) FILTER (
                WHERE NOT balance_matches(balance_delta, amount)
                    AND NOT balance_matches(balance_delta, -amount)
                    AND NOT balance_unchanged(balance_delta)
    ) AS other_balance_delta
FROM deltas
GROUP BY type, receiver_prefix;

CREATE OR REPLACE TEMP VIEW balance_zero_patterns AS
SELECT
    type AS transaction_type,
    COUNT(*) AS transaction_count,
    COUNT(*) FILTER (WHERE oldbalanceOrg = 0) AS sender_pre_zero,
    COUNT(*) FILTER (WHERE newbalanceOrig = 0) AS sender_post_zero,
    COUNT(*) FILTER (WHERE oldbalanceOrg = 0 AND newbalanceOrig = 0) AS sender_both_zero,
    COUNT(*) FILTER (WHERE oldbalanceDest = 0) AS receiver_pre_zero,
    COUNT(*) FILTER (WHERE newbalanceDest = 0) AS receiver_post_zero,
    COUNT(*) FILTER (WHERE oldbalanceDest = 0 AND newbalanceDest = 0) AS receiver_both_zero
FROM transactions
GROUP BY type;

CREATE OR REPLACE TEMP VIEW balance_by_label AS
WITH deltas AS (
    SELECT
        *,
        newbalanceOrig - oldbalanceOrg AS sender_delta,
        newbalanceDest - oldbalanceDest AS receiver_delta,
        CASE WHEN type = 'CASH_IN' THEN amount ELSE -amount END AS candidate_sender_delta
    FROM transactions
)
SELECT
    type AS transaction_type,
    isFraud AS is_fraud,
    COUNT(*) AS transaction_count,
    COUNT(*) FILTER (
        WHERE NOT balance_matches(sender_delta, candidate_sender_delta)
    ) AS sender_candidate_mismatch_count,
    COUNT(*) FILTER (WHERE ABS(sender_delta) <= 0.01) AS sender_unchanged_count,
    COUNT(*) FILTER (WHERE ABS(receiver_delta) <= 0.01) AS receiver_unchanged_count
FROM deltas
GROUP BY type, isFraud;

CREATE OR REPLACE TEMP VIEW balance_exceptions AS
WITH candidates AS (
    SELECT
        step,
        type AS transaction_type,
        amount,
        oldbalanceOrg AS sender_pre_balance,
        newbalanceOrig AS sender_post_balance,
        newbalanceOrig - oldbalanceOrg AS sender_delta,
        amount > oldbalanceOrg AS amount_exceeds_sender_pre_balance,
        CASE
            WHEN nameDest LIKE 'C%' THEN 'C-prefix'
            WHEN nameDest LIKE 'M%' THEN 'M-prefix'
            ELSE 'other-prefix'
        END AS receiver_prefix,
        oldbalanceDest AS receiver_pre_balance,
        newbalanceDest AS receiver_post_balance,
        newbalanceDest - oldbalanceDest AS receiver_delta,
        isFraud AS label_is_fraud,
        ROW_NUMBER() OVER (PARTITION BY type ORDER BY step, amount) AS example_rank
    FROM transactions
        WHERE NOT balance_matches(newbalanceOrig - oldbalanceOrg, amount)
            AND NOT balance_matches(newbalanceOrig - oldbalanceOrg, -amount)
            AND NOT balance_unchanged(newbalanceOrig - oldbalanceOrg)
)
SELECT * EXCLUDE (example_rank)
FROM candidates
WHERE example_rank <= 2;