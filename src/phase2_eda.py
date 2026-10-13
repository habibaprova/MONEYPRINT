"""Run Phase 2 exploratory summaries and chronology-safe feature preparation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb

from .features import ROOT, build_candidate_parquet, execute_sql_file, register_transactions


DEFAULT_CSV = ROOT / "data" / "raw" / "PS_20174392719_1491204439457_log.csv"
DEFAULT_PARQUET = ROOT / "data" / "processed" / "transaction_features.parquet"
DEFAULT_REPORT_DIR = ROOT / "reports"
EDA_SQL = ROOT / "sql" / "phase2_eda.sql"


def fetch_dicts(connection: duckdb.DuckDBPyConnection, query: str) -> list[dict[str, Any]]:
    cursor = connection.execute(query)
    names = [description[0] for description in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def run_phase2(csv_path: Path, parquet_path: Path, report_dir: Path) -> dict[str, Any]:
    connection = duckdb.connect()
    try:
        connection.execute("SET memory_limit = '1GB'")
        register_transactions(connection, csv_path)
        execute_sql_file(connection, EDA_SQL)

        summary = {
            "dataset": csv_path.name,
            "source_schema": [
                {"name": row[0], "type": row[1]}
                for row in connection.execute("DESCRIBE transactions").fetchall()
            ],
            "transaction_summary_by_type": fetch_dicts(
                connection, "SELECT * FROM type_summary ORDER BY transaction_type"
            ),
            "fraud_amount_comparison": fetch_dicts(
                connection,
                "SELECT * FROM fraud_amount_comparison "
                "ORDER BY transaction_type, is_fraud",
            ),
            "hourly_step_trends": fetch_dicts(
                connection, "SELECT * FROM hourly_trends ORDER BY simulated_hour"
            ),
            "receiver_concentration": fetch_dicts(
                connection, "SELECT * FROM receiver_concentration"
            )[0],
            "account_frequency_summary": fetch_dicts(
                connection, "SELECT * FROM account_frequency_summary ORDER BY account_role"
            ),
            "account_frequency_bins": fetch_dicts(
                connection,
                "SELECT * FROM account_frequency_bins "
                "ORDER BY account_role, CASE frequency_bin "
                "WHEN '1' THEN 1 WHEN '2' THEN 2 WHEN '3-5' THEN 3 "
                "WHEN '6-10' THEN 4 WHEN '11-25' THEN 5 ELSE 6 END",
            ),
            "sender_balance_by_type": fetch_dicts(
                connection, "SELECT * FROM sender_balance_by_type ORDER BY transaction_type"
            ),
            "receiver_balance_by_type": fetch_dicts(
                connection,
                "SELECT * FROM receiver_balance_by_type "
                "ORDER BY transaction_type, receiver_prefix",
            ),
            "balance_zero_patterns": fetch_dicts(
                connection, "SELECT * FROM balance_zero_patterns ORDER BY transaction_type"
            ),
            "balance_by_label": fetch_dicts(
                connection, "SELECT * FROM balance_by_label ORDER BY transaction_type, is_fraud"
            ),
            "representative_balance_exceptions": fetch_dicts(
                connection, "SELECT * FROM balance_exceptions ORDER BY transaction_type, step"
            ),
        }

        type_total = sum(row["transaction_count"] for row in summary["transaction_summary_by_type"])
        hour_total = sum(row["transaction_count"] for row in summary["hourly_step_trends"])
        if type_total != hour_total:
            raise AssertionError("Transaction-type and simulated-hour totals do not reconcile")
        summary["total_records"] = type_total
        summary["fraud_records"] = sum(
            row["fraud_count"] for row in summary["transaction_summary_by_type"]
        )

        features = build_candidate_parquet(connection, parquet_path)
        if features["total_records"] != summary["total_records"]:
            raise AssertionError("Feature output row count does not reconcile to EDA totals")
        if features["fraud_records"] != summary["fraud_records"]:
            raise AssertionError("Feature output label count does not reconcile to EDA totals")
        summary["chronological_split"] = {
            "strategy": "contiguous ranges of distinct ascending step values; no row shuffle",
            "target_step_proportions": {"train": 0.70, "validation": 0.15, "test": 0.15},
            **features,
        }
        summary["feature_policy"] = {
            "predictors": features["predictor_columns"],
            "split_metadata": ["split_step", "split"],
            "target_only": ["label_is_fraud"],
            "excluded_from_feature_output": [
                "isFraud (renamed only as target label_is_fraud)",
                "isFlaggedFraud",
                "newbalanceOrig",
                "oldbalanceDest",
                "newbalanceDest",
                "nameOrig",
                "nameDest",
                "future-derived aggregates",
            ],
            "simulated_hour_interpretation": (
                "step modulo 24 under PaySim's hourly-step convention; this is a simulated "
                "hour index, not a wall-clock time or timezone"
            ),
            "recipient_history": (
                "prior destination transaction count and amount aggregate all transactions "
                "at recipient-step grain, then sum only strictly earlier steps; same-step "
                "transactions do not contribute to each other"
            ),
            "amount_to_sender_pre_balance": (
                "amount divided by sender pre-transaction balance; null only when the "
                "pre-transaction balance is zero"
            ),
            "sender_balance_covers_amount": (
                "pre-transaction balance >= amount; available at decision time, but may "
                "encode a PaySim simulation artifact"
            ),
        }
        summary["interpretation_limitations"] = [
            "Balance differences are descriptive diagnostics, not evidence of fraud.",
            "The signed sender equation (CASH_IN positive, other types negative) is a candidate comparison only; high deviations require simulator-specific context.",
            "The receiver account prefix and balance fields do not establish the real-world economic role of a transaction.",
            "PaySim labels fraud only in selected transaction types and its balance generation may make classification artificially easy.",
            "All test-split label summaries are descriptive; test labels were not used to design features, thresholds, or models.",
        ]
        summary["balance_comparison"] = {
            "tolerance_currency_units": 0.01,
            "method": "round absolute residuals to cents, then allow a one-cent difference",
            "sender_candidate_equation": "CASH_IN: +amount; other types: -amount",
            "interpretation": "empirical diagnostic only; not a validated accounting rule or fraud signal",
        }

        report_dir.mkdir(parents=True, exist_ok=True)
        json_path = report_dir / "phase2_eda.json"
        markdown_path = report_dir / "phase2_eda.md"
        json_path.write_text(
            json.dumps(summary, indent=2, allow_nan=False, default=str) + "\n",
            encoding="utf-8",
        )
        markdown_path.write_text(render_markdown(summary), encoding="utf-8")
        return summary
    finally:
        connection.close()


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Exploratory Analysis",
        "",
        f"- **Dataset:** `{summary['dataset']}`",
        f"- **Transactions:** {summary['total_records']:,}",
        f"- **Fraud labels:** {summary['fraud_records']:,}",
        "",
        "## Type and Amount Summary",
        "",
        "| Type | Transactions | Total amount | Mean | Median | P90 | P95 | P99 | Fraud | Fraud rate | Flagged |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {row['transaction_type']} | {row['transaction_count']:,} | "
        f"{row['total_amount']:,.2f} | {row['mean_amount']:,.2f} | "
        f"{row['median_amount']:,.2f} | {row['p90_amount']:,.2f} | "
        f"{row['p95_amount']:,.2f} | {row['p99_amount']:,.2f} | "
        f"{row['fraud_count']:,} | {row['fraud_rate']:.6%} | "
        f"{row['flagged_fraud_count']:,} |"
        for row in summary["transaction_summary_by_type"]
    )
    lines.extend(
        [
            "",
            "## Fraud and Amount: TRANSFER and CASH_OUT",
            "",
            "| Type | Fraud label | Transactions | Mean amount | Median | P95 | Max | Sender pre-balance zero | Amount > sender pre-balance |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {row['transaction_type']} | {row['is_fraud']} | {row['transaction_count']:,} | "
        f"{row['mean_amount']:,.2f} | {row['median_amount']:,.2f} | "
        f"{row['p95_amount']:,.2f} | {row['max_amount']:,.2f} | "
        f"{row['sender_pre_balance_zero']:,} | "
        f"{row['amount_exceeds_sender_pre_balance']:,} |"
        for row in summary["fraud_amount_comparison"]
    )
    lines.extend(
        [
            "",
            "## Chronological Split",
            "",
            f"Distinct steps: {summary['chronological_split']['split_step_count']:,}; "
            f"training ends at step {summary['chronological_split']['train_end_step']:,}; "
            f"validation ends at step {summary['chronological_split']['validation_end_step']:,}.",
            "",
            "| Split | Steps | Transactions | Fraud labels | Label rate |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in summary["chronological_split"]["splits"]:
        rate = row["fraud_count"] / row["transaction_count"] if row["transaction_count"] else 0.0
        lines.append(
            f"| {row['split']} | {row['distinct_steps']:,} | "
            f"{row['transaction_count']:,} | {row['fraud_count']:,} | {rate:.6%} |"
        )
    lines.extend(
        [
            "",
            "## Hourly-Step Trend",
            "",
            "`simulated_hour = step % 24`; this wraps the simulated hourly step index and is not a wall-clock hour.",
            "",
            "| Simulated hour | Transactions | Fraud labels | Fraud rate | Total amount |",
            "| ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {row['simulated_hour']} | {row['transaction_count']:,} | "
        f"{row['fraud_count']:,} | {row['fraud_rate']:.6%} | {row['total_amount']:,.2f} |"
        for row in summary["hourly_step_trends"]
    )
    concentration = summary["receiver_concentration"]
    lines.extend(
        [
            "",
            "## Receiver Concentration",
            "",
            f"Unique receivers: {concentration['unique_receivers']:,}; maximum transactions to one receiver: {concentration['max_receiver_transactions']:,}.",
            f"Top receiver share of transactions: {concentration['top_receiver_transaction_share']:.4%}; "
            f"top 10 share by transaction count: {concentration['top_10_transaction_share']:.4%}; "
            f"top 10 share of amount (ranked by count): {concentration['top_10_by_count_amount_share']:.4%}; "
            f"top 10 amount share (ranked by amount): {concentration['top_10_amount_share']:.4%}.",
            "",
            "## Repeated-Account Frequency",
            "",
            "| Role | Unique accounts | Repeated accounts | Rows in repeated accounts | Median tx/account | P90 | P99 | Max |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {row['account_role']} | {row['unique_accounts']:,} | "
        f"{row['repeated_accounts']:,} | {row['rows_in_repeated_accounts']:,} | "
        f"{row['median_transactions']:,.0f} | {row['p90_transactions']:,.0f} | "
        f"{row['p99_transactions']:,.0f} | {row['max_transactions']:,} |"
        for row in summary["account_frequency_summary"]
    )
    lines.extend(
        [
            "",
            "### Account-frequency bins",
            "",
            "| Role | Transactions/account | Accounts | Transaction rows |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {row['account_role']} | {row['frequency_bin']} | "
        f"{row['account_count']:,} | {row['transaction_rows']:,} |"
        for row in summary["account_frequency_bins"]
    )
    lines.extend(
        [
            "",
            "## Balance Investigation",
            "",
            "The signed sender comparison is only a diagnostic hypothesis: `CASH_IN` is compared with +amount and the other transaction types with -amount. Receiver deltas are classified empirically by transaction type and destination-ID prefix, without asserting a universal accounting rule. Mismatches are not fraud findings.",
            "Balance residuals are rounded to cents before applying a one-cent tolerance to avoid binary floating-point boundary artifacts.",
            "",
            "### Sender deltas by type",
            "",
            "| Type | Rows | Pre zero | Post zero | Amount > pre | Delta = +amount | Delta = -amount | Unchanged | Other delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {row['transaction_type']} | {row['transaction_count']:,} | "
        f"{row['pre_balance_zero']:,} | {row['post_balance_zero']:,} | "
        f"{row['amount_exceeds_pre_balance']:,} | "
        f"{row['delta_matches_positive_amount']:,} | "
        f"{row['delta_matches_negative_amount']:,} | "
        f"{row['unchanged_balance']:,} | {row['other_balance_delta']:,} |"
        for row in summary["sender_balance_by_type"]
    )
    lines.extend(
        [
            "",
            "### Zero-balance patterns",
            "",
            "| Type | Rows | Sender pre zero | Sender post zero | Sender both zero | Receiver pre zero | Receiver post zero | Receiver both zero |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {row['transaction_type']} | {row['transaction_count']:,} | "
        f"{row['sender_pre_zero']:,} | {row['sender_post_zero']:,} | "
        f"{row['sender_both_zero']:,} | {row['receiver_pre_zero']:,} | "
        f"{row['receiver_post_zero']:,} | {row['receiver_both_zero']:,} |"
        for row in summary["balance_zero_patterns"]
    )
    lines.extend(
        [
            "",
            "### Receiver deltas by type and account-ID prefix",
            "",
            "| Type | Prefix | Rows | Pre zero | Post zero | Delta = +amount | Delta = -amount | Unchanged | Other delta |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {row['transaction_type']} | {row['receiver_prefix']} | "
        f"{row['transaction_count']:,} | {row['pre_balance_zero']:,} | "
        f"{row['post_balance_zero']:,} | {row['delta_matches_positive_amount']:,} | "
        f"{row['delta_matches_negative_amount']:,} | {row['unchanged_balance']:,} | "
        f"{row['other_balance_delta']:,} |"
        for row in summary["receiver_balance_by_type"]
    )
    lines.extend(
        [
            "",
            "### Balance deltas by fraud label",
            "",
            "| Type | isFraud label | Rows | Sender candidate mismatch | Sender unchanged | Receiver unchanged |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {row['transaction_type']} | {row['is_fraud']} | "
        f"{row['transaction_count']:,} | {row['sender_candidate_mismatch_count']:,} | "
        f"{row['sender_unchanged_count']:,} | {row['receiver_unchanged_count']:,} |"
        for row in summary["balance_by_label"]
    )
    lines.extend(["", "### Representative non-zero sender exceptions", ""])
    lines.extend(
        f"- `{row['transaction_type']}` at step {row['step']}: amount {row['amount']:,.2f}; "
        f"sender balance {row['sender_pre_balance']:,.2f} -> {row['sender_post_balance']:,.2f} "
        f"(delta {row['sender_delta']:,.2f}); amount exceeds starting balance: "
        f"{str(row['amount_exceeds_sender_pre_balance']).lower()}; "
        f"fraud label: {row['label_is_fraud']}."
        for row in summary["representative_balance_exceptions"]
    )
    lines.extend(
        [
            "",
            "## Candidate Feature Policy",
            "",
            "| Candidate predictor | Definition |",
            "| --- | --- |",
            "| amount | Transaction amount known at decision time |",
            "| transaction_type | Transaction category known at decision time |",
            "| simulated_hour | `step % 24`; simulated index, not clock time |",
            "| sender_pre_balance | `oldbalanceOrg`; available before the transaction, but artifact-sensitive |",
            "| amount_to_sender_pre_balance | Amount / old sender balance; null when old balance is zero |",
            "| sender_balance_covers_amount | Whether old sender balance is at least amount |",
            "| recipient_prior_transaction_count | Count of receipts at strictly earlier steps |",
            "| recipient_prior_received_amount | Sum of receipt amounts at strictly earlier steps |",
            "",
            "The feature Parquet includes `split_step` and `split` as evaluation metadata and `label_is_fraud` as the target, not as predictors. Raw sender/receiver IDs, `isFlaggedFraud`, post-transaction balances, and future-derived fields are absent. Same-step receipts never contribute to one another's historical features. No model was trained and no Power BI CSV was exported.",
            "",
            "## Leakage and Simulation Limitations",
            "",
        ]
    )
    lines.extend(f"- {limitation}" for limitation in summary["interpretation_limitations"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--feature-parquet", type=Path, default=DEFAULT_PARQUET)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()
    summary = run_phase2(args.csv_path, args.feature_parquet, args.report_dir)
    print(f"Analyzed {summary['total_records']:,} transactions")
    print(f"Wrote {args.feature_parquet}")
    print(f"Wrote {args.report_dir / 'phase2_eda.json'}")
    print(f"Wrote {args.report_dir / 'phase2_eda.md'}")


if __name__ == "__main__":
    main()