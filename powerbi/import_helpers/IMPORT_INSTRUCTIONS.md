# Power BI import instructions for the remaining 11 CSV tables

The already imported tables are:
- dim_evaluation_window
- dim_model_method
- dim_simulated_hour
- dim_simulated_step
- executive_kpi_summary

Do not use a Folder import for the exported CSVs. That would also pick up the five already imported tables and create duplicate queries.

The safe method is one explicit query per missing table:

1. Open the existing Power BI Desktop report.
2. On the Home tab, choose Transform data.
3. In the Queries pane, right-click and choose New Source > Blank Query.
4. Open the Advanced Editor.
5. Paste the content from one of the `.pq` files in this folder, then name the query to match the table name.
6. Choose Close & Apply.
7. Repeat for the remaining 11 missing tables.

The 11 missing files are:
- dim_transaction_type.csv
- fraud_by_transaction_type.csv
- phase4_investigation_capacity.csv
- phase4_model_feature_ablation.csv
- phase4_selected_model_investigation_examples.csv
- phase4_walkforward_fold_metrics.csv
- split_distribution_comparison.csv
- transaction_amount_distribution.csv
- transaction_trends_by_hour.csv
- transaction_trends_by_step.csv
- transaction_type_overview.csv

Each `.pq` file uses UTF-8 CSV encoding, comma delimiters, and explicit column typing to preserve the exported schema without touching the original CSV files or the existing five imported tables.
