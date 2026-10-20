"""Deterministic SBOM and evidence from frozen output, installed metadata and locks.

No network, hardware, license decisions, archive creation or publishing.
CycloneDX 1.6 records license declarations as names, never guessed SPDX IDs.
"""
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import quote


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def python_lock(path):
    return {normalized(name): version for line in path.read_text(encoding='utf-8').splitlines()
            if line and not line.startswith('#') for name, version in [line.split('==', 1)]}


def write_evidence(root, target, inventory, modules):
    locked = python_lock(root / 'requirements-build.lock.txt')
    for name in ('requirements.txt', 'requirements-build.txt'):
        direct = {normalized(package): version for line in (root / name).read_text(encoding='utf-8').splitlines()
                  if line.strip() and not line.startswith(('#', '-r '))
                  for package, version in [line.split('==', 1)]}
        if any(locked.get(package) != version for package, version in direct.items()):
            raise RuntimeError('Direct dependency/build lock mismatch: ' + name)
    installed = {normalized(d.metadata['Name']): d.version for d in metadata.distributions()}
    drift = [{'name': name, 'locked': version, 'installed': installed.get(name)}
             for name, version in sorted(locked.items()) if installed.get(name) != version]
    unlocked = sorted(set(installed) - set(locked) - {'pip'})
    if drift or unlocked:
        raise RuntimeError(f'Python build lock mismatch: {drift}; unlocked: {unlocked}')
    components = []
    for row in inventory['python']:
        name, version = row['name'], row['version']
        ref = f'pkg:pypi/{normalized(name)}@{version}'
        component = {'type': 'library', 'bom-ref': ref, 'name': name, 'version': version, 'purl': ref,
                     'properties': [{'name': 'g10:bundled-namespace-match', 'value': str(row['bundled_namespace_match']).lower()},
                                    {'name': 'g10:license-text-missing', 'value': str(row['missing_license_text']).lower()}]}
        if row['declared_license']:
            component['licenses'] = [{'license': {'name': row['declared_license']}}]
        components.append(component)
    lock = json.loads((root / 'desktop-ui/web/package-lock.json').read_text(encoding='utf-8'))
    for relative, item in sorted(lock['packages'].items()):
        if not relative:
            continue
        name = relative.split('node_modules/')[-1]
        ref = f'pkg:npm/{quote(name, safe="/")}@{item["version"]}'
        package_file = root / 'desktop-ui/web' / relative / 'package.json'
        if package_file.is_file():
            actual = json.loads(package_file.read_text(encoding='utf-8'))
            if actual['version'] != item['version']:
                raise RuntimeError(f'npm lock mismatch: {relative}')
        # All lock entries retained, including uninstalled platform alternatives.
        component = {'type': 'library', 'bom-ref': ref, 'name': name, 'version': item['version'], 'purl': ref,
                     'properties': [{'name': 'g10:lock-path', 'value': relative},
                                    {'name': 'g10:installed', 'value': str(package_file.is_file()).lower()},
                                    {'name': 'g10:lock-integrity', 'value': item.get('integrity', '')},
                                    {'name': 'g10:scope', 'value': 'build/optional' if item.get('dev') else 'browser dependency; tree-shaking not resolved'}]}
        if item.get('license'):
            component['licenses'] = [{'license': {'name': item['license']}}]
        components.append(component)
    # Binary presence/hash is hard evidence. Do not invent upstream versions or
    # claim every embedded library can be inferred from its containing DLL.
    native = []
    for file in sorted((target / '_internal').rglob('*')):
        if file.suffix.lower() not in {'.dll', '.pyd', '.exe'}:
            continue
        relative = file.relative_to(target).as_posix()
        digest = sha256(file)
        native.append({'path': relative, 'sha256': digest, 'license_review': 'pending exact binary provenance'})
        components.append({'type': 'file', 'bom-ref': 'file:' + relative, 'name': relative,
                           'hashes': [{'alg': 'SHA-256', 'content': digest}]})
    # Duplicate purls are possible in nested npm trees; retain distinct refs.
    seen = set()
    for index, component in enumerate(components):
        ref = component['bom-ref']
        if ref in seen:
            component['bom-ref'] = ref + f'#instance-{index}'
        seen.add(component['bom-ref'])
    bom = {'bomFormat': 'CycloneDX', 'specVersion': '1.6', 'version': 1,
           'metadata': {'component': {'type': 'application', 'name': 'G10 Control', 'version': '0.1.0-beta'},
                        'properties': [{'name': 'g10:redistribution-ready', 'value': 'false'},
                                       {'name': 'g10:limitations', 'value': 'Build/runtime superset; namespace evidence is not complete native attribution. Dependency graph and legal clearance pending.'}]},
           'components': components}
    evidence = {'python_lock_matched': True, 'npm_lock_checked': True,
                'inputs': {name: sha256(root / name) for name in
                           ('requirements.txt', 'requirements-build.txt', 'requirements-build.lock.txt', 'desktop-ui/web/package-lock.json', 'build/portable_onedir.spec')},
                'pyz_modules': sorted(modules), 'native_files': native,
                'license_texts': [{'path': f.relative_to(target).as_posix(), 'sha256': sha256(f)}
                                 for f in sorted((target / 'licenses').rglob('*')) if f.is_file()],
                'redistribution_ready': False}
    # No absolute build-machine paths or private runtime inputs in the record.
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode('utf-8').split('\0')
    evidence['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    evidence['source_inputs'] = {name: sha256(root / name) for name in sorted(tracked)
                                 if name and (root / name).is_file() and
                                 (name.endswith(('.py', '.ts', '.tsx', '.css', '.spec')) or name in
                                  {'desktop-ui/web/index.html', 'desktop-ui/web/package.json'})}
    evidence['source_materials'] = {name: sha256(root / name) for name in sorted(tracked)
                                    if name and (root / name).is_file()}
    for name, value in [('sbom.cdx.json', bom), ('build-evidence.json', evidence)]:
        (target / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# Third-party license inventory', '',
             'Installed build environment; declarations are not legal clearance. redistribution_ready=false.', '',
             '| Ecosystem | Package | Version | Bundled evidence / scope | Declared license | Text missing |',
             '| --- | --- | --- | --- | --- | --- |']
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    for ecosystem in ('python', 'npm'):
        for row in inventory[ecosystem]:
            scope = ('PYZ namespace match' if row.get('bundled_namespace_match') else 'build environment; no PYZ match') if ecosystem == 'python' else row['scope']
            lines.append('| ' + ' | '.join(cell(value) for value in
                         (ecosystem, row['name'], row['version'], scope, row['declared_license'] or 'UNKNOWN', row['missing_license_text'])) + ' |')
    lines.extend(['', 'Native DLL/PYD/EXE identities and SHA256: build-evidence.json / sbom.cdx.json.',
                  'Static binary dependencies still require provenance and license review; see BETA-LICENSE-REVIEW.md.',
                  'Uninstalled npm lock alternatives are also listed in sbom.cdx.json.', ''])
    (target / 'THIRD-PARTY-LICENSES.md').write_text('\n'.join(lines), encoding='utf-8')
    return {'components': len(components), 'native_files': len(native)}
