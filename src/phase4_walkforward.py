"""Run a separate expanding-window, walk-forward PaySim robustness protocol."""

from __future__ import annotations

import argparse
import gc
import hashlib
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
from sklearn.exceptions import ConvergenceWarning

from .features import ROOT
from .phase3_evaluation import (
    DEFAULT_PARQUET,
    FEATURE_ABLATIONS,
    NUMERIC_COLUMNS,
    calculate_metrics,
    make_logistic_pipeline,
)


REPORT_DIR = ROOT / "reports"
MODEL_DIR = ROOT / "models"
SQL_PATH = ROOT / "sql" / "phase4_walkforward.sql"
PROTOCOL_VERSION = "phase4_walkforward_v1"
REPORT_JSON = REPORT_DIR / f"{PROTOCOL_VERSION}.json"
REPORT_MD = REPORT_DIR / f"{PROTOCOL_VERSION}.md"
FOLD_METRICS_CSV = REPORT_DIR / f"{PROTOCOL_VERSION}_fold_metrics.csv"
FOLD_METRICS_PARQUET = REPORT_DIR / f"{PROTOCOL_VERSION}_fold_metrics.parquet"
FOLD_ASSIGNMENTS_CSV = REPORT_DIR / f"{PROTOCOL_VERSION}_step_assignments.csv"
FOLD_ASSIGNMENTS_PARQUET = REPORT_DIR / f"{PROTOCOL_VERSION}_step_assignments.parquet"
MODEL_PATH = MODEL_DIR / f"{PROTOCOL_VERSION}_final_model.joblib"
PROTOCOL_PATH = MODEL_DIR / f"{PROTOCOL_VERSION}_protocol.json"
ORIGINAL_ARTIFACTS = (
    ROOT / "reports" / "phase3_evaluation.json",
    ROOT / "reports" / "phase3_evaluation.md",
    ROOT / "reports" / "phase3_robustness.json",
    ROOT / "reports" / "phase3_robustness.md",
    ROOT / "models" / "phase3_rankers.joblib",
    ROOT / "models" / "phase3_robustness_models.joblib",
    ROOT / "models" / "phase3_selection.json",
    ROOT / "models" / "phase3_robustness_selection.json",
)

ELIGIBLE_TYPES = ("TRANSFER", "CASH_OUT")
FOLD_SPECS = (
    {"fold": "fold_1", "train_start": 1, "train_end": 250, "validation_start": 251, "validation_end": 350},
    {"fold": "fold_2", "train_start": 1, "train_end": 350, "validation_start": 351, "validation_end": 450},
    {"fold": "fold_3", "train_start": 1, "train_end": 450, "validation_start": 451, "validation_end": 540},
    {"fold": "fold_4", "train_start": 1, "train_end": 540, "validation_start": 541, "validation_end": 631},
)
FINAL_PERIOD = {"start_step": 632, "end_step": 743}
FEATURE_SET_NAMES = ("amount_type", "plus_hour", "plus_balance", "full_context")
LOGISTIC_NAMES = {
    "amount_type": "logistic_amount_type_balanced",
    "plus_hour": "logistic_plus_hour_balanced",
    "plus_balance": "logistic_plus_balance_balanced",
    "full_context": "logistic_full_context_balanced",
}
ALERT_RATE = 0.005
MIN_VALIDATION_FRAUD = 200
MAX_ITER = 640
CLASS_WEIGHT = "balanced"
SOLVER = "newton-cholesky"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_fold_specs(fold_specs: tuple[dict[str, Any], ...]) -> None:
    if len(fold_specs) < 2:
        raise ValueError("Walk-forward validation requires multiple folds")
    previous_validation_end = 0
    for spec in fold_specs:
        if spec["train_start"] != 1:
            raise ValueError("Expanding training windows must begin at the first step")
        if spec["train_end"] != spec["validation_start"] - 1:
            raise ValueError("Training and validation must be adjacent whole-step windows")
        if spec["validation_start"] <= previous_validation_end:
            raise ValueError("Validation windows must be strictly chronological and disjoint")
        if spec["validation_end"] < spec["validation_start"]:
            raise ValueError("Validation window is empty")
        if spec["train_end"] < previous_validation_end:
            raise ValueError("Training window did not expand beyond the preceding fold")
        previous_validation_end = spec["validation_end"]
    if FINAL_PERIOD["start_step"] != previous_validation_end + 1:
        raise ValueError("Reserved final period must immediately follow walk-forward validation")


def choose_final_feature_set(
    fold_validation_metrics: dict[str, list[dict[str, Any]]],
) -> tuple[str, dict[str, Any]]:
    summary = {}
    for feature_set in FEATURE_SET_NAMES:
        values = [
            row["transfer_cash_out"]["pr_auc_average_precision"]
            for row in fold_validation_metrics[feature_set]
        ]
        roc_values = [
            row["transfer_cash_out"]["roc_auc"]
            for row in fold_validation_metrics[feature_set]
        ]
        if not values or not roc_values:
            raise ValueError(f"No validation fold metrics for {feature_set}")
        summary[feature_set] = {
            "fold_pr_auc": values,
            "mean_pr_auc": float(np.mean(values)),
            "std_pr_auc": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
            "fold_roc_auc": roc_values,
            "mean_roc_auc": float(np.mean(roc_values)),
            "std_roc_auc": float(np.std(roc_values, ddof=1)) if len(roc_values) > 1 else 0.0,
        }
    selected = max(FEATURE_SET_NAMES, key=lambda name: summary[name]["mean_roc_auc"])
    return selected, summary


