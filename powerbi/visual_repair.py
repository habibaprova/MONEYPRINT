"""Focused visual repair of the Desktop-exported QA copy. Never edits frozen exports/models."""
import json, re, shutil, uuid, hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent
QA=ROOT/'visual_qa'
REPORT=QA/'MONEYPRINT_QA.Report/definition'
MODEL=QA/'MONEYPRINT_QA.SemanticModel/definition'
if not (ROOT/'backups/visual_QA_project_original').exists():
    shutil.copytree(QA,ROOT/'backups/visual_QA_project_original')
def lit(v):return {'expr':{'Literal':{'Value':str(v)}}}
def string(v):return lit("'"+v.replace("'","''")+"'")
def color(v):return {'solid':{'color':string(v)}}
def obj(**v):return [{'properties':v}]
def save(p,d):p.write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding='utf-8')
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def col(table,name):return {'Column':{'Expression':{'SourceRef':{'Entity':table}},'Property':name}}
def projection(table,name):return {'field':col(table,name),'queryRef':table+'.'+name,'nativeQueryRef':name,'displayName':name}
def title(v,s):v['visual']['visualContainerObjects']['title']=obj(show=lit('true'),text=string(s),fontSize=lit('10D'),fontColor=color('#474538'),fontFamily=string('Segoe UI Semibold'))
def position(v,x,y,w,h):v['position'].update(x=x,y=y,width=w,height=h)
def column(table,name,expr,sort=None):
    p=MODEL/'tables'/f'{table}.tmdl';s=p.read_text(encoding='utf-8-sig')
    imported={'transaction_amount_distribution':('amount_band_label','let Code = Text.Start([amount_band], 2) in if Code = "01" then "<1K" else if Code = "02" then "1–10K" else if Code = "03" then "10–100K" else if Code = "04" then "100–500K" else if Code = "05" then "500K–1M" else if Code = "06" then "1–5M" else if Code = "07" then "5–10M" else if Code = "08" then "10M+" else [amount_band]'),
        'dim_evaluation_window':('window_label','if Text.StartsWith([evaluation_window], "fold_") then "Fold " & Text.End([evaluation_window], 1) else "Exploratory 632–743"'),
        'split_distribution_comparison':('protocol_label','if [split_protocol] = "phase3_alternative_cumulative_row_split" then "Cumulative rows" else if [split_protocol] = "phase3_original_step_split" then "Original steps" else [split_protocol]'),
        'phase4_investigation_capacity':('budget_label','if [capacity_measure] = "top_100" then "Top 100" else if [capacity_measure] = "top_500" then "Top 500" else "Alert rate 0.5%"')}
    source,mexpr=imported[table]
    if table=='phase4_investigation_capacity' and name=='Window Label':
        source,mexpr='window_label','if Text.StartsWith([evaluation_window], "fold_") then "Fold " & Text.End([evaluation_window], 1) else "Exploratory 632–743"'
    if f'\t\tsourceColumn: {source}' in s:return
    s=re.sub(r"\n\tcolumn '"+re.escape(name)+r"'.*?(?=\n\t(?:column|partition|annotation)|\Z)",'',s,flags=re.S)
    block=f"\n\tcolumn '{name}'\n\t\tdataType: string\n\t\tsummarizeBy: none\n\t\tsourceColumn: {source}\n\t\tlineageTag: {uuid.uuid4()}\n"
    if sort:block+=f'\t\tsortByColumn: {sort}\n'
    s=s.replace('\n\tpartition ',block+'\n\tpartition ',1)
    match=re.search(r'\n\t\t\t\tin\n\t\t\t\t    (Typed|#"Changed Type"|WithVisualLabel)',s)
    assert match,table
    prior=match.group(1)
    step='WithWindowLabel' if prior=='WithVisualLabel' else 'WithVisualLabel'
    addition=f',\n\t\t\t\t    {step} = Table.AddColumn({prior}, "{source}", each {mexpr}, type text)\n\t\t\t\tin\n\t\t\t\t    {step}'
    s=s[:match.start()]+addition+s[match.end():]
    p.write_text(s,encoding='utf-8')
column('transaction_amount_distribution','Amount Band Label','SWITCH(LEFT(transaction_amount_distribution[amount_band], 2), "01", "<1K", "02", "1–10K", "03", "10–100K", "04", "100–500K", "05", "500K–1M", "06", "1–5M", "07", "5–10M", "08", "10M+", transaction_amount_distribution[amount_band])','amount_band')
column('dim_evaluation_window','Window Label','IF(LEFT(dim_evaluation_window[evaluation_window], 5) = "fold_", "Fold " & RIGHT(dim_evaluation_window[evaluation_window], 1), "Exploratory 632–743")','evaluation_window')
column('split_distribution_comparison','Protocol Label','SWITCH(split_distribution_comparison[split_protocol], "phase3_alternative_cumulative_row_split", "Cumulative rows", "phase3_original_step_split", "Original steps", split_distribution_comparison[split_protocol])','split_protocol')
column('phase4_investigation_capacity','Budget Label','','capacity_measure')
column('phase4_investigation_capacity','Window Label','','evaluation_window')
for p in (MODEL/'tables').glob('*.tmdl'):
    s=p.read_text(encoding='utf-8-sig')
    s=s.replace('Encoding=1252','Encoding=65001').replace('QuoteStyle=QuoteStyle.None','QuoteStyle=QuoteStyle.Csv')
    p.write_text(s,encoding='utf-8')

