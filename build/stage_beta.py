"""Allowlist a LOCAL-ONLY candidate, collect notices and audit files/embedded code.

Never creates an archive or uploads anything. Missing license decisions remain
explicit blockers even when the privacy and content audit passes.
"""
import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import shutil
import sys
import zipfile
try:
    from .release_evidence import write_evidence
    from .license_review import supplement, write_review
except ImportError:
    from release_evidence import write_evidence
    from license_review import supplement, write_review

FORBIDDEN_PARTS = {'.git', '.venv', 'node_modules', 'output', '__pycache__'}
FORBIDDEN_NAMES = {'local-settings.json', 'settings.json', 'route-proof.json', 'setup-progress.json',
                   'endpoints.json', 'route-test.json', 'defaults-after.json', '.env'}
FORBIDDEN_SUFFIXES = {'.log', '.jsonl', '.wav', '.pcm', '.adpcm', '.dmp', '.mp3', '.mp4'}
ROOT_ALLOWED = {'G10-Control.exe', 'G10-AudioBridge.exe', '_internal', 'portable.marker', 'data', 'licenses',
                'README-PORTABLE.zh-CN.md', 'ACCEPTANCE-WIN11-X64.md', 'BETA-LICENSE-REVIEW.md',
                'LICENSE_STATUS.md', 'THIRD-PARTY-NOTICES.md', 'license-inventory.json', 'package-audit.json', 'manifest.json',
                'sbom.cdx.json', 'build-evidence.json', 'accept_win11.ps1', 'RELEASE-NOTES.zh-CN.md', 'THIRD-PARTY-LICENSES.md',
                'LICENSE', 'LICENSE-MIT-DRAFT.txt', 'release-metadata.json', 'LGPL-PYSTRAY.md', 'RELEASE-PROCESS.md', 'license-review.json'}


def audit_files(directory, identities=None):
    identities = identities or {}
    violations, sensitive = [], []
    count = 0
    for path in directory.rglob('*'):
        relative = path.relative_to(directory)
        if (any(part.lower() in FORBIDDEN_PARTS for part in relative.parts)
                or path.name.lower() in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES
                or '.corrupt-' in path.name.lower()
                or '-asio' in path.name.lower()):
            violations.append(relative.as_posix())
        if relative.parts[0] == 'data' and path.is_file():
            violations.append(relative.as_posix())
        if not path.is_file():
            continue
        count += 1
        def inspect(blob, member=''):
            for kind, patterns in identities.items():
                if any(pattern in blob for pattern in patterns):
                    sensitive.append({'file': relative.as_posix() + member, 'kind': kind})
        inspect(path.read_bytes())
        if path.suffix.lower() == '.zip':
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if any(part.lower() in FORBIDDEN_PARTS for part in Path(name).parts):
                        violations.append(relative.as_posix() + ':' + name)
                    inspect(archive.read(name), ':' + name)
    return {'passed': not violations and not sensitive, 'file_count': count,
            'forbidden_files': sorted(set(violations)), 'sensitive_hits': sensitive}


def embedded_audit(directory, identities):
    from PyInstaller.archive.readers import CArchiveReader
    counts, modules, hits = {}, set(), []
    for filename in ('G10-Control.exe', 'G10-AudioBridge.exe'):
        reader = CArchiveReader(directory / filename)
        for name, entry in reader.toc.items():
            if entry[-1] == 'z':
                pyz = reader.open_embedded_archive(name)
                counts[filename] = len(pyz.toc)
                for module in pyz.toc:
                    modules.add(module)
                    blob = pyz.extract(module, raw=True) or b''
                    for kind, patterns in identities.items():
                        if any(pattern in blob for pattern in patterns):
                            hits.append({'file': filename + ':' + module, 'kind': kind})
            elif entry[-1] not in ('o', 'd'):
                blob = reader.extract(name)
                for kind, patterns in identities.items():
                    if any(pattern in blob for pattern in patterns):
                        hits.append({'file': filename + ':' + name, 'kind': kind})
    test_modules = sorted(name for name in modules if name.startswith(('test_audio_route', 'test_device_setup', 'test_onboarding', 'test_shell', 'test_runtime', 'test_portable_paths')))
    return {'module_counts': counts, 'sensitive_hits': hits, 'test_modules': test_modules}, modules


