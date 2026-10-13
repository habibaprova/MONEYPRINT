"""Enhance the Desktop-exported current project; never change frozen source files."""
from pathlib import Path
import json, shutil, uuid, csv, hashlib

ROOT=Path(__file__).parent
REPORT=ROOT/'MONEYPRINT_UX.Report'/'definition'
MODEL=ROOT/'MONEYPRINT_UX.SemanticModel'/'definition'
PAGES=['a247c16910f06e0dae90','investigation','reliability']
backup=ROOT/'backups'/'interactivity_current_project'
if not backup.exists():
    backup.mkdir()
    for n in ['MONEYPRINT_UX.Report','MONEYPRINT_UX.SemanticModel']:
        shutil.copytree(ROOT/n,backup/n)
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def vp(page,name): return REPORT/'pages'/page/'visuals'/name/'visual.json'
def lit(v): return {'expr':{'Literal':{'Value':str(v)}}}
def string(v): return lit("'"+v.replace("'","''")+"'")
def color(v): return {'solid':{'color':string(v)}}
def obj(**kw):return [{'properties':kw}]
def field(t,c,measure=False):
    f={('Measure' if measure else 'Column'):{'Expression':{'SourceRef':{'Entity':t}},'Property':c}}
    return {'field':f,'queryRef':t+'.'+c,'nativeQueryRef':c,'displayName':c}
def m(n):return field('executive_kpi_summary',n,True)
def state(props,id):return {'properties':props,'selector':{'id':id}}

# A: all tooltip measures read the full-population five-row summary under type context.
measures={
 'Type Transactions':('SUM(transaction_type_overview[transaction_count])','#,0'),
 'Type Share of Population':('DIVIDE([Type Transactions], CALCULATE(SUM(transaction_type_overview[transaction_count]), REMOVEFILTERS(dim_transaction_type), REMOVEFILTERS(transaction_type_overview)))','0.00%'),
 'Type Synthetic Amount':('SUM(transaction_type_overview[total_synthetic_amount])','#,0.00'),
 'Type Fraud Labels':('SUM(transaction_type_overview[fraud_count])','#,0'),
 'Type Fraud Label Rate':('DIVIDE([Type Fraud Labels], [Type Transactions])','0.0000%'),
 'Selected Type Label':('VAR N = COUNTROWS(VALUES(dim_transaction_type[transaction_type])) VAR AllN = CALCULATE(COUNTROWS(VALUES(dim_transaction_type[transaction_type])), REMOVEFILTERS(dim_transaction_type)) RETURN SWITCH(TRUE(), N = AllN, "Selected type: All", N = 1, "Selected type: " & SELECTEDVALUE(dim_transaction_type[transaction_type]), N = 0, "Selected types: None", "Selected types: Multiple")',None),
 'Comparison Value':('SWITCH(SELECTEDVALUE(ux_metric_selector[Metric], "Transaction count"), "Synthetic amount", [Type Synthetic Amount] / 1000000000, "Fraud count", [Type Fraud Labels], [Type Transactions])','#,0.##'),
 'Comparison Title':('SWITCH(SELECTEDVALUE(ux_metric_selector[Metric], "Transaction count"), "Synthetic amount", "Synthetic Amount by Type (billions of units)", "Fraud count", "Fraud Labels by Type", "Transactions by Type")',None),
 'Budget Status':('"Budget: " & SELECTEDVALUE(phase4_investigation_capacity[Budget Label], "Top 500 (default)")',None),
}
path=MODEL/'tables'/'executive_kpi_summary.tmdl'
s=path.read_text(encoding='utf-8-sig')
block=''
for name,(expr,fmt) in measures.items():
    block+=f"\n\tmeasure '{name}' = {expr}\n"
    if fmt:block+=f'\t\tformatString: {fmt}\n'
    block+=f'\t\tlineageTag: {uuid.uuid4()}\n'
s=s.replace('\n\tcolumn metric_key',block+'\n\tcolumn metric_key',1)
path.write_text(s,encoding='utf-8')
# A disconnected, three-row UI table is metadata, not a duplicate source dataset.
(MODEL/'tables'/'ux_metric_selector.tmdl').write_text('''table ux_metric_selector
\tlineageTag: '''+str(uuid.uuid4())+'''

\tcolumn Metric
\t\tdataType: string
\t\tsummarizeBy: none
\t\tsourceColumn: Metric
\t\tsortByColumn: Sort

\tcolumn Sort
\t\tdataType: int64
\t\tisHidden
\t\tsummarizeBy: none
\t\tsourceColumn: Sort

\tpartition ux_metric_selector = m
\t\tmode: import
\t\tsource =
\t\t\t#table(type table [Metric=text, Sort=Int64.Type], {{"Transaction count", 1}, {"Synthetic amount", 2}, {"Fraud count", 3}})

\tannotation PBI_ResultType = Table
''',encoding='utf-8')
model=MODEL/'model.tmdl'
s=model.read_text(encoding='utf-8-sig')
s=s.replace('ref cultureInfo','ref table ux_metric_selector\n\nref cultureInfo')
model.write_text(s,encoding='utf-8')

for page in PAGES:
    # B: native state selectors; all existing actions/destinations remain untouched.
    for name in ['native_navigation','clear_slicers']:
        v=read(vp(page,name));o=v['visual']['objects']
        o['fill']=[state({'show':lit('true'),'fillColor':color(c),'transparency':lit('0D')},st) for st,c in [('default','#D5CE91'),('hover','#BC858A'),('press','#474538'),('selected','#FAF9EF')]]
        o['text']=[state({'show':lit('true'),'fontSize':lit('10D'),'fontColor':color('#FAF9EF' if st=='press' else '#474538'),**({'text':string('Clear all slicers'),'horizontalAlignment':string('center')} if name=='clear_slicers' else {})},st) for st in ['default','hover','press','selected']]
        if name=='native_navigation':o['outline']=[state({'show':lit('true'),'lineColor':color('#BC858A'),'weight':lit('2D')},'selected'),state({'show':lit('false')},'default')]
        write(vp(page,name),v)

