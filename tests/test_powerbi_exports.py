from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import pandas as pd

from src.powerbi_exports import (
    EXPORT_DIR,
    EXAMPLE_CAP,
    EXPORT_FILENAMES,
    MODEL_ID,
    PHASE3_REPORT_PATH,
    PHASE4_REPORT_PATH,
    PROTOCOL_VERSION,
)


ROOT = Path(__file__).resolve().parents[1]


class PowerBIExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        missing = [name for name in EXPORT_FILENAMES if not (EXPORT_DIR / name).is_file()]
        if missing:
            raise AssertionError(f"Run src.powerbi_exports before export integrity tests: {missing}")
        cls.phase3 = json.loads(PHASE3_REPORT_PATH.read_text(encoding="utf-8"))
        cls.phase4 = json.loads(PHASE4_REPORT_PATH.read_text(encoding="utf-8"))

    def _read(self, filename: str) -> pd.DataFrame:
        return pd.read_csv(EXPORT_DIR / filename)

    def test_population_totals_reconcile_to_saved_audit(self) -> None:
        executive = self._read("executive_kpi_summary.csv")
        overview = self._read("transaction_type_overview.csv")
        amount_distribution = self._read("transaction_amount_distribution.csv")
        fraud = self._read("fraud_by_transaction_type.csv")
        trends_by_step = self._read("transaction_trends_by_step.csv")
        trends_by_hour = self._read("transaction_trends_by_hour.csv")
        expected_rows = sum(
            int(row["transaction_count"])
            for row in self.phase3["split_audit"]["split_summary"]
        )
        expected_fraud = sum(
            int(row["fraud_count"])
            for row in self.phase3["split_audit"]["split_summary"]
        )
        self.assertEqual(int(overview.transaction_count.sum()), expected_rows)
        self.assertEqual(int(fraud.transaction_count.sum()), expected_rows)
        self.assertEqual(int(overview.fraud_count.sum()), expected_fraud)
        executive_values = dict(zip(executive.metric_key, executive.metric_value))
        self.assertEqual(int(executive_values["total_transactions"]), expected_rows)
        self.assertEqual(int(executive_values["fraud_labels"]), expected_fraud)
        self.assertEqual(int(amount_distribution.transaction_count.sum()), expected_rows)
        self.assertEqual(int(trends_by_step.transaction_count.sum()), expected_rows)
        self.assertEqual(int(trends_by_hour.transaction_count.sum()), expected_rows)

    def test_performance_exports_are_phase4_only_and_match_authoritative_report(self) -> None:
        fold_metrics = self._read("phase4_walkforward_fold_metrics.csv")
        capacity = self._read("phase4_investigation_capacity.csv")
        self.assertEqual(set(fold_metrics.protocol_version), {PROTOCOL_VERSION})
        self.assertTrue(fold_metrics.is_selected_phase4_model.dtype == bool)
        selected = fold_metrics.loc[
            fold_metrics.is_selected_phase4_model
            & (fold_metrics.population == "transfer_cash_out")
            & (fold_metrics.split == "validation")
        ]
        self.assertEqual(set(selected.model_id), {MODEL_ID})
        self.assertGreater(fold_metrics.model_id.nunique(), 1)
        saved = [
            row
            for row in self.phase4["validation_metrics"]
            if row["method"] == "logistic_plus_balance_balanced"
            and row["population"] == "transfer_cash_out"
        ]
        self.assertEqual(len(selected), len(saved))
        saved_index = {row["fold"]: row for row in saved}
        for row in selected.itertuples(index=False):
            self.assertAlmostEqual(row.roc_auc, saved_index[row.fold]["roc_auc"], places=12)
            self.assertAlmostEqual(
                row.pr_auc_average_precision,
                saved_index[row.fold]["pr_auc_average_precision"],
                places=12,
            )
        self.assertEqual(set(capacity.model_id), {MODEL_ID})
        self.assertEqual(set(capacity.protocol_version), {PROTOCOL_VERSION})

    def test_investigation_examples_are_capped_ranked_and_labeled_as_selected(self) -> None:
        examples = self._read("phase4_selected_model_investigation_examples.csv")
        self.assertEqual(len(examples), EXAMPLE_CAP)
        self.assertEqual(set(examples.model_id), {MODEL_ID})
        self.assertEqual(set(examples.protocol_version), {PROTOCOL_VERSION})
        self.assertTrue(examples.risk_score.is_monotonic_decreasing)
        self.assertTrue(examples.split_step.between(632, 743).all())
        self.assertTrue(examples.transaction_type.isin(["TRANSFER", "CASH_OUT"]).all())
        selected_metrics = next(
            row
            for row in self.phase4["reserved_period_metrics"]
            if row["method"] == "logistic_plus_balance_balanced"
            and row["population"] == "transfer_cash_out"
        )
        self.assertEqual(
            int(examples.label_for_retrospective_review.sum()),
            selected_metrics["true_positives_at_500"],
        )
        self.assertNotIn("nameOrig", examples.columns)
        self.assertNotIn("nameDest", examples.columns)
        self.assertNotIn("isFlaggedFraud", examples.columns)
        self.assertIn("Top-ranked", examples.population_warning.iloc[0])
        self.assertIn("label_for_retrospective_review", examples.columns)

    def test_split_comparison_and_relationship_dimensions_reconcile(self) -> None:
        comparison = self._read("split_distribution_comparison.csv")
        expected_rows = sum(
            int(row["transaction_count"])
            for row in self.phase3["split_audit"]["split_summary"]
        )
        for protocol in comparison.split_protocol.unique():
            all_rows = comparison.loc[
                (comparison.split_protocol == protocol)
                & (comparison.transaction_type == "ALL"),
                "transaction_count",
            ].sum()
            self.assertEqual(int(all_rows), expected_rows)
        self.assertEqual(
            len(self._read("dim_transaction_type.csv")), 5
        )
        self.assertEqual(len(self._read("dim_simulated_hour.csv")), 24)
        self.assertEqual(len(self._read("dim_simulated_step.csv")), 743)
        type_rows = comparison.loc[comparison.transaction_type != "ALL"]
        shares = type_rows.groupby(["split_protocol", "split"])["transaction_share"].sum()
        for share in shares:
            self.assertAlmostEqual(float(share), 1.0, places=10)

    def test_theme_and_guide_use_real_export_columns(self) -> None:
        theme_path = ROOT / "powerbi" / "MONEYPRINT_THEME.json"
        theme = json.loads(theme_path.read_text(encoding="utf-8"))
        self.assertEqual(theme["background"], "#F0EDCF")
        self.assertEqual(theme["foreground"], "#474538")
        guide = (ROOT / "powerbi" / "POWER_BI_BUILD_GUIDE.md").read_text(encoding="utf-8")
        self.assertIn("executive_kpi_summary[metric_value]", guide)
        self.assertIn("transaction_amount_distribution[amount_band]", guide)
        self.assertIn("phase4_walkforward_fold_metrics[roc_auc]", guide)
        self.assertIn("phase4_investigation_capacity[precision]", guide)
        self.assertIn("label_for_retrospective_review", guide)
        self.assertIn("not representative", guide)
        for filename in (
            "DASHBOARD_WIREFRAME.md",
            "POWER_BI_BUILD_CHECKLIST.md",
        ):
            self.assertTrue((ROOT / "powerbi" / filename).is_file())

    def test_every_dax_table_column_reference_exists_in_an_export(self) -> None:
        guide = (ROOT / "powerbi" / "POWER_BI_BUILD_GUIDE.md").read_text(encoding="utf-8")
        references = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\[([^\]]+)\]", guide))
        columns_by_table = {
            path.stem: set(pd.read_csv(path, nrows=0).columns)
            for path in EXPORT_DIR.glob("*.csv")
        }
        missing = sorted(
            (table, column)
            for table, column in references
            if table in columns_by_table and column not in columns_by_table[table]
        )
        unknown_tables = sorted(table for table, _ in references if table not in columns_by_table)
        self.assertEqual(missing, [])
        self.assertEqual(unknown_tables, [])


if __name__ == "__main__":
    unittest.main()