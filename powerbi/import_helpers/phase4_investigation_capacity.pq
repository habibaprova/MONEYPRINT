let
    Source = Csv.Document(
        File.Contents("C:\Users\user4\Desktop\MONEYPRINT\powerbi\exports\phase4_investigation_capacity.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    PromoteHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(PromoteHeaders, {
        {"protocol_version", type text},
        {"model_id", type text},
        {"method", type text},
        {"model_display_name", type text},
        {"evaluation_window", type text},
        {"evaluation_status", type text},
        {"population", type text},
        {"transaction_count", Int64.Type},
        {"fraud_count", Int64.Type},
        {"fraud_prevalence", type number},
        {"capacity_measure", type text},
        {"alert_count", Int64.Type},
        {"true_positives", Int64.Type},
        {"false_positives", Int64.Type},
        {"precision", type number},
        {"recall", type number},
        {"pr_auc_average_precision", type number},
        {"roc_auc", type number},
        {"source_provenance", type text}
    })
in
    Typed
