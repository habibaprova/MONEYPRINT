let
    Source = Csv.Document(
        File.Contents("C:\Users\user4\Desktop\MONEYPRINT\powerbi\exports\phase4_selected_model_investigation_examples.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    PromoteHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(PromoteHeaders, {
        {"case_rank", Int64.Type},
        {"protocol_version", type text},
        {"model_id", type text},
        {"method", type text},
        {"model_display_name", type text},
        {"score_source", type text},
        {"evaluation_window", type text},
        {"evaluation_status", type text},
        {"split_step", Int64.Type},
        {"simulated_hour", Int64.Type},
        {"transaction_type", type text},
        {"synthetic_amount", type number},
        {"sender_pre_balance", type number},
        {"amount_to_sender_pre_balance", type number},
        {"sender_balance_covers_amount", type logical},
        {"risk_score", type number},
        {"top_model_contributions", type text},
        {"explanation_caveat", type text},
        {"label_for_retrospective_review", Int64.Type},
        {"population_warning", type text}
    })
in
    Typed