p=PAGES[0]
for name in ['volume','value','fraud']:
    v=read(vp(p,name))
    v['visual']['query']['queryState']['Tooltips']={'projections':[m(n) for n in list(measures)[:5]]}
    v['visual']['visualContainerObjects']['tooltips']=obj(show=lit('true'))
    write(vp(p,name),v)
# C: compact dropdown occupies part of the existing bottom slicer row.
v=read(vp(p,'type_filter'))
v['position']['width']=252
v.pop('filterConfig',None) # clean opening state (original current report was filtered).
write(vp(p,'type_filter'),v)
v=read(vp(p,'step_filter'));v.pop('filterConfig',None);write(vp(p,'step_filter'),v)
v=read(vp(p,'type_filter'));v['name']='metric_selector';v['position'].update(x=472,width=246,z=51,tabOrder=51)
v['visual']['query']={'queryState':{'Values':{'projections':[field('ux_metric_selector','Metric')]}}}
v['visual']['objects']['header'][0]['properties']['text']=string('Compare by • default: count')
v['visual']['objects']['selection']=obj(singleSelect=lit('true'),selectAllCheckboxEnabled=lit('false'))
write(vp(p,'metric_selector'),v)
v=read(vp(p,'volume'))
v['visual']['query']['queryState']['Y']={'projections':[m('Comparison Value')]}
v['visual']['query']['sortDefinition']={'sort':[{'field':m('Comparison Value')['field'],'direction':'Descending'}]}
v['visual']['objects']['labels'][0]['properties'].update(labelDisplayUnits=lit('1D'),labelPrecision=lit('2D'))
v['visual']['objects']['valueAxis'][0]['properties'].update(labelDisplayUnits=lit('1D'))
v['visual']['visualContainerObjects']['title'][0]['properties']['text']={'expr':m('Comparison Title')['field']}
write(vp(p,'volume'),v)
# D: use the unused bottom of the existing explanatory panel, no layout redesign.
v=read(vp(p,'evidence'));v['position']['height']=105;write(vp(p,'evidence'),v)
v=read(vp(p,'kpi_0'));v['name']='selected_type';v['position'].update(x=730,y=584,width=526,height=24,z=52,tabOrder=52)
v.pop('filterConfig',None)
v['visual']['query']={'queryState':{'Values':{'projections':[m('Selected Type Label')]}}}
v['visual']['objects']['labels'][0]['properties'].update(fontSize=lit('10D'),displayUnits=lit('1D'))
v['visual']['visualContainerObjects']['title']=obj(show=lit('false'))
v['visual']['visualContainerObjects']['padding']=obj(top=lit('0D'),bottom=lit('0D'),left=lit('6D'),right=lit('6D'))
write(vp(p,'selected_type'),v)
v=read(vp(p,'footer'));v['name']='click_hint';v['position'].update(x=730,y=608,width=526,height=16,z=53,tabOrder=53)
v['visual']['objects']['general'][0]['properties']['paragraphs']=[{'textRuns':[{'value':'Click a bar to explore • click again to clear','textStyle':{'fontFamily':'Segoe UI','fontSize':'9pt','color':'#474538'}}]}]
write(vp(p,'click_hint'),v)
page=read(REPORT/'pages'/p/'page.json')
page.setdefault('visualInteractions',[]).extend([{'source':n,'target':'selected_type','type':'DataFilter'} for n in ['volume','value','fraud','type_filter']])
write(REPORT/'pages'/p/'page.json',page)
# E: native horizontal tile slicer, all three validated budgets remain accessible.
p=PAGES[1];v=read(vp(p,'capacity'));v.pop('filterConfig',None)
v['visual']['objects']['data']=obj(mode=string('Horizontal'))
v['visual']['objects']['items']=obj(fontColor=color('#474538'),textSize=lit('9D'),background=color('#FAF9EF'))
write(vp(p,'capacity'),v)
# Prevent ambiguous filtered multi-budget contexts from silently selecting MAX.
path=MODEL/'tables'/'executive_kpi_summary.tmdl';s=path.read_text(encoding='utf-8')
import re
for name in ['Capacity Precision','Capacity Recall','Capacity False Positives']:
    pattern=r"(\tmeasure '"+name+r"' = )(.*?)(\n\t\tformatString:)"
    match=re.search(pattern,s,re.S)
    expr=match.group(2)
    guarded='IF(ISFILTERED(phase4_investigation_capacity[Budget Label]) && NOT HASONEVALUE(phase4_investigation_capacity[Budget Label]), BLANK(), '+expr+')'
    s=s[:match.start(2)]+guarded+s[match.end(2):]
path.write_text(s,encoding='utf-8')
# Record exact expected tooltip metrics without changing any export.
rows=list(csv.DictReader((ROOT/'exports'/'transaction_type_overview.csv').open()))
expected=[{'type':r['transaction_type'],'transactions':int(r['transaction_count']),'share':int(r['transaction_count'])/6362620,'amount':float(r['total_synthetic_amount']),'fraud':int(r['fraud_count']),'rate':int(r['fraud_count'])/int(r['transaction_count'])} for r in rows]
write(ROOT/'UX_EXPECTED_VALUES.json',{'tooltips':expected,'added_measures':list(measures),'relationships_sha256':hashlib.sha256((MODEL/'relationships.tmdl').read_bytes()).hexdigest()})
print('Enhanced isolated current project. Desktop validation required.')
