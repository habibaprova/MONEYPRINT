from pathlib import Path
import json,hashlib,zipfile,shutil,csv
R=Path(__file__).parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
protected=read(R/'QA_PROTECTED_HASHES.json')
assert all(sha(R.parent/p)==h for p,h in protected.items())
source=R/'interactivity'/'MONEYPRINT_UX.pbix'
z=zipfile.ZipFile(source);assert z.testzip() is None
pages=[read(R/'interactivity'/'MONEYPRINT_UX.Report'/'definition'/p.removeprefix('Report/definition/')) for p in z.namelist() if p.endswith('/page.json')]
assert [p['displayName'] for p in pages]==['Executive Overview','Investigation Desk','Behind the Score']
assert all(p['width']==1280 and p['height']==720 for p in pages)
visuals=[json.loads(z.read(n).decode('utf-8-sig')) for n in z.namelist() if n.endswith('/visual.json')]
assert len(visuals)==54
assert all(0<=v['position']['x'] and 0<=v['position']['y'] and v['position']['x']+v['position']['width']<=1280.1 and v['position']['y']+v['position']['height']<=720.1 for v in visuals)
baseline=R/'backups'/'interactivity_before_20261012'
if sha(R/'MONEYPRINT.pbix')!=sha(baseline/'MONEYPRINT.pbix'):
 # Desktop may save the original instance's UI state when releasing its file lock.
 # Preserve that complete saved state as well as the initial byte-exact backup.
 shutil.copy2(R/'MONEYPRINT.pbix',baseline/'MONEYPRINT_saved_original_before_replace.pbix')
model=R/'interactivity'/'MONEYPRINT_UX.SemanticModel'
original_model=R/'backups'/'interactivity_current_project'/'MONEYPRINT_UX.SemanticModel'
assert sha(model/'definition'/'relationships.tmdl')==sha(original_model/'definition'/'relationships.tmdl')
# Preserve reliability content exactly, allowing the two requested sidebar controls.
newreport=R/'interactivity'/'MONEYPRINT_UX.Report'
oldreport=R/'backups'/'interactivity_current_project'/'MONEYPRINT_UX.Report'
for old in (oldreport/'definition/pages/reliability/visuals').glob('*/visual.json'):
 if old.parent.name not in ['native_navigation','clear_slicers']:
  assert read(old)==read(newreport/old.relative_to(oldreport)),old.parent.name
for doc in ['FINAL_HANDOVER.md','VISUAL_QA_REPORT.md','POWER_BI_BUILD_GUIDE.md']:
 shutil.copy2(R/doc,baseline/doc)
shutil.copy2(source,R/'MONEYPRINT.pbix')
shutil.copytree(newreport,R/'MONEYPRINT.Report',dirs_exist_ok=True)
shutil.copytree(model,R/'MONEYPRINT.SemanticModel',dirs_exist_ok=True)
p=R/'MONEYPRINT.Report'/'definition.pbir';v=read(p);v['datasetReference']['byPath']['path']='../MONEYPRINT.SemanticModel';p.write_text(json.dumps(v,indent=2),encoding='utf-8')
record={'pbix':str(R/'MONEYPRINT.pbix'),'bytes':source.stat().st_size,'sha256':sha(source),'pages':[p['displayName'] for p in pages],'canvas':[1280,720],'visual_count':len(visuals),'protected_files':len(protected),'protected_hashes_unchanged':True,'relationships_unchanged':True,'reliability_content_unchanged':True,'source_csv_count':len(list((R/'exports').glob('*.csv'))),'native_tooltips':True,'switch_method':'disconnected three-row metadata selector + numeric SWITCH and dynamic format string','added_measures':read(R/'UX_EXPECTED_VALUES.json')['added_measures'],'desktop_pbix_reopen_verified':False,'limitations':['Transient mouse-down pressed appearance not captured; native state formatting checked in Desktop.']}
(R/'UX_VERIFICATION.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record,indent=2))
