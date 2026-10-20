"""Fetch only pinned public CycloneDX schemas; never fetch code or execute it."""
import hashlib
import json
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parent.parent
output = root / 'output/mit-sbom-schema'
output.mkdir(parents=True, exist_ok=True)
for item in json.loads((root / 'build/schema-lock.json').read_text(encoding='utf-8')):
    data = urllib.request.urlopen(item['url'], timeout=30).read()
    if hashlib.sha256(data).hexdigest() != item['sha256']:
        raise SystemExit('Schema hash mismatch: ' + item['name'])
    (output / item['name']).write_bytes(data)
print('Pinned CycloneDX schema hashes verified.')
