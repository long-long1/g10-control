"""Evidence-only license review. No network, device access or license guessing."""
import hashlib
from importlib import metadata
import json
from pathlib import Path
import shutil
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def supplement(root, target, inventory):
    index = json.loads((root / 'desktop-ui/licenses/upstream/index.json').read_text(encoding='utf-8'))
    for item in index:
        source = root / item['path']
        source.resolve().relative_to((root / 'desktop-ui/licenses').resolve())
        if digest(source) != item['sha256']:
            raise RuntimeError('Supplemental license hash mismatch: ' + item['path'])
        dest = target / 'licenses/upstream' / source.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        for row in inventory['python']:
            if row['name'].lower() in {n.lower() for n in item['components']}:
                row['collected_files'].append(dest.relative_to(target).as_posix())
                row['missing_license_text'] = False
                row['upstream_review'] = item
    shutil.copytree(root / 'desktop-ui/licenses/sources', target / 'licenses/sources')
    proof = json.loads((target / 'licenses/sources/pystray-source-evidence.json').read_text(encoding='utf-8'))
    if digest(target / 'licenses/sources/pystray-0.19.5.tar.gz') != proof['sha256']:
        raise RuntimeError('pystray source archive hash mismatch')
    if not proof['files'] or not all(f['equal'] for f in proof['files']):
        raise RuntimeError('pystray source correspondence not verified')
    (target / 'licenses/upstream/index.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')
    # Preserve installed package data notices (Tcl/Tk license.terms etc.), too.
    for file in (target / '_internal').rglob('*'):
        if file.is_file() and file.name.lower() in {'license.terms', 'notice.txt'}:
            dest = target / 'licenses/bundled-data' / file.relative_to(target / '_internal')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, dest)


