"""Build chronology-safe candidate features as a compressed Parquet dataset."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb


ROOT = Path(__file__).resolve().parents[1]
CHRONOLOGICAL_SQL = ROOT / "sql" / "chronological_splits.sql"
CANDIDATE_FEATURES_SQL = ROOT / "sql" / "candidate_features.sql"
PREDICTOR_COLUMNS = (
    "amount",
    "transaction_type",
    "simulated_hour",
    "sender_pre_balance",
    "amount_to_sender_pre_balance",
    "sender_balance_covers_amount",
    "recipient_prior_transaction_count",
    "recipient_prior_received_amount",
)
FORBIDDEN_PREDICTOR_COLUMNS = (
    "isFraud",
    "isFlaggedFraud",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
    "nameOrig",
    "nameDest",
)


def execute_sql_file(connection: duckdb.DuckDBPyConnection, sql_path: Path) -> None:
    for statement in connection.extract_statements(sql_path.read_text(encoding="utf-8")):
        connection.execute(statement)


def register_transactions(
    connection: duckdb.DuckDBPyConnection, csv_path: Path
) -> None:
    if not csv_path.is_file():
        raise FileNotFoundError(f"PaySim CSV not found: {csv_path}")
    csv_literal = str(csv_path.resolve()).replace("'", "''")
    connection.execute(
        "CREATE OR REPLACE TEMP VIEW transactions AS "
        f"SELECT * FROM read_csv_auto('{csv_literal}', header = true)"
    )


def build_candidate_parquet(
    connection: duckdb.DuckDBPyConnection, parquet_path: Path
) -> dict[str, Any]:
    execute_sql_file(connection, CHRONOLOGICAL_SQL)
    cutoffs = connection.execute(
        "SELECT step_count, train_end_rank, validation_end_rank, "
        "train_end_step, validation_end_step FROM phase2_split_cutoffs"
    ).fetchone()
    if cutoffs is None or cutoffs[0] < 3:
        raise ValueError("At least three distinct time steps are required for a split")

    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_literal = str(parquet_path.resolve()).replace("\\", "/").replace("'", "''")
    feature_sql = CANDIDATE_FEATURES_SQL.read_text(encoding="utf-8").strip().removesuffix(";")
    connection.execute(
        f"COPY ({feature_sql}) TO '{parquet_literal}' "
        "(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE)"
    )

    parquet_source = f"read_parquet('{parquet_literal}')"
    output_columns = {
        row[0]
        for row in connection.execute(f"DESCRIBE SELECT * FROM {parquet_source}").fetchall()
    }
    if output_columns.intersection(FORBIDDEN_PREDICTOR_COLUMNS):
        raise AssertionError("Forbidden post-event or raw-ID fields found in feature output")
    if not set(PREDICTOR_COLUMNS).issubset(output_columns):
        raise AssertionError("Candidate predictor columns are missing from feature output")

    non_ratio_null_checks = " OR ".join(
        f"{column} IS NULL"
        for column in PREDICTOR_COLUMNS
        if column != "amount_to_sender_pre_balance"
    )
    feature_checks = connection.execute(
        f"SELECT COUNT(*) AS total_records, "
        f"COUNT(*) FILTER (WHERE {non_ratio_null_checks}) AS unexpected_null_rows, "
        "COUNT(*) FILTER (WHERE amount_to_sender_pre_balance IS NULL) AS ratio_nulls, "
        "COUNT(*) FILTER (WHERE sender_pre_balance = 0) AS zero_sender_pre_balance, "
        "COUNT(*) FILTER (WHERE label_is_fraud = 1) AS fraud_records "
        f"FROM {parquet_source}"
    ).fetchone()
    if feature_checks[1] != 0:
        raise AssertionError(f"Unexpected null in candidate features: {feature_checks[1]} rows")
    if feature_checks[2] != feature_checks[3]:
        raise AssertionError("The balance ratio should be null only for zero pre-balances")

    split_rows = connection.execute(
        f"SELECT split, COUNT(*) AS transaction_count, "
        "COUNT(*) FILTER (WHERE label_is_fraud = 1) AS fraud_count, "
        "COUNT(DISTINCT split_step) AS distinct_steps "
        f"FROM {parquet_source} GROUP BY split "
        "ORDER BY CASE split WHEN 'train' THEN 1 WHEN 'validation' THEN 2 ELSE 3 END"
    ).fetchall()
    total_records = int(feature_checks[0])
    fraud_records = int(feature_checks[4])
    if sum(int(row[1]) for row in split_rows) != total_records:
        raise AssertionError("Chronological split counts do not reconcile to the feature row count")
    if sum(int(row[2]) for row in split_rows) != fraud_records:
        raise AssertionError("Chronological split fraud counts do not reconcile")

    mixed_steps = connection.execute(
        f"SELECT COUNT(*) FROM (SELECT split_step FROM {parquet_source} "
        "GROUP BY split_step HAVING COUNT(DISTINCT split) > 1)"
    ).fetchone()[0]
    if mixed_steps:
        raise AssertionError("Transactions from one step were assigned to multiple splits")

    return {
        "parquet_path": str(parquet_path),
        "compression": "ZSTD",
        "total_records": total_records,
        "fraud_records": fraud_records,
        "split_step_count": int(cutoffs[0]),
        "train_end_rank": int(cutoffs[1]),
        "validation_end_rank": int(cutoffs[2]),
        "train_end_step": int(cutoffs[3]),
        "validation_end_step": int(cutoffs[4]),
        "splits": [
            {
                "split": row[0],
                "transaction_count": int(row[1]),
                "fraud_count": int(row[2]),
                "distinct_steps": int(row[3]),
            }
            for row in split_rows
        ],
        "predictor_columns": list(PREDICTOR_COLUMNS),
        "target_column": "label_is_fraud",
        "output_columns": sorted(output_columns),
        "unexpected_null_rows": int(feature_checks[1]),
        "ratio_null_count": int(feature_checks[2]),
        "zero_sender_pre_balance_count": int(feature_checks[3]),
        "mixed_step_count": int(mixed_steps),
    }