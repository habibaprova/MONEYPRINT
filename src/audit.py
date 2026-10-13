"""Generate a memory-conscious audit of the PaySim transaction CSV."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "raw" / "PS_20174392719_1491204439457_log.csv"
DEFAULT_REPORT_DIR = ROOT / "reports"
BALANCE_TOLERANCE = 0.01


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return value


def audit(csv_path: Path) -> dict[str, Any]:
    if not csv_path.is_file():
        raise FileNotFoundError(f"PaySim CSV not found: {csv_path}")

    connection = duckdb.connect()
    try:
        connection.execute("SET memory_limit = '1GB'")
        csv_literal = str(csv_path.resolve()).replace("'", "''")
        connection.execute(
            "CREATE TEMP VIEW transactions AS "
            f"SELECT * FROM read_csv_auto('{csv_literal}', header = true)"
        )

        schema = [
            {"name": row[0], "type": row[1]}
            for row in connection.execute("DESCRIBE transactions").fetchall()
        ]
        columns = [column["name"] for column in schema]
        required = {
            "step", "type", "nameOrig", "oldbalanceOrg", "newbalanceOrig",
            "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud",
        }
        missing_columns = sorted(required.difference(columns))
        if missing_columns:
            raise ValueError(
                "CSV is missing required PaySim columns: " + ", ".join(missing_columns)
            )

        quoted_columns = ", ".join(quote_identifier(name) for name in columns)
        null_expressions = ", ".join(
            f"COUNT(*) FILTER (WHERE {quote_identifier(name)} IS NULL) "
            f"AS {quote_identifier(name)}"
            for name in columns
        )
        null_values = connection.execute(
            f"SELECT {null_expressions} FROM transactions"
        ).fetchone()
        missing_values = {
            name: int(scalar(null_values[index]))
            for index, name in enumerate(columns)
        }

        overview = connection.execute(
            "SELECT COUNT(*) AS total_records, "
            f"COUNT(*) - COUNT(DISTINCT ({quoted_columns})) AS duplicate_rows, "
            "MIN(step) AS min_step, MAX(step) AS max_step, "
            "COUNT(*) FILTER (WHERE isFraud = 1) AS fraud_records, "
            "COUNT(*) FILTER (WHERE isFraud = 0) AS non_fraud_records, "
            "COUNT(*) FILTER (WHERE isFlaggedFraud = 1) AS flagged_fraud_records "
            "FROM transactions"
        ).fetchone()
        total_records = int(scalar(overview[0]))
        fraud_records = int(scalar(overview[4]))

        type_counts = {
            str(transaction_type): int(count)
            for transaction_type, count in connection.execute(
                "SELECT type, COUNT(*) FROM transactions "
                "GROUP BY type ORDER BY type"
            ).fetchall()
        }
        fraud_by_type = {
            str(transaction_type): {
                "fraud_records": int(fraud_count),
                "total_records": int(count),
                "fraud_rate": (int(fraud_count) / int(count)) if count else 0.0,
            }
            for transaction_type, fraud_count, count in connection.execute(
                "SELECT type, COUNT(*) FILTER (WHERE isFraud = 1), COUNT(*) "
                "FROM transactions GROUP BY type ORDER BY type"
            ).fetchall()
        }

        repeated_accounts = {}
        for role, column in (("sender", "nameOrig"), ("receiver", "nameDest")):
            repeated_accounts[role] = connection.execute(
                f"SELECT COUNT(*), COALESCE(SUM(account_rows), 0) "
                f"FROM (SELECT COUNT(*) AS account_rows FROM transactions "
                f"WHERE {quote_identifier(column)} IS NOT NULL "
                f"GROUP BY {quote_identifier(column)} HAVING COUNT(*) > 1)"
            ).fetchone()

        sender_balance = "CASE WHEN type = 'CASH_IN' THEN amount ELSE -amount END"
        receiver_balance = "amount"
        balances = connection.execute(
            "SELECT "
            "COUNT(*) FILTER (WHERE type IN "
            "('CASH_IN', 'CASH_OUT', 'DEBIT', 'PAYMENT', 'TRANSFER') "
            "AND oldbalanceOrg IS NOT NULL AND newbalanceOrig IS NOT NULL "
            "AND amount IS NOT NULL) AS sender_checked, "
            "COUNT(*) FILTER (WHERE type IN "
            "('CASH_IN', 'CASH_OUT', 'DEBIT', 'PAYMENT', 'TRANSFER') "
            "AND oldbalanceOrg IS NOT NULL AND newbalanceOrig IS NOT NULL "
            "AND amount IS NOT NULL AND ABS((newbalanceOrig - oldbalanceOrg) - "
            f"({sender_balance})) > {BALANCE_TOLERANCE}) AS sender_inconsistent, "
            "COUNT(*) FILTER (WHERE nameDest LIKE 'C%' AND type IN "
            "('CASH_IN', 'TRANSFER') AND oldbalanceDest IS NOT NULL "
            "AND newbalanceDest IS NOT NULL AND amount IS NOT NULL) AS receiver_checked, "
            "COUNT(*) FILTER (WHERE nameDest LIKE 'C%' AND type IN "
            "('CASH_IN', 'TRANSFER') AND oldbalanceDest IS NOT NULL "
            "AND newbalanceDest IS NOT NULL AND amount IS NOT NULL "
            "AND ABS((newbalanceDest - oldbalanceDest) - "
            f"({receiver_balance})) > {BALANCE_TOLERANCE}) AS receiver_inconsistent "
            "FROM transactions"
        ).fetchone()

        sender_accounts = repeated_accounts["sender"]
        receiver_accounts = repeated_accounts["receiver"]
        sender_checked = int(scalar(balances[0]))
        receiver_checked = int(scalar(balances[2]))
        sender_inconsistent = int(scalar(balances[1]))
        receiver_inconsistent = int(scalar(balances[3]))

        return {
            "dataset": csv_path.name,
            "total_records": total_records,
            "columns": schema,
            "missing_values": missing_values,
            "duplicate_rows": int(scalar(overview[1])),
            "transaction_types": type_counts,
            "fraud": {
                "fraud_records": fraud_records,
                "non_fraud_records": int(scalar(overview[5])),
                "fraud_rate": fraud_records / total_records if total_records else 0.0,
                "flagged_fraud_records": int(scalar(overview[6])),
                "flagged_fraud_rate": (
                    int(scalar(overview[6])) / total_records if total_records else 0.0
                ),
                "by_transaction_type": fraud_by_type,
            },
            "time_step": {
                "min": scalar(overview[2]),
                "max": scalar(overview[3]),
            },
            "repeated_accounts": {
                "sender_accounts_repeated": int(scalar(sender_accounts[0])),
                "sender_rows_in_repeated_accounts": int(scalar(sender_accounts[1])),
                "receiver_accounts_repeated": int(scalar(receiver_accounts[0])),
                "receiver_rows_in_repeated_accounts": int(scalar(receiver_accounts[1])),
            },
            "balance_consistency": {
                "tolerance": BALANCE_TOLERANCE,
                "sender_checked": sender_checked,
                "sender_inconsistent": sender_inconsistent,
                "sender_inconsistent_rate": (
                    sender_inconsistent / sender_checked if sender_checked else 0.0
                ),
                "receiver_checked": receiver_checked,
                "receiver_inconsistent": receiver_inconsistent,
                "receiver_inconsistent_rate": (
                    receiver_inconsistent / receiver_checked if receiver_checked else 0.0
                ),
            },
        }
    finally:
        connection.close()


def render_markdown(result: dict[str, Any]) -> str:
    fraud = result["fraud"]
    steps = result["time_step"]
    repeated = result["repeated_accounts"]
    balances = result["balance_consistency"]
    lines = [
        "# PaySim Dataset Audit",
        "",
        f"- **Dataset:** `{result['dataset']}`",
        f"- **Total records:** {result['total_records']:,}",
        f"- **Exact duplicate rows:** {result['duplicate_rows']:,}",
        f"- **Time-step range:** {steps['min']} to {steps['max']}",
        f"- **Fraud records:** {fraud['fraud_records']:,} "
        f"({fraud['fraud_rate']:.6%})",
        f"- **Flagged fraud records:** {fraud['flagged_fraud_records']:,} "
        f"({fraud['flagged_fraud_rate']:.6%})",
        f"- **Non-fraud records:** {fraud['non_fraud_records']:,}",
        "",
        "## Columns and types",
        "",
        "| Column | Type | Missing values |",
        "| --- | --- | ---: |",
    ]
    lines.extend(
        f"| `{column['name']}` | {column['type']} | "
        f"{result['missing_values'][column['name']]:,} |"
        for column in result["columns"]
    )
    lines.extend(["", "## Transaction types", "", "| Type | Records | Fraud records | Fraud rate |", "| --- | ---: | ---: | ---: |"])
    lines.extend(
        f"| {transaction_type} | {count:,} | "
        f"{fraud['by_transaction_type'][transaction_type]['fraud_records']:,} | "
        f"{fraud['by_transaction_type'][transaction_type]['fraud_rate']:.6%} |"
        for transaction_type, count in result["transaction_types"].items()
    )
    lines.extend(
        [
            "",
            "## Repeated accounts",
            "",
            "| Role | Accounts appearing more than once | Rows belonging to those accounts |",
            "| --- | ---: | ---: |",
            f"| Sender | {repeated['sender_accounts_repeated']:,} | "
            f"{repeated['sender_rows_in_repeated_accounts']:,} |",
            f"| Receiver | {repeated['receiver_accounts_repeated']:,} | "
            f"{repeated['receiver_rows_in_repeated_accounts']:,} |",
            "",
            "## Balance consistency",
            "",
            f"Tolerance: {balances['tolerance']:.2f} currency units.",
            "Sender expectation: amount is subtracted except for `CASH_IN`, when it is added.",
            "Receiver expectation: amount is added for customer accounts (`C...`) on `CASH_IN` and `TRANSFER`; other receiver cases are excluded.",
            "",
            "| Account side | Checked | Inconsistent | Inconsistent rate |",
            "| --- | ---: | ---: | ---: |",
            f"| Sender | {balances['sender_checked']:,} | "
            f"{balances['sender_inconsistent']:,} | "
            f"{balances['sender_inconsistent_rate']:.6%} |",
            f"| Receiver | {balances['receiver_checked']:,} | "
            f"{balances['receiver_inconsistent']:,} | "
            f"{balances['receiver_inconsistent_rate']:.6%} |",
            "",
            "Generated by `src/audit.py` using DuckDB scans over the source CSV.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", nargs="?", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()

    result = audit(args.csv_path)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.report_dir / "paysim_audit.json"
    markdown_path = args.report_dir / "paysim_audit.md"
    json_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    print(f"Audited {result['total_records']:,} records from {result['dataset']}")


if __name__ == "__main__":
    main()