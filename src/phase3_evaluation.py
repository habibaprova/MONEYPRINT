"""Train transparent rankers on PaySim train data and evaluate once on test."""

from __future__ import annotations

import argparse
import json
import time
import warnings
from pathlib import Path
from typing import Any

from .runtime_config import (
    RUNTIME_CONFIG,
    ResourceMonitor,
    numeric_thread_limits,
    threadpool_snapshot,
)

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from .features import ROOT


DEFAULT_PARQUET = ROOT / "data" / "processed" / "transaction_features.parquet"
DEFAULT_REPORT_DIR = ROOT / "reports"
DEFAULT_MODEL_DIR = ROOT / "models"
OVERVIEW_SQL = ROOT / "sql" / "phase3_transaction_overview.sql"
SEED = 42
TOP_K_VALUES = (100, 500)
INVESTIGATION_CAP_PER_SPLIT = 500
ELIGIBLE_TYPES = ("TRANSFER", "CASH_OUT")
PREDICTORS = (
    "amount",
    "transaction_type",
    "simulated_hour",
    "sender_pre_balance",
    "amount_to_sender_pre_balance",
    "sender_balance_covers_amount",
    "recipient_prior_transaction_count",
    "recipient_prior_received_amount",
)
FORBIDDEN_FIELDS = {
    "label_is_fraud",
    "isFraud",
    "isFlaggedFraud",
    "newbalanceOrig",
    "newbalanceDest",
    "nameOrig",
    "nameDest",
    "split_step",
    "split",
}
NUMERIC_COLUMNS = (
    "amount",
    "sender_pre_balance",
    "amount_to_sender_pre_balance",
    "sender_balance_covers_amount",
    "recipient_prior_transaction_count",
    "recipient_prior_received_amount",
)
CATEGORICAL_COLUMNS = ("transaction_type", "simulated_hour")
FEATURE_ABLATIONS = {
    "amount_type": {"numeric": ("amount",), "categorical": ("transaction_type",)},
    "plus_hour": {
        "numeric": ("amount",),
        "categorical": ("transaction_type", "simulated_hour"),
    },
    "plus_balance": {
        "numeric": (
            "amount",
            "sender_pre_balance",
            "amount_to_sender_pre_balance",
            "sender_balance_covers_amount",
        ),
        "categorical": ("transaction_type", "simulated_hour"),
    },
    "full_context": {
        "numeric": NUMERIC_COLUMNS,
        "categorical": CATEGORICAL_COLUMNS,
    },
}
POLICY_ORDER = (
    "amount_raw",
    "amount_type_train_percentile",
    "logistic_amount_type_balanced",
    "logistic_plus_hour_balanced",
    "logistic_plus_balance_balanced",
    "logistic_full_context_balanced",
    "logistic_full_context_unweighted",
)


def make_preprocessor(
    numeric_columns: tuple[str, ...], categorical_columns: tuple[str, ...]
) -> ColumnTransformer:
    numeric_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("log1p", FunctionTransformer(np.log1p, feature_names_out="one-to-one")),
            ("scale", StandardScaler()),
        ]
    )
    categorical_pipeline = OneHotEncoder(
        handle_unknown="ignore", drop="first", sparse_output=True, dtype=np.float32
    )
    return ColumnTransformer(
        [
            ("numeric", numeric_pipeline, list(numeric_columns)),
            ("categorical", categorical_pipeline, list(categorical_columns)),
        ],
        sparse_threshold=1.0,
        verbose_feature_names_out=True,
    )


def make_logistic_pipeline(
    numeric_columns: tuple[str, ...],
    categorical_columns: tuple[str, ...],
    class_weight: str | None,
    *,
    max_iter: int = 80,
) -> Pipeline:
    return Pipeline(
        [
            ("preprocessor", make_preprocessor(numeric_columns, categorical_columns)),
            (
                "logistic",
                LogisticRegression(
                    solver="newton-cholesky",
                    C=1.0,
                    class_weight=class_weight,
                    max_iter=max_iter,
                    tol=1e-5,
                    random_state=SEED,
                ),
            ),
        ]
    )


def rank_indices(scores: np.ndarray, tie_breaker: np.ndarray | None = None) -> np.ndarray:
    score_array = np.asarray(scores, dtype=np.float64)
    if tie_breaker is None:
        tie_breaker = np.arange(score_array.size, dtype=np.int64)
    tie_array = np.asarray(tie_breaker)
    if score_array.ndim != 1 or tie_array.ndim != 1 or score_array.size != tie_array.size:
        raise ValueError("Scores and deterministic tie-break keys must be aligned 1-D arrays")
    return np.lexsort((tie_array, -score_array))


