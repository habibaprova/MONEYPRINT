"""Deliver the Desktop-saved candidate after archive/backup guards."""
import json, hashlib, shutil, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QA = ROOT / 'visual_qa'
candidate = QA / 'MONEYPRINT_QA.pbix'
with zipfile.ZipFile(candidate) as z:
    assert z.testzip() is None
    pages = [json.loads(z.read(n).decode('utf-8-sig')) for n in z.namelist() if n.startswith('Report/definition/pages/') and n.endswith('/page.json')]
    visuals = [n for n in z.namelist() if n.startswith('Report/definition/pages/') and n.endswith('/visual.json')]
    assert len(pages) == 3 and len(visuals) == 50
    assert all(p['width']==1280 and p['height']==720 for p in pages)
primary = ROOT / 'MONEYPRINT.pbix'
backup = ROOT / 'backups/MONEYPRINT_before_visual_QA_20261012.pbix'
assert hashlib.sha256(primary.read_bytes()).digest() == hashlib.sha256(backup.read_bytes()).digest(), 'Primary changed since backup; do not overwrite'
shutil.copy2(candidate, primary)
project_backup = ROOT / 'backups/main_project_before_visual_QA_sync'
project_backup.mkdir(exist_ok=True)
for suffix in ['Report', 'SemanticModel']:
    dest = ROOT / ('MONEYPRINT.' + suffix)
    if dest.exists() and not (project_backup / dest.name).exists():
        shutil.copytree(dest, project_backup / dest.name)
    shutil.copytree(QA / ('MONEYPRINT_QA.' + suffix), dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns('cache_before_*.abf'))
ref = ROOT / 'MONEYPRINT.Report/definition.pbir'
data = json.loads(ref.read_text(encoding='utf-8-sig'))
data['datasetReference']['byPath']['path'] = '../MONEYPRINT.SemanticModel'
ref.write_text(json.dumps(data, indent=2), encoding='utf-8')
project = json.loads((QA / 'MONEYPRINT_QA.pbip').read_text(encoding='utf-8-sig'))
project['artifacts'][0]['report']['path'] = 'MONEYPRINT.Report'
(ROOT / 'MONEYPRINT.pbip').write_text(json.dumps(project, indent=2), encoding='utf-8')
print('Verified candidate archive; delivered primary PBIX and synchronized editable project. Desktop reopen still required.')