def metrics_for_population(
    labels: np.ndarray,
    scores: np.ndarray,
    *,
    alert_rate: float = ALERT_RATE,
) -> dict[str, Any]:
    base = calculate_metrics(labels, scores, k_values=(100, 500))
    count = len(labels)
    if count != len(scores):
        raise ValueError("Metric score count does not match labels")
    alert_count = min(count, max(1, int(np.ceil(count * alert_rate))))
    order = np.lexsort((np.arange(count, dtype=np.int64), -np.asarray(scores, dtype=np.float64)))
    true_positives = int(np.asarray(labels, dtype=np.int8)[order[:alert_count]].sum())
    positive_count = int(np.asarray(labels, dtype=np.int8).sum())
    base.update(
        {
            "alert_rate_target": alert_rate,
            "alerts_at_fixed_rate": alert_count,
            "realized_alert_rate": alert_count / count,
            "true_positives_at_fixed_rate": true_positives,
            "false_positives_at_fixed_rate": alert_count - true_positives,
            "precision_at_fixed_rate": true_positives / alert_count,
            "recall_at_fixed_rate": true_positives / positive_count if positive_count else 0.0,
        }
    )
    return base


def evaluate_scores(frame: pd.DataFrame, scores: np.ndarray) -> dict[str, Any]:
    if len(frame) != len(scores):
        raise ValueError("Score rows do not reconcile with frame rows")
    labels = frame["label_is_fraud"].to_numpy(dtype=np.int8, copy=False)
    eligible = frame["transaction_type"].isin(ELIGIBLE_TYPES).to_numpy()
    return {
        "all_transactions": metrics_for_population(labels, scores),
        "transfer_cash_out": metrics_for_population(labels[eligible], scores[eligible]),
    }


