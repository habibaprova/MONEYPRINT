from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.phase3_evaluation import FEATURE_ABLATIONS, FORBIDDEN_FIELDS, PREDICTORS
from src.phase4_walkforward import (
    ALERT_RATE,
    FEATURE_SET_NAMES,
    FOLD_SPECS,
    FINAL_PERIOD,
    choose_final_feature_set,
    metrics_for_population,
    validate_fold_specs,
)
from src.features import ROOT


class Phase4WalkForwardTests(unittest.TestCase):
    def test_folds_expand_and_reserved_period_is_disjoint(self) -> None:
        validate_fold_specs(FOLD_SPECS)
        for previous, current in zip(FOLD_SPECS, FOLD_SPECS[1:], strict=False):
            self.assertGreater(current["train_end"], previous["train_end"])
            self.assertGreater(current["validation_start"], previous["validation_end"])
        self.assertEqual(FINAL_PERIOD["start_step"], FOLD_SPECS[-1]["validation_end"] + 1)

    def test_all_feature_sets_exclude_label_and_forbidden_fields(self) -> None:
        self.assertEqual(set(FEATURE_SET_NAMES), set(FEATURE_ABLATIONS))
        for feature_set in FEATURE_SET_NAMES:
            features = set(FEATURE_ABLATIONS[feature_set]["numeric"]) | set(
                FEATURE_ABLATIONS[feature_set]["categorical"]
            )
            self.assertTrue(features.issubset(PREDICTORS))
            self.assertFalse(features.intersection(FORBIDDEN_FIELDS))

    def test_selection_uses_fold_validation_metrics_and_not_final_period(self) -> None:
        values = {}
        for index, feature_set in enumerate(FEATURE_SET_NAMES, start=1):
            values[feature_set] = [
                {
                    "transfer_cash_out": {
                        "pr_auc_average_precision": (5 - index) / 10,
                        "roc_auc": index / 10,
                    }
                },
                {
                    "transfer_cash_out": {
                        "pr_auc_average_precision": (5 - index) / 10,
                        "roc_auc": index / 10,
                    }
                },
            ]
        selected, summary = choose_final_feature_set(values)
        self.assertEqual(selected, FEATURE_SET_NAMES[-1])
        self.assertEqual(summary[selected]["mean_roc_auc"], 0.4)
        self.assertEqual(summary[selected]["mean_pr_auc"], 0.1)

    def test_fixed_alert_rate_metric_uses_deterministic_top_fraction(self) -> None:
        labels = np.array([1, 0, 1, 0, 1, 0, 0, 0], dtype=np.int8)
        scores = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2])
        metrics = metrics_for_population(labels, scores, alert_rate=0.25)
        self.assertEqual(metrics["alerts_at_fixed_rate"], 2)
        self.assertEqual(metrics["true_positives_at_fixed_rate"], 1)
        self.assertEqual(metrics["false_positives_at_fixed_rate"], 1)
        self.assertEqual(metrics["precision_at_fixed_rate"], 0.5)
        self.assertEqual(metrics["alert_rate_target"], 0.25)

    def test_recipient_history_sql_excludes_current_and_future_steps(self) -> None:
        sql = (ROOT / "sql" / "candidate_features.sql").read_text(encoding="utf-8")
        self.assertIn("ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING", sql)
        self.assertIn("GROUP BY nameDest, step", sql)
        self.assertIn("history.step = source.step", sql)

        events = pd.DataFrame(
            {
                "step": [1, 1, 2, 2, 3],
                "recipient": ["R", "R", "R", "R", "R"],
                "amount": [10.0, 20.0, 30.0, 40.0, 50.0],
            }
        )
        grouped = events.groupby(["recipient", "step"], as_index=False).agg(
            prior_count_seed=("amount", "count"), prior_amount_seed=("amount", "sum")
        )
        grouped["prior_count"] = grouped.groupby("recipient")["prior_count_seed"].cumsum() - grouped["prior_count_seed"]
        grouped["prior_amount"] = grouped.groupby("recipient")["prior_amount_seed"].cumsum() - grouped["prior_amount_seed"]
        self.assertEqual(grouped.loc[grouped.step == 1, "prior_count"].iloc[0], 0)
        self.assertEqual(grouped.loc[grouped.step == 2, "prior_count"].iloc[0], 2)
        self.assertEqual(grouped.loc[grouped.step == 2, "prior_amount"].iloc[0], 30.0)
        self.assertEqual(grouped.loc[grouped.step == 3, "prior_count"].iloc[0], 4)
        self.assertEqual(grouped.loc[grouped.step == 3, "prior_amount"].iloc[0], 100.0)


if __name__ == "__main__":
    unittest.main()