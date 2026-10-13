"""Read-only frozen evidence and final PBIX checks; writes only QA records."""
import csv, hashlib, json, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

protected = json.loads((ROOT / 'QA_PROTECTED_HASHES.json').read_text())
changed = [p for p, digest in protected.items() if sha(PROJECT / p) != digest]
assert not changed, changed
manifest = json.loads((ROOT / 'exports/export_manifest.json').read_text())
for name, spec in manifest['files'].items():
    path = ROOT / 'exports' / name
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == spec['rows'] and path.stat().st_size == spec['bytes'], name
source_checks = {}
for label, key in [('model', 'source_model'), ('phase4_report', 'source_phase4_report'), ('feature_parquet', 'source_feature_parquet')]:
    path = Path(manifest[key])
    digest_key = 'source_parquet_sha256' if label=='feature_parquet' else key + '_sha256'
    source_checks[label] = sha(path) == manifest[digest_key]
assert all(source_checks.values()), source_checks
pbix = ROOT / 'MONEYPRINT.pbix'
with zipfile.ZipFile(pbix) as z:
    assert z.testzip() is None
    pages = []
    for name in z.namelist():
        if name.startswith('Report/definition/pages/') and name.endswith('/page.json'):
            p = json.loads(z.read(name).decode('utf-8-sig'))
            prefix = name.rsplit('/', 1)[0] + '/visuals/'
            visuals = [n for n in z.namelist() if n.startswith(prefix) and n.endswith('/visual.json')]
            for n in visuals:
                v = json.loads(z.read(n).decode('utf-8-sig'))['position']
                assert v['x']>=0 and v['y']>=0 and v['x']+v['width']<=1280 and v['y']+v['height']<=720, n
            pages.append({'name': p['displayName'], 'width': p['width'], 'height': p['height'], 'visuals': len(visuals)})
assert len(pages) == 3 and sum(p['visuals'] for p in pages) == 50
assert all(p['width'] == 1280 and p['height'] == 720 for p in pages)
result = {'pbix': str(pbix), 'bytes': pbix.stat().st_size, 'sha256': sha(pbix), 'zip_integrity': 'passed', 'pages': pages, 'protected_files_checked': len(protected), 'changed_protected_files': changed, 'manifest_csv_checks': len(manifest['files']), 'frozen_source_hashes_match': source_checks}
(ROOT / 'PBIX_VERIFICATION.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