def calculate_metrics(
    labels: np.ndarray,
    scores: np.ndarray,
    *,
    tie_breaker: np.ndarray | None = None,
    k_values: tuple[int, ...] = TOP_K_VALUES,
) -> dict[str, Any]:
    y_true = np.asarray(labels, dtype=np.int8)
    y_score = np.asarray(scores, dtype=np.float64)
    if y_true.ndim != 1 or y_score.ndim != 1 or y_true.size != y_score.size:
        raise ValueError("Label and score rows must reconcile")
    if y_true.size == 0:
        raise ValueError("Metrics require at least one scored transaction")
    if np.unique(y_true).size != 2:
        raise ValueError("ROC-AUC/PR-AUC require both label classes in the population")

    order = rank_indices(y_score, tie_breaker)
    positive_count = int(y_true.sum())
    metrics: dict[str, Any] = {
        "transaction_count": int(y_true.size),
        "fraud_count": positive_count,
        "fraud_prevalence": float(positive_count / y_true.size),
        "pr_auc_average_precision": float(average_precision_score(y_true, y_score)),
        "roc_auc": float(roc_auc_score(y_true, y_score)),
    }
    for requested_k in k_values:
        alert_count = min(requested_k, y_true.size)
        true_positives = int(y_true[order[:alert_count]].sum())
        precision = true_positives / alert_count
        recall = true_positives / positive_count if positive_count else 0.0
        metrics[f"alerts_at_{requested_k}"] = int(alert_count)
        metrics[f"true_positives_at_{requested_k}"] = true_positives
        metrics[f"false_positives_at_{requested_k}"] = int(alert_count - true_positives)
        metrics[f"precision_at_{requested_k}"] = float(precision)
        metrics[f"recall_at_{requested_k}"] = float(recall)
        metrics[f"f1_at_{requested_k}"] = (
            float(2 * precision * recall / (precision + recall))
            if precision + recall
            else 0.0
        )
    return metrics


def evaluate_populations(frame: pd.DataFrame, scores: np.ndarray) -> dict[str, Any]:
    if len(frame) != len(scores):
        raise ValueError("Score row count does not match the scored population")
    labels = frame["label_is_fraud"].to_numpy(dtype=np.int8, copy=False)
    tie_keys = np.arange(len(frame), dtype=np.int64)
    eligible = frame["transaction_type"].isin(ELIGIBLE_TYPES).to_numpy()
    result = {
        "all_transactions": calculate_metrics(labels, scores, tie_breaker=tie_keys),
        "transfer_cash_out": calculate_metrics(
            labels[eligible], scores[eligible], tie_breaker=tie_keys[eligible]
        ),
    }
    if result["all_transactions"]["transaction_count"] != len(frame):
        raise AssertionError("All-population evaluation row count did not reconcile")
    if result["transfer_cash_out"]["transaction_count"] != int(eligible.sum()):
        raise AssertionError("Eligible-population evaluation row count did not reconcile")
    return result


def _read_split(
    connection: duckdb.DuckDBPyConnection, parquet_path: Path, split: str
) -> pd.DataFrame:
    escaped_path = str(parquet_path.resolve()).replace("\\", "/").replace("'", "''")
    query = (
        "SELECT split_step, split, label_is_fraud, amount, transaction_type, "
        "simulated_hour, sender_pre_balance, amount_to_sender_pre_balance, "
        "sender_balance_covers_amount, recipient_prior_transaction_count, "
        "recipient_prior_received_amount "
        f"FROM read_parquet('{escaped_path}') WHERE split = ?"
    )
    frame = connection.execute(query, [split]).fetch_df()
    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(np.float32)
    frame["simulated_hour"] = frame["simulated_hour"].astype("string")
    frame["transaction_type"] = frame["transaction_type"].astype("string")
    return frame


