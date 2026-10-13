let
    Source = Csv.Document(
        File.Contents("C:\Users\user4\Desktop\MONEYPRINT\powerbi\exports\fraud_by_transaction_type.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    PromoteHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(PromoteHeaders, {
        {"transaction_type", type text},
        {"transaction_count", Int64.Type},
        {"fraud_count", Int64.Type},
        {"fraud_label_prevalence", type number},
        {"data_scope", type text},
        {"source_provenance", type text},
        {"label_definition", type text}
    })
in
    Typed
