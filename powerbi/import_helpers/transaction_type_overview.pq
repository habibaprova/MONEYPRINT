let
    Source = Csv.Document(
        File.Contents("C:\Users\user4\Desktop\MONEYPRINT\powerbi\exports\transaction_type_overview.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    PromoteHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(PromoteHeaders, {
        {"transaction_type", type text},
        {"transaction_count", Int64.Type},
        {"total_synthetic_amount", type number},
        {"mean_synthetic_amount", type number},
        {"median_synthetic_amount", type number},
        {"p95_synthetic_amount", type number},
        {"fraud_count", Int64.Type},
        {"fraud_label_prevalence", type number},
        {"data_scope", type text},
        {"source_provenance", type text}
    })
in
    Typed
