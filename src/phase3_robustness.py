"""Audit the Phase 3 time-step split and run a separate row-balanced robustness study."""

from __future__ import annotations

import argparse
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

from .features import ROOT, execute_sql_file
from .phase3_evaluation import (
    CATEGORICAL_COLUMNS,
    DEFAULT_PARQUET,
    FEATURE_ABLATIONS,
    FORBIDDEN_FIELDS,
    NUMERIC_COLUMNS,
    calculate_metrics,
    evaluate_populations,
    make_logistic_pipeline,
)


DEFAULT_REPORT_DIR = ROOT / "reports"
DEFAULT_MODEL_DIR = ROOT / "models"
SQL_PATH = ROOT / "sql" / "phase3_robustness.sql"
MAIN_REPORT_JSON = ROOT / "reports" / "phase3_evaluation.json"
MAIN_REPORT_MD = ROOT / "reports" / "phase3_evaluation.md"
MAIN_MODEL_PATH = ROOT / "models" / "phase3_rankers.joblib"
MAIN_SELECTION_PATH = ROOT / "models" / "phase3_selection.json"
ROBUSTNESS_NAME = "phase3_robustness"
FEATURE_SET_ORDER = (
    "amount_type",
    "plus_hour",
    "plus_balance",
    "full_context",
)
MODEL_NAMES = {
    "amount_type": "logistic_amount_type_balanced",
    "plus_hour": "logistic_plus_hour_balanced",
    "plus_balance": "logistic_plus_balance_balanced",
    "full_context": "logistic_full_context_balanced",
}
SPLIT_ORDER = ("train", "validation", "test")
TOP_K_VALUES = (100, 500)
ELIGIBLE_TYPES = ("TRANSFER", "CASH_OUT")


def choose_whole_step_boundaries(
    step_counts: list[tuple[int, int]],
    train_fraction: float = 0.70,
    validation_end_fraction: float = 0.85,
) -> dict[str, Any]:
    if len(step_counts) < 3:
        raise ValueError("At least three complete steps are required")
    if any(count <= 0 for _, count in step_counts):
        raise ValueError("Every step must contain at least one transaction")
    steps = [step for step, _ in step_counts]
    if steps != sorted(set(steps)):
        raise ValueError("Steps must be unique and in ascending order")
    total = sum(count for _, count in step_counts)
    cumulative = np.cumsum([count for _, count in step_counts], dtype=np.int64)
    eligible_first = range(0, len(step_counts) - 2)
    first_index = min(
        eligible_first,
        key=lambda index: (abs(int(cumulative[index]) - train_fraction * total), index),
    )
    eligible_second = range(first_index + 1, len(step_counts) - 1)
    second_index = min(
        eligible_second,
        key=lambda index: (
            abs(int(cumulative[index]) - validation_end_fraction * total), index
        ),
    )
    first_cumulative = int(cumulative[first_index])
    second_cumulative = int(cumulative[second_index])
    return {
        "train_end_step": int(steps[first_index]),
        "validation_end_step": int(steps[second_index]),
        "train_end_cumulative_transactions": first_cumulative,
        "validation_end_cumulative_transactions": second_cumulative,
        "total_transactions": int(total),
        "train_cumulative_share": first_cumulative / total,
        "validation_end_cumulative_share": second_cumulative / total,
        "train_target_fraction": train_fraction,
        "validation_end_target_fraction": validation_end_fraction,
        "train_boundary_absolute_row_error": abs(
            first_cumulative - train_fraction * total
        ),
        "validation_boundary_absolute_row_error": abs(
            second_cumulative - validation_end_fraction * total
        ),
    }