qt='phase4_selected_model_investigation_examples'
p=MODEL/'tables'/f'{qt}.tmdl';s=p.read_text(encoding='utf-8-sig')
if '\tcolumn contribution_display' not in s:
    block=f'\n\tcolumn contribution_display\n\t\tdataType: string\n\t\tsummarizeBy: none\n\t\tsourceColumn: contribution_display\n\t\tlineageTag: {uuid.uuid4()}\n'
    s=s.replace('\n\tpartition ',block+'\n\tpartition ',1)
    old='\t\t\t\t    })\n\t\t\t\tin\n\t\t\t\t    Typed'
    new='''\t\t\t\t    }),
\t\t\t\t    WithContributionText = Table.AddColumn(Typed, "contribution_display", each
\t\t\t\t        let Items = try Json.Document([top_model_contributions]) otherwise null
\t\t\t\t        in if Value.Is(Items, type list) then Text.Combine(List.Transform(Items, (Item) =>
\t\t\t\t            Text.From(Item[input]) & ": " & Number.ToText(Number.From(Item[standardized_log_odds_contribution]), "+0.00;-0.00;0.00", "en-US")), "#(lf)")
\t\t\t\t        else null, type text)
\t\t\t\tin
\t\t\t\t    WithContributionText'''
    assert old in s,'Expected existing typed CSV source'
    s=s.replace(old,new);p.write_text(s,encoding='utf-8')

p=MODEL/'tables/executive_kpi_summary.tmdl';s=p.read_text(encoding='utf-8-sig')
s=re.sub(r"(\tmeasure 'Total Synthetic Amount' =[^\n]+\n\t\tformatString: )[^\n]+",r'\g<1>#,0.00',s)
s=s.replace('FORMAT([Total Synthetic Amount] / 1000000000000, "0.00") & "T"','FORMAT([Total Synthetic Amount] / 1000000000000, "0.000") & " T"')
s=s.replace(f'SELECTEDVALUE({qt}[top_model_contributions])',f'COALESCE(SELECTEDVALUE({qt}[contribution_display]), "No saved contributions available")')
s=s.replace('"Associational contributions; not causal explanations."','"Select one case. Contributions are associational, not causal."')
p.write_text(s,encoding='utf-8')

