let
    Source = Csv.Document(
        File.Contents("C:\Users\user4\Desktop\MONEYPRINT\powerbi\exports\transaction_trends_by_hour.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    PromoteHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(PromoteHeaders, {
        {"simulated_hour", Int64.Type},
        {"transaction_type", type text},
        {"transaction_count", Int64.Type},
        {"total_synthetic_amount", type number},
        {"mean_synthetic_amount", type number},
        {"fraud_count", Int64.Type},
        {"fraud_label_prevalence", type number},
        {"source_provenance", type text},
        {"time_interpretation", type text}
    })
in
    Typed