def write_review(root, target, inventory):
    """Every SBOM component receives a review row, including uninstalled tools."""
    bom = json.loads((target / 'sbom.cdx.json').read_text(encoding='utf-8'))
    supplements = json.loads((target / 'licenses/upstream/index.json').read_text(encoding='utf-8'))
    python = {r['name'].lower(): r for r in inventory['python']}
    npm = {(r['name'], r['version']): r for r in inventory['npm']}
    binary_sources = {}
    for dist in metadata.distributions():
        for relative in dist.files or []:
            if Path(relative).suffix.lower() in {'.dll', '.pyd', '.exe'}:
                source = Path(dist.locate_file(relative))
                if source.is_file():
                    binary_sources.setdefault(source.name.lower(), []).append((dist.metadata['Name'], dist.version, source))
    rows = []
    for c in bom['components']:
        ref = c['bom-ref']
        row = dict(component_ref=ref, name=c['name'], version=c.get('version'),
                   bundled=None, spdx=None, official_sources=[], license_texts=[],
                   copyright_notice_required='review upstream terms; preserve notices',
                   source_replacement_relink_required='not established; review terms',
                   status='review-required', risks=[])
        if ref.startswith('pkg:pypi/'):
            item = python[c['name'].lower()]
            row['bundled'] = 'PYZ namespace match' if item['bundled_namespace_match'] else 'build environment; no PYZ match (not proof of absence)'
            row['license_texts'] = item['collected_files']
            dist = metadata.distribution(c['name'])
            row['official_sources'] = (dist.metadata.get_all('Project-URL') or []) + [f'https://pypi.org/project/{c["name"]}/{c["version"]}/']
            row['declared_license'] = item['declared_license']
            if item.get('upstream_review'):
                extra = item['upstream_review']
                row.update(spdx=extra['spdx'], status=extra['status'])
                row['official_sources'].append(extra['source'])
                row['risks'].append(extra['risk'])
            if c['name'].lower() == 'pystray':
                row.update(spdx='LGPL-3.0-or-later', status='source-matched-recombination-review-pending',
                           source_replacement_relink_required='LGPL 4(d)(0) proposed: full library source + application source/build materials; modified rebuild evidence required')
                row['license_texts'].append('licenses/sources/pystray-0.19.5.tar.gz')
                row['risks'].append('Embedded in both PYZ archives; adjacent .py replacement not established. See LGPL-PYSTRAY.md; owner grant and final legal review pending.')
            if not row['license_texts']:
                row['risks'].append('Full license text missing')
            if c['name'].lower() in {'numpy', 'pillow', 'sounddevice', 'pywebview', 'pythonnet', 'clr_loader'}:
                row['risks'].append('Distribution license text retained; embedded native/static dependencies need separate attribution')
        elif ref.startswith('pkg:npm/'):
            props = {v['name']: v['value'] for v in c['properties']}
            item = npm.get((c['name'], c['version']))
            row['bundled'] = item['scope'] + '; exact tree-shaken presence unresolved' if item else 'uninstalled lock alternative; not bundled'
            row['official_sources'] = [f'https://registry.npmjs.org/{c["name"]}/{c["version"]}']
            row['license_texts'] = item['collected_files'] if item else []
            row['declared_license'] = c.get('licenses', [])
            row['status'] = 'text-collected-review-pending' if row['license_texts'] else 'uninstalled-tooling-text-not-collected'
            row['risks'].append('Lock declaration is not independent legal verification; installed=' + props['g10:installed'])
        else:
            file = target / c['name']
            row.update(bundled=True, sha256=digest(file), origin_matches=[])
            for name, version, source in binary_sources.get(file.name.lower(), []):
                if digest(source) == row['sha256']:
                    row['origin_matches'].append({'distribution': name, 'version': version})
                    row['license_texts'].extend(python.get(name.lower(), {}).get('collected_files', []))
                    row['official_sources'].append(f'https://pypi.org/project/{name}/{version}/')
            # Python installation exact-byte attribution; never record personal paths.
            for folder in ('', 'DLLs'):
                source = Path(sys.base_prefix) / folder / file.name
                if source.is_file() and digest(source) == row['sha256']:
                    row['origin_matches'].append({'distribution': 'CPython installation', 'version': sys.version.split()[0]})
                    row['license_texts'].append('licenses/Python-3.12-LICENSE.txt')
                    row['official_sources'].append('https://www.python.org/downloads/release/python-31210/')
            try:
                import pefile
                pe = pefile.PE(str(file), fast_load=False)
                for block in getattr(pe, 'FileInfo', []):
                    for info in block:
                        for table in getattr(info, 'StringTable', []):
                            values = {k.decode(): v.decode(errors='replace') for k, v in table.entries.items()}
                            row['version'] = values.get('FileVersion', row['version'])
                pe.close()
            except (ImportError, OSError, ValueError):
                row['risks'].append('PE version unavailable')
            for extra in supplements:
                match = (c['name'] in extra.get('matching_binaries', [])
                         or ('PortAudio' in extra['components'] and file.name == 'libportaudio64bit.dll')
                         or ('Tcl' in extra['components'] and file.name == 'tcl86t.dll')
                         or ('Tk' in extra['components'] and file.name == 'tk86t.dll'))
                if match:
                    row['license_texts'].append('licenses/upstream/' + Path(extra['path']).name)
                    row['official_sources'].append(extra['source'])
                    row['risks'].append(extra['risk'])
            row['status'] = 'origin-matched-native-terms-pending' if row['origin_matches'] else 'unresolved-native-origin'
            row['risks'].append('Container origin is not complete static dependency attribution; SDK/compiler/runtime notices and rights pending')
        row['license_texts'] = sorted(set(row['license_texts']))
        rows.append(row)
    report = {'redistribution_ready': False, 'component_count': len(rows), 'components': rows,
              'limitations': 'Conservative build/runtime superset; every SBOM component retained. SPDX only when corroborated. Unknown versions/rights remain null.'}
    (target / 'license-review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    lines = ['# Third-party license review', '', 'redistribution_ready=false. Every SBOM component is retained; metadata is not legal clearance.', '',
             '| Component | Version | Bundled / scope | SPDX (verified only) | Sources | Texts | Notice | Source/relink | Status | Risks |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in rows:
        lines.append('| ' + ' | '.join(cell(r[k]) for k in ('name','version','bundled','spdx','official_sources','license_texts','copyright_notice_required','source_replacement_relink_required','status','risks')) + ' |')
    (target / 'THIRD-PARTY-LICENSES.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report