def _parquet_path_sql(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def _execute_plan_sql(connection: duckdb.DuckDBPyConnection, parquet_path: Path) -> None:
    sql = SQL_PATH.read_text(encoding="utf-8").replace(
        "__PARQUET_PATH__", _parquet_path_sql(parquet_path)
    )
    for statement in connection.extract_statements(sql):
        connection.execute(statement)


def _get_support(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    step_counts = connection.execute(
        "SELECT step, transaction_count, fraud_count FROM phase4_step_support ORDER BY step"
    ).fetchall()
    support: dict[str, Any] = {"step_counts": [(int(a), int(b), int(c)) for a, b, c in step_counts]}
    summaries = []
    for spec in FOLD_SPECS:
        train = connection.execute(
            "SELECT COUNT(*), COUNT(*) FILTER(WHERE label_is_fraud=1), "
            "COUNT(DISTINCT split_step) FROM phase4_features "
            "WHERE split_step BETWEEN ? AND ?",
            [spec["train_start"], spec["train_end"]],
        ).fetchone()
        validation = connection.execute(
            "SELECT COUNT(*), COUNT(*) FILTER(WHERE label_is_fraud=1), "
            "COUNT(DISTINCT split_step) FROM phase4_features "
            "WHERE split_step BETWEEN ? AND ?",
            [spec["validation_start"], spec["validation_end"]],
        ).fetchone()
        type_rows = connection.execute(
            "SELECT transaction_type, COUNT(*), COUNT(*) FILTER(WHERE label_is_fraud=1) "
            "FROM phase4_features WHERE split_step BETWEEN ? AND ? "
            "GROUP BY transaction_type ORDER BY transaction_type",
            [spec["validation_start"], spec["validation_end"]],
        ).fetchall()
        summaries.append(
            {
                **spec,
                "train_transaction_count": int(train[0]),
                "train_fraud_count": int(train[1]),
                "train_step_count": int(train[2]),
                "validation_transaction_count": int(validation[0]),
                "validation_fraud_count": int(validation[1]),
                "validation_prevalence": int(validation[1]) / int(validation[0]),
                "validation_step_count": int(validation[2]),
                "validation_by_type": [
                    {
                        "transaction_type": row[0],
                        "transaction_count": int(row[1]),
                        "fraud_count": int(row[2]),
                    }
                    for row in type_rows
                ],
                "rationale": "Fixed contiguous 90-100-step validation window; chosen from chronology and minimum support, not model results.",
            }
        )
        if int(validation[1]) < MIN_VALIDATION_FRAUD:
            raise ValueError(
                f"{spec['fold']} has only {validation[1]} validation frauds; "
                f"minimum support is {MIN_VALIDATION_FRAUD}"
            )
    final = connection.execute(
        "SELECT COUNT(*), COUNT(*) FILTER(WHERE label_is_fraud=1), "
        "COUNT(DISTINCT split_step) FROM phase4_features "
        "WHERE split_step BETWEEN ? AND ?",
        [FINAL_PERIOD["start_step"], FINAL_PERIOD["end_step"]],
    ).fetchone()
    if int(final[1]) < MIN_VALIDATION_FRAUD:
        raise ValueError("Reserved final period has insufficient positive-label support")
    support["folds"] = summaries
    support["reserved_final_period"] = {
        **FINAL_PERIOD,
        "transaction_count": int(final[0]),
        "fraud_count": int(final[1]),
        "prevalence": int(final[1]) / int(final[0]),
        "step_count": int(final[2]),
        "status": "previously accessed; reserved from this protocol's model/feature selection",
    }
    return support


def print_proposed_plan(support: dict[str, Any]) -> None:
    print(f"PROPOSED {PROTOCOL_VERSION} PLAN (no model fitting has occurred)")
    print("Protocol: expanding training through each prior step; score the next contiguous window.")
    print("Boundary rule: fixed chronological step windows and >=200 fraud labels per validation window; no performance-based boundary search.")
    print("Fold           Train steps       Rows      Fraud | Validation steps       Rows      Fraud   Prevalence")
    for fold in support["folds"]:
        print(
            f"{fold['fold']:<14} 1-{fold['train_end']:<12} "
            f"{fold['train_transaction_count']:>10,} {fold['train_fraud_count']:>9,} | "
            f"{fold['validation_start']}-{fold['validation_end']:<10} "
            f"{fold['validation_transaction_count']:>10,} "
            f"{fold['validation_fraud_count']:>9,} {fold['validation_prevalence']:>10.4%}"
        )
    final = support["reserved_final_period"]
    print(
        f"Reserved final: steps {final['start_step']}-{final['end_step']}, "
        f"{final['transaction_count']:,} rows, {final['fraud_count']:,} fraud "
        f"({final['prevalence']:.4%}); previously accessed, not pristine."
    )
    print("Rationale: windows are contiguous, expand training, cover different transaction-volume regimes, and each validation window has adequate label support.")


def _read_range(
    connection: duckdb.DuckDBPyConnection,
    parquet_path: Path,
    start_step: int,
    end_step: int,
) -> pd.DataFrame:
    path = _parquet_path_sql(parquet_path)
    frame = connection.execute(
        "SELECT split_step, label_is_fraud, amount, transaction_type, simulated_hour, "
        "sender_pre_balance, amount_to_sender_pre_balance, sender_balance_covers_amount, "
        "recipient_prior_transaction_count, recipient_prior_received_amount "
        f"FROM read_parquet('{path}') WHERE split_step BETWEEN ? AND ? "
        "ORDER BY split_step",
        [start_step, end_step],
    ).fetch_df()
    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(np.float32)
    frame["label_is_fraud"] = frame["label_is_fraud"].astype(np.int8)
    frame["transaction_type"] = frame["transaction_type"].astype("string")
    frame["simulated_hour"] = frame["simulated_hour"].astype("string")
    return frame


def _score_model(
    model: Any,
    frame: pd.DataFrame,
    feature_set: str,
) -> np.ndarray:
    spec = FEATURE_ABLATIONS[feature_set]
    columns = list(spec["numeric"] + spec["categorical"])
    scores = model.predict_proba(frame[columns])[:, 1].astype(np.float32)
    if len(scores) != len(frame) or not np.isfinite(scores).all():
        raise AssertionError("Model score rows are invalid or do not reconcile")
    return scores


def _training_amount_references(train: pd.DataFrame) -> dict[str, np.ndarray]:
    return {
        str(transaction_type): np.quantile(
            group["amount"].to_numpy(dtype=np.float64, copy=False),
            np.linspace(0.0, 1.0, 1001),
        )
        for transaction_type, group in train.groupby("transaction_type", observed=True)
    }


def _percentile_scores(
    frame: pd.DataFrame, references: dict[str, np.ndarray]
) -> np.ndarray:
    probability_grid = np.linspace(0.0, 1.0, 1001)
    result = np.zeros(len(frame), dtype=np.float32)
    types = frame["transaction_type"].astype(str).to_numpy()
    amounts = frame["amount"].to_numpy(dtype=np.float64, copy=False)
    for transaction_type in np.unique(types):
        mask = types == transaction_type
        if transaction_type in references:
            result[mask] = np.interp(
                amounts[mask], references[transaction_type], probability_grid,
                left=0.0, right=1.0,
            )
    return result


def _evaluate_methods(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    models: dict[str, Any],
    amount_references: dict[str, np.ndarray],
    *,
    include_train: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    methods: dict[str, dict[str, np.ndarray]] = {
        "amount_raw": {
            "train": train["amount"].to_numpy(dtype=np.float32, copy=False),
            "validation": validation["amount"].to_numpy(dtype=np.float32, copy=False),
        },
        "amount_type_train_percentile": {
            "train": _percentile_scores(train, amount_references),
            "validation": _percentile_scores(validation, amount_references),
        },
    }
    for feature_set, model in models.items():
        methods[LOGISTIC_NAMES[feature_set]] = {
            "train": _score_model(model, train, feature_set),
            "validation": _score_model(model, validation, feature_set),
        }
    outputs: dict[str, Any] = {}
    for name, split_scores in methods.items():
        outputs[name] = {"validation": evaluate_scores(validation, split_scores["validation"])}
        if include_train:
            outputs[name]["train"] = evaluate_scores(train, split_scores["train"])
    return outputs, methods


def _flatten_metrics(
    fold_name: str,
    split: str,
    method_metrics: dict[str, Any],
    provenance: str,
) -> list[dict[str, Any]]:
    return [
        {
            "fold": fold_name,
            "split": split,
            "method": method,
            "population": population,
            "metrics_provenance": provenance,
            **metrics,
        }
        for method, populations in method_metrics.items()
        for population, metrics in populations.items()
    ]


def _write_assignments(
    connection: duckdb.DuckDBPyConnection,
    report_dir: Path,
) -> None:
    assignments = connection.execute(
        "SELECT * FROM phase4_fold_assignments ORDER BY step"
    ).fetchdf()
    assignments.to_csv(FOLD_ASSIGNMENTS_CSV, index=False)
    assignments.to_parquet(FOLD_ASSIGNMENTS_PARQUET, index=False, compression="zstd")


def _report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# MONEYPRINT Walk-Forward Evaluation",
        "",
        "**Protocol:** expanding-window validation with four contiguous chronological folds. The 632–743 period is reserved from the new selection process but has already been accessed by previous experiments; it is not a pristine holdout. No raw data or prior experiment artifacts are overwritten.",
        "",
        "## Method Audit",
        "",
        "- The Phase 3 primary split used equal shares of distinct steps, not rows: 95.59% / 3.00% / 1.41% of transactions fell in train/validation/test.",
        "- Phase 3 compared logistic models with validation metrics and selected a feature set/budget; some prior validation and test results were examined. The Phase 3 robustness analysis added another overlapping, previously accessed alternate test.",
        "- Current predictors exclude labels, flagged-fraud, post-event balances, IDs, and split metadata. Numeric imputation/scaling and one-hot categories are re-fit independently on each fold's training range.",
        "- Recipient history is computed at recipient-step grain with a window ending at `1 PRECEDING`; no current-step or future-step receipt contributes. This temporal property is tested on a fixture and rechecked against the SQL definition.",
        "- Sender pre-balance is decision-time available but strongly artifact-sensitive. Simulated hour (`step % 24`) is not real clock time and may encode simulator schedules.",
        "",
        "## Fold Plan and Support",
        "",
        "Windows were fixed by chronological coverage and minimum support, not model performance. Training expands from step 1; validation windows are disjoint and adjacent to the training cutoff.",
        "",
        "| Fold | Train steps | Train rows | Train fraud | Validation steps | Validation rows | Validation fraud | Prevalence |",
        "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |",
    ]
    for fold in report["fold_plan"]:
        lines.append(
            f"| {fold['fold']} | 1–{fold['train_end']} | "
            f"{fold['train_transaction_count']:,} | {fold['train_fraud_count']:,} | "
            f"{fold['validation_start']}–{fold['validation_end']} | "
            f"{fold['validation_transaction_count']:,} | "
            f"{fold['validation_fraud_count']:,} | {fold['validation_prevalence']:.4%} |"
        )
    final = report["reserved_final_period"]
    lines.extend(
        [
            "",
            f"Reserved final period: steps {final['start_step']}–{final['end_step']}, {final['transaction_count']:,} rows, {final['fraud_count']:,} fraud ({final['prevalence']:.4%}). It was previously accessed; this protocol does not use it for selection.",
            "",
            "## Walk-Forward Validation Results",
            "",
            "Primary population is TRANSFER/CASH_OUT; all-transactions metrics are included in JSON. PR-AUC is average precision. Alert@0.5% selects the highest-scored 0.5% independently within each evaluation period as a capacity metric, not a threshold tuned on labels.",
            "",
            "| Fold | Method | Prevalence | PR-AUC | ROC-AUC | P@100 | R@100 | P@500 | R@500 | P@0.5% | R@0.5% |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["validation_metrics"]:
        if row["population"] != "transfer_cash_out":
            continue
        lines.append(
            f"| {row['fold']} | {row['method']} | {row['fraud_prevalence']:.4%} | "
            f"{row['pr_auc_average_precision']:.6f} | {row['roc_auc']:.6f} | "
            f"{row['precision_at_100']:.2%} | {row['recall_at_100']:.2%} | "
            f"{row['precision_at_500']:.2%} | {row['recall_at_500']:.2%} | "
            f"{row['precision_at_fixed_rate']:.2%} | {row['recall_at_fixed_rate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Fold Variation and Train–Validation Gap",
            "",
            "| Feature set | Mean validation PR-AUC | SD across folds | Mean validation ROC-AUC | Mean train PR-AUC | Mean val minus train PR-AUC |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for feature_set in FEATURE_SET_NAMES:
        item = report["fold_stability"][feature_set]
        lines.append(
            f"| {feature_set} | {item['mean_validation_pr_auc']:.6f} | "
            f"{item['sd_validation_pr_auc']:.6f} | "
            f"{item['mean_validation_roc_auc']:.6f} | "
            f"{item['mean_train_pr_auc']:.6f} | {item['mean_validation_minus_train_pr_auc']:+.6f} |"
        )
    lines.extend(
        [
            "",
            "The in-sample training scores are diagnostics and optimistically biased; fold validation metrics are the generalization estimates. Prevalence varies materially across folds, so PR-AUC and precision variation mixes prevalence shift with ranking change. ROC-AUC and the per-fold ranking metrics help separate those effects but do not remove period shift.",
            "",
            "## Simulation-Artifact Ablation",
            "",
            "The report compares the amount+type baseline, adding simulated hour, then adding sender pre-balance/ratio/coverage, then strictly historical recipient aggregates. A large balance-feature lift is consistent with a PaySim shortcut risk; it does not establish causality. Hour performance is also subject to step-period and simulation schedule shifts.",
            "",
            "## Validation-Selected Configuration",
            "",
            f"Selected feature set: **{report['selection']['feature_set']}**, chosen by highest mean eligible-population validation ROC-AUC across the four walk-forward folds ({report['selection']['mean_validation_roc_auc']:.6f}). ROC-AUC is the primary selection criterion because fold prevalence shifts substantially; PR-AUC remains fully reported per fold. Configuration is fixed balanced logistic regression, Newton-Cholesky, C=1.0; no hyperparameter search was performed. The final model preprocessing was refit on steps 1–631 only.",
            "",
            "## Reserved Previously Accessed Evaluation",
            "",
            "| Method | Prevalence | PR-AUC | ROC-AUC | P@100 | R@100 | P@500 | R@500 | P@0.5% | R@0.5% |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["reserved_period_metrics"]:
        if row["population"] != "transfer_cash_out":
            continue
        lines.append(
            f"| {row['method']} | {row['fraud_prevalence']:.4%} | "
            f"{row['pr_auc_average_precision']:.6f} | {row['roc_auc']:.6f} | "
            f"{row['precision_at_100']:.2%} | {row['recall_at_100']:.2%} | "
            f"{row['precision_at_500']:.2%} | {row['recall_at_500']:.2%} | "
            f"{row['precision_at_fixed_rate']:.2%} | {row['recall_at_fixed_rate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "This period has been read in prior Phase 3 experiments, including test scoring, and was also scored in preliminary Phase 4 implementation runs before the final protocol revision. The final code computes selection from walk-forward validation folds only; however, because earlier reserved-period metrics were visible during protocol iteration, zero influence cannot be claimed. Treat these values as exploratory diagnostics, not a fresh confirmatory estimate.",
            "",
            "## Caveats",
            "",
            "- The folds share expanding training history; fold scores are correlated, not independent replications.",
            "- PR-AUC and precision depend on prevalence. Fold-to-fold changes cannot be called ranking deterioration without accounting for the changing fraud prevalence and mix.",
            "- Sender balance fields may encode simulator balance clipping; the hour field is a synthetic step index. Neither supports causal interpretation.",
            "- All experiments reuse one synthetic dataset and prior exploration has accessed the reserved period. No real-world fraud performance claim is warranted.",
            "",
            "## Reproduction",
            "",
            "```powershell",
            r".\.venv\Scripts\python.exe -m src.phase4_walkforward --plan-only",
            r".\.venv\Scripts\python.exe -m src.phase4_walkforward",
            r".\.venv\Scripts\python.exe -m unittest discover -s tests -v",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _collect_model_fold_metrics(
    connection: duckdb.DuckDBPyConnection,
    parquet_path: Path,
    fold: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    train = _read_range(connection, parquet_path, fold["train_start"], fold["train_end"])
    validation = _read_range(
        connection, parquet_path, fold["validation_start"], fold["validation_end"]
    )
    y_train = train["label_is_fraud"].to_numpy(dtype=np.int8, copy=False)
    if np.unique(y_train).size != 2:
        raise ValueError(f"{fold['fold']} training period lacks both label classes")
    amount_references = _training_amount_references(train)
    results: dict[str, Any] = {}
    fit_status: dict[str, Any] = {}
    models = {}
    for feature_set in FEATURE_SET_NAMES:
        spec = FEATURE_ABLATIONS[feature_set]
        model = make_logistic_pipeline(spec["numeric"], spec["categorical"], CLASS_WEIGHT, max_iter=MAX_ITER)
        columns = list(spec["numeric"] + spec["categorical"])
        started = time.perf_counter()
        with ResourceMonitor(f"{fold['fold']}_{feature_set}") as monitor:
            with numeric_thread_limits():
                with warnings.catch_warnings(record=True) as captured:
                    warnings.simplefilter("always", ConvergenceWarning)
                    model.fit(train[columns], y_train)
        elapsed = time.perf_counter() - started
        classifier = model.named_steps["logistic"]
        models[feature_set] = model
        fit_status[feature_set] = {
            "training_rows": int(len(train)),
            "preprocessing_fit_rows": int(len(train)),
            "iterations": int(classifier.n_iter_[0]),
            "max_iter": int(classifier.max_iter),
            "converged": not captured,
            "warnings": [str(item.message) for item in captured],
            "fit_seconds": float(elapsed),
            "resource_usage": monitor.summary(),
            "effective_threadpools": threadpool_snapshot(),
        }
        print(f"{fold['fold']} {feature_set}: fit {classifier.n_iter_[0]} iterations ({elapsed:.1f}s)")

    methods, _ = _evaluate_methods(
        train, validation, models, amount_references, include_train=True
    )
    for method, splits in methods.items():
        for split, populations in splits.items():
            results[(method, split)] = populations
    rows = []
    for feature_set in FEATURE_SET_NAMES:
        method = LOGISTIC_NAMES[feature_set]
        for split in ("train", "validation"):
            for population, metrics in results[(method, split)].items():
                rows.append(
                    {
                        "fold": fold["fold"],
                        "feature_set": feature_set,
                        "method": method,
                        "split": split,
                        "population": population,
                        **metrics,
                    }
                )
    for method in ("amount_raw", "amount_type_train_percentile"):
        for split in ("train", "validation"):
            for population, metrics in results[(method, split)].items():
                rows.append(
                    {
                        "fold": fold["fold"],
                        "feature_set": method,
                        "method": method,
                        "split": split,
                        "population": population,
                        **metrics,
                    }
                )
    fold_results = {
        feature_set: {
            "train": results[(LOGISTIC_NAMES[feature_set], "train")],
            "validation": results[(LOGISTIC_NAMES[feature_set], "validation")],
        }
        for feature_set in FEATURE_SET_NAMES
    }
    del train, validation, models
    gc.collect()
    return rows, {"metrics": fold_results, "fit_status": fit_status}


def _fold_stability(all_fold_results: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {}
    for feature_set in FEATURE_SET_NAMES:
        rows = [
            row
            for result in all_fold_results
            for row in result["metric_rows"]
            if row["feature_set"] == feature_set
            and row["population"] == "transfer_cash_out"
        ]
        validation = [row for row in rows if row["split"] == "validation"]
        training = [row for row in rows if row["split"] == "train"]
        val_ap = [row["pr_auc_average_precision"] for row in validation]
        val_roc = [row["roc_auc"] for row in validation]
        train_ap = [row["pr_auc_average_precision"] for row in training]
        summary[feature_set] = {
            "fold_validation_pr_auc": val_ap,
            "mean_validation_pr_auc": float(np.mean(val_ap)),
            "sd_validation_pr_auc": float(np.std(val_ap, ddof=1)),
            "min_validation_pr_auc": float(np.min(val_ap)),
            "max_validation_pr_auc": float(np.max(val_ap)),
            "mean_validation_roc_auc": float(np.mean(val_roc)),
            "sd_validation_roc_auc": float(np.std(val_roc, ddof=1)),
            "mean_train_pr_auc": float(np.mean(train_ap)),
            "fold_train_pr_auc": train_ap,
            "fold_validation_minus_train_pr_auc": [
                float(valid - train)
                for train, valid in zip(train_ap, val_ap, strict=True)
            ],
            "mean_validation_minus_train_pr_auc": float(np.mean(val_ap) - np.mean(train_ap)),
        }
    return summary


def run_protocol(
    parquet_path: Path = DEFAULT_PARQUET,
    *,
    plan_only: bool = False,
) -> dict[str, Any] | None:
    validate_fold_specs(FOLD_SPECS)
    if not parquet_path.is_file():
        raise FileNotFoundError(f"Feature Parquet is missing: {parquet_path}")
    protected = [path for path in (*ORIGINAL_ARTIFACTS, parquet_path) if path.is_file()]
    hashes_before = {str(path): sha256_file(path) for path in protected}
    connection = duckdb.connect()
    try:
        _execute_plan_sql(connection, parquet_path)
        support = _get_support(connection)
        print_proposed_plan(support)
        if plan_only:
            return None

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        PROTOCOL_PATH.write_text(
            json.dumps(
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "folds": list(FOLD_SPECS),
                    "reserved_final_period": FINAL_PERIOD,
                    "boundary_rationale": "Fixed chronological windows selected for expanding historical coverage and >=200 validation fraud labels; no model metric used.",
                    "selection_rule": "highest mean TRANSFER/CASH_OUT validation ROC-AUC across four folds; all folds' PR-AUCs retained in reports",
                    "feature_sets": {
                        feature_set: {
                            key: list(values)
                            for key, values in FEATURE_ABLATIONS[feature_set].items()
                        }
                        for feature_set in FEATURE_SET_NAMES
                    },
                    "model": {
                        "estimator": "LogisticRegression",
                        "solver": SOLVER,
                        "class_weight": CLASS_WEIGHT,
                        "C": 1.0,
                        "max_iter": MAX_ITER,
                    },
                    "fixed_alert_rate": ALERT_RATE,
                    "top_k": [100, 500],
                    "reserved_period_previously_accessed": True,
                },
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )

        step_assignments = connection.execute(
            "SELECT * FROM phase4_fold_assignments ORDER BY step"
        ).fetchdf()
        step_assignments.to_csv(FOLD_ASSIGNMENTS_CSV, index=False)
        step_assignments.to_parquet(FOLD_ASSIGNMENTS_PARQUET, index=False, compression="zstd")

        all_fold_results = []
        fold_metric_rows = []
        for fold in FOLD_SPECS:
            metric_rows, result = _collect_model_fold_metrics(connection, parquet_path, fold)
            result["fold"] = fold["fold"]
            result["metric_rows"] = metric_rows
            all_fold_results.append(result)
            fold_metric_rows.extend(metric_rows)

        validation_metrics_by_feature = {
            feature_set: [
                result["metrics"][feature_set]["validation"]
                for result in all_fold_results
            ]
            for feature_set in FEATURE_SET_NAMES
        }
        selected_feature_set, selection_summary = choose_final_feature_set(
            validation_metrics_by_feature
        )
        selection = {
            "feature_set": selected_feature_set,
            "mean_validation_roc_auc": selection_summary[selected_feature_set]["mean_roc_auc"],
            "mean_validation_pr_auc_descriptive": selection_summary[selected_feature_set]["mean_pr_auc"],
            "selection_rule": "highest mean TRANSFER/CASH_OUT ROC-AUC across four walk-forward validation windows; chosen as less directly prevalence-dependent",
            "decision_computed_before_reserved_period_scoring_in_final_run": True,
            "class_weight": CLASS_WEIGHT,
            "solver": SOLVER,
            "C": 1.0,
            "hyperparameter_search": False,
            "fold_summary": selection_summary,
        }

        final_train = _read_range(connection, parquet_path, 1, 631)
        final_eval = _read_range(
            connection,
            parquet_path,
            FINAL_PERIOD["start_step"],
            FINAL_PERIOD["end_step"],
        )
        selected_spec = FEATURE_ABLATIONS[selected_feature_set]
        selected_columns = list(selected_spec["numeric"] + selected_spec["categorical"])
        final_model = make_logistic_pipeline(
            selected_spec["numeric"], selected_spec["categorical"], CLASS_WEIGHT, max_iter=MAX_ITER
        )
        with ResourceMonitor("phase4_final_selected_model") as final_resource_monitor:
            with numeric_thread_limits():
                with warnings.catch_warnings(record=True) as captured:
                    warnings.simplefilter("always", ConvergenceWarning)
                    final_model.fit(
                        final_train[selected_columns],
                        final_train["label_is_fraud"].to_numpy(dtype=np.int8, copy=False),
                    )
        final_classifier = final_model.named_steps["logistic"]

        # Final period is scored only after the validation feature-set decision is fixed.
        final_scores = _score_model(final_model, final_eval, selected_feature_set)
        reserved_metrics = evaluate_scores(final_eval, final_scores)
        # Fixed baselines are reported as reference rankings; they do not change selection.
        final_amount_refs = _training_amount_references(final_train)
        reserved_baselines = {
            "amount_raw": evaluate_scores(
                final_eval, final_eval["amount"].to_numpy(dtype=np.float32, copy=False)
            ),
            "amount_type_train_percentile": evaluate_scores(
                final_eval, _percentile_scores(final_eval, final_amount_refs)
            ),
        }
        model_dir = MODEL_DIR
        model_dir.mkdir(parents=True, exist_ok=True)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "protocol_version": PROTOCOL_VERSION,
                "model": final_model,
                "feature_set": selected_feature_set,
                "feature_spec": {key: list(value) for key, value in selected_spec.items()},
                "selection": selection,
                "fit_steps": [1, 631],
                "solver": SOLVER,
                "class_weight": CLASS_WEIGHT,
                "C": 1.0,
                "seed": 42,
            },
            MODEL_PATH,
            compress=3,
        )

        for path, digest in hashes_before.items():
            if sha256_file(Path(path)) != digest:
                raise AssertionError(f"Protected input/artifact changed: {path}")

        stability = _fold_stability(all_fold_results)
        validation_flat = [
            row
            for row in fold_metric_rows
            if row["split"] == "validation"
        ]
        train_flat = [row for row in fold_metric_rows if row["split"] == "train"]
        final_flat = []
        for method, populations in reserved_baselines.items():
            for population, metric_values in populations.items():
                final_flat.append(
                    {"method": method, "population": population, **metric_values}
                )
        for population, metric_values in reserved_metrics.items():
            final_flat.append(
                {"method": LOGISTIC_NAMES[selected_feature_set], "population": population, **metric_values}
            )

        report = {
            "protocol_version": PROTOCOL_VERSION,
            "status": "expanding-window walk-forward; reserved period previously accessed by earlier experiments",
            "source_parquet": str(parquet_path),
            "source_parquet_sha256": hashes_before[str(parquet_path)],
            "prior_experiment_access_disclosure": {
                "original_phase3_test_accesses": 2,
                "phase3_robustness_alternative_period_accessed": True,
                "reserved_steps_632_743_previously_accessed": True,
                "reserved_period_is_pristine": False,
                "phase4_reserved_period_scored_during_intermediate_protocol_runs": True,
                "reserved_period_metrics_visible_before_final_protocol_revision": True,
                "final_run_selection_computed_before_reserved_period_scoring": True,
                "explicit_selection_function_uses_reserved_period_metrics": False,
                "contamination_assessment": "Reserved-period metrics were visible during protocol iteration; although the final selection function uses only walk-forward validation metrics, zero influence cannot be claimed. Treat as exploratory, not confirmatory.",
                "prior_models_reports_preserved_and_hash_checked": True,
            },
            "method_audit": {
                "original_phase3_split": "equal distinct time-step ranks at 520/631 yielded 95.59%/3.00%/1.41% transaction rows",
                "prior_model_selection": "Phase 3 selected after validation comparisons; prior exploration also trained on overlapping alternative folds/splits",
                "preprocessing": "scaler/imputer/one-hot encoder fit in each model pipeline using only that fold's training rows",
                "recipient_history": "recipient-step aggregate followed by cumulative window ending at 1 PRECEDING; validation rows may use strictly earlier historical observations, never same/future steps",
                "train_metric_caveat": "training metrics are in-sample and optimistic; compare against each fold's subsequent validation window",
            },
            "fold_boundary_rationale": "Four fixed chronological windows with expanding training history, approximately 90-100 validation steps, and at least 200 fraud labels per validation period. Boundaries were not selected using model performance.",
            "fold_plan": support["folds"],
            "reserved_final_period": support["reserved_final_period"],
            "fixed_model_configuration": {
                "estimator": "scikit-learn LogisticRegression",
                "solver": SOLVER,
                "class_weight": CLASS_WEIGHT,
                "C": 1.0,
                "max_iter": MAX_ITER,
                "feature_selection_only_from_walk_forward_validation": True,
                "fixed_alert_rate": ALERT_RATE,
                "top_k": [100, 500],
                "eligible_population": list(ELIGIBLE_TYPES),
                "predictor_sets": {
                    feature_set: {key: list(values) for key, values in FEATURE_ABLATIONS[feature_set].items()}
                    for feature_set in FEATURE_SET_NAMES
                },
            },
            "runtime_configuration": {
                **RUNTIME_CONFIG,
                "effective_threadpools": threadpool_snapshot(),
            },
            "fold_fit_status": [
                {"fold": result["fold"], "models": result["fit_status"]}
                for result in all_fold_results
            ],
            "fold_metrics": fold_metric_rows,
            "validation_metrics": validation_flat,
            "train_diagnostic_metrics": train_flat,
            "fold_stability": stability,
            "selection": selection,
            "final_model_fit": {
                "fit_steps": [1, 631],
                "fit_rows": int(len(final_train)),
                "fit_fraud_count": int(final_train["label_is_fraud"].sum()),
                "iterations": int(final_classifier.n_iter_[0]),
                "max_iter": int(final_classifier.max_iter),
                "converged": not captured,
                "warnings": [str(item.message) for item in captured],
                "resource_usage": final_resource_monitor.summary(),
            },
            "reserved_period_metrics": final_flat,
            "final_model_artifact": str(MODEL_PATH),
            "protocol_manifest": str(PROTOCOL_PATH),
            "fold_metrics_files": {
                "csv": str(FOLD_METRICS_CSV),
                "parquet": str(FOLD_METRICS_PARQUET),
            },
            "step_assignment_files": {
                "csv": str(FOLD_ASSIGNMENTS_CSV),
                "parquet": str(FOLD_ASSIGNMENTS_PARQUET),
            },
            "preservation": {
                path: {"sha256": digest, "unchanged": True}
                for path, digest in hashes_before.items()
            },
            "limitations": [
                "Folds are dependent because training sets expand and overlap.",
                "PR-AUC and precision respond to prevalence; compare them with each fold's prevalence, and use ROC-AUC/ranking capacity metrics as complementary—not prevalence-free proof.",
                "The reserved period has previously been accessed in this project and is not a pristine holdout.",
                "Balance and simulated-hour signals may exploit PaySim simulation artifacts; results are not causal or real-world fraud evidence.",
                "No confidence intervals are supplied; temporal dependence and account dependence make naive row bootstrap intervals misleading.",
            ],
        }
        FOLD_METRICS_CSV.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(fold_metric_rows).to_csv(FOLD_METRICS_CSV, index=False)
        pd.DataFrame(fold_metric_rows).to_parquet(FOLD_METRICS_PARQUET, index=False, compression="zstd")
        REPORT_JSON.write_text(json.dumps(report, indent=2, allow_nan=False, default=_json_default) + "\n", encoding="utf-8")
        REPORT_MD.write_text(_report_markdown(report), encoding="utf-8")
        print(f"Selected {selected_feature_set} by mean walk-forward validation ROC-AUC; final period scored after selection.")
        print(f"Wrote {REPORT_MD} and {REPORT_JSON}")
        print(f"Saved final model to {MODEL_PATH}")
        del final_train, final_eval
        gc.collect()
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
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument(
        "--render-existing-json",
        type=Path,
        help="render Markdown from saved metrics without refitting or rescoring",
    )
    args = parser.parse_args()
    if args.render_existing_json is not None:
        report = json.loads(args.render_existing_json.read_text(encoding="utf-8"))
        disclosure = report["prior_experiment_access_disclosure"]
        disclosure.pop("reserved_period_scores_used_to_change_protocol", None)
        disclosure.update(
            {
                "phase4_reserved_period_scored_during_intermediate_protocol_runs": True,
                "reserved_period_metrics_visible_before_final_protocol_revision": True,
                "final_run_selection_computed_before_reserved_period_scoring": True,
                "explicit_selection_function_uses_reserved_period_metrics": False,
                "contamination_assessment": "Reserved-period metrics were visible during protocol iteration; although the final selection function uses only walk-forward validation metrics, zero influence cannot be claimed. Treat as exploratory, not confirmatory.",
            }
        )
        report["selection"]["decision_computed_before_reserved_period_scoring_in_final_run"] = report[
            "selection"
        ].pop("decision_made_before_reserved_period_scoring", True)
        args.render_existing_json.write_text(
            json.dumps(report, indent=2, allow_nan=False, default=_json_default) + "\n",
            encoding="utf-8",
        )
        markdown_path = args.render_existing_json.with_suffix(".md")
        markdown_path.write_text(_report_markdown(report), encoding="utf-8")
        print(f"Rendered {markdown_path} from saved metrics; no model or evaluation rerun")
        return
    run_protocol(args.parquet_path, plan_only=args.plan_only)


if __name__ == "__main__":
    main()