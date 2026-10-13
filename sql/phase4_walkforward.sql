CREATE OR REPLACE TEMP VIEW phase4_features AS
SELECT * FROM read_parquet('__PARQUET_PATH__');

CREATE OR REPLACE TEMP VIEW phase4_step_support AS
SELECT
    split_step AS step,
    COUNT(*) AS transaction_count,
    COUNT(*) FILTER (WHERE label_is_fraud = 1) AS fraud_count
FROM phase4_features
GROUP BY split_step;

CREATE OR REPLACE TEMP VIEW phase4_fold_assignments AS
SELECT
    step,
    transaction_count,
    fraud_count,
    CASE
        WHEN step BETWEEN 251 AND 350 THEN 'fold_1_validation'
        WHEN step BETWEEN 351 AND 450 THEN 'fold_2_validation'
        WHEN step BETWEEN 451 AND 540 THEN 'fold_3_validation'
        WHEN step BETWEEN 541 AND 631 THEN 'fold_4_validation'
        WHEN step BETWEEN 632 AND 743 THEN 'reserved_final_evaluation'
        ELSE 'walk_forward_history'
    END AS latest_role,
    step <= 250 AS fold_1_train_eligible,
    step <= 350 AS fold_2_train_eligible,
    step <= 450 AS fold_3_train_eligible,
    step <= 540 AS fold_4_train_eligible,
    step <= 631 AS final_fit_eligible,
    step BETWEEN 632 AND 743 AS reserved_final_evaluation
FROM phase4_step_support;