-- Aggregate all receipts at a recipient-step grain before applying the window.
-- ROWS ... 1 PRECEDING then excludes the current step as a whole, so rows from
-- the same step cannot contribute to one another's history.
WITH recipient_step_totals AS (
    SELECT
        nameDest,
        step,
        COUNT(*) AS received_transaction_count,
        SUM(amount) AS received_amount
    FROM transactions
    GROUP BY nameDest, step
), recipient_history AS (
    SELECT
        nameDest,
        step,
        CAST(COALESCE(
            SUM(received_transaction_count) OVER (
                PARTITION BY nameDest
                ORDER BY step
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ),
            0
        ) AS BIGINT) AS recipient_prior_transaction_count,
        COALESCE(
            SUM(received_amount) OVER (
                PARTITION BY nameDest
                ORDER BY step
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ),
            0.0
        ) AS recipient_prior_received_amount
    FROM recipient_step_totals
)
SELECT
    source.step AS split_step,
    split.split,
    source.isFraud AS label_is_fraud,
    source.amount,
    source.type AS transaction_type,
    CAST(source.step % 24 AS INTEGER) AS simulated_hour,
    source.oldbalanceOrg AS sender_pre_balance,
    source.amount / NULLIF(source.oldbalanceOrg, 0) AS amount_to_sender_pre_balance,
    source.oldbalanceOrg >= source.amount AS sender_balance_covers_amount,
    history.recipient_prior_transaction_count,
    history.recipient_prior_received_amount
FROM transactions AS source
JOIN phase2_split_by_step AS split ON split.step = source.step
JOIN recipient_history AS history
    ON history.nameDest = source.nameDest
   AND history.step = source.step