def private_identities(root):
    values = []
    for path in (root / 'local-settings.json', root / 'output/beta-local-proof/route-proof.json'):
        if path.is_file():
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            values.extend((data.get('bluetooth_address'), data.get('cable_capture_id')))
            values.extend(item.get('id') for item in data.get('pair', {}).values())
    values.extend(os.environ.get(name) for name in ('G10_BLUETOOTH_ADDRESS', 'G10_CABLE_CAPTURE_ID'))
    patterns = []
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        forms = {value, value.lower(), value.upper()}
        compact = value.replace(':', '').replace('-', '')
        if re.fullmatch('[0-9A-Fa-f]{12}', compact):
            forms.update({compact.upper(), compact.lower()})
            forms.update(separator.join(variant[i:i+2] for i in range(0,12,2))
                         for variant in (compact.upper(), compact.lower()) for separator in (':', '-'))
        patterns.extend(form.encode(encoding) for form in forms for encoding in ('utf-8', 'utf-16-le'))
    result = {'known_local_identity': list(set(patterns))} if patterns else {}
    paths = {str(root.resolve()), os.environ.get('USERPROFILE', '')}
    result['developer_path'] = list({form.encode(encoding) for path in paths if path
                                     for form in (path, path.replace('\\', '/'), path.lower())
                                     for encoding in ('utf-8', 'utf-16-le')})
    return result


def license_file(path):
    return (path.is_file() and path.suffix.lower() not in {'.py', '.pyc', '.pyd', '.dll', '.exe'}
            and any(word in path.name.lower() for word in ('license', 'copying', 'notice', 'authors')))


