let
    Source = Csv.Document(
        File.Contents("C:\Users\user4\Desktop\MONEYPRINT\powerbi\exports\phase4_model_feature_ablation.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    PromoteHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(PromoteHeaders, {
        {"protocol_version", type text},
        {"feature_set", type text},
        {"feature_configuration", type text},
        {"fold", type text},
        {"validation_prevalence", type number},
        {"pr_auc_average_precision", type number},
        {"roc_auc", type number},
        {"precision_at_100", type number},
        {"recall_at_100", type number},
        {"precision_at_500", type number},
        {"recall_at_500", type number},
        {"mean_fold_validation_pr_auc", type number},
        {"sd_fold_validation_pr_auc", type number},
        {"mean_fold_validation_roc_auc", type number},
        {"mean_train_pr_auc_in_sample", type number},
        {"is_selected_phase4_model", type logical},
        {"source_provenance", type text}
    })
in
    Typed