def _split_audit(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    split_rows = connection.execute(
        "SELECT split, COUNT(*) AS transaction_count, "
        "COUNT(*) FILTER (WHERE label_is_fraud = 1) AS fraud_count, "
        "COUNT(DISTINCT split_step) AS step_count, SUM(amount) AS total_amount, "
        "AVG(amount) AS mean_amount, quantile_cont(amount, 0.50) AS median_amount, "
        "quantile_cont(amount, 0.95) AS p95_amount "
        "FROM phase3_features GROUP BY split "
        "ORDER BY CASE split WHEN 'train' THEN 1 WHEN 'validation' THEN 2 ELSE 3 END"
    ).fetchall()
    type_rows = connection.execute(
        "SELECT split, transaction_type, COUNT(*) AS transaction_count, "
        "COUNT(*) FILTER (WHERE label_is_fraud = 1) AS fraud_count, "
        "SUM(amount) AS total_amount, AVG(amount) AS mean_amount, "
        "quantile_cont(amount, 0.50) AS median_amount, "
        "quantile_cont(amount, 0.95) AS p95_amount "
        "FROM phase3_features GROUP BY split, transaction_type "
        "ORDER BY CASE split WHEN 'train' THEN 1 WHEN 'validation' THEN 2 ELSE 3 END, "
        "transaction_type"
    ).fetchall()
    hour_rows = connection.execute(
        "SELECT split, simulated_hour, COUNT(*) AS transaction_count, "
        "COUNT(*) FILTER (WHERE label_is_fraud = 1) AS fraud_count "
        "FROM phase3_features GROUP BY split, simulated_hour ORDER BY split, simulated_hour"
    ).fetchall()
    split_audit = {
        "split_summary": [],
        "type_mix_and_amounts": [],
        "hourly_patterns": [],
    }
    for row in split_rows:
        records, fraud = int(row[1]), int(row[2])
        split_audit["split_summary"].append(
            {
                "split": row[0],
                "transaction_count": records,
                "fraud_count": fraud,
                "fraud_prevalence": fraud / records,
                "distinct_steps": int(row[3]),
                "total_amount": float(row[4]),
                "mean_amount": float(row[5]),
                "median_amount": float(row[6]),
                "p95_amount": float(row[7]),
            }
        )
    records_by_split = {row["split"]: row["transaction_count"] for row in split_audit["split_summary"]}
    for row in type_rows:
        split, transaction_type, count, fraud = row[:4]
        split_total = records_by_split[split]
        split_audit["type_mix_and_amounts"].append(
            {
                "split": split,
                "transaction_type": transaction_type,
                "transaction_count": int(count),
                "transaction_share": int(count) / split_total,
                "fraud_count": int(fraud),
                "fraud_prevalence_within_type": int(fraud) / int(count),
                "total_amount": float(row[4]),
                "mean_amount": float(row[5]),
                "median_amount": float(row[6]),
                "p95_amount": float(row[7]),
            }
        )
    for row in hour_rows:
        count, fraud = int(row[2]), int(row[3])
        split_audit["hourly_patterns"].append(
            {
                "split": row[0],
                "simulated_hour": int(row[1]),
                "transaction_count": count,
                "fraud_count": fraud,
                "fraud_prevalence": fraud / count,
            }
        )
    if sum(records_by_split.values()) != int(
        connection.execute("SELECT COUNT(*) FROM phase3_features").fetchone()[0]
    ):
        raise AssertionError("Split audit transaction counts do not reconcile")
    return split_audit


def _fit_models(
    train_frame: pd.DataFrame,
) -> tuple[dict[str, Pipeline], dict[str, Any]]:
    y_train = train_frame["label_is_fraud"].to_numpy(dtype=np.int8, copy=False)
    model_specs = [
        ("logistic_amount_type_balanced", "amount_type", "balanced"),
        ("logistic_plus_hour_balanced", "plus_hour", "balanced"),
        ("logistic_plus_balance_balanced", "plus_balance", "balanced"),
        ("logistic_full_context_balanced", "full_context", "balanced"),
        ("logistic_full_context_unweighted", "full_context", None),
    ]
    fitted: dict[str, Pipeline] = {}
    fit_summary: dict[str, Any] = {}
    for model_name, ablation, class_weight in model_specs:
        spec = FEATURE_ABLATIONS[ablation]
        feature_columns = list(spec["numeric"] + spec["categorical"])
        model = make_logistic_pipeline(
            spec["numeric"], spec["categorical"], class_weight
        )
        started = time.perf_counter()
        with ResourceMonitor(model_name) as monitor:
            with numeric_thread_limits():
                with warnings.catch_warnings(record=True) as captured:
                    warnings.simplefilter("always", ConvergenceWarning)
                    model.fit(train_frame[feature_columns], y_train)
        elapsed = time.perf_counter() - started
        classifier = model.named_steps["logistic"]
        fitted[model_name] = model
        fit_summary[model_name] = {
            "ablation": ablation,
            "class_weight": class_weight,
            "features": feature_columns,
            "training_rows": int(len(train_frame)),
            "positive_training_rows": int(y_train.sum()),
            "iterations": int(classifier.n_iter_[0]),
            "max_iter": int(classifier.max_iter),
            "converged_before_max_iter": int(classifier.n_iter_[0]) < int(classifier.max_iter),
            "convergence_warnings": [str(item.message) for item in captured],
            "fit_seconds": float(elapsed),
            "resource_usage": monitor.summary(),
            "effective_threadpools": threadpool_snapshot(),
            "runtime_thread_plan": RUNTIME_CONFIG,
        }
        print(
            f"Fit {model_name}: {len(train_frame):,} rows, "
            f"{classifier.n_iter_[0]} iterations, {elapsed:.1f}s"
        )
    return fitted, fit_summary


def _fit_amount_references(train_frame: pd.DataFrame) -> dict[str, dict[str, list[float]]]:
    probabilities = np.linspace(0.0, 1.0, 1001)
    references: dict[str, dict[str, list[float]]] = {}
    for transaction_type, group in train_frame.groupby("transaction_type", observed=True):
        quantile_amounts = np.quantile(
            group["amount"].to_numpy(dtype=np.float64, copy=False),
            probabilities,
            method="linear",
        )
        references[str(transaction_type)] = {
            "probabilities": probabilities.tolist(),
            "quantile_amounts": quantile_amounts.tolist(),
        }
    return references


def _score_amount_percentile(
    frame: pd.DataFrame, references: dict[str, dict[str, list[float]]]
) -> np.ndarray:
    scores = np.zeros(len(frame), dtype=np.float32)
    transaction_types = frame["transaction_type"].astype(str).to_numpy()
    amounts = frame["amount"].to_numpy(dtype=np.float64, copy=False)
    for transaction_type in np.unique(transaction_types):
        mask = transaction_types == transaction_type
        reference = references.get(transaction_type)
        if reference is None:
            continue
        scores[mask] = np.interp(
            amounts[mask],
            np.asarray(reference["quantile_amounts"], dtype=np.float64),
            np.asarray(reference["probabilities"], dtype=np.float64),
            left=0.0,
            right=1.0,
        )
    return scores


def _score_policies(
    frame: pd.DataFrame,
    models: dict[str, Pipeline],
    references: dict[str, dict[str, list[float]]],
) -> dict[str, np.ndarray]:
    scores: dict[str, np.ndarray] = {
        "amount_raw": frame["amount"].to_numpy(dtype=np.float32, copy=True),
        "amount_type_train_percentile": _score_amount_percentile(frame, references),
    }
    for model_name, model in models.items():
        fit_info_features = model.named_steps["preprocessor"].feature_names_in_
        score_frame = frame[list(fit_info_features)]
        scores[model_name] = model.predict_proba(score_frame)[:, 1].astype(np.float32)
    for method_name, method_scores in scores.items():
        if len(method_scores) != len(frame) or not np.isfinite(method_scores).all():
            raise AssertionError(f"Invalid or unreconciled scores for {method_name}")
    return scores


def _evaluate_scores(
    frame: pd.DataFrame, scores: dict[str, np.ndarray]
) -> dict[str, dict[str, Any]]:
    return {method: evaluate_populations(frame, values) for method, values in scores.items()}


def _flatten_evaluation(
    split: str, evaluation: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {"split": split, "method": method, "population": population, **metrics}
        for method, populations in evaluation.items()
        for population, metrics in populations.items()
    ]


def _select_policy_and_budget(
    validation_evaluation: dict[str, dict[str, Any]],
) -> tuple[str, int, dict[str, Any]]:
    method_priority = {method: index for index, method in enumerate(POLICY_ORDER)}
    selected_method = max(
        validation_evaluation,
        key=lambda method: (
            validation_evaluation[method]["transfer_cash_out"]["pr_auc_average_precision"],
            -method_priority[method],
        ),
    )
    eligible_metrics = validation_evaluation[selected_method]["transfer_cash_out"]
    selected_budget = max(
        TOP_K_VALUES,
        key=lambda budget: (eligible_metrics[f"f1_at_{budget}"], -budget),
    )
    selection = {
        "selected_method": selected_method,
        "selection_population": "TRANSFER and CASH_OUT only",
        "selection_metric": "validation PR-AUC (average precision)",
        "validation_eligible_pr_auc": eligible_metrics["pr_auc_average_precision"],
        "candidate_budgets": list(TOP_K_VALUES),
        "selected_budget": int(selected_budget),
        "budget_selection_metric": "validation F1 at K; ties choose smaller K",
        "validation_precision_at_selected_budget": eligible_metrics[
            f"precision_at_{selected_budget}"
        ],
        "validation_recall_at_selected_budget": eligible_metrics[
            f"recall_at_{selected_budget}"
        ],
        "validation_false_positives_at_selected_budget": eligible_metrics[
            f"false_positives_at_{selected_budget}"
        ],
        "test_labels_used_for_selection": False,
    }
    return selected_method, int(selected_budget), selection


def _coefficients(model: Pipeline, limit: int = 12) -> dict[str, Any]:
    names = model.named_steps["preprocessor"].get_feature_names_out()
    values = model.named_steps["logistic"].coef_[0]
    ordered = sorted(zip(names, values, strict=True), key=lambda pair: float(pair[1]))
    return {
        "most_negative": [
            {"feature": str(name), "coefficient": float(value)}
            for name, value in ordered[:limit]
        ],
        "most_positive": [
            {"feature": str(name), "coefficient": float(value)}
            for name, value in reversed(ordered[-limit:])
        ],
        "interpretation": "Coefficients are on standardized log1p numeric and one-hot scales; association is not causation.",
    }


def _risk_bands(
    frame: pd.DataFrame,
    scores: np.ndarray,
    thresholds: dict[str, float],
    split: str,
) -> list[dict[str, Any]]:
    eligible = frame["transaction_type"].isin(ELIGIBLE_TYPES).to_numpy()
    assigned = np.where(
        scores >= thresholds["very_high"],
        "very_high",
        np.where(
            scores >= thresholds["high"],
            "high",
            np.where(scores >= thresholds["moderate"], "moderate", "low"),
        ),
    )
    rows = []
    for population, mask in (("all_transactions", np.ones(len(frame), dtype=bool)), ("transfer_cash_out", eligible)):
        for band in ("very_high", "high", "moderate", "low"):
            indices = np.flatnonzero(mask & (assigned == band))
            labels = frame["label_is_fraud"].to_numpy(dtype=np.int8, copy=False)[indices]
            count = int(indices.size)
            fraud_count = int(labels.sum())
            rows.append(
                {
                    "split": split,
                    "population": population,
                    "risk_band": band,
                    "transaction_count": count,
                    "fraud_count": fraud_count,
                    "fraud_prevalence": fraud_count / count if count else 0.0,
                    "mean_score": float(scores[indices].mean()) if count else 0.0,
                    "score_threshold_source": "validation eligible-population score quantiles",
                }
            )
    return rows


def _investigation_rows(
    frame: pd.DataFrame,
    scores: np.ndarray,
    method: str,
    split: str,
) -> list[dict[str, Any]]:
    eligible = frame["transaction_type"].isin(ELIGIBLE_TYPES).to_numpy()
    eligible_indices = np.flatnonzero(eligible)
    order = rank_indices(scores[eligible], eligible_indices)
    selected = eligible_indices[order[:INVESTIGATION_CAP_PER_SPLIT]]
    rows = []
    visible_columns = (
        "split_step",
        "transaction_type",
        "amount",
        "simulated_hour",
        "sender_pre_balance",
        "amount_to_sender_pre_balance",
        "sender_balance_covers_amount",
        "recipient_prior_transaction_count",
        "recipient_prior_received_amount",
        "label_is_fraud",
    )
    for rank, index in enumerate(selected, start=1):
        row = {column: frame.iloc[index][column] for column in visible_columns}
        row.update(
            {
                "split": split,
                "rank": rank,
                "risk_score": float(scores[index]),
                "score_method": method,
                "score_provenance": "train-fitted policy; method and budget selected on validation",
                "selection_scope": "top-ranked TRANSFER/CASH_OUT; capped investigation list, not population sample",
            }
        )
        rows.append(row)
    return rows


def _write_powerbi_outputs(
    connection: duckdb.DuckDBPyConnection,
    parquet_path: Path,
    report_dir: Path,
    evaluation_rows: list[dict[str, Any]],
    risk_rows: list[dict[str, Any]],
    investigation_rows: list[dict[str, Any]],
) -> dict[str, str]:
    escaped_path = str(parquet_path.resolve()).replace("\\", "/").replace("'", "''")
    connection.execute(
        "CREATE OR REPLACE TEMP VIEW phase3_features AS "
        f"SELECT * FROM read_parquet('{escaped_path}')"
    )
    overview_sql = OVERVIEW_SQL.read_text(encoding="utf-8").strip().removesuffix(";")
    overview = connection.execute(overview_sql).fetch_df()
    tables = {
        "transaction_overview": overview,
        "risk_bands": pd.DataFrame(risk_rows),
        "evaluation_summary": pd.DataFrame(evaluation_rows),
        "investigation_top500": pd.DataFrame(investigation_rows),
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for name, table in tables.items():
        csv_path = report_dir / f"phase3_{name}.csv"
        parquet_output = report_dir / f"phase3_{name}.parquet"
        table.to_csv(csv_path, index=False)
        table.to_parquet(parquet_output, index=False, compression="zstd")
        paths[name] = str(csv_path)
        paths[f"{name}_parquet"] = str(parquet_output)
    if len(tables["investigation_top500"]) > INVESTIGATION_CAP_PER_SPLIT * 2:
        raise AssertionError("Investigation output exceeded its per-split cap")
    return paths


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 3: Explainable Risk Ranking",
        "",
        "Evaluation population: all transactions, with a separately reported TRANSFER/CASH_OUT-only population because the other PaySim types contain no fraud labels. PR-AUC is average precision. All baselines and ablations are compared on validation; model/policy and the investigation budget are frozen before the single test evaluation.",
        "",
        "## Split Audit",
        "",
        "| Split | Steps | Transactions | Fraud | Prevalence | Mean amount | Median | P95 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["split_audit"]["split_summary"]:
        lines.append(
            f"| {row['split']} | {row['distinct_steps']:,} | {row['transaction_count']:,} | "
            f"{row['fraud_count']:,} | {row['fraud_prevalence']:.6%} | "
            f"{row['mean_amount']:,.2f} | {row['median_amount']:,.2f} | {row['p95_amount']:,.2f} |"
        )
    lines.extend(
        [
            "",
            "The split keeps contiguous steps (train 1–520, validation 521–631, test 632–743). It is approximately 70/15/15 by steps, not by transactions. The sharp prevalence and volume shift is reported, not corrected by resampling.",
            "",
            "### Type Mix and Amounts by Split",
            "",
            "| Split | Type | Rows | Split share | Fraud | Type prevalence | Mean amount | Median | P95 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["split_audit"]["type_mix_and_amounts"]:
        lines.append(
            f"| {row['split']} | {row['transaction_type']} | {row['transaction_count']:,} | "
            f"{row['transaction_share']:.2%} | {row['fraud_count']:,} | "
            f"{row['fraud_prevalence_within_type']:.6%} | {row['mean_amount']:,.2f} | "
            f"{row['median_amount']:,.2f} | {row['p95_amount']:,.2f} |"
        )
    lines.extend(
        [
            "",
            "### Hour Patterns by Split",
            "",
            "| Split | Simulated hour | Rows | Fraud | Prevalence |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["split_audit"]["hourly_patterns"]:
        lines.append(
            f"| {row['split']} | {row['simulated_hour']} | {row['transaction_count']:,} | "
            f"{row['fraud_count']:,} | {row['fraud_prevalence']:.6%} |"
        )
    lines.extend(
        [
            "",
            "## Validation Results",
            "",
            "| Method | Population | PR-AUC | ROC-AUC | P@100 | R@100 | FP@100 | P@500 | R@500 | FP@500 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["validation_evaluation"]:
        lines.append(_metric_row(row))
    lines.extend(["", "### Feature Ablation (Validation PR-AUC)", ""])
    lines.extend(
        [
            "| Model | All transactions | TRANSFER/CASH_OUT |",
            "| --- | ---: | ---: |",
        ]
    )
    for name, results in report["validation_by_method"].items():
        if name.startswith("logistic_"):
            lines.append(
                f"| {name} | {results['all_transactions']['pr_auc_average_precision']:.6f} | "
                f"{results['transfer_cash_out']['pr_auc_average_precision']:.6f} |"
            )
    selection = report["selection"]
    lines.extend(
        [
            "",
            "### Frozen Decision",
            "",
            f"Selected policy: **{selection['selected_method']}**; chosen on validation eligible-population PR-AUC. "
            f"Selected budget: **top {selection['selected_budget']} eligible transactions**, chosen from K=100/500 by validation F1. "
            f"Validation precision/recall at that budget: {selection['validation_precision_at_selected_budget']:.4%} / "
            f"{selection['validation_recall_at_selected_budget']:.4%}; false positives: "
            f"{selection['validation_false_positives_at_selected_budget']:,}.",
            "",
            "## Final Frozen Test Evaluation",
            "",
            "| Method | Population | PR-AUC | ROC-AUC | P@100 | R@100 | FP@100 | P@500 | R@500 | FP@500 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["test_evaluation"]:
        lines.append(_metric_row(row))
    lines.extend(
        [
            "",
            "A preliminary SAGA run scored the test before its non-convergence was noticed; that run is discarded. The solver change was based on a train-only convergence check, not test metrics. The corrected model and validation-selected policy were frozen before this final test pass; no test result informed features, model selection, thresholds, or budgets.",
            "",
            "## Coefficients and Artifact Risk",
            "",
        ]
    )
    coefficient_report = report.get("full_context_coefficients")
    if coefficient_report:
        lines.append("Full balanced logistic model coefficient extremes (standardized log1p numeric and one-hot scales):")
        lines.extend(
            f"- `{row['feature']}`: {row['coefficient']:.5f}"
            for row in coefficient_report["most_positive"][:8]
        )
        lines.extend(
            f"- `{row['feature']}`: {row['coefficient']:.5f}"
            for row in coefficient_report["most_negative"][:8]
        )
    lines.extend(
        [
            "",
            "Balance-feature ablations are sensitive to the simulator: many labeled nonfraud rows have amount greater than sender pre-balance and are clipped to zero after the event, while labeled fraud rows usually are not. Post-event balances are excluded from every predictor. Pre-balance and its ratios remain legitimate decision-time candidates but may still encode this synthetic rule; compare ablations and do not interpret performance as real-world fraud detection.",
            "Simulated hour has an abrupt distribution/prevalence shift across chronological periods; its ablation should be read as a dataset-specific signal, not a validated daily-cycle effect.",
            "",
            "## Risk Bands and Investigation Export",
            "",
            f"Risk bands use validation eligible-population score quantiles only: `{json.dumps(report['risk_band_thresholds'], sort_keys=True)}`. The capped transaction table contains at most {INVESTIGATION_CAP_PER_SPLIT:,} top-ranked eligible rows per split. It is a risk-selected investigation list, not a prevalence sample. Aggregated overview and risk-band prevalence use the full population.",
            "",
            "## Limits",
            "",
            "- The test period contains 1,252 positives; at K=100, recall resolution is about 0.08 percentage points per captured transaction. Top-K estimates remain sensitive to the simulator and time shift.",
            "- No confidence interval is presented because transactions are not independent and account-level dependence is not modeled.",
            "- Evaluation is offline on synthetic PaySim labels; no real-world detection claim is supported.",
            "- Training used all chronological training rows with sparse-compatible scikit-learn Newton-Cholesky logistic regression. Inspect iteration/convergence status in the JSON report.",
            "",
            "## Reproduction",
            "",
            "```powershell",
            r".\.venv\Scripts\python.exe -m src.phase3_evaluation",
            r".\.venv\Scripts\python.exe -m unittest discover -s tests -v",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _metric_row(row: dict[str, Any]) -> str:
    return (
        f"| {row['method']} | {row['population']} | "
        f"{row['pr_auc_average_precision']:.6f} | {row['roc_auc']:.6f} | "
        f"{row['precision_at_100']:.4%} | {row['recall_at_100']:.4%} | "
        f"{row['false_positives_at_100']:,} | {row['precision_at_500']:.4%} | "
        f"{row['recall_at_500']:.4%} | {row['false_positives_at_500']:,} |"
    )


def run_experiment(
    parquet_path: Path = DEFAULT_PARQUET,
    report_dir: Path = DEFAULT_REPORT_DIR,
    model_dir: Path = DEFAULT_MODEL_DIR,
) -> dict[str, Any]:
    if not parquet_path.is_file():
        raise FileNotFoundError(f"Phase 2 feature Parquet not found: {parquet_path}")
    connection = duckdb.connect()
    try:
        parquet_literal = str(parquet_path.resolve()).replace("\\", "/").replace("'", "''")
        connection.execute(
            "CREATE TEMP VIEW phase3_features AS "
            f"SELECT * FROM read_parquet('{parquet_literal}')"
        )
        split_audit = _split_audit(connection)
        train_frame = _read_split(connection, parquet_path, "train")
        validation_frame = _read_split(connection, parquet_path, "validation")
        if train_frame["label_is_fraud"].nunique() != 2:
            raise ValueError("Training split must contain both target classes")

        references = _fit_amount_references(train_frame)
        fitted_models, fit_summary = _fit_models(train_frame)
        validation_scores = _score_policies(validation_frame, fitted_models, references)
        validation_by_method = _evaluate_scores(validation_frame, validation_scores)
        validation_rows = _flatten_evaluation("validation", validation_by_method)
        selected_method, selected_budget, selection = _select_policy_and_budget(
            validation_by_method
        )
        selected_validation_scores = validation_scores[selected_method]
        validation_eligible = validation_frame["transaction_type"].isin(ELIGIBLE_TYPES).to_numpy()
        eligible_validation_scores = selected_validation_scores[validation_eligible]
        band_quantiles = np.quantile(
            eligible_validation_scores, [0.90, 0.99, 0.999], method="higher"
        )
        risk_band_thresholds = {
            "moderate": float(band_quantiles[0]),
            "high": float(band_quantiles[1]),
            "very_high": float(band_quantiles[2]),
        }
        final_selection = {
            **selection,
            "frozen_before_test": True,
            "risk_band_thresholds": risk_band_thresholds,
            "risk_band_threshold_source": "validation TRANSFER/CASH_OUT scores only",
            "feature_sets": {name: {key: list(value) for key, value in spec.items()} for name, spec in FEATURE_ABLATIONS.items()},
            "split_steps": {row["split"]: row["distinct_steps"] for row in split_audit["split_summary"]},
        }

        model_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)
        selection_path = model_dir / "phase3_selection.json"
        selection_path.write_text(json.dumps(final_selection, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        artifact_path = model_dir / "phase3_rankers.joblib"
        joblib.dump(
            {
                "selected_method": selected_method,
                "selected_budget": selected_budget,
                "models": fitted_models,
                "amount_type_percentile_reference": references,
                "feature_ablations": FEATURE_ABLATIONS,
                "predictors": PREDICTORS,
                "forbidden_fields": sorted(FORBIDDEN_FIELDS),
                "selection": final_selection,
                "seed": SEED,
            },
            artifact_path,
            compress=3,
        )

        print(
            f"Frozen validation decision: {selected_method}, "
            f"eligible investigation budget={selected_budget}"
        )
        # Test labels are first loaded only after the validation decision and artifact are frozen.
        test_frame = _read_split(connection, parquet_path, "test")
        test_scores = _score_policies(test_frame, fitted_models, references)
        test_by_method = _evaluate_scores(test_frame, test_scores)
        test_rows = _flatten_evaluation("test", test_by_method)

        selected_test_scores = test_scores[selected_method]
        risk_rows = _risk_bands(
            validation_frame, selected_validation_scores, risk_band_thresholds, "validation"
        ) + _risk_bands(test_frame, selected_test_scores, risk_band_thresholds, "test")
        investigation_rows = _investigation_rows(
            validation_frame, selected_validation_scores, selected_method, "validation"
        ) + _investigation_rows(test_frame, selected_test_scores, selected_method, "test")
        powerbi_paths = _write_powerbi_outputs(
            connection,
            parquet_path,
            report_dir,
            validation_rows + test_rows,
            risk_rows,
            investigation_rows,
        )

        coefficient_model = fitted_models["logistic_full_context_balanced"]
        full_coefficients = _coefficients(coefficient_model)
        report = {
            "dataset": parquet_path.name,
            "evaluation_scope": {
                "primary_population": "all transactions",
                "secondary_population": "TRANSFER and CASH_OUT only",
                "eligible_types": list(ELIGIBLE_TYPES),
                "pr_auc_definition": "scikit-learn average_precision_score",
                "final_corrected_model_test_passes": 1,
                "preliminary_discarded_saga_test_passes": 1,
                "preliminary_test_metrics_used_for_any_selection": False,
                "preliminary_run_discard_reason": "all initial SAGA models reached max_iter without convergence; replacement solver chosen using train-only solver diagnostics",
                "test_labels_used_for_selection": False,
            },
            "split_audit": split_audit,
            "validation_evaluation": validation_rows,
            "test_evaluation": test_rows,
            "validation_by_method": validation_by_method,
            "test_by_method": test_by_method,
            "feature_ablation_validation": {
                name: validation_by_method[name]
                for name in validation_by_method
                if name.startswith("logistic_")
            },
            "fit_summary": fit_summary,
            "selection": final_selection,
            "full_context_coefficients": full_coefficients,
            "risk_band_thresholds": risk_band_thresholds,
            "risk_band_summaries": risk_rows,
            "investigation_table": {
                "rows": len(investigation_rows),
                "cap_per_split": INVESTIGATION_CAP_PER_SPLIT,
                "population": "TRANSFER and CASH_OUT only",
                "prevalence_warning": "Risk-ranked capped rows are not a population sample; do not interpret their fraud rate as population prevalence.",
            },
            "powerbi_outputs": powerbi_paths,
            "model_artifacts": {
                "rankers": str(artifact_path),
                "frozen_selection": str(selection_path),
            },
            "limitations": [
                "The model and evaluation are for synthetic PaySim data only.",
                "The chronological periods have strongly different row volume and fraud prevalence.",
                "Fraud labels occur only in CASH_OUT and TRANSFER, making transaction type a simulation shortcut in all-population metrics.",
                "Sender pre-balance and balance ratios are available at decision time but may encode PaySim balance-generation artifacts.",
                "Post-event balances and flagged-fraud indicators are excluded from all predictors.",
                "No confidence intervals are reported because transactions are dependent and account-level resampling was not performed.",
            ],
        }
        (report_dir / "phase3_evaluation.json").write_text(
            json.dumps(report, indent=2, allow_nan=False, default=_json_default) + "\n",
            encoding="utf-8",
        )
        (report_dir / "phase3_evaluation.md").write_text(_markdown(report), encoding="utf-8")
        print(f"Selected {selected_method}; validation-selected K={selected_budget}")
        print(f"Wrote {report_dir / 'phase3_evaluation.md'}")
        print(f"Wrote {report_dir / 'phase3_evaluation.json'}")
        print(f"Saved frozen models to {artifact_path}")
        return report
    finally:
        connection.close()


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if pd.isna(value):
        return None
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet-path", type=Path, default=DEFAULT_PARQUET)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    args = parser.parse_args()
    run_experiment(args.parquet_path, args.report_dir, args.model_dir)


if __name__ == "__main__":
    main()