let
    Source = Csv.Document(
        File.Contents("C:\Users\user4\Desktop\MONEYPRINT\powerbi\exports\split_distribution_comparison.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    PromoteHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(PromoteHeaders, {
        {"split_protocol", type text},
        {"split", type text},
        {"transaction_type", type text},
        {"step_start", Int64.Type},
        {"step_end", Int64.Type},
        {"step_count", Int64.Type},
        {"transaction_count", Int64.Type},
        {"transaction_share", type number},
        {"fraud_count", Int64.Type},
        {"fraud_label_prevalence", type number},
        {"share_of_all_fraud_labels", type number},
        {"mean_synthetic_amount", type number},
        {"median_synthetic_amount", type number},
        {"p95_synthetic_amount", type number},
        {"source_provenance", type text}
    })
in
    Typed
