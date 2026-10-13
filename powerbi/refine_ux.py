from pathlib import Path
import json,re
R=Path(__file__).parent/'MONEYPRINT_UX.Report'/'definition'/'pages'/'a247c16910f06e0dae90'/'visuals'
def read(n):return json.loads((R/n/'visual.json').read_text(encoding='utf-8-sig'))
def save(n,v):(R/n/'visual.json').write_text(json.dumps(v,indent=2,ensure_ascii=False))
v=read('evidence')
lines=['About the Dashboard:','Fraud labels occur in CASH_OUT and TRANSFER in PaySim.','Synthetic simulator findings; not real banking behavior.','Type filters affect charts; step filters affect the trend.','Headline cards always describe the full dataset.']
v['visual']['objects']['general'][0]['properties']['paragraphs']=[{'textRuns':[{'value':s,'textStyle':{'fontFamily':'Georgia','fontSize':'10pt','fontWeight':'bold','color':'#474538'}}]} for s in lines]
save('evidence',v)
v=read('click_hint');v['position']['height']=18
v['visual']['visualContainerObjects']['padding']=[{'properties':{a:{'expr':{'Literal':{'Value':'0D'}}} for a in ['top','bottom','left','right']}}]
save('click_hint',v)
v=read('volume');v['visual']['objects']['labels'][0]['properties'].pop('labelPrecision',None)
save('volume',v)
p=Path(__file__).parent/'MONEYPRINT_UX.SemanticModel'/'definition'/'tables'/'executive_kpi_summary.tmdl'
s=p.read_text(encoding='utf-8-sig')
s=s.replace('\tmeasure \'Comparison Value\' =', '\tmeasure \'Comparison Value\' =',1)
start=s.index("\tmeasure 'Comparison Value'")
end=s.index('\n\tmeasure ',start+1)
block=s[start:end]
if 'formatStringDefinition' not in block:
    block += '\n\t\tformatStringDefinition = IF(SELECTEDVALUE(ux_metric_selector[Metric], "Transaction count") = "Synthetic amount", "0.00", "#,0")\n'
s=s[:start]+block+s[end:]
p.write_text(s,encoding='utf-8')
print('Refined compact panel and numeric dynamic formatting')