def select_validation_model(
    validation_results: dict[str, dict[str, Any]],
) -> tuple[str, int, dict[str, Any]]:
    selected_name = max(
        FEATURE_SET_ORDER,
        key=lambda name: validation_results[name]["transfer_cash_out"][
            "pr_auc_average_precision"
        ],
    )
    metrics = validation_results[selected_name]["transfer_cash_out"]
    budget = max(
        TOP_K_VALUES,
        key=lambda value: (metrics[f"f1_at_{value}"], -value),
    )
    return selected_name, budget, {
        "selected_feature_set": selected_name,
        "selection_population": "TRANSFER and CASH_OUT only",
        "selection_metric": "validation PR-AUC (average precision)",
        "validation_pr_auc": metrics["pr_auc_average_precision"],
        "selected_investigation_budget": budget,
        "budget_selection_metric": "validation F1 at K; ties choose smaller K",
        "validation_precision_at_budget": metrics[f"precision_at_{budget}"],
        "validation_recall_at_budget": metrics[f"recall_at_{budget}"],
        "validation_false_positives_at_budget": metrics[
            f"false_positives_at_{budget}"
        ],
        "test_labels_used_for_selection": False,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_parquet_split(
    connection: duckdb.DuckDBPyConnection,
    parquet_path: Path,
    protocol: str,
    split: str,
    boundaries: dict[str, Any] | None = None,
) -> pd.DataFrame:
    escaped_path = str(parquet_path.resolve()).replace("\\", "/").replace("'", "''")
    split_filter: str
    parameters: list[Any]
    if protocol == "original":
        split_filter = "split = ?"
        parameters = [split]
    else:
        assert boundaries is not None
        if split == "train":
            split_filter = "split_step <= ?"
            parameters = [boundaries["train_end_step"]]
        elif split == "validation":
            split_filter = "split_step > ? AND split_step <= ?"
            parameters = [
                boundaries["train_end_step"],
                boundaries["validation_end_step"],
            ]
        elif split == "test":
            split_filter = "split_step > ?"
            parameters = [boundaries["validation_end_step"]]
        else:
            raise ValueError(f"Unknown split: {split}")
    query = (
        "SELECT split_step, label_is_fraud, amount, transaction_type, simulated_hour, "
        "sender_pre_balance, amount_to_sender_pre_balance, "
        "sender_balance_covers_amount, recipient_prior_transaction_count, "
        "recipient_prior_received_amount "
        f"FROM read_parquet('{escaped_path}') WHERE {split_filter} ORDER BY split_step"
    )
    frame = connection.execute(query, parameters).fetch_df()
    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(np.float32)
    frame["label_is_fraud"] = frame["label_is_fraud"].astype(np.int8)
    frame["simulated_hour"] = frame["simulated_hour"].astype("string")
    frame["transaction_type"] = frame["transaction_type"].astype("string")
    return frame


def _metric_rows(
    protocol: str,
    split: str,
    by_feature_set: dict[str, dict[str, Any]],
    provenance: str,
) -> list[dict[str, Any]]:
    return [
        {
            "protocol": protocol,
            "split": split,
            "feature_set": feature_set,
            "population": population,
            "metrics_source": provenance,
            **metrics,
        }
        for feature_set, populations in by_feature_set.items()
        for population, metrics in populations.items()
    ]


def _existing_main_metrics(
    main_report: dict[str, Any], split: str
) -> dict[str, dict[str, Any]]:
    source_key = "validation_by_method" if split == "validation" else "test_by_method"
    source = main_report[source_key]
    result = {}
    for feature_set in FEATURE_SET_ORDER:
        method = MODEL_NAMES[feature_set]
        if method not in source:
            raise KeyError(f"Original Phase 3 report does not contain {method}")
        result[feature_set] = source[method]
    return result


def _split_and_type_summaries(
    connection: duckdb.DuckDBPyConnection,
    boundaries: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    train_end = int(boundaries["train_end_step"])
    validation_end = int(boundaries["validation_end_step"])
    connection.execute(
        "CREATE OR REPLACE TEMP VIEW robustness_labeled AS "
        "SELECT *, CASE WHEN split_step <= "
        f"{train_end} THEN 'train' WHEN split_step <= {validation_end} "
        "THEN 'validation' ELSE 'test' END AS robustness_split "
        "FROM robustness_source"
    )
    split_rows = connection.execute(
        "SELECT robustness_split, COUNT(*) AS transactions, "
        "COUNT(*) FILTER (WHERE label_is_fraud = 1) AS fraud_count, "
        "COUNT(DISTINCT split_step) AS distinct_steps, MIN(split_step) AS min_step, "
        "MAX(split_step) AS max_step, SUM(amount) AS total_amount, AVG(amount) AS mean_amount, "
        "quantile_cont(amount, 0.50) AS median_amount, "
        "quantile_cont(amount, 0.95) AS p95_amount "
        "FROM robustness_labeled GROUP BY robustness_split "
        "ORDER BY CASE robustness_split WHEN 'train' THEN 1 "
        "WHEN 'validation' THEN 2 ELSE 3 END"
    ).fetchall()
    total_rows = sum(int(row[1]) for row in split_rows)
    split_summary = []
    for row in split_rows:
        transactions, fraud = int(row[1]), int(row[2])
        split_summary.append(
            {
                "split": row[0],
                "transaction_count": transactions,
                "row_share": transactions / total_rows,
                "fraud_count": fraud,
                "fraud_prevalence": fraud / transactions,
                "distinct_steps": int(row[3]),
                "min_step": int(row[4]),
                "max_step": int(row[5]),
                "total_amount": float(row[6]),
                "mean_amount": float(row[7]),
                "median_amount": float(row[8]),
                "p95_amount": float(row[9]),
            }
        )
    type_rows = connection.execute(
        "SELECT robustness_split, transaction_type, COUNT(*) AS transactions, "
        "COUNT(*) FILTER (WHERE label_is_fraud = 1) AS fraud_count, "
        "SUM(amount) AS total_amount, AVG(amount) AS mean_amount, "
        "quantile_cont(amount, 0.50) AS median_amount, "
        "quantile_cont(amount, 0.95) AS p95_amount "
        "FROM robustness_labeled GROUP BY robustness_split, transaction_type "
        "ORDER BY CASE robustness_split WHEN 'train' THEN 1 "
        "WHEN 'validation' THEN 2 ELSE 3 END, transaction_type"
    ).fetchall()
    counts_by_split = {row["split"]: row["transaction_count"] for row in split_summary}
    type_mix = []
    for row in type_rows:
        split, transaction_type, count, fraud = row[:4]
        type_mix.append(
            {
                "split": split,
                "transaction_type": transaction_type,
                "transaction_count": int(count),
                "transaction_share": int(count) / counts_by_split[split],
                "fraud_count": int(fraud),
                "fraud_prevalence": int(fraud) / int(count),
                "total_amount": float(row[4]),
                "mean_amount": float(row[5]),
                "median_amount": float(row[6]),
                "p95_amount": float(row[7]),
            }
        )
    hourly_rows = connection.execute(
        "SELECT robustness_split, simulated_hour, COUNT(*) AS transactions, "
        "COUNT(*) FILTER (WHERE label_is_fraud = 1) AS fraud_count "
        "FROM robustness_labeled GROUP BY robustness_split, simulated_hour "
        "ORDER BY CASE robustness_split WHEN 'train' THEN 1 "
        "WHEN 'validation' THEN 2 ELSE 3 END, simulated_hour"
    ).fetchall()
    hourly_patterns = [
        {
            "split": row[0],
            "simulated_hour": int(row[1]),
            "transaction_count": int(row[2]),
            "fraud_count": int(row[3]),
            "fraud_prevalence": int(row[3]) / int(row[2]),
        }
        for row in hourly_rows
    ]
    if total_rows != int(connection.execute("SELECT COUNT(*) FROM robustness_source").fetchone()[0]):
        raise AssertionError("Alternative split rows do not reconcile")
    return {
        "split_summary": split_summary,
        "type_mix_and_amounts": type_mix,
        "hourly_patterns": hourly_patterns,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    original_row_distribution = report["original_protocol"]["row_distribution"]
    lines = [
        "# Phase 3 Chronological Robustness Audit",
        "",
        "**Secondary exploratory robustness analysis; not a pristine holdout.** The original Phase 3 split, model bundle, reports, and selection file were preserved. Original validation/test classifier metrics below are reused from the saved Phase 3 report; the original test was not rescored by this audit. The original test had already been accessed twice (the discarded non-converged SAGA run and the corrected Phase 3 run).",
        "",
        "## Why the Original Row Shares Skewed",
        "",
        "The primary split assigned equal proportions of the 743 distinct step values, implicitly treating each step as equal in volume. Transaction counts per step are highly nonuniform: the original training period averaged 11,696 rows/step, validation 1,722, and test 799. Thus the row shares are "
        + ", ".join(
            f"{row['split']} {row['row_share']:.2%} ({row['transaction_count']:,} rows)"
            for row in original_row_distribution
        )
        + ", although the step shares were approximately 70/15/15. The full per-step cumulative transaction and fraud series is provided in the companion CSV/Parquet files.",
        "",
        "| Original split | Steps | Transactions | Row share | Mean transactions/step | Fraud | Prevalence |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in original_row_distribution:
        lines.append(
            f"| {row['split']} | {row['distinct_steps']:,} | "
            f"{row['transaction_count']:,} | {row['row_share']:.4%} | "
            f"{row['mean_transactions_per_step']:,.1f} | {row['fraud_count']:,} | "
            f"{row['fraud_prevalence']:.4%} |"
        )
    lines.extend(
        [
            "",
        "| Original boundary | Through step | Cumulative transactions | Row share | Cumulative fraud labels | Fraud share |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["original_cumulative_checkpoints"]:
        lines.append(
            f"| {row['boundary']} | {row['step']:,} | "
            f"{row['cumulative_transactions']:,} | {row['cumulative_transaction_share']:.4%} | "
            f"{row['cumulative_fraud']:,} | {row['cumulative_fraud_share']:.4%} |"
        )
    lines.extend(
        [
            "",
            "The largest individual steps are also tens of thousands of rows (the top step contains 51,352 transactions), which is why step-count proportions are not transaction-count proportions.",
            "",
            "## Alternative Whole-Step Split",
            "",
            f"Boundaries minimize absolute row-count error to cumulative 70% and 85%, using transaction counts only and never cutting a step: train through step {report['alternative_boundaries']['train_end_step']:,}; validation through step {report['alternative_boundaries']['validation_end_step']:,}.",
            "",
            "| Split | Steps | Transactions | Row share | Fraud | Prevalence | Mean amount | Median | P95 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["alternative_split_audit"]["split_summary"]:
        lines.append(
            f"| {row['split']} | {row['distinct_steps']:,} ({row['min_step']}–{row['max_step']}) | "
            f"{row['transaction_count']:,} | {row['row_share']:.2%} | {row['fraud_count']:,} | "
            f"{row['fraud_prevalence']:.4%} | {row['mean_amount']:,.2f} | "
            f"{row['median_amount']:,.2f} | {row['p95_amount']:,.2f} |"
        )
    lines.extend(
        [
            "",
            "### Type Mix and Fraud by Type",
            "",
            "| Split | Type | Transactions | Split share | Fraud | Type prevalence | Mean amount | Median | P95 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["alternative_split_audit"]["type_mix_and_amounts"]:
        lines.append(
            f"| {row['split']} | {row['transaction_type']} | {row['transaction_count']:,} | "
            f"{row['transaction_share']:.2%} | {row['fraud_count']:,} | "
            f"{row['fraud_prevalence']:.4%} | {row['mean_amount']:,.2f} | "
            f"{row['median_amount']:,.2f} | {row['p95_amount']:,.2f} |"
        )
    lines.extend(
        [
            "",
            "Validation has 560 fraud cases overall (280 per labeled transaction type); alternative test has 4,010 (2,005 each in CASH_OUT and TRANSFER). These counts support exploratory ranking estimates, but test prevalence is 0.4196% and remains subject to temporal and project-level reuse. No confidence interval is claimed.",
            "",
            "## Feature-Set Comparison",
            "",
            "All four feature sets use balanced logistic regression for comparability. Feature sets match the Phase 3 hierarchy: amount+type; add simulated hour; add sender pre-balance/ratio/coverage to amount+type+hour; then add strictly historical recipient count/amount. The balance ablation therefore includes hour, as in the original Phase 3 saved specification.",
            "PR-AUC is average precision. Every row reports prevalence to make the period mix visible; PR-AUC and precision depend on prevalence and must not be naively compared across periods.",
            "",
            "| Protocol | Split | Feature set | Population | Fraud prevalence | PR-AUC | ROC-AUC | P@100 | R@100 | P@500 | R@500 |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["model_metrics"]:
        lines.append(
            f"| {row['protocol']} | {row['split']} | {row['feature_set']} | "
            f"{row['population']} | {row['fraud_prevalence']:.4%} | "
            f"{row['pr_auc_average_precision']:.6f} | {row['roc_auc']:.6f} | "
            f"{row['precision_at_100']:.2%} | {row['recall_at_100']:.2%} | "
            f"{row['precision_at_500']:.2%} | {row['recall_at_500']:.2%} |"
        )
    def metric(protocol: str, split: str, feature_set: str) -> dict[str, Any]:
        return next(
            row
            for row in report["model_metrics"]
            if row["protocol"] == protocol
            and row["split"] == split
            and row["feature_set"] == feature_set
            and row["population"] == "transfer_cash_out"
        )

    original_validation_balance = metric("original_step_split", "validation", "plus_balance")
    original_validation_full = metric("original_step_split", "validation", "full_context")
    original_test_balance = metric("original_step_split", "test", "plus_balance")
    original_test_full = metric("original_step_split", "test", "full_context")
    row_validation_balance = metric("cumulative_row_split", "validation", "plus_balance")
    row_validation_full = metric("cumulative_row_split", "validation", "full_context")
    row_test_balance = metric("cumulative_row_split", "test", "plus_balance")
    row_test_full = metric("cumulative_row_split", "test", "full_context")
    lines.extend(
        [
            "",
            "## Stability Summary",
            "",
            "The ordering is directionally stable: amount/type alone is weak, adding simulated hour improves ranking, and adding balance features accounts for most of the lift under both protocols. Full context edges the balance ablation on eligible-population PR-AUC by "
            f"{original_validation_full['pr_auc_average_precision'] - original_validation_balance['pr_auc_average_precision']:.4f} / "
            f"{original_test_full['pr_auc_average_precision'] - original_test_balance['pr_auc_average_precision']:.4f} "
            "on original validation/test and "
            f"{row_validation_full['pr_auc_average_precision'] - row_validation_balance['pr_auc_average_precision']:.4f} / "
            f"{row_test_full['pr_auc_average_precision'] - row_test_balance['pr_auc_average_precision']:.4f} "
            "on row-based validation/test. This is a relatively small added increment beyond balance features, not evidence of a causal recipient-history effect.",
            f"Top-budget recall is less stable: full-context recall@500 is {original_test_full['recall_at_500']:.2%} on the original test and {row_test_full['recall_at_500']:.2%} on the exploratory row-based test. Period prevalence and transaction mix differ, and the latter overlaps prior analysis.",
            "",
            "## Alternative Protocol Selection",
            "",
            f"Validation-only selected feature set: **{report['alternative_validation_selection']['selected_feature_set']}**; budget: **top {report['alternative_validation_selection']['selected_investigation_budget']} TRANSFER/CASH_OUT transactions**, by validation F1. Test labels were not used in this selection. The alternative test is exploratory: steps 378–520 were in the original Phase 3 training period, and later steps were in its validation/test periods.",
            "",
            "## Methodological Checks and Limitations",
            "",
            "- The alternate cutoffs use step transaction counts only; fraud counts are not used to place boundaries.",
            "- Every model's imputer, scaler, and one-hot encoder is fit on that protocol's training period only. The alternative models are newly fit; original models are loaded read-only.",
            "- Recipient histories were precomputed at recipient-step grain from all transactions, then restricted to strictly earlier steps. Same-step activity does not contribute to another transaction's history; validation/test historical state may legitimately include earlier-period observations.",
            "- Predictor inputs exclude fraud labels, flagged-fraud indicators, post-event balances, account IDs, and split metadata.",
            "- Sender pre-balance and balance ratios sharply improve scores and may encode PaySim balance-generation shortcuts. Simulated hour is not wall-clock time and exhibits period-dependent label patterns. These are associations, not causal effects.",
            "- The alternate test is not pristine because the same dataset and overlapping periods were previously examined in Phase 3. Original primary test results are copied from the saved report, not recomputed here.",
            "- All results are synthetic-data research diagnostics, not claims of real-world fraud-detection performance.",
            "",
            "## Reproduction",
            "",
            "```powershell",
            r".\.venv\Scripts\python.exe -m src.phase3_robustness",
            r".\.venv\Scripts\python.exe -m unittest discover -s tests -v",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _original_cumulative_checkpoints(
    step_cumulative: pd.DataFrame, total_fraud: int
) -> list[dict[str, Any]]:
    checkpoints = []
    for label, end_step in (("train", 520), ("validation", 631), ("test", 743)):
        selected = step_cumulative.loc[step_cumulative["step"] == end_step]
        if selected.empty:
            raise ValueError(f"Original split boundary {end_step} is absent from feature data")
        row = selected.iloc[0]
        checkpoints.append(
            {
                "boundary": label,
                "step": end_step,
                "cumulative_transactions": int(row["cumulative_transactions"]),
                "cumulative_transaction_share": float(
                    row["cumulative_transactions"] / row["total_transactions"]
                ),
                "cumulative_fraud": int(row["cumulative_fraud"]),
                "cumulative_fraud_share": (
                    int(row["cumulative_fraud"]) / total_fraud if total_fraud else 0.0
                ),
            }
        )
    return checkpoints


def _original_row_distribution(split_summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total_transactions = sum(int(row["transaction_count"]) for row in split_summary)
    result = []
    for row in split_summary:
        transactions = int(row["transaction_count"])
        steps = int(row["distinct_steps"])
        result.append(
            {
                "split": row["split"],
                "distinct_steps": steps,
                "transaction_count": transactions,
                "row_share": transactions / total_transactions,
                "mean_transactions_per_step": transactions / steps,
                "fraud_count": int(row["fraud_count"]),
                "fraud_prevalence": float(row["fraud_prevalence"]),
            }
        )
    return result


def _population_metrics_for_model(
    model: Any, frame: pd.DataFrame, spec: dict[str, tuple[str, ...]]
) -> dict[str, Any]:
    columns = list(spec["numeric"] + spec["categorical"])
    scores = model.predict_proba(frame[columns])[:, 1]
    if len(scores) != len(frame):
        raise AssertionError("Predicted score count does not match transaction rows")
    return evaluate_populations(frame, scores)


def _alternative_split_metrics(
    frame: pd.DataFrame,
    models: dict[str, Any],
    fit_summaries: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    results = {}
    for feature_set, model in models.items():
        results[feature_set] = _population_metrics_for_model(
            model, frame, FEATURE_ABLATIONS[feature_set]
        )
    return results


def run_robustness(
    parquet_path: Path = DEFAULT_PARQUET,
    report_dir: Path = DEFAULT_REPORT_DIR,
    model_dir: Path = DEFAULT_MODEL_DIR,
) -> dict[str, Any]:
    for required_path in (parquet_path, MAIN_MODEL_PATH, MAIN_REPORT_JSON, MAIN_REPORT_MD, MAIN_SELECTION_PATH):
        if not required_path.is_file():
            raise FileNotFoundError(f"Required Phase 3 input not found: {required_path}")
    preserved_paths = (
        MAIN_MODEL_PATH,
        MAIN_REPORT_JSON,
        MAIN_REPORT_MD,
        MAIN_SELECTION_PATH,
    )
    hashes_before = {str(path): sha256_file(path) for path in preserved_paths}
    main_report = json.loads(MAIN_REPORT_JSON.read_text(encoding="utf-8"))
    main_bundle = joblib.load(MAIN_MODEL_PATH)
    connection = duckdb.connect()
    try:
        parquet_literal = str(parquet_path.resolve()).replace("\\", "/").replace("'", "''")
        sql_text = SQL_PATH.read_text(encoding="utf-8").replace(
            "__PARQUET_PATH__", parquet_literal
        )
        for statement in connection.extract_statements(sql_text):
            connection.execute(statement)

        step_rows = connection.execute(
            "SELECT step, transaction_count FROM robustness_step_counts ORDER BY step"
        ).fetchall()
        boundaries = choose_whole_step_boundaries(
            [(int(row[0]), int(row[1])) for row in step_rows]
        )

        # Score original training rows only; validation/test metrics are reused from Phase 3.
        original_train = _read_parquet_split(connection, parquet_path, "original", "train")
        original_metrics: dict[str, dict[str, Any]] = {}
        original_train_results = {}
        for feature_set in FEATURE_SET_ORDER:
            model_name = MODEL_NAMES[feature_set]
            original_model = main_bundle["models"][model_name]
            original_train_results[feature_set] = _population_metrics_for_model(
                original_model,
                original_train,
                FEATURE_ABLATIONS[feature_set],
            )
        original_metrics["train"] = original_train_results
        original_metrics["validation"] = _existing_main_metrics(main_report, "validation")
        original_metrics["test"] = _existing_main_metrics(main_report, "test")

        alternative_train = _read_parquet_split(
            connection, parquet_path, "alternative", "train", boundaries
        )
        alternative_validation = _read_parquet_split(
            connection, parquet_path, "alternative", "validation", boundaries
        )
        train_labels = alternative_train["label_is_fraud"].to_numpy(dtype=np.int8)
        if np.unique(train_labels).size != 2:
            raise ValueError("Alternative training period must contain both label classes")

        alternative_models: dict[str, Any] = {}
        fit_summaries: dict[str, Any] = {}
        train_results = {}
        validation_results = {}
        for feature_set in FEATURE_SET_ORDER:
            spec = FEATURE_ABLATIONS[feature_set]
            model = make_logistic_pipeline(spec["numeric"], spec["categorical"], "balanced")
            columns = list(spec["numeric"] + spec["categorical"])
            started = time.perf_counter()
            with ResourceMonitor(f"{feature_set}") as monitor:
                with numeric_thread_limits():
                    with warnings.catch_warnings(record=True) as captured:
                        warnings.simplefilter("always", ConvergenceWarning)
                        model.fit(alternative_train[columns], train_labels)
            elapsed = time.perf_counter() - started
            classifier = model.named_steps["logistic"]
            alternative_models[feature_set] = model
            fit_summaries[feature_set] = {
                "training_rows": int(len(alternative_train)),
                "training_fraud_count": int(train_labels.sum()),
                "class_weight": "balanced",
                "solver": classifier.solver,
                "iterations": int(classifier.n_iter_[0]),
                "max_iter": int(classifier.max_iter),
                "converged_before_max_iter": int(classifier.n_iter_[0]) < int(classifier.max_iter),
                "warnings": [str(item.message) for item in captured],
                "fit_seconds": float(elapsed),
                "preprocessing_fit_rows": int(len(alternative_train)),
                "resource_usage": monitor.summary(),
                "effective_threadpools": threadpool_snapshot(),
                "runtime_thread_plan": RUNTIME_CONFIG,
            }
            train_results[feature_set] = _population_metrics_for_model(
                model, alternative_train, spec
            )
            validation_results[feature_set] = _population_metrics_for_model(
                model, alternative_validation, spec
            )
            print(
                f"Alternative fit {feature_set}: {classifier.n_iter_[0]} iterations, "
                f"{elapsed:.1f}s"
            )

        selected_feature_set, selected_budget, selection = select_validation_model(
            validation_results
        )
        frozen_selection = {
            **selection,
            "frozen_before_alternative_test_load": True,
            "split_rule": "nearest whole-step cumulative transaction shares to 70% and 85%",
            "boundaries": boundaries,
            "feature_sets": {
                name: {key: list(values) for key, values in FEATURE_ABLATIONS[name].items()}
                for name in FEATURE_SET_ORDER
            },
        }
        model_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)
        selection_path = model_dir / "phase3_robustness_selection.json"
        model_path = model_dir / "phase3_robustness_models.joblib"
        selection_path.write_text(
            json.dumps(frozen_selection, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        joblib.dump(
            {
                "models": alternative_models,
                "feature_sets": frozen_selection["feature_sets"],
                "selection": frozen_selection,
                "training_protocol": "alternative cumulative-row whole-step split",
                "seed": 42,
            },
            model_path,
            compress=3,
        )

        # This is the only load and model-scoring pass over alternative test labels.
        alternative_test = _read_parquet_split(
            connection, parquet_path, "alternative", "test", boundaries
        )
        test_results = _alternative_split_metrics(
            alternative_test, alternative_models, fit_summaries
        )

        # Add fraud counts only after the alternative selection is frozen.
        cumulative_rows = connection.execute(
            "WITH per_step AS (SELECT split_step AS step, COUNT(*) AS transaction_count, "
            "COUNT(*) FILTER (WHERE label_is_fraud = 1) AS fraud_count "
            "FROM robustness_source GROUP BY split_step) "
            "SELECT step, transaction_count, fraud_count, "
            "SUM(transaction_count) OVER (ORDER BY step) AS cumulative_transactions, "
            "SUM(fraud_count) OVER (ORDER BY step) AS cumulative_fraud, "
            "SUM(transaction_count) OVER () AS total_transactions, "
            "SUM(fraud_count) OVER () AS total_fraud "
            "FROM per_step ORDER BY step"
        ).fetchdf()
        cumulative_rows["cumulative_transaction_share"] = (
            cumulative_rows["cumulative_transactions"] / cumulative_rows["total_transactions"]
        )
        cumulative_rows["cumulative_fraud_share"] = (
            cumulative_rows["cumulative_fraud"] / cumulative_rows["total_fraud"]
        )
        cumulative_csv = report_dir / "phase3_robustness_step_cumulative.csv"
        cumulative_parquet = report_dir / "phase3_robustness_step_cumulative.parquet"
        cumulative_rows.to_csv(cumulative_csv, index=False)
        cumulative_rows.to_parquet(cumulative_parquet, index=False, compression="zstd")
        total_fraud = int(cumulative_rows["total_fraud"].iloc[0])
        original_checkpoints = _original_cumulative_checkpoints(
            cumulative_rows, total_fraud
        )

        alternative_split_audit = _split_and_type_summaries(connection, boundaries)
        model_metrics = []
        for split in SPLIT_ORDER:
            if split == "train":
                split_data = original_metrics[split]
                source = "saved Phase 3 model artifact scored on original training rows"
            elif split in ("validation", "test"):
                split_data = original_metrics[split]
                source = "copied verbatim from preserved Phase 3 report; not rescored"
            for row in _metric_rows("original_step_split", split, split_data, source):
                row["feature_set_definition"] = {
                    key: list(values)
                    for key, values in FEATURE_ABLATIONS[row["feature_set"]].items()
                }
                model_metrics.append(row)

            alternative_data = {
                "train": train_results,
                "validation": validation_results,
                "test": test_results,
            }[split]
            alternative_source = (
                "alternative train-only fitted model; in-sample ranking"
                if split == "train"
                else "alternative train-fitted model; validation/test scored on distinct whole-step period"
            )
            for row in _metric_rows(
                "cumulative_row_split", split, alternative_data, alternative_source
            ):
                row["feature_set_definition"] = {
                    key: list(values)
                    for key, values in FEATURE_ABLATIONS[row["feature_set"]].items()
                }
                model_metrics.append(row)

        preservation_after = {str(path): sha256_file(path) for path in preserved_paths}
        preservation = {
            path: {
                "sha256_before": hashes_before[path],
                "sha256_after": preservation_after[path],
                "unchanged": hashes_before[path] == preservation_after[path],
            }
            for path in hashes_before
        }
        if not all(record["unchanged"] for record in preservation.values()):
            raise AssertionError("A protected original Phase 3 artifact changed")

        report: dict[str, Any] = {
            "analysis_status": "secondary exploratory robustness analysis; not a pristine holdout",
            "source_parquet": str(parquet_path),
            "original_protocol": {
                "name": "original equal-distinct-step split",
                "boundaries": {"train_end_step": 520, "validation_end_step": 631, "test_end_step": 743},
                "split_summary": main_report["split_audit"]["split_summary"],
                "row_distribution": _original_row_distribution(
                    main_report["split_audit"]["split_summary"]
                ),
                "type_mix_and_amounts": main_report["split_audit"]["type_mix_and_amounts"],
                "hourly_patterns": main_report["split_audit"]["hourly_patterns"],
                "metrics_source": "preserved Phase 3 report for validation/test; saved Phase 3 models scored on train only",
                "prior_test_accesses": 2,
                "this_audit_rescored_original_test": False,
            },
            "original_cumulative_checkpoints": original_checkpoints,
            "step_count_distribution": {
                "top_10_steps_by_transactions": cumulative_rows.nlargest(
                    10, "transaction_count"
                )[["step", "transaction_count", "fraud_count"]].to_dict(orient="records"),
                "original_mean_rows_per_step": [
                    {
                        "split": row[0],
                        "mean_transactions_per_step": float(row[1]),
                    }
                    for row in connection.execute(
                        "SELECT split, AVG(step_count) FROM ("
                        "SELECT split, split_step, COUNT(*) AS step_count "
                        "FROM robustness_source GROUP BY split, split_step) "
                        "GROUP BY split ORDER BY CASE split WHEN 'train' THEN 1 "
                        "WHEN 'validation' THEN 2 ELSE 3 END"
                    ).fetchall()
                ],
                "full_series_csv": str(cumulative_csv),
                "full_series_parquet": str(cumulative_parquet),
            },
            "alternative_boundaries": boundaries,
            "alternative_split_audit": alternative_split_audit,
            "alternative_validation_selection": frozen_selection,
            "alternative_fit_summary": fit_summaries,
            "model_metrics": model_metrics,
            "validation_by_feature_set": validation_results,
            "test_by_feature_set": test_results,
            "preservation_hashes": preservation,
            "artifacts": {
                "robustness_models": str(model_path),
                "robustness_selection": str(selection_path),
                "step_cumulative_csv": str(cumulative_csv),
                "step_cumulative_parquet": str(cumulative_parquet),
                "json_report": str(report_dir / "phase3_robustness.json"),
                "markdown_report": str(report_dir / "phase3_robustness.md"),
            },
            "methodological_risks": [
                "Transaction-count boundaries correct row allocation but create different-length time periods.",
                "PR-AUC and precision are prevalence-sensitive; report values with each split's fraud prevalence and avoid naive cross-period comparisons.",
                "Alternative test steps 378-520 were part of the original Phase 3 training period; later steps overlapped its validation/test periods and prior analysis.",
                "The original Phase 3 test had two prior accesses; this audit reuses its saved report and does not rescore that test.",
                "Recipient histories are strictly earlier-step aggregates and include earlier observations available at decision time; no same-step information is used.",
                "Hour and pre-balance features may exploit PaySim generation shortcuts; coefficient and score associations are not causal or real-world claims.",
            ],
        }
        report_json = report_dir / "phase3_robustness.json"
        report_md = report_dir / "phase3_robustness.md"
        report_json.write_text(
            json.dumps(report, indent=2, allow_nan=False, default=_json_default) + "\n",
            encoding="utf-8",
        )
        report_md.write_text(_render_markdown(report), encoding="utf-8")
        print(
            "Alternative split: "
            f"train through {boundaries['train_end_step']}, "
            f"validation through {boundaries['validation_end_step']}"
        )
        print(f"Saved {report_json}")
        print(f"Saved {report_md}")
        print(f"Preserved {len(preservation)} original artifact hashes")
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
    parser.add_argument(
        "--render-existing-json",
        type=Path,
        help="render Markdown from an existing robustness JSON without rerunning analysis",
    )
    args = parser.parse_args()
    if args.render_existing_json is not None:
        report = json.loads(args.render_existing_json.read_text(encoding="utf-8"))
        report["original_protocol"]["row_distribution"] = _original_row_distribution(
            report["original_protocol"]["split_summary"]
        )
        args.render_existing_json.write_text(
            json.dumps(report, indent=2, allow_nan=False, default=_json_default) + "\n",
            encoding="utf-8",
        )
        markdown_path = args.render_existing_json.with_suffix(".md")
        markdown_path.write_text(_render_markdown(report), encoding="utf-8")
        print(f"Refreshed {args.render_existing_json} and {markdown_path} from saved results; no data or model was re-evaluated")
        return
    run_robustness(args.parquet_path, args.report_dir, args.model_dir)


if __name__ == "__main__":
    main()