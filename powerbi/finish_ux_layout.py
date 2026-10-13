from pathlib import Path
import json
ROOT=Path(__file__).parent/'MONEYPRINT_UX.Report'/'definition'/'pages'
def load(page,name):
 p=ROOT/page/'visuals'/name/'visual.json'
 return p,json.loads(p.read_text(encoding='utf-8-sig'))
def dump(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
def lit(v):return {'expr':{'Literal':{'Value':v}}}
p,v=load('investigation','capacity');v['position'].update(x=400,width=260,height=70)
v['visual']['objects']['header'][0]['properties']['show']=lit('false')
v['visual']['visualContainerObjects']['title'][0]['properties'].update(show=lit('true'),fontSize=lit('9D'),text={'expr':{'Measure':{'Expression':{'SourceRef':{'Entity':'executive_kpi_summary'}},'Property':'Budget Status'}}})
dump(p,v)
p,v=load('investigation','window');v['position']['width']=180;dump(p,v)
p,v=load('a247c16910f06e0dae90','type_filter')
v['visual']['objects'].setdefault('selection',[{'properties':{}}])[0]['properties'].update(singleSelect=lit('false'),multiSelect=lit('false'))
dump(p,v)
print('Budget width, default status, and type multi-selection refined')