layouts={}; count=0
for page in (REPORT/'pages').iterdir():
    if not page.is_dir():continue
    pagefile=page/'page.json';pd=load(pagefile);pd['displayOption']='FitToPage';save(pagefile,pd)
    vs={f.parent.name:(f,load(f)) for f in (page/'visuals').glob('*/visual.json')}
    for name,(f,v) in vs.items():
        visual=v['visual'];objects=visual.setdefault('objects',{});container=visual.setdefault('visualContainerObjects',{})
        if visual['visualType']=='card':
            objects['labels']=obj(fontSize=lit('22D'),color=color('#474538'),labelDisplayUnits=lit('1D'))
        if visual['visualType']=='slicer':
            objects['items']=obj(fontSize=lit('10D'),fontColor=color('#474538'))
            if name in ['window','capacity']:
                objects['selection']=obj(singleSelect=lit('true'),selectAllCheckboxEnabled=lit('false'))
        if visual['visualType'].endswith('Chart') or visual['visualType'] in ['columnChart','lineChart']:
            objects.setdefault('categoryAxis',obj())[0]['properties'].update(fontSize=lit('9D'),showAxisTitle=lit('false'))
            objects.setdefault('valueAxis',obj())[0]['properties'].update(fontSize=lit('8D'),showAxisTitle=lit('false'))
            objects.setdefault('legend',obj())[0]['properties'].update(fontSize=lit('9D'))
        if name=='native_navigation':
            objects['fill']=[{'selector':{'id':state},'properties':{'show':lit('true'),'fillColor':color('#FAF9EF' if state=='selected' else '#D5CE91'),'transparency':lit('0D')}} for state in ['default','selected','hover','press']]
            objects['outline']=[{'selector':{'id':'selected'},'properties':{'show':lit('true'),'lineColor':color('#BC858A'),'weight':lit('2D')}},{'selector':{'id':'default'},'properties':{'show':lit('false')}}]
        if name=='clear_slicers':
            objects['fill']=[{'selector':{'id':state},'properties':{'show':lit('true'),'fillColor':color('#FAF9EF'),'transparency':lit('0D')}} for state in ['default','hover','press']]
            objects['outline']=obj(show=lit('true'),lineColor=color('#9D9D78'),weight=lit('1D'))
            objects['shape']=[{'selector':{'id':'default'},'properties':{'tileShape':string('rectangle'),'roundEdge':lit('0D')}}]
            for x in objects.get('text',[]):x['properties'].update(fontColor=color('#474538'),fontSize=lit('10D'))
        if name=='footer':
            position(v,208,694 if page.name=='a247c16910f06e0dae90' else 687,1048,24)
        if page.name=='a247c16910f06e0dae90':
            if name=='kpi_3':title(v,'Synthetic amount (trillion units)')
            if name in ['volume','trend']:position(v,208 if name=='volume' else 730,176,510 if name=='volume' else 526,145)
            if name in ['value','fraud']:position(v,208 if name=='value' else 730,327,510 if name=='value' else 526,145)
            if name in ['amount','evidence']:position(v,208 if name=='amount' else 730,478,510 if name=='amount' else 526,145)
            if name in ['type_filter','step_filter']:position(v,208 if name=='type_filter' else 730,632,510 if name=='type_filter' else 526,60)
            if name in ['volume','fraud']:
                objects['labels']=obj(show=lit('true'),fontSize=lit('8D'),labelDisplayUnits=lit('1D'),labelPrecision=lit('0D'))
                for projection_ in visual['query']['queryState']['Y']['projections']:projection_['format']='#,0'
            if name=='value':
                title(v,'Synthetic amount by type (billions of units)')
                objects['labels']=obj(show=lit('true'),fontSize=lit('8D'),labelDisplayUnits=lit('1000000000D'),labelPrecision=lit('2D'))
                objects['valueAxis'][0]['properties'].update(labelDisplayUnits=lit('1000000000D'),labelPrecision=lit('0D'))
                for projection_ in visual['query']['queryState']['Y']['projections']:projection_['format']='#,0.00'
            if name=='amount':
                title(v,'Transaction amount bands • synthetic units')
                visual['query']['queryState']['Category']['projections']=[projection('transaction_amount_distribution','Amount Band Label')]
                visual['query']['queryState']['Tooltips']={'projections':[projection('transaction_amount_distribution','amount_band')]}
                objects['categoryAxis'][0]['properties'].update(fontSize=lit('8D'),show=lit('true'))
                objects['labels']=obj(show=lit('true'),fontSize=lit('8D'),labelDisplayUnits=lit('1000000D'),labelPrecision=lit('2D'))
        if page.name=='investigation':
            if name=='window':
                visual['query']['queryState']['Values']['projections']=[projection('phase4_investigation_capacity','Window Label')]
            if name=='capacity':
                visual['query']['queryState']['Values']['projections']=[projection('phase4_investigation_capacity','Budget Label')]
            if name=='queue':
                position(v,208,168,690,356)
                objects['values']=obj(wordWrap=lit('false'),fontColor=color('#474538'))
                objects['columnHeaders']=obj(wordWrap=lit('false'),fontColor=color('#474538'),fontSize=lit('10D'))
                for q in visual['query']['queryState']['Values']['projections']:
                    if q.get('displayName')=='Amount':q['displayName']='Amount (units)'
            if name=='contributions':
                title(v,'Saved contributions • Δ log-odds')
                objects['grid']=obj(textSize=lit('9D'),rowPadding=lit('1D'))
                objects['values']=obj(wordWrap=lit('true'),fontColor=color('#474538'))
            if name=='topk':
                title(v,'Saved queue ranks · set upper bound K')
                position(v,208,528,690,80)
                objects['header']=obj(show=lit('false'))
        if page.name=='reliability':
            if name=='windows':
                visual['query']['queryState']['Values']['projections'][0]=projection('dim_evaluation_window','Window Label')
                objects['grid']=obj(textSize=lit('9D'),rowPadding=lit('0D'))
                objects['columnHeaders']=obj(fontSize=lit('9D'),wordWrap=lit('false'))
            if name=='split':
                visual['query']['queryState']['Series']['projections']=[projection('split_distribution_comparison','Protocol Label')]
        p_=v['position'];assert p_['x']>=0 and p_['y']>=0 and p_['x']+p_['width']<=1280 and p_['y']+p_['height']<=720,(page.name,name)
        save(f,v);count+=1
    layouts[pd['displayName']]=[{'name':v['name'],'position':v['position']} for _,v in vs.values()]
save(ROOT/'VISUAL_QA_LAYOUT.json',layouts)
print(f'Repaired {count} preserved visuals. Relationships and frozen data unchanged. Desktop refresh/QA required.')
