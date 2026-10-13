from pathlib import Path
import json,copy
ROOT=Path(__file__).parent
R=ROOT/'MONEYPRINT_UX.Report'/'definition'/'pages'
p=R/'investigation'/'visuals'/'capacity'/'visual.json';v=json.loads(p.read_text(encoding='utf-8-sig'))
v['position'].update(y=114,height=46)
v['visual']['visualContainerObjects']['title'][0]['properties']['show']={'expr':{'Literal':{'Value':'false'}}}
p.write_text(json.dumps(v,indent=2),encoding='utf-8')
v=json.loads((R/'a247c16910f06e0dae90'/'visuals'/'selected_type'/'visual.json').read_text(encoding='utf-8-sig'))
v['name']='budget_status';v['position'].update(x=400,y=90,width=260,height=24,z=54,tabOrder=54)
for item in v['visual']['query']['queryState']['Values']['projections']:
 item['field']['Measure']['Property']='Budget Status'
 item['queryRef']='executive_kpi_summary.Budget Status'
 item['displayName']=item['nativeQueryRef']='Budget Status'
v['visual']['objects']['labels'][0]['properties']['fontSize']={'expr':{'Literal':{'Value':'9D'}}}
p=R/'investigation'/'visuals'/'budget_status'/'visual.json';p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(v,indent=2),encoding='utf-8')
p=ROOT/'MONEYPRINT_UX.SemanticModel'/'definition'/'tables'/'phase4_investigation_capacity.tmdl'
s=p.read_text(encoding='utf-8-sig').replace('Alert rate 0.5%','0.5%');p.write_text(s,encoding='utf-8')
p=ROOT/'MONEYPRINT_UX.SemanticModel'/'definition'/'tables'/'executive_kpi_summary.tmdl'
s=p.read_text(encoding='utf-8-sig').replace('"Budget: " & SELECTEDVALUE(phase4_investigation_capacity[Budget Label], "Top 500 (default)")','"Budget: " & IF(SELECTEDVALUE(phase4_investigation_capacity[Budget Label]) = "0.5%", "Alert rate 0.5%", SELECTEDVALUE(phase4_investigation_capacity[Budget Label], "Top 500 (default)"))')
p.write_text(s,encoding='utf-8')
print('Budget caption is a separate filter-responsive card; compact 0.5% display label')
