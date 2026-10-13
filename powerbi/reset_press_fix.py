from pathlib import Path
import json
R=Path(__file__).parent/'MONEYPRINT_UX.Report'/'definition'/'pages'
def color(c):return {'solid':{'color':{'expr':{'Literal':{'Value':"'"+c+"'"}}}}}
for page in ['a247c16910f06e0dae90','investigation','reliability']:
 p=R/page/'visuals'/'clear_slicers'/'visual.json'
 v=json.loads(p.read_text(encoding='utf-8-sig'))
 for a in v['visual']['objects']['fill']:
  if a.get('selector',{}).get('id')=='selected':a['properties']['fillColor']=color('#474538')
 for a in v['visual']['objects']['text']:
  if a.get('selector',{}).get('id')=='selected':a['properties']['fontColor']=color('#FAF9EF')
 p.write_text(json.dumps(v,indent=2),encoding='utf-8')
