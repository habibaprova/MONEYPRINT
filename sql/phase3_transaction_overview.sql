SELECT
    split,
    transaction_type,
    simulated_hour,
    COUNT(*) AS transaction_count,
    SUM(amount) AS total_amount,
    AVG(amount) AS mean_amount,
    quantile_cont(amount, 0.50) AS median_amount,
    quantile_cont(amount, 0.95) AS p95_amount,
    COUNT(*) FILTER (WHERE label_is_fraud = 1) AS fraud_count,
    COUNT(*) FILTER (WHERE label_is_fraud = 1)::DOUBLE / COUNT(*) AS fraud_prevalence
FROM phase3_features
GROUP BY split, transaction_type, simulated_hour
ORDER BY
    CASE split WHEN 'train' THEN 1 WHEN 'validation' THEN 2 ELSE 3 END,
    transaction_type,
    simulated_hour;