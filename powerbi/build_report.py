"""Build PBIR visuals around the model preserved by Desktop Save As. No scoring or training."""
import csv, json, re, uuid, shutil, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / 'MONEYPRINT.Report' / 'definition'
MODEL = ROOT / 'MONEYPRINT.SemanticModel' / 'definition'
def dump(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding='utf-8')
def rows(name):
    return list(csv.DictReader((ROOT/'exports'/f'{name}.csv').open(encoding='utf-8-sig')))

manifest=json.loads((ROOT/'exports/export_manifest.json').read_text())
checks={}
for name, meta in manifest['files'].items():
    p=ROOT/'exports'/name
    r=list(csv.DictReader(p.open(encoding='utf-8-sig')))
    assert len(r)==meta['rows'] and p.stat().st_size==meta['bytes'], name
    checks[name]={'rows':len(r),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
for name in ['transaction_type_overview','transaction_amount_distribution','transaction_trends_by_step','transaction_trends_by_hour']:
    assert sum(int(r['transaction_count']) for r in rows(name))==6362620
queue=rows('phase4_selected_model_investigation_examples')
assert len(queue)==500 and sum(int(r['label_for_retrospective_review']) for r in queue)==456
cap=next(r for r in rows('phase4_investigation_capacity') if r['evaluation_window']=='reserved_final_exploratory' and r['capacity_measure']=='top_500')
assert float(cap['precision'])==.912
assert int(cap['true_positives'])==456
dump(ROOT/'QA_EXPORT_RECONCILIATION.json',{'files':checks,'capacity_top500':cap,'checks_passed':True})

# Preserve the Desktop-generated project before modifying its editable definitions.
for folder in ['MONEYPRINT.Report','MONEYPRINT.SemanticModel']:
    backup=ROOT/'backups'/(folder+'_desktop_original')
    if not backup.exists(): shutil.copytree(ROOT/folder,backup)

relations=[]
# One existing query was saved as pasted M text in a single Column1, rather than a CSV import.
bad=MODEL/'tables/fraud_by_transaction_type.tmdl'
if '\tcolumn Column1' in bad.read_text(encoding='utf-8-sig'):
    data=rows('fraud_by_transaction_type'); cols=data[0].keys()
    s='table fraud_by_transaction_type\n\tlineageTag: '+str(uuid.uuid4())+'\n'
    for c in cols:
        dtype='int64' if c in ['transaction_count','fraud_count'] else 'double' if c=='fraud_label_prevalence' else 'string'
        s+=f'\n\tcolumn {c}\n\t\tdataType: {dtype}\n\t\tsummarizeBy: none\n\t\tsourceColumn: {c}\n'
    pq=(ROOT/'import_helpers/fraud_by_transaction_type.pq').read_text(encoding='utf-8-sig')
    s+='\n\tpartition fraud_by_transaction_type = m\n\t\tmode: import\n\t\tsource =\n'+''.join('\t\t\t'+line+'\n' for line in pq.splitlines())
    bad.write_text(s,encoding='utf-8')
def rel(dim,dc,fact,fc):
    relations.append(f'relationship {uuid.uuid4()}\n\tfromColumn: {fact}.{fc}\n\ttoColumn: {dim}.{dc}\n\tfromCardinality: many\n\ttoCardinality: one\n\tcrossFilteringBehavior: oneDirection\n')
for t in ['transaction_type_overview','transaction_amount_distribution','fraud_by_transaction_type','transaction_trends_by_step','transaction_trends_by_hour','phase4_selected_model_investigation_examples']:
    rel('dim_transaction_type','transaction_type',t,'transaction_type')
for t,c in [('transaction_trends_by_step','simulated_step'),('phase4_selected_model_investigation_examples','split_step')]: rel('dim_simulated_step','simulated_step',t,c)
rel('dim_simulated_hour','simulated_hour','transaction_trends_by_hour','simulated_hour')
for t,c in [('phase4_walkforward_fold_metrics','fold'),('phase4_investigation_capacity','evaluation_window'),('phase4_selected_model_investigation_examples','evaluation_window')]: rel('dim_evaluation_window','evaluation_window',t,c)
for t in ['phase4_walkforward_fold_metrics','phase4_investigation_capacity','phase4_selected_model_investigation_examples']: rel('dim_model_method','method',t,'method')
(MODEL/'relationships.tmdl').write_text('\n'.join(relations),encoding='utf-8')

measures={}
def measure(name,expr,fmt='#,0'): measures[name]=(expr,fmt)
for name,key,fmt in [('Total Transactions','total_transactions','#,0'),('Fraud Labels','fraud_labels','#,0'),('Fraud Label Prevalence','fraud_label_prevalence','0.0000%'),('Total Synthetic Amount','total_synthetic_amount','#,0.00')]:
    measure(name,f'CALCULATE(MAX(executive_kpi_summary[metric_value]), executive_kpi_summary[metric_key] = "{key}")',fmt)
measure('Transactions Display','FORMAT([Total Transactions], "#,0")','')
measure('Amount Display','FORMAT([Total Synthetic Amount] / 1000000000000, "0.00") & "T"','')
fold='phase4_walkforward_fold_metrics'
for name,col in [('Validation ROC-AUC','roc_auc'),('Validation PR-AUC','pr_auc_average_precision'),('Validation Prevalence','fraud_prevalence')]:
    measure(name,f'CALCULATE(AVERAGE({fold}[{col}]), {fold}[is_selected_phase4_model] = TRUE(), {fold}[split] = "validation", {fold}[population] = "transfer_cash_out")','0.00%')
for name,col in [('Ablation ROC-AUC','mean_fold_validation_roc_auc'),('Ablation PR-AUC','mean_fold_validation_pr_auc')]: measure(name,f'MAX(phase4_model_feature_ablation[{col}])','0.00%')
ct='phase4_investigation_capacity'
for name,col,fmt in [('Capacity Precision','precision','0.00%'),('Capacity Recall','recall','0.00%'),('Capacity False Positives','false_positives','#,0')]:
    measure(name,f'VAR W = SELECTEDVALUE({ct}[evaluation_window], "reserved_final_exploratory") VAR K = SELECTEDVALUE({ct}[capacity_measure], "top_500") RETURN CALCULATE(MAX({ct}[{col}]), {ct}[evaluation_window] = W, {ct}[capacity_measure] = K, {ct}[model_id] = "phase4_walkforward_v1_plus_balance", {ct}[population] = "TRANSFER/CASH_OUT")',fmt)
qt='phase4_selected_model_investigation_examples'
measure('Selected Case Context',f'IF(HASONEVALUE({qt}[case_rank]), "Step " & SELECTEDVALUE({qt}[split_step]) & " | " & SELECTEDVALUE({qt}[transaction_type]) & UNICHAR(10) & "Amount: " & FORMAT(SELECTEDVALUE({qt}[synthetic_amount]), "#,0.00") & UNICHAR(10) & "Pre-balance: " & FORMAT(SELECTEDVALUE({qt}[sender_pre_balance]), "#,0.00") & UNICHAR(10) & "Amount / pre-balance: " & IF(ISBLANK(SELECTEDVALUE({qt}[amount_to_sender_pre_balance])), "undefined (zero balance)", FORMAT(SELECTEDVALUE({qt}[amount_to_sender_pre_balance]), "0.000")) & UNICHAR(10) & "Score: " & FORMAT(SELECTEDVALUE({qt}[risk_score]), "0.0000"), "Select one row in the ranked queue")','')
measure('Selected Contributions',f'IF(HASONEVALUE({qt}[case_rank]), SELECTEDVALUE({qt}[top_model_contributions]), "Associational contributions; not causal explanations.")','')
measure('Historical Split Share','CALCULATE(MAX(split_distribution_comparison[transaction_share]), split_distribution_comparison[transaction_type] = "ALL")','0.0%')
p=MODEL/'tables/executive_kpi_summary.tmdl'
s=p.read_text(encoding='utf-8-sig'); block=''
for name in measures:
    s=re.sub(r"\n\tmeasure '"+re.escape(name)+r"' =.*?(?=\n\t(?:measure|column|partition|annotation)|\Z)",'',s,flags=re.S)
for name,(expr,fmt) in measures.items():
    block+=f"\n\tmeasure '{name}' = {expr}\n\t\tformatString: {fmt or chr(34)+chr(34)}\n\t\tlineageTag: {uuid.uuid4()}\n"
s=s.replace('\n\tcolumn metric_key',block+'\n\tcolumn metric_key',1);p.write_text(s,encoding='utf-8')

def lit(v): return {'expr':{'Literal':{'Value':str(v)}}}
def string(v): return lit("'"+v.replace("'","''")+"'")
def color(v): return {'solid':{'color':string(v)}}
def obj(**kw): return [{'properties':kw}]
def field(t,c,agg=None,ms=False,label=None,fmt=None):
    f={('Measure' if ms else 'Column'):{'Expression':{'SourceRef':{'Entity':t}},'Property':c}}
    if agg is not None: f={'Aggregation':{'Expression':f,'Function':agg}}
    q={'field':f,'queryRef':f'{t}.{c}'+(f'.{agg}' if agg is not None else ''),'displayName':label or c,'nativeQueryRef':label or c}
    if fmt:q['format']=fmt
    return q
def m(name):return field('executive_kpi_summary',name,ms=True)
pages=['a247c16910f06e0dae90','investigation','reliability']
names=['Executive Overview','Investigation Desk','Behind the Score']
visuals={p:[] for p in pages}
def visual(page,name,typ,rect,title='',roles=None,objects=None,bg='#FAF9EF',sort=None):
    x,y,w,h=rect
    v={'name':name,'position':{'x':x,'y':y,'width':w,'height':h,'z':len(visuals[page]),'tabOrder':len(visuals[page])},'visual':{'visualType':typ,'drillFilterOtherVisuals':True,'visualContainerObjects':{'title':obj(show=lit('true' if title else 'false'),text=string(title),fontColor=color('#474538'),fontSize=lit('11D'),fontFamily=string('Segoe UI Semibold')),'background':obj(show=lit('true'),color=color(bg),transparency=lit('0D')),'border':obj(show=lit('false'))}}}
    if roles:
        v['visual']['query']={'queryState':{r:{'projections':fs} for r,fs in roles.items()}}
        if sort: v['visual']['query']['sortDefinition']={'sort':[{'field':sort[0]['field'],'direction':sort[1]}],'isDefaultSort':False}
    if objects: v['visual']['objects']=objects
    v['visual']['visualContainerObjects']['subTitle']=obj(show=lit('false'))
    v['visual']['visualContainerObjects']['padding']=obj(top=lit('4D'),bottom=lit('4D'),left=lit('6D'),right=lit('6D'))
    visuals[page].append(v);return v
def text(page,name,txt,rect,size=11,bg='#F0EDCF',bold=False):
    paragraphs=[{'textRuns':[{'value':line,'textStyle':{'fontFamily':'Segoe UI','fontSize':f'{size}pt','color':'#474538','fontWeight':'bold' if bold else 'normal'}}]} for line in txt.split('\n')]
    v=visual(page,name,'textbox',rect,objects={'general':obj(paragraphs=paragraphs)},bg=bg)
    v['visual']['visualContainerObjects']['padding']=obj(top=lit('0D'),bottom=lit('0D'),left=lit('0D'),right=lit('0D'))
    return v
def chart(page,name,typ,rect,title,cat,vals,series=None,sort=None):
    roles={'Category':[cat],'Y':vals}
    if series:roles['Series']=[series]
    return visual(page,name,typ,rect,title,roles,{'legend':obj(show=lit('true' if len(vals)>1 or series else 'false')),'labels':obj(show=lit('false' if name=='trend' else 'true'),fontSize=lit('9D')),'categoryAxis':obj(fontSize=lit('9D')),'valueAxis':obj(fontSize=lit('9D'))},sort=sort)
def table(page,name,rect,title,fs):return visual(page,name,'tableEx',rect,title,{'Values':fs}, {'grid':obj(textSize=lit('10D'),rowPadding=lit('2D')),'values':obj(wordWrap=lit('true'))})
def slicer(page,name,rect,title,f):return visual(page,name,'slicer',rect,'',{'Values':[f]},{'data':obj(mode=string('Dropdown')),'header':obj(show=lit('true'),text=string(title),textSize=lit('9D'))})
def card(page,name,rect,title,ms):return visual(page,name,'card',rect,title,{'Values':[m(ms)]},{'labels':obj(fontSize=lit('23D'),color=color('#474538'),displayUnits=lit('1D')),'categoryLabels':obj(show=lit('false'))})

for i,p in enumerate(pages):
    page={'$schema':'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json','name':p,'displayName':names[i],'displayOption':'FitToPage','height':720,'width':1280,'objects':{'background':obj(color=color('#F0EDCF'),transparency=lit('0D'))}}
    dump(REPORT/'pages'/p/'page.json',page)
    text(p,'sidebar','MONEYPRINT\n\nTRANSACTION\nINTELLIGENCE', (0,0,184,720),16,'#D5CE91',True)
    def stateprop(props,state): return {'properties':props,'selector':{'id':state}}
    nav=visual(p,'native_navigation','pageNavigator',(16,126,152,164),bg='#D5CE91',objects={
        'layout':obj(orientation=lit('1D'),cellPadding=lit('8D')),
        'text':[stateprop({'fontSize':lit('10D'),'fontColor':color('#474538')},st) for st in ['default','selected']],
        'fill':[stateprop({'show':lit('true'),'fillColor':color('#BC858A' if st=='selected' else '#D5CE91'),'transparency':lit('0D')},st) for st in ['default','selected']],
        'outline':obj(show=lit('false')),
        'shape':[stateprop({'tileShape':string('rectangle'),'roundEdge':lit('0D')},'default')]
    })
    reset=json.loads((ROOT/'native_templates/actionButton.json').read_text())
    reset['name']='clear_slicers';reset['position']={'x':16,'y':310,'width':152,'height':36,'z':30,'tabOrder':30}
    reset['visual']['objects']['text'].append(stateprop({'fontSize':lit('10D'),'fontColor':color('#474538')},'default'))
    reset['visual']['visualContainerObjects']['background']=obj(show=lit('true'),color=color('#D5CE91'),transparency=lit('0D'))
    visuals[p].append(reset)
    text(p,'sidebar_note','SYNTHETIC PAYSIM\n\nOffline portfolio\n\nFrozen Phase 4\nmodel evidence',(16,500,152,150),10,'#D5CE91')
    text(p,'heading',['Transaction Intelligence','Investigation Desk','Behind the Score'][i],(208,12,1048,50),22,bold=True)
    text(p,'footer','Synthetic amount units • Simulated time, not calendar dates • Research portfolio',(208,700 if i==0 else 687,1048,20),9)

p=pages[0]
text(p,'subtitle','Full PaySim population • 6,362,620 transactions • Steps 1–743 • Headline KPIs remain dataset-wide',(208,58,1048,24),10)
for j,(title,ms) in enumerate([('Transactions','Transactions Display'),('Fraud labels','Fraud Labels'),('Labeled prevalence','Fraud Label Prevalence'),('Synthetic amount (trillions)','Amount Display')]):card(p,f'kpi_{j}',(208+j*262,94,250,76),title,ms)
typefield=field('dim_transaction_type','transaction_type')
vol=field('transaction_type_overview','transaction_count',0,label='Transactions')
chart(p,'volume','clusteredColumnChart',(208,182,510,145),'Transaction volume by type',typefield,[vol],sort=(vol,'Descending'))
chart(p,'trend','lineChart',(730,182,526,145),'Activity by simulated step',field('dim_simulated_step','simulated_step'),[field('transaction_trends_by_step','transaction_count',0,label='Transactions')])
chart(p,'value','clusteredColumnChart',(208,339,510,145),'Synthetic amount by type',typefield,[field('transaction_type_overview','total_synthetic_amount',0,label='Synthetic units')])
chart(p,'fraud','clusteredColumnChart',(730,339,526,145),'Fraud labels by transaction type',typefield,[field('fraud_by_transaction_type','fraud_count',0,label='Fraud labels')])
chart(p,'amount','clusteredColumnChart',(208,496,510,148),'Transaction amount distribution • synthetic units',field('transaction_amount_distribution','amount_band'),[field('transaction_amount_distribution','transaction_count',0,label='Transactions')])
text(p,'evidence','READING THIS PAGE\nFraud labels occur in CASH_OUT and TRANSFER in PaySim.\nThis describes the simulator, not real banking behavior.\nType filters affect charts; step filters affect the trend.\nHeadline cards always describe the full dataset.',(730,496,526,148),11,'#FAF9EF')
slicer(p,'type_filter',(208,650,510,48),'Transaction type',typefield)
slicer(p,'step_filter',(730,650,526,48),'Simulated step',field('dim_simulated_step','simulated_step'))

p=pages[1]
text(p,'subtitle','Frozen plus_balance model • Previously accessed later period • Score is not a calibrated probability',(208,58,1048,24),10)
slicer(p,'window',(208,90,230,62),'Capacity window',field(ct,'evaluation_window'))
slicer(p,'capacity',(450,90,210,62),'Investigation budget',field(ct,'capacity_measure'))
for j,(t,ms) in enumerate([('Precision@K','Capacity Precision'),('Recall@K','Capacity Recall'),('False positives','Capacity False Positives')]):card(p,f'capacity_{j}',(672+j*196,90,185,62),t,ms)
fs=[field(qt,c,label=l,fmt=f) for c,l,f in [('case_rank','Rank','0'),('split_step','Step','0'),('transaction_type','Type',None),('synthetic_amount','Amount','#,0.00'),('risk_score','Score','0.0000'),('label_for_retrospective_review','Retrospective label','0')]]
v=table(p,'queue',(208,168,690,382),'Top 500 ranked cases • select a row',fs)
v['visual']['query']['sortDefinition']={'sort':[{'field':fs[0]['field'],'direction':'Ascending'}],'isDefaultSort':False}
table(p,'case_detail',(910,168,346,220),'Selected case context',[m('Selected Case Context')])
table(p,'contributions',(910,400,346,150),'Saved model contributions',[m('Selected Contributions')])
v=slicer(p,'topk',(208,554,690,54),'Queue rank • select range 1–K',field(qt,'case_rank'))
v['visual']['objects']['data']=obj(mode=string('Between'))
text(p,'note','CAPACITY CARDS: default to exploratory period + top 500 when no single option is selected.\nQUEUE: 500 saved, risk-selected TRANSFER/CASH_OUT cases from steps 632–743; not the full population.\nRetrospective labels support post hoc review only. 456/500 are labeled; this is not population prevalence.',(208,612,1048,65),10,'#FAF9EF')

p=pages[2]
text(p,'subtitle','Four expanding chronological folds • Eligible TRANSFER/CASH_OUT population • Frozen Phase 4 evidence',(208,58,1048,24),10)
chart(p,'folds','lineChart',(208,90,510,174),'Walk-forward validation ROC-AUC / PR-AUC',field('dim_evaluation_window','evaluation_window'),[m('Validation ROC-AUC'),m('Validation PR-AUC')])
chart(p,'prevalence','columnChart',(730,90,526,174),'Validation label prevalence by fold',field('dim_evaluation_window','evaluation_window'),[m('Validation Prevalence')])
chart(p,'ablation','clusteredColumnChart',(208,276,510,174),'Feature ablation • mean validation metrics',field('phase4_model_feature_ablation','feature_set'),[m('Ablation ROC-AUC'),m('Ablation PR-AUC')])
table(p,'windows',(730,276,526,174),'Training and evaluation step definitions',[field('dim_evaluation_window',c,label=l) for c,l in [('evaluation_window','Window'),('train_end_step','Train through'),('evaluation_start_step','From'),('evaluation_end_step','Through')]])
chart(p,'split','clusteredColumnChart',(208,462,510,150),'Historical split diagnostics • ALL rows only',field('split_distribution_comparison','split'),[m('Historical Split Share')],field('split_distribution_comparison','split_protocol'))
text(p,'caveats','INTERPRETATION & LIMITATIONS\nPaySim is synthetic; severe class imbalance makes PR-AUC essential.\nBalance features may exploit simulator artifacts.\nSteps 632–743 were previously accessed: exploratory, not pristine.\nScores do not establish production banking performance.',(730,462,526,150),10,'#FAF9EF')
text(p,'reliability_note','ROC-AUC measures discrimination; PR-AUC evaluates ranking under imbalance.\nThe fold curves show period stability; ablation exposes dependence on synthetic balance patterns.',(208,624,1048,54),10)

for p in pages:
    keep={v['name'] for v in visuals[p]}
    for stale in (REPORT/'pages'/p/'visuals').glob('*/visual.json'):
        if stale.parent.name not in keep:
            assert stale.resolve().is_relative_to(REPORT.resolve())
            stale.unlink()
    for v in visuals[p]:
        v['$schema']='https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json'
        dump(REPORT/'pages'/p/'visuals'/v['name']/'visual.json',v)
dump(REPORT/'pages/pages.json',{'$schema':'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json','pageOrder':pages,'activePageName':pages[0]})
dump(ROOT/'REPORT_LAYOUT.json',{p:[{'name':v['name'],'position':v['position'],'visual':v['visual']} for v in visuals[p]] for p in pages})
print('16 exports reconciled. Built',sum(map(len,visuals.values())),'PBIR visuals and',len(measures),'measures; Desktop reopening required.')
