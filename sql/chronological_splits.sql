CREATE OR REPLACE TEMP VIEW phase2_step_ranks AS
SELECT
    step,
    ROW_NUMBER() OVER (ORDER BY step) AS step_rank,
    COUNT(*) OVER () AS step_count
FROM (SELECT DISTINCT step FROM transactions);

CREATE OR REPLACE TEMP VIEW phase2_split_cutoffs AS
WITH counts AS (
    SELECT MAX(step_count) AS step_count
    FROM phase2_step_ranks
), ranks AS (
    SELECT
        step_count,
        GREATEST(
            1,
            LEAST(step_count - 2, CAST(FLOOR(step_count * 0.70) AS BIGINT))
        ) AS train_end_rank,
        GREATEST(
            2,
            LEAST(step_count - 1, CAST(FLOOR(step_count * 0.85) AS BIGINT))
        ) AS validation_end_rank
    FROM counts
)
SELECT
    ranks.step_count,
    ranks.train_end_rank,
    ranks.validation_end_rank,
    MAX(phase2_step_ranks.step) FILTER (
        WHERE phase2_step_ranks.step_rank = ranks.train_end_rank
    ) AS train_end_step,
    MAX(phase2_step_ranks.step) FILTER (
        WHERE phase2_step_ranks.step_rank = ranks.validation_end_rank
    ) AS validation_end_step
FROM ranks
JOIN phase2_step_ranks ON TRUE
GROUP BY ALL;

CREATE OR REPLACE TEMP VIEW phase2_split_by_step AS
SELECT
    phase2_step_ranks.step,
    CASE
        WHEN phase2_step_ranks.step <= phase2_split_cutoffs.train_end_step THEN 'train'
        WHEN phase2_step_ranks.step <= phase2_split_cutoffs.validation_end_step THEN 'validation'
        ELSE 'test'
    END AS split
FROM phase2_step_ranks
CROSS JOIN phase2_split_cutoffs;

CREATE OR REPLACE TEMP VIEW transaction_split AS
SELECT transactions.*, phase2_split_by_step.split
FROM transactions
JOIN phase2_split_by_step USING (step);