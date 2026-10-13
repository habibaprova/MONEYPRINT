from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import duckdb

from src.features import (
    FORBIDDEN_PREDICTOR_COLUMNS,
    PREDICTOR_COLUMNS,
    ROOT,
    build_candidate_parquet,
    execute_sql_file,
    register_transactions,
)


class CandidateFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.csv_path = self.root / "fixture.csv"
        self.parquet_path = self.root / "features.parquet"
        columns = [
            "step", "type", "amount", "nameOrig", "oldbalanceOrg",
            "newbalanceOrig", "nameDest", "oldbalanceDest", "newbalanceDest",
            "isFraud", "isFlaggedFraud",
        ]
        rows = [
            [1, "TRANSFER", 10, "S1", 100, 89.99, "R1", 0, 10, 0, 0],
            [1, "TRANSFER", 20, "S2", 100, 80, "R1", 0, 20, 1, 0],
            [2, "CASH_OUT", 5, "S3", 0, 0, "R1", 30, 25, 0, 0],
            [3, "PAYMENT", 7, "S4", 50, 43, "R1", 35, 35, 0, 0],
            [3, "TRANSFER", 3, "S5", 60, 57, "R2", 0, 3, 0, 0],
        ]
        with self.csv_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(columns)
            writer.writerows(rows)
        self.connection = duckdb.connect()
        register_transactions(self.connection, self.csv_path)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()

    def test_same_step_rows_do_not_enter_recipient_history(self) -> None:
        result = build_candidate_parquet(self.connection, self.parquet_path)
        rows = self.connection.execute(
            "SELECT split_step, amount, recipient_prior_transaction_count, "
            "recipient_prior_received_amount FROM read_parquet(?) "
            "ORDER BY split_step, amount",
            [str(self.parquet_path)],
        ).fetchall()

        self.assertEqual([(row[2], row[3]) for row in rows[:2]], [(0, 0.0), (0, 0.0)])
        self.assertEqual(rows[2][2:], (2, 30.0))
        self.assertEqual(rows[3][2:], (0, 0.0))
        self.assertEqual(rows[4][2:], (3, 35.0))
        self.assertEqual(result["mixed_step_count"], 0)

    def test_chronological_splits_are_disjoint_and_reconcile(self) -> None:
        result = build_candidate_parquet(self.connection, self.parquet_path)
        self.assertEqual(
            [(row["split"], row["distinct_steps"]) for row in result["splits"]],
            [("train", 1), ("validation", 1), ("test", 1)],
        )
        self.assertEqual(sum(row["transaction_count"] for row in result["splits"]), 5)
        self.assertEqual(sum(row["fraud_count"] for row in result["splits"]), 1)

    def test_predictor_policy_and_null_contract(self) -> None:
        result = build_candidate_parquet(self.connection, self.parquet_path)
        self.assertNotIn("label_is_fraud", PREDICTOR_COLUMNS)
        self.assertFalse(set(FORBIDDEN_PREDICTOR_COLUMNS).intersection(PREDICTOR_COLUMNS))
        self.assertEqual(result["unexpected_null_rows"], 0)
        self.assertEqual(result["ratio_null_count"], result["zero_sender_pre_balance_count"])
        self.assertEqual(result["ratio_null_count"], 1)
        self.assertFalse(set(FORBIDDEN_PREDICTOR_COLUMNS).intersection(result["output_columns"]))
        count_type = self.connection.execute(
            "DESCRIBE SELECT recipient_prior_transaction_count "
            "FROM read_parquet(?)",
            [str(self.parquet_path)],
        ).fetchone()[1]
        self.assertEqual(count_type, "BIGINT")

    def test_balance_tolerance_and_eda_aggregates(self) -> None:
        execute_sql_file(self.connection, ROOT / "sql" / "phase2_eda.sql")
        transfer = self.connection.execute(
            "SELECT delta_matches_negative_amount, other_balance_delta "
            "FROM sender_balance_by_type WHERE transaction_type = 'TRANSFER'"
        ).fetchone()
        type_total = self.connection.execute(
            "SELECT SUM(transaction_count) FROM type_summary"
        ).fetchone()[0]
        hour_total = self.connection.execute(
            "SELECT SUM(transaction_count) FROM hourly_trends"
        ).fetchone()[0]

        self.assertEqual(transfer, (3, 0))
        self.assertEqual(type_total, 5)
        self.assertEqual(hour_total, 5)


if __name__ == "__main__":
    unittest.main()