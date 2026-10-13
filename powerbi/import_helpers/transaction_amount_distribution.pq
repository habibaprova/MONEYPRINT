let
    Source = Csv.Document(
        File.Contents("C:\Users\user4\Desktop\MONEYPRINT\powerbi\exports\transaction_amount_distribution.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    PromoteHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(PromoteHeaders, {
        {"transaction_type", type text},
        {"amount_band", type text},
        {"transaction_count", Int64.Type},
        {"total_synthetic_amount", type number},
        {"fraud_count", Int64.Type},
        {"transaction_share_within_type", type number},
        {"source_provenance", type text}
    })
in
    Typed
