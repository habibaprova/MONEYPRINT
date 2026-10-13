from __future__ import annotations

import unittest

from src.phase3_evaluation import FEATURE_ABLATIONS, FORBIDDEN_FIELDS, PREDICTORS
from src.phase3_robustness import (
    FEATURE_SET_ORDER,
    choose_whole_step_boundaries,
    select_validation_model,
)


class Phase3RobustnessTests(unittest.TestCase):
    def test_row_weighted_boundaries_use_complete_steps(self) -> None:
        rows = [(1, 70), (2, 5), (3, 10), (4, 5), (5, 10)]
        result = choose_whole_step_boundaries(rows)

        self.assertEqual(result["train_end_step"], 1)
        self.assertEqual(result["validation_end_step"], 3)
        self.assertLess(result["train_end_step"], result["validation_end_step"])
        self.assertEqual(result["train_end_cumulative_transactions"], 70)
        self.assertEqual(result["validation_end_cumulative_transactions"], 85)

    def test_boundaries_are_based_only_on_step_transaction_counts(self) -> None:
        rows = [(10, 7), (20, 1), (30, 1), (40, 1), (50, 1), (60, 1)]
        result = choose_whole_step_boundaries(rows)
        self.assertIn(result["train_end_step"], {10, 20, 30, 40})
        self.assertIn(result["validation_end_step"], {20, 30, 40, 50})

    def test_feature_sets_exclude_leakage_fields(self) -> None:
        self.assertEqual(set(FEATURE_SET_ORDER), set(FEATURE_ABLATIONS))
        for feature_set in FEATURE_SET_ORDER:
            selected = set(FEATURE_ABLATIONS[feature_set]["numeric"]) | set(
                FEATURE_ABLATIONS[feature_set]["categorical"]
            )
            self.assertTrue(selected.issubset(PREDICTORS))
            self.assertFalse(selected.intersection(FORBIDDEN_FIELDS))

    def test_selection_uses_validation_metrics_only(self) -> None:
        results = {
            name: {
                "transfer_cash_out": {
                    "pr_auc_average_precision": index / 10,
                    "f1_at_100": index / 10,
                    "f1_at_500": index / 10,
                    "precision_at_100": index / 10,
                    "recall_at_100": index / 10,
                    "false_positives_at_100": 100 - index,
                    "precision_at_500": index / 10,
                    "recall_at_500": index / 10,
                    "false_positives_at_500": 500 - index,
                }
            }
            for index, name in enumerate(FEATURE_SET_ORDER, start=1)
        }
        selected, budget, metadata = select_validation_model(results)

        self.assertEqual(selected, FEATURE_SET_ORDER[-1])
        self.assertEqual(budget, 100)
        self.assertFalse(metadata["test_labels_used_for_selection"])


if __name__ == "__main__":
    unittest.main()