def collect_licenses(root, target, modules):
    inventory = {'scope': 'Installed build environment; bundled Python modules reconciled by top-level namespace. Native/transitive rights need owner review.',
                 'redistribution_ready': False, 'python': [], 'npm': [], 'native_review_required':
                 ['WebView2 SDK/Loader binaries', 'PortAudio exact binary copyright/permission text',
                  'Python/Tcl/Tk native dependencies', 'NumPy/OpenBLAS/LAPACK/compiler runtime license stack',
                  'PyInstaller bootloader exception and pystray LGPL combined-work/source/replacement obligations']}
    top_modules = {name.split('.')[0] for name in modules}
    for dist in sorted(metadata.distributions(), key=lambda item: item.metadata['Name'].lower()):
        name, version = dist.metadata['Name'], dist.version
        owned = {str(path).replace('\\', '/').split('/')[0].split('.')[0]
                 for path in dist.files or [] if '.dist-info' not in str(path) and not str(path).startswith('..')}
        bundled = bool(owned & top_modules)
        row = {'name': name, 'version': version, 'bundled_namespace_match': bundled,
               'declared_license': dist.metadata.get('License-Expression') or (dist.metadata.get('License') or '').split('\n')[0],
               'collected_files': []}
        # Include known build notices too, but mark them separately from runtime.
        for index, relative in enumerate(dist.files or []):
            source = Path(dist.locate_file(relative))
            if not license_file(source):
                continue
            dest = target / 'licenses/python' / f'{name}-{version}' / f'{index}-{source.name}'
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            row['collected_files'].append(dest.relative_to(target).as_posix())
        row['missing_license_text'] = not row['collected_files']
        inventory['python'].append(row)
    npm_root = root / 'desktop-ui/web'
    lock = json.loads((npm_root / 'package-lock.json').read_text(encoding='utf-8'))
    runtime = {'react', 'react-dom', 'scheduler', 'loose-envify', 'js-tokens', 'lucide-react'}
    for relative, info in lock['packages'].items():
        if not relative:
            continue
        source = npm_root / relative
        if not (source / 'package.json').is_file():
            continue  # Optional packages for other operating systems were not installed.
        package = json.loads((source / 'package.json').read_text(encoding='utf-8'))
        name, version = package['name'], package['version']
        row = {'name': name, 'version': version, 'scope': 'browser runtime' if name in runtime else 'build/optional tooling',
               'declared_license': package.get('license'), 'collected_files': []}
        for file in source.iterdir():
            if license_file(file):
                dest = target / 'licenses/npm' / f'{name.replace("/", "_")}-{version}' / file.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, dest)
                row['collected_files'].append(dest.relative_to(target).as_posix())
        row['missing_license_text'] = not row['collected_files']
        inventory['npm'].append(row)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.is_file():
        destination = target / 'licenses/Python-3.12-LICENSE.txt'
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(python_license, destination)
    return inventory


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=root / 'dist/G10-Control-v0.1.0-Beta-candidate-win64')
    args = parser.parse_args()
    target = args.destination.resolve()
    target.relative_to((root / 'dist').resolve())
    target.mkdir(exist_ok=False)  # Never deletes or overwrites a previous candidate.
    source = root / 'dist/G10-Control'
    for name in ('G10-Control.exe', 'G10-AudioBridge.exe', 'portable.marker'):
        shutil.copy2(source / name, target / name)
    shutil.copytree(source / '_internal', target / '_internal')
    (target / 'data').mkdir()
    documents = {'docs/README-PORTABLE.zh-CN.md': 'README-PORTABLE.zh-CN.md',
                 'docs/ACCEPTANCE-WIN11-X64.md': 'ACCEPTANCE-WIN11-X64.md',
                 'docs/BETA_LICENSE_REVIEW.md': 'BETA-LICENSE-REVIEW.md',
                 'LICENSE_STATUS.md': 'LICENSE_STATUS.md',
                 'desktop-ui/THIRD-PARTY-NOTICES.md': 'THIRD-PARTY-NOTICES.md'}
    documents.update({'build/accept_win11.ps1': 'accept_win11.ps1', 'docs/RELEASE-NOTES.zh-CN.md': 'RELEASE-NOTES.zh-CN.md',
                      'release-metadata.json': 'release-metadata.json', 'docs/LGPL-PYSTRAY.md': 'LGPL-PYSTRAY.md',
                      'docs/RELEASE-PROCESS.md': 'RELEASE-PROCESS.md'})
    if (root / 'LICENSE').is_file():
        documents['LICENSE'] = 'LICENSE'
    else:
        documents['docs/LICENSE-MIT-DRAFT.txt'] = 'LICENSE-MIT-DRAFT.txt'
    for origin, name in documents.items():
        shutil.copy2(root / origin, target / name)
    status = target / 'LICENSE_STATUS.md'
    status.write_text(status.read_text(encoding='utf-8').replace('(desktop-ui/THIRD-PARTY-NOTICES.md)',
                      '(THIRD-PARTY-NOTICES.md)'), encoding='utf-8')
    identities = private_identities(root)
    embedded, modules = embedded_audit(target, identities)
    inventory = collect_licenses(root, target, modules)
    supplement(root, target, inventory)
    (target / 'license-inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')
    evidence_summary = write_evidence(root, target, inventory, modules)
    write_review(root, target, inventory)
    audit = audit_files(target, identities)
    audit['unexpected_root_entries'] = sorted(path.name for path in target.iterdir() if path.name not in ROOT_ALLOWED)
    audit['embedded_code'] = embedded
    audit['known_identity_patterns_checked'] = sum(len(values) for values in identities.values())
    audit['redistribution_ready'] = False
    audit['passed'] = (audit['passed'] and not audit['unexpected_root_entries']
                       and not embedded['sensitive_hits'] and not embedded['test_modules'])
    (target / 'package-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    files = [{'path': path.relative_to(target).as_posix(), 'bytes': path.stat().st_size,
              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
             for path in sorted(target.rglob('*')) if path.is_file()]
    (target / 'manifest.json').write_text(json.dumps({'files': files, 'excludes_self': True}, indent=2), encoding='utf-8')
    print(json.dumps({'directory': str(target), 'files': len(files), 'privacy_audit_passed': audit['passed'],
                      'redistribution_ready': False, 'python_distributions': len(inventory['python']),
                      'npm_packages': len(inventory['npm']), 'sbom': evidence_summary}, ensure_ascii=False))
    if not audit['passed']:
        raise SystemExit('Candidate audit failed; inspect package-audit.json. No archive was created.')


if __name__ == '__main__':
    main()
