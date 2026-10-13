let
    Source = Csv.Document(
        File.Contents("C:\Users\user4\Desktop\MONEYPRINT\powerbi\exports\dim_transaction_type.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    PromoteHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(PromoteHeaders, {
        {"transaction_type", type text},
        {"type_sort", Int64.Type}
    })
in
    Typed
