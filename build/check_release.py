"""Offline candidate integrity checks; never approves publication or executes EXEs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_file(root, relative):
    path = root / relative
    path.resolve().relative_to(root.resolve())
    if not path.is_file():
        raise ValueError('Missing file: ' + relative)
    return path


def check_source(root):
    try:
        from .stage_beta import private_identities
    except ImportError:
        from stage_beta import private_identities
    # Include new files, exclude ignored runtime/build products; never print values.
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root).decode().split('\0')
    patterns = private_identities(root)
    hits = []
    for name in sorted(set(names) - {''}):
        file = root / name
        if not file.is_file():
            continue
        blob = file.read_bytes()
        if any(pattern in blob for values in patterns.values() for pattern in values):
            hits.append(name)
        if re.search(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)', blob):
            hits.append(name)
    if hits:
        raise ValueError('Source privacy scan failed (values suppressed): ' + ', '.join(sorted(set(hits))))
    return {'source_files_scanned': len(set(names) - {''}), 'known_private_values_found': False}


def check_bundle(root, schema_directory=None):
    manifest = read(root / 'manifest.json')
    expected = {'manifest.json'}
    for row in manifest['files']:
        if row['path'] in expected:
            raise ValueError('Duplicate manifest path')
        expected.add(row['path'])
        file = safe_file(root, row['path'])
        if file.stat().st_size != row['bytes'] or sha(file) != row['sha256']:
            raise ValueError('Manifest content mismatch: ' + row['path'])
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if expected != actual:
        raise ValueError('Unexpected/missing candidate files')
    audit = read(root / 'package-audit.json')
    if not audit['passed'] or audit['redistribution_ready']:
        raise ValueError('Privacy audit failed or unsupported redistribution claim')
    bom = read(root / 'sbom.cdx.json')
    review = read(root / 'license-review.json')
    refs = [c['bom-ref'] for c in bom['components']]
    if len(refs) != len(set(refs)) or set(refs) != {c['component_ref'] for c in review['components']} or len(refs) != review['component_count'] or len(refs) != len(review['components']):
        raise ValueError('SBOM/review component mismatch')
    native = {p.relative_to(root).as_posix(): sha(p) for p in (root / '_internal').rglob('*')
              if p.suffix.lower() in {'.dll', '.pyd', '.exe'}}
    recorded = {c['name']: c['hashes'][0]['content'] for c in bom['components'] if c['type'] == 'file'}
    if native != recorded:
        raise ValueError('SBOM/native binary mapping mismatch')
    evidence = read(root / 'build-evidence.json')
    if not evidence['python_lock_matched'] or not evidence['npm_lock_checked'] or evidence['redistribution_ready'] or review['redistribution_ready']:
        raise ValueError('Dependency lock or readiness evidence invalid')
    for item in evidence['license_texts']:
        if sha(safe_file(root, item['path'])) != item['sha256']:
            raise ValueError('License text hash mismatch')
    for item in review['components']:
        for relative in item['license_texts']:
            safe_file(root, relative)
    version = read(root / 'release-metadata.json')['version']
    if bom['metadata']['component']['version'] != version:
        raise ValueError('Version drift')
    schema_validated = False
    if schema_directory:
        from jsonschema import Draft7Validator, RefResolver
        directory = schema_directory.resolve()
        schema = read(directory / 'bom-1.6.schema.json')
        resolver = RefResolver((directory.as_uri() + '/'), schema, store={
            'http://cyclonedx.org/schema/spdx.schema.json': read(directory / 'spdx.schema.json'),
            'http://cyclonedx.org/schema/jsf-0.82.schema.json': read(directory / 'jsf-0.82.schema.json')})
        Draft7Validator(schema, resolver=resolver).validate(bom)
        schema_validated = True
    return {'manifest_files_verified': len(expected), 'components': len(refs), 'native_files': len(native),
            'schema_validated': schema_validated, 'redistribution_ready': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='store_true')
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--schema-directory', type=Path)
    args = parser.parse_args()
    if not args.source and not args.bundle:
        parser.error('Choose --source and/or --bundle')
    result = {}
    if args.source:
        result.update(check_source(Path(__file__).resolve().parent.parent))
    if args.bundle:
        result.update(check_bundle(args.bundle, args.schema_directory))
    print(json.dumps(result))
