"""Compare two frozen payloads by SHA256; reports drift, never rewrites output."""
import argparse
import json
from pathlib import Path
from release_evidence import sha256


def inventory(root):
    return {p.relative_to(root).as_posix(): sha256(p) for p in sorted(root.rglob('*'))
            if p.is_file() and p.relative_to(root).parts[0] in
            {'G10-Control.exe', 'G10-AudioBridge.exe', '_internal', 'portable.marker'}}


def compare(first, second):
    a, b = inventory(first), inventory(second)
    return {'byte_identical': a == b and bool(a), 'first_files': len(a), 'second_files': len(b),
            'changed': sorted(k for k in a.keys() & b.keys() if a[k] != b[k]),
            'added': sorted(b.keys() - a.keys()), 'removed': sorted(a.keys() - b.keys())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first', type=Path)
    parser.add_argument('second', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.first, args.second)
    args.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    raise SystemExit(0 if result['byte_identical'] else 1)
