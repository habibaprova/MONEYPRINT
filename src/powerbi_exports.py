"""Create Power BI exports from saved MONEYPRINT reports and the frozen Phase 4 model.

No estimator is fitted in this module. Investigation scores come from the saved
Phase 4 plus_balance bundle and are limited to its previously accessed later period.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .runtime_config import RUNTIME_CONFIG

import duckdb
import joblib
import numpy as np
import pandas as pd

from .features import ROOT


EXPORT_DIR = ROOT / "powerbi" / "exports"
PARQUET_PATH = ROOT / "data" / "processed" / "transaction_features.parquet"
MODEL_PATH = ROOT / "models" / "phase4_walkforward_v1_final_model.joblib"
PROTOCOL_PATH = ROOT / "models" / "phase4_walkforward_v1_protocol.json"
PHASE4_REPORT_PATH = ROOT / "reports" / "phase4_walkforward_v1.json"
PHASE3_REPORT_PATH = ROOT / "reports" / "phase3_evaluation.json"
ROBUSTNESS_REPORT_PATH = ROOT / "reports" / "phase3_robustness.json"
PROTOCOL_VERSION = "phase4_walkforward_v1"
MODEL_ID = "phase4_walkforward_v1_plus_balance"
MODEL_DISPLAY = "Phase 4 Plus-Balance Logistic Regression"
EVALUATION_START_STEP = 632
EVALUATION_END_STEP = 743
EXAMPLE_CAP = 500
ELIGIBLE_TYPES = ("TRANSFER", "CASH_OUT")

EXPORT_FILENAMES = (
    "executive_kpi_summary.csv",
    "transaction_type_overview.csv",
    "transaction_amount_distribution.csv",
    "transaction_trends_by_step.csv",
    "transaction_trends_by_hour.csv",
    "fraud_by_transaction_type.csv",
    "phase4_walkforward_fold_metrics.csv",
    "phase4_model_feature_ablation.csv",
    "phase4_investigation_capacity.csv",
    "phase4_selected_model_investigation_examples.csv",
    "split_distribution_comparison.csv",
    "dim_transaction_type.csv",
    "dim_simulated_hour.csv",
    "dim_simulated_step.csv",
    "dim_evaluation_window.csv",
    "dim_model_method.csv",
)


def _path_literal(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(name: str, frame: pd.DataFrame, output_dir: Path) -> Path:
    path = output_dir / name
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    return path


def _friendly_feature_name(name: str) -> str:
    replacements = (
        ("numeric__sender_balance_covers_amount", "sender starting balance covers amount"),
        ("numeric__amount_to_sender_pre_balance", "amount / sender starting balance"),
        ("numeric__sender_pre_balance", "sender starting balance"),
        ("numeric__amount", "transaction amount"),
        ("categorical__transaction_type_", "transaction type = "),
        ("categorical__simulated_hour_", "simulated hour = "),
    )
    for prefix, label in replacements:
        if name.startswith(prefix):
            return label + name[len(prefix):]
    if name.startswith("numeric__"):
        return name.removeprefix("numeric__").replace("_", " ")
    return name.replace("_", " ")


def _score_case_examples(
    connection: duckdb.DuckDBPyConnection,
    bundle: dict[str, Any],
) -> pd.DataFrame:
    if bundle.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("Frozen model protocol does not match Phase 4 v1")
    if bundle.get("feature_set") != "plus_balance" or bundle.get("fit_steps") != [1, 631]:
        raise ValueError("Model must be the saved plus_balance model trained on steps 1-631")

    model = bundle["model"]
    input_columns = list(model.named_steps["preprocessor"].feature_names_in_)
    cases = connection.execute(
        "SELECT split_step, transaction_type, amount, simulated_hour, "
        "sender_pre_balance, amount_to_sender_pre_balance, "
        "sender_balance_covers_amount, label_is_fraud "
        "FROM phase4_features WHERE split_step BETWEEN ? AND ? "
        "AND transaction_type IN (?, ?) "
        "ORDER BY split_step, transaction_type, amount, sender_pre_balance",
        [EVALUATION_START_STEP, EVALUATION_END_STEP, *ELIGIBLE_TYPES],
    ).fetch_df()
    cases["transaction_type"] = cases["transaction_type"].astype("string")
    cases["simulated_hour"] = cases["simulated_hour"].astype("string")
    for column in (
        "amount",
        "sender_pre_balance",
        "amount_to_sender_pre_balance",
        "sender_balance_covers_amount",
    ):
        cases[column] = pd.to_numeric(cases[column], errors="raise").astype(np.float32)

    feature_frame = cases[input_columns]
    scores = model.predict_proba(feature_frame)[:, 1].astype(np.float64)
    if len(scores) != len(cases) or not np.isfinite(scores).all():
        raise AssertionError("Frozen-model scores failed row reconciliation")

    preprocessor = model.named_steps["preprocessor"]
    coefficient = model.named_steps["logistic"].coef_[0]
    transformed = preprocessor.transform(feature_frame)
    contributions = transformed.multiply(coefficient).tocsr() if hasattr(transformed, "multiply") else np.asarray(transformed) * coefficient
    feature_names = preprocessor.get_feature_names_out()
    selected_order = np.lexsort((np.arange(len(scores), dtype=np.int64), -scores))[:EXAMPLE_CAP]

    output = []
    for rank, position in enumerate(selected_order, start=1):
        if hasattr(contributions, "getrow"):
            sparse_row = contributions.getrow(int(position))
            indexes, impacts = sparse_row.indices, sparse_row.data
        else:
            dense_row = contributions[int(position)]
            indexes = np.flatnonzero(dense_row)
            impacts = dense_row[indexes]
        top_positions = sorted(
            range(len(indexes)), key=lambda i: abs(float(impacts[i])), reverse=True
        )[:3]
        drivers = [
            {
                "input": _friendly_feature_name(str(feature_names[indexes[i]])),
                "standardized_log_odds_contribution": round(float(impacts[i]), 4),
            }
            for i in top_positions
        ]
        case = cases.iloc[int(position)]
        ratio = case["amount_to_sender_pre_balance"]
        output.append(
            {
                "case_rank": rank,
                "protocol_version": PROTOCOL_VERSION,
                "model_id": MODEL_ID,
                "method": "logistic_plus_balance_balanced",
                "model_display_name": MODEL_DISPLAY,
                "score_source": "predict_proba from saved model; no fitting",
                "evaluation_window": "reserved_final_exploratory",
                "evaluation_status": "previously accessed exploratory period; not pristine",
                "split_step": int(case["split_step"]),
                "simulated_hour": int(case["simulated_hour"]),
                "transaction_type": str(case["transaction_type"]),
                "synthetic_amount": float(case["amount"]),
                "sender_pre_balance": float(case["sender_pre_balance"]),
                "amount_to_sender_pre_balance": None if pd.isna(ratio) else float(ratio),
                "sender_balance_covers_amount": bool(case["sender_balance_covers_amount"]),
                "risk_score": float(scores[int(position)]),
                "top_model_contributions": json.dumps(drivers, separators=(",", ":")),
                "explanation_caveat": "Model contribution is associational, not causal or a calibrated probability explanation",
                "label_for_retrospective_review": int(case["label_is_fraud"]),
                "population_warning": "Top-ranked eligible cases only; not representative and not for estimating prevalence",
            }
        )
    return pd.DataFrame(output)


def _append_capacity_rows(
    output: list[dict[str, Any]],
    source: dict[str, Any],
    window: str,
    evaluation_status: str,
) -> None:
    for budget, suffix in ((100, "100"), (500, "500")):
        output.append(
            {
                "protocol_version": PROTOCOL_VERSION,
                "model_id": MODEL_ID,
                "method": "logistic_plus_balance_balanced",
                "model_display_name": MODEL_DISPLAY,
                "evaluation_window": window,
                "evaluation_status": evaluation_status,
                "population": "TRANSFER/CASH_OUT",
                "transaction_count": source["transaction_count"],
                "fraud_count": source["fraud_count"],
                "fraud_prevalence": source["fraud_prevalence"],
                "capacity_measure": f"top_{budget}",
                "alert_count": source[f"alerts_at_{suffix}"],
                "true_positives": source[f"true_positives_at_{suffix}"],
                "false_positives": source[f"false_positives_at_{suffix}"],
                "precision": source[f"precision_at_{suffix}"],
                "recall": source[f"recall_at_{suffix}"],
                "pr_auc_average_precision": source["pr_auc_average_precision"],
                "roc_auc": source["roc_auc"],
                "source_provenance": "saved Phase 4 v1 JSON metrics",
            }
        )
    output.append(
        {
            "protocol_version": PROTOCOL_VERSION,
            "model_id": MODEL_ID,
            "method": "logistic_plus_balance_balanced",
            "model_display_name": MODEL_DISPLAY,
            "evaluation_window": window,
            "evaluation_status": evaluation_status,
            "population": "TRANSFER/CASH_OUT",
            "transaction_count": source["transaction_count"],
            "fraud_count": source["fraud_count"],
            "fraud_prevalence": source["fraud_prevalence"],
            "capacity_measure": "fixed_alert_rate_0_5pct",
            "alert_count": source["alerts_at_fixed_rate"],
            "true_positives": source["true_positives_at_fixed_rate"],
            "false_positives": source["false_positives_at_fixed_rate"],
            "precision": source["precision_at_fixed_rate"],
            "recall": source["recall_at_fixed_rate"],
            "pr_auc_average_precision": source["pr_auc_average_precision"],
            "roc_auc": source["roc_auc"],
            "source_provenance": "saved Phase 4 v1 JSON metrics",
        }
    )


def _split_comparison(
    phase3_report: dict[str, Any], robustness_report: dict[str, Any]
) -> pd.DataFrame:
    total_fraud = sum(int(row["fraud_count"]) for row in phase3_report["split_audit"]["split_summary"])
    specifications = (
        (
            "phase3_original_step_split",
            phase3_report["split_audit"]["split_summary"],
            phase3_report["split_audit"]["type_mix_and_amounts"],
            "reports/phase3_evaluation.json; distribution only, no Phase 3 model metrics",
        ),
        (
            "phase3_alternative_cumulative_row_split",
            robustness_report["alternative_split_audit"]["split_summary"],
            robustness_report["alternative_split_audit"]["type_mix_and_amounts"],
            "reports/phase3_robustness.json; secondary exploratory distribution only",
        ),
    )
    rows = []
    for protocol, split_summaries, type_summaries, provenance in specifications:
        total_rows = sum(int(item.get("transaction_count", item.get("transactions"))) for item in split_summaries)
        by_split = {item["split"]: item for item in split_summaries}
        original_bounds = {
            "train": (1, 520),
            "validation": (521, 631),
            "test": (632, 743),
        }
        for split, summary in by_split.items():
            count = int(summary.get("transaction_count", summary.get("transactions")))
            fraud_count = int(summary["fraud_count"])
            start, end = (
                (int(summary["min_step"]), int(summary["max_step"]))
                if "min_step" in summary
                else original_bounds[split]
            )
            step_count = int(summary.get("distinct_steps", end - start + 1))
            rows.append(
                {
                    "split_protocol": protocol,
                    "split": split,
                    "transaction_type": "ALL",
                    "step_start": start,
                    "step_end": end,
                    "step_count": step_count,
                    "transaction_count": count,
                    "transaction_share": count / total_rows,
                    "fraud_count": fraud_count,
                    "fraud_label_prevalence": fraud_count / count,
                    "share_of_all_fraud_labels": fraud_count / total_fraud,
                    "mean_synthetic_amount": float(summary["mean_amount"]),
                    "median_synthetic_amount": float(summary["median_amount"]),
                    "p95_synthetic_amount": float(summary["p95_amount"]),
                    "source_provenance": provenance,
                }
            )
        for item in type_summaries:
            summary = by_split[item["split"]]
            count = int(item["transaction_count"])
            fraud_count = int(item["fraud_count"])
            split_total = int(summary.get("transaction_count", summary.get("transactions")))
            rows.append(
                {
                    "split_protocol": protocol,
                    "split": item["split"],
                    "transaction_type": item["transaction_type"],
                    "step_start": int(summary.get("min_step", original_bounds[item["split"]][0])),
                    "step_end": int(summary.get("max_step", original_bounds[item["split"]][1])),
                    "step_count": int(summary.get("distinct_steps", original_bounds[item["split"]][1] - original_bounds[item["split"]][0] + 1)),
                    "transaction_count": count,
                    "transaction_share": float(item.get("transaction_share", count / split_total)),
                    "fraud_count": fraud_count,
                    "fraud_label_prevalence": fraud_count / count,
                    "share_of_all_fraud_labels": fraud_count / total_fraud,
                    "mean_synthetic_amount": float(item["mean_amount"]),
                    "median_synthetic_amount": float(item["median_amount"]),
                    "p95_synthetic_amount": float(item["p95_amount"]),
                    "source_provenance": provenance,
                }
            )
    return pd.DataFrame(rows)


def _build_frames() -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    required = (
        PARQUET_PATH,
        MODEL_PATH,
        PROTOCOL_PATH,
        PHASE4_REPORT_PATH,
        PHASE3_REPORT_PATH,
        ROBUSTNESS_REPORT_PATH,
    )
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"Required saved Phase 4/EDA input missing: {path}")

    phase4 = json.loads(PHASE4_REPORT_PATH.read_text(encoding="utf-8"))
    phase3 = json.loads(PHASE3_REPORT_PATH.read_text(encoding="utf-8"))
    robustness = json.loads(ROBUSTNESS_REPORT_PATH.read_text(encoding="utf-8"))
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    bundle = joblib.load(MODEL_PATH)
    if protocol["protocol_version"] != PROTOCOL_VERSION:
        raise ValueError("Unexpected Phase 4 protocol version")
    if bundle["protocol_version"] != PROTOCOL_VERSION or bundle["feature_set"] != "plus_balance":
        raise ValueError("Frozen model must be the selected Phase 4 plus_balance bundle")
    if bundle["fit_steps"] != [1, 631]:
        raise ValueError("Frozen Phase 4 model training boundary differs from protocol")
    if bundle["selection"]["feature_set"] != "plus_balance":
        raise ValueError("Saved model selection manifest does not identify plus_balance")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    try:
        parquet = _path_literal(PARQUET_PATH)
        connection.execute(
            "CREATE TEMP VIEW phase4_features AS "
            f"SELECT * FROM read_parquet('{parquet}')"
        )

        type_overview = connection.execute(
            "SELECT transaction_type, COUNT(*) AS transaction_count, "
            "SUM(amount) AS total_synthetic_amount, AVG(amount) AS mean_synthetic_amount, "
            "quantile_cont(amount, 0.5) AS median_synthetic_amount, "
            "quantile_cont(amount, 0.95) AS p95_synthetic_amount, "
            "COUNT(*) FILTER(WHERE label_is_fraud=1) AS fraud_count, "
            "COUNT(*) FILTER(WHERE label_is_fraud=1)::DOUBLE/COUNT(*) AS fraud_label_prevalence "
            "FROM phase4_features GROUP BY transaction_type ORDER BY transaction_type"
        ).fetchdf()
        type_overview["data_scope"] = "full_dataset_population"
        type_overview["source_provenance"] = "data/processed/transaction_features.parquet"

        fraud_by_type = type_overview[
            ["transaction_type", "transaction_count", "fraud_count", "fraud_label_prevalence", "data_scope", "source_provenance"]
        ].copy()
        fraud_by_type["label_definition"] = "Synthetic PaySim isFraud target; not a real-world adjudicated outcome"

        total_transactions = int(type_overview["transaction_count"].sum())
        total_fraud_labels = int(type_overview["fraud_count"].sum())
        total_synthetic_value = float(type_overview["total_synthetic_amount"].sum())
        executive_kpis = pd.DataFrame(
            [
                {"metric_key": "total_transactions", "metric_label": "Total transactions", "metric_value": total_transactions, "unit": "records", "data_scope": "full_dataset_population", "source_provenance": "transaction_features.parquet"},
                {"metric_key": "fraud_labels", "metric_label": "Fraud labels", "metric_value": total_fraud_labels, "unit": "synthetic labeled records", "data_scope": "full_dataset_population", "source_provenance": "transaction_features.parquet"},
                {"metric_key": "fraud_label_prevalence", "metric_label": "Fraud-label prevalence", "metric_value": total_fraud_labels / total_transactions, "unit": "proportion", "data_scope": "full_dataset_population", "source_provenance": "transaction_features.parquet"},
                {"metric_key": "total_synthetic_amount", "metric_label": "Total transaction value", "metric_value": total_synthetic_value, "unit": "synthetic amount units; currency unspecified", "data_scope": "full_dataset_population", "source_provenance": "transaction_features.parquet"},
            ]
        )

        amount_distribution = connection.execute(
            "SELECT transaction_type, "
            "CASE WHEN amount < 1000 THEN '01 <1K' "
            "WHEN amount < 10000 THEN '02 1K-<10K' "
            "WHEN amount < 100000 THEN '03 10K-<100K' "
            "WHEN amount < 500000 THEN '04 100K-<500K' "
            "WHEN amount < 1000000 THEN '05 500K-<1M' "
            "WHEN amount < 5000000 THEN '06 1M-<5M' "
            "WHEN amount < 10000000 THEN '07 5M-<10M' ELSE '08 10M+' END AS amount_band, "
            "COUNT(*) AS transaction_count, SUM(amount) AS total_synthetic_amount, "
            "COUNT(*) FILTER(WHERE label_is_fraud=1) AS fraud_count "
            "FROM phase4_features GROUP BY transaction_type, amount_band "
            "ORDER BY transaction_type, amount_band"
        ).fetchdf()
        amount_distribution["transaction_share_within_type"] = amount_distribution.apply(
            lambda row: row["transaction_count"] / int(type_overview.loc[
                type_overview["transaction_type"] == row["transaction_type"], "transaction_count"
            ].iloc[0]),
            axis=1,
        )
        amount_distribution["source_provenance"] = "Full-population binned amount distribution; synthetic units"

        step_trends = connection.execute(
            "SELECT split_step AS simulated_step, simulated_hour, transaction_type, "
            "COUNT(*) AS transaction_count, SUM(amount) AS total_synthetic_amount, "
            "AVG(amount) AS mean_synthetic_amount, "
            "COUNT(*) FILTER(WHERE label_is_fraud=1) AS fraud_count, "
            "COUNT(*) FILTER(WHERE label_is_fraud=1)::DOUBLE/COUNT(*) AS fraud_label_prevalence "
            "FROM phase4_features GROUP BY split_step, simulated_hour, transaction_type "
            "ORDER BY split_step, transaction_type"
        ).fetchdf()
        step_trends["original_phase3_split"] = np.select(
            [step_trends["simulated_step"] <= 520, step_trends["simulated_step"] <= 631],
            ["train", "validation"],
            default="test",
        )
        step_trends["phase4_role"] = np.select(
            [
                step_trends["simulated_step"].between(251, 350),
                step_trends["simulated_step"].between(351, 450),
                step_trends["simulated_step"].between(451, 540),
                step_trends["simulated_step"].between(541, 631),
                step_trends["simulated_step"].between(632, 743),
            ],
            ["fold_1_validation", "fold_2_validation", "fold_3_validation", "fold_4_validation", "reserved_final_exploratory"],
            default="walk_forward_training_history",
        )
        step_trends["source_provenance"] = "Full-population descriptive aggregate from transaction_features.parquet"
        step_trends["time_interpretation"] = "Simulated step and step-modulo-24 hour; not wall-clock time"

        hour_trends = connection.execute(
            "SELECT simulated_hour, transaction_type, COUNT(*) AS transaction_count, "
            "SUM(amount) AS total_synthetic_amount, AVG(amount) AS mean_synthetic_amount, "
            "COUNT(*) FILTER(WHERE label_is_fraud=1) AS fraud_count, "
            "COUNT(*) FILTER(WHERE label_is_fraud=1)::DOUBLE/COUNT(*) AS fraud_label_prevalence "
            "FROM phase4_features GROUP BY simulated_hour, transaction_type "
            "ORDER BY simulated_hour, transaction_type"
        ).fetchdf()
        hour_trends["source_provenance"] = "Full-population descriptive aggregate from transaction_features.parquet"
        hour_trends["time_interpretation"] = "step modulo 24; simulated-hour index, not clock time"

        step_dimension = connection.execute(
            "SELECT DISTINCT split_step AS simulated_step, simulated_hour "
            "FROM phase4_features ORDER BY simulated_step"
        ).fetchdf()
        step_dimension["original_phase3_split"] = np.select(
            [step_dimension["simulated_step"] <= 520, step_dimension["simulated_step"] <= 631],
            ["train", "validation"],
            default="test",
        )
        step_dimension["phase4_role"] = np.select(
            [
                step_dimension["simulated_step"].between(251, 350),
                step_dimension["simulated_step"].between(351, 450),
                step_dimension["simulated_step"].between(451, 540),
                step_dimension["simulated_step"].between(541, 631),
                step_dimension["simulated_step"].between(632, 743),
            ],
            ["fold_1_validation", "fold_2_validation", "fold_3_validation", "fold_4_validation", "reserved_final_exploratory"],
            default="walk_forward_training_history",
        )
        type_dimension = pd.DataFrame(
            {
                "transaction_type": ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"],
                "type_sort": [1, 2, 3, 4, 5],
            }
        )
        hour_dimension = pd.DataFrame(
            {
                "simulated_hour": list(range(24)),
                "hour_label": [f"Simulated hour {hour:02d}" for hour in range(24)],
                "time_basis": "step modulo 24; not a wall-clock timestamp",
            }
        )
        window_rows = [
            {
                "evaluation_window": fold["fold"],
                "window_type": "walk_forward_validation",
                "train_start_step": fold["train_start"],
                "train_end_step": fold["train_end"],
                "evaluation_start_step": fold["validation_start"],
                "evaluation_end_step": fold["validation_end"],
                "evidence_status": "Walk-forward validation; fold-local training",
            }
            for fold in phase4["fold_plan"]
        ]
        window_rows.append(
            {
                "evaluation_window": "reserved_final_exploratory",
                "window_type": "previously_accessed_later_period",
                "train_start_step": 1,
                "train_end_step": 631,
                "evaluation_start_step": 632,
                "evaluation_end_step": 743,
                "evidence_status": "Exploratory, previously accessed; not pristine",
            }
        )
        window_dimension = pd.DataFrame(window_rows)

        feature_labels = {
            "amount_type": "Amount + transaction type",
            "plus_hour": "Amount + type + simulated hour",
            "plus_balance": "Amount + type + hour + sender pre-balance features (selected)",
            "full_context": "Plus-balance + strictly historical recipient features",
        }
        validation_rows = list(phase4["validation_metrics"])
        fold_metrics = pd.DataFrame(validation_rows)
        fold_metrics["protocol_version"] = PROTOCOL_VERSION
        fold_metrics["model_id"] = np.where(
            fold_metrics["method"].eq("logistic_plus_balance_balanced"),
            MODEL_ID,
            PROTOCOL_VERSION + "_" + fold_metrics["method"].astype(str),
        )
        fold_metrics["feature_configuration"] = fold_metrics["feature_set"].map(feature_labels).fillna(fold_metrics["method"])
        fold_metrics["is_selected_phase4_model"] = fold_metrics["method"].eq("logistic_plus_balance_balanced")
        fold_metrics["result_status"] = "walk_forward_validation"
        fold_metrics["source_provenance"] = "Saved reports/phase4_walkforward_v1.json; not Phase 3 model performance"

        ablation_rows = []
        for feature_set, summary in phase4["fold_stability"].items():
            for fold in phase4["fold_plan"]:
                metric = next(
                    row for row in validation_rows
                    if row["fold"] == fold["fold"]
                    and row["feature_set"] == feature_set
                    and row["population"] == "transfer_cash_out"
                    and row["method"].startswith("logistic_")
                )
                ablation_rows.append(
                    {
                        "protocol_version": PROTOCOL_VERSION,
                        "feature_set": feature_set,
                        "feature_configuration": feature_labels[feature_set],
                        "fold": fold["fold"],
                        "validation_prevalence": metric["fraud_prevalence"],
                        "pr_auc_average_precision": metric["pr_auc_average_precision"],
                        "roc_auc": metric["roc_auc"],
                        "precision_at_100": metric["precision_at_100"],
                        "recall_at_100": metric["recall_at_100"],
                        "precision_at_500": metric["precision_at_500"],
                        "recall_at_500": metric["recall_at_500"],
                        "mean_fold_validation_pr_auc": summary["mean_validation_pr_auc"],
                        "sd_fold_validation_pr_auc": summary["sd_validation_pr_auc"],
                        "mean_fold_validation_roc_auc": summary["mean_validation_roc_auc"],
                        "mean_train_pr_auc_in_sample": summary["mean_train_pr_auc"],
                        "is_selected_phase4_model": feature_set == "plus_balance",
                        "source_provenance": "Phase 4 walk-forward validation only",
                    }
                )
        ablation_frame = pd.DataFrame(ablation_rows)

        capacity_rows = []
        selected_method = "logistic_plus_balance_balanced"
        for row in validation_rows:
            if row["method"] == selected_method and row["population"] == "transfer_cash_out":
                _append_capacity_rows(capacity_rows, row, row["fold"], "walk_forward_validation")
        for row in phase4["reserved_period_metrics"]:
            if row["method"] == selected_method and row["population"] == "transfer_cash_out":
                _append_capacity_rows(
                    capacity_rows,
                    row,
                    "reserved_final_exploratory",
                    "previously_accessed_exploratory_later_period",
                )
        capacity_frame = pd.DataFrame(capacity_rows)

        examples = _score_case_examples(connection, bundle)
        split_comparison = _split_comparison(phase3, robustness)
        methods = sorted(fold_metrics["method"].unique().tolist())
        method_dimension = pd.DataFrame(
            [
                {
                    "method": method,
                    "display_name": MODEL_DISPLAY if method == selected_method else str(method),
                    "feature_set": str(fold_metrics.loc[fold_metrics["method"] == method, "feature_set"].iloc[0]),
                    "is_selected_phase4_model": method == selected_method,
                    "protocol_version": PROTOCOL_VERSION,
                    "performance_source": "Phase 4 walk-forward validation only",
                }
                for method in methods
            ]
        )

        frames = {
            "executive_kpi_summary.csv": executive_kpis,
            "transaction_type_overview.csv": type_overview,
            "transaction_amount_distribution.csv": amount_distribution,
            "transaction_trends_by_step.csv": step_trends,
            "transaction_trends_by_hour.csv": hour_trends,
            "fraud_by_transaction_type.csv": fraud_by_type,
            "phase4_walkforward_fold_metrics.csv": fold_metrics,
            "phase4_model_feature_ablation.csv": ablation_frame,
            "phase4_investigation_capacity.csv": capacity_frame,
            "phase4_selected_model_investigation_examples.csv": examples,
            "split_distribution_comparison.csv": split_comparison,
            "dim_transaction_type.csv": type_dimension,
            "dim_simulated_hour.csv": hour_dimension,
            "dim_simulated_step.csv": step_dimension,
            "dim_evaluation_window.csv": window_dimension,
            "dim_model_method.csv": method_dimension,
        }
        export_counts = _validate_frames(frames, phase4, phase3)
        manifest = {
            "protocol_version": PROTOCOL_VERSION,
            "selected_model_id": MODEL_ID,
            "selected_feature_set": "plus_balance",
            "training_steps": [1, 631],
            "reserved_evaluation_steps": [632, 743],
            "reserved_period_status": "exploratory and previously accessed; not pristine",
            "score_generation": "frozen joblib model predict_proba only; no fit or retraining",
            "scored_investigation_population_rows": int(
                connection.execute(
                    "SELECT COUNT(*) FROM phase4_features WHERE split_step BETWEEN 632 AND 743 AND transaction_type IN ('TRANSFER','CASH_OUT')"
                ).fetchone()[0]
            ),
            "source_model": str(MODEL_PATH),
            "source_model_sha256": _sha256(MODEL_PATH),
            "source_phase4_report": str(PHASE4_REPORT_PATH),
            "source_phase4_report_sha256": _sha256(PHASE4_REPORT_PATH),
            "source_feature_parquet": str(PARQUET_PATH),
            "source_parquet_sha256": phase4["source_parquet_sha256"],
            "validation": export_counts,
            "sample_warning": "Investigation examples are top-ranked cases, not representative population data; do not estimate prevalence from them.",
            "runtime_thread_plan": RUNTIME_CONFIG,
            "files": {},
        }
        return frames, manifest
    finally:
        connection.close()


def _validate_frames(
    frames: dict[str, pd.DataFrame],
    phase4: dict[str, Any],
    phase3: dict[str, Any],
) -> dict[str, Any]:
    overview = frames["transaction_type_overview.csv"]
    executive = frames["executive_kpi_summary.csv"]
    amount_distribution = frames["transaction_amount_distribution.csv"]
    fraud = frames["fraud_by_transaction_type.csv"]
    step_trends = frames["transaction_trends_by_step.csv"]
    hour_trends = frames["transaction_trends_by_hour.csv"]
    fold_metrics = frames["phase4_walkforward_fold_metrics.csv"]
    ablation = frames["phase4_model_feature_ablation.csv"]
    capacity = frames["phase4_investigation_capacity.csv"]
    examples = frames["phase4_selected_model_investigation_examples.csv"]
    splits = frames["split_distribution_comparison.csv"]

    phase3_splits = phase3["split_audit"]["split_summary"]
    expected_transactions = sum(int(row["transaction_count"]) for row in phase3_splits)
    expected_fraud = sum(int(row["fraud_count"]) for row in phase3_splits)
    if int(overview["transaction_count"].sum()) != expected_transactions:
        raise AssertionError("Transaction type overview total does not reconcile to Phase 1/2 audit")
    if int(overview["fraud_count"].sum()) != expected_fraud:
        raise AssertionError("Overview fraud labels do not reconcile to saved audit")
    executive_values = dict(zip(executive["metric_key"], executive["metric_value"], strict=True))
    if int(executive_values["total_transactions"]) != expected_transactions:
        raise AssertionError("Executive KPI transaction count does not reconcile")
    if int(executive_values["fraud_labels"]) != expected_fraud:
        raise AssertionError("Executive KPI fraud labels do not reconcile")
    if int(amount_distribution["transaction_count"].sum()) != expected_transactions:
        raise AssertionError("Amount distribution bins do not reconcile to population rows")
    if int(fraud["transaction_count"].sum()) != expected_transactions or int(fraud["fraud_count"].sum()) != expected_fraud:
        raise AssertionError("Fraud-by-type totals do not reconcile")
    if int(step_trends["transaction_count"].sum()) != expected_transactions:
        raise AssertionError("Step trend total does not reconcile")
    if int(hour_trends["transaction_count"].sum()) != expected_transactions:
        raise AssertionError("Hour trend total does not reconcile")
    if len(frames["dim_simulated_step.csv"]) != 743:
        raise AssertionError("Simulated step dimension does not cover all 743 steps")

    selected_report_rows = [
        row for row in phase4["validation_metrics"]
        if row["method"] == "logistic_plus_balance_balanced"
    ]
    selected_export_rows = fold_metrics.loc[fold_metrics["is_selected_phase4_model"]]
    if len(selected_report_rows) != len(selected_export_rows):
        raise AssertionError("Selected-model fold metric row count mismatch")
    report_index = {
        (row["fold"], row["population"]): row for row in selected_report_rows
    }
    for row in selected_export_rows.itertuples(index=False):
        saved = report_index[(row.fold, row.population)]
        for column in ("roc_auc", "pr_auc_average_precision", "precision_at_500", "recall_at_500"):
            if not np.isclose(getattr(row, column), saved[column], atol=1e-12):
                raise AssertionError(f"Exported selected-model metric mismatch for {row.fold}/{column}")
    if set(fold_metrics["protocol_version"].unique()) != {PROTOCOL_VERSION}:
        raise AssertionError("Fold metrics contain an unexpected protocol version")
    if set(selected_export_rows["model_id"].unique()) != {MODEL_ID}:
        raise AssertionError("Selected fold metrics have incorrect model identity")
    if len(ablation) != 16:
        raise AssertionError("Expected 4 selected-protocol feature sets by 4 validation folds")
    if set(capacity["model_id"].unique()) != {MODEL_ID}:
        raise AssertionError("Investigation capacity table mixes model identities")
    if len(examples) > EXAMPLE_CAP:
        raise AssertionError("Investigation examples exceed cap")
    if len(examples) and (
        not examples["split_step"].between(EVALUATION_START_STEP, EVALUATION_END_STEP).all()
        or not examples["transaction_type"].isin(ELIGIBLE_TYPES).all()
        or not examples["risk_score"].is_monotonic_decreasing
        or examples["model_id"].nunique() != 1
        or examples["model_id"].iloc[0] != MODEL_ID
    ):
        raise AssertionError("Selected model examples failed period, ordering, or provenance checks")
    expected_later_capacity = next(
        row
        for row in phase4["reserved_period_metrics"]
        if row["method"] == "logistic_plus_balance_balanced"
        and row["population"] == "transfer_cash_out"
    )
    expected_later_tp_at_500 = int(expected_later_capacity["true_positives_at_500"])
    exported_tp_at_500 = int(examples["label_for_retrospective_review"].sum())
    if len(examples) != int(expected_later_capacity["alerts_at_500"]):
        raise AssertionError("Investigation example count differs from saved Phase 4 K=500 count")
    if exported_tp_at_500 != expected_later_tp_at_500:
        raise AssertionError("Frozen-model investigation labels do not match saved Phase 4 top-500 outcome")
    if any(column in examples.columns for column in ("nameOrig", "nameDest", "isFraud", "isFlaggedFraud")):
        raise AssertionError("Investigation export contains a forbidden identifier/target predictor column")

    for protocol_name in (
        "phase3_original_step_split",
        "phase3_alternative_cumulative_row_split",
    ):
        protocol_rows = splits.loc[splits["split_protocol"] == protocol_name]
        all_rows = protocol_rows.loc[protocol_rows["transaction_type"] == "ALL"]
        if int(all_rows["transaction_count"].sum()) != expected_transactions:
            raise AssertionError(f"Split comparison totals failed for {protocol_name}")
        by_split = protocol_rows.loc[protocol_rows["transaction_type"] != "ALL"].groupby("split")["transaction_count"].sum()
        all_by_split = all_rows.set_index("split")["transaction_count"]
        if by_split.sort_index().to_dict() != all_by_split.sort_index().to_dict():
            raise AssertionError(f"Split/type mix failed to reconcile for {protocol_name}")

    return {
        "transactions": expected_transactions,
        "fraud_labels": expected_fraud,
        "executive_kpis": int(len(executive)),
        "amount_distribution_bins": int(len(amount_distribution)),
        "step_trend_transactions": int(step_trends["transaction_count"].sum()),
        "hour_trend_transactions": int(hour_trends["transaction_count"].sum()),
        "phase4_fold_metric_rows": int(len(fold_metrics)),
        "selected_model_fold_metric_rows": int(len(selected_export_rows)),
        "feature_ablation_rows": int(len(ablation)),
        "capacity_rows": int(len(capacity)),
        "selected_model_example_rows": int(len(examples)),
        "selected_model_example_cap": EXAMPLE_CAP,
        "selected_model_examples_true_positives_at_500": exported_tp_at_500,
        "split_protocols_checked": 2,
        "all_checks_passed": True,
    }


def export_powerbi(output_dir: Path = EXPORT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frames, manifest = _build_frames()
    for filename in EXPORT_FILENAMES:
        if filename not in frames:
            raise AssertionError(f"Expected export missing: {filename}")
        path = _write_csv(filename, frames[filename], output_dir)
        manifest["files"][filename] = {
            "path": str(path),
            "rows": int(len(frames[filename])),
            "bytes": int(path.stat().st_size),
        }
    manifest_path = output_dir / "export_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest["validation"], indent=2))
    print(f"Wrote {len(EXPORT_FILENAMES)} CSVs and {manifest_path.name} to {output_dir}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=EXPORT_DIR)
    args = parser.parse_args()
    export_powerbi(args.output_dir)


if __name__ == "__main__":
    main()