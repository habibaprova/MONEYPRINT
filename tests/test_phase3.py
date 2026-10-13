from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.phase3_evaluation import (
    FEATURE_ABLATIONS,
    FORBIDDEN_FIELDS,
    PREDICTORS,
    calculate_metrics,
    evaluate_populations,
    make_logistic_pipeline,
    make_preprocessor,
    rank_indices,
)


class Phase3EvaluationTests(unittest.TestCase):
    def test_predictor_sets_exclude_targets_post_event_and_metadata(self) -> None:
        for spec in FEATURE_ABLATIONS.values():
            used = set(spec["numeric"]) | set(spec["categorical"])
            self.assertTrue(used.issubset(PREDICTORS))
            self.assertFalse(used.intersection(FORBIDDEN_FIELDS))
        self.assertNotIn("label_is_fraud", PREDICTORS)

    def test_preprocessor_learns_categories_from_training_only(self) -> None:
        training = pd.DataFrame(
            {"amount": [10.0, 30.0], "transaction_type": ["TRANSFER", "CASH_OUT"]}
        )
        validation = pd.DataFrame(
            {"amount": [20.0], "transaction_type": ["DEBIT"]}
        )
        preprocessor = make_preprocessor(("amount",), ("transaction_type",))
        preprocessor.fit(training)

        categories = preprocessor.named_transformers_["categorical"].categories_[0]
        transformed_validation = preprocessor.transform(validation)
        self.assertEqual(set(categories), {"CASH_OUT", "TRANSFER"})
        self.assertEqual(transformed_validation.shape[0], 1)
        self.assertEqual(preprocessor.named_transformers_["numeric"].named_steps["scale"].mean_.shape, (1,))

    def test_logistic_solver_supports_sparse_cholesky(self) -> None:
        model = make_logistic_pipeline(("amount",), ("transaction_type",), "balanced")
        self.assertEqual(model.named_steps["logistic"].solver, "newton-cholesky")
        self.assertEqual(model.named_steps["logistic"].tol, 1e-5)

    def test_metric_values_on_hand_calculated_example(self) -> None:
        labels = np.array([1, 0, 1, 0], dtype=np.int8)
        scores = np.array([0.9, 0.8, 0.7, 0.1])
        metrics = calculate_metrics(labels, scores, k_values=(1, 2, 4))

        self.assertAlmostEqual(metrics["pr_auc_average_precision"], 5 / 6)
        self.assertAlmostEqual(metrics["roc_auc"], 0.75)
        self.assertEqual(metrics["true_positives_at_1"], 1)
        self.assertEqual(metrics["false_positives_at_2"], 1)
        self.assertAlmostEqual(metrics["precision_at_2"], 0.5)
        self.assertAlmostEqual(metrics["recall_at_2"], 0.5)

    def test_ranking_is_deterministic_for_tied_scores(self) -> None:
        scores = np.array([0.5, 0.5, 0.9, 0.5])
        tie_keys = np.array([30, 10, 20, 5])
        expected = np.array([2, 3, 1, 0])
        np.testing.assert_array_equal(rank_indices(scores, tie_keys), expected)
        np.testing.assert_array_equal(rank_indices(scores, tie_keys), expected)

    def test_scores_reconcile_to_rows_and_population_metrics(self) -> None:
        frame = pd.DataFrame(
            {
                "transaction_type": ["TRANSFER", "CASH_IN", "CASH_OUT", "PAYMENT"],
                "label_is_fraud": [1, 0, 0, 1],
            }
        )
        result = evaluate_populations(frame, np.array([0.9, 0.1, 0.8, 0.2]))
        self.assertEqual(result["all_transactions"]["transaction_count"], 4)
        self.assertEqual(result["transfer_cash_out"]["transaction_count"], 2)
        with self.assertRaises(ValueError):
            evaluate_populations(frame, np.array([0.9, 0.1]))


if __name__ == "__main__":
    unittest.main()