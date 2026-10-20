import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from build.release_evidence import write_evidence


class ReleaseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'candidate'
        (self.target / '_internal').mkdir(parents=True)
        (self.target / '_internal/native.dll').write_bytes(b'fake native library')
        (self.target / 'licenses').mkdir()
        (self.target / 'licenses/license.txt').write_text('test license')
        for name in ('requirements.txt', 'requirements-build.txt', 'requirements-build.lock.txt',
                     'build/portable_onedir.spec'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('example==1.0\n')
        package = self.root / 'desktop-ui/web'
        package.mkdir(parents=True)
        (package / 'package-lock.json').write_text(json.dumps({'packages': {'': {},
            'node_modules/example': {'version': '1.0', 'license': 'MIT', 'integrity': 'sha512-fake'}}}))
        self.dist = SimpleNamespace(metadata={'Name': 'example'}, version='1.0')
        self.inventory = {'python': [{'name': 'example', 'version': '1.0',
            'bundled_namespace_match': True, 'declared_license': 'MIT', 'missing_license_text': False}], 'npm': []}

    def run_evidence(self):
        with patch('build.release_evidence.metadata.distributions', return_value=[self.dist]), \
                patch('build.release_evidence.subprocess.check_output', side_effect=[b'\0', 'test-source-commit\n']):
            return write_evidence(self.root, self.target, self.inventory, {'example'})

    def test_sbom_native_hash_and_uninstalled_lock_entry_preserved(self):
        self.run_evidence()
        first = (self.target / 'sbom.cdx.json').read_bytes()
        bom = json.loads(first)
        self.assertEqual(bom['bomFormat'], 'CycloneDX')
        self.assertEqual(len(bom['components']), 3)
        native = next(c for c in bom['components'] if c['type'] == 'file')
        self.assertEqual(len(native['hashes'][0]['content']), 64)
        npm = next(c for c in bom['components'] if c['bom-ref'].startswith('pkg:npm/'))
        self.assertIn({'name': 'g10:installed', 'value': 'false'}, npm['properties'])
        self.run_evidence()
        self.assertEqual(first, (self.target / 'sbom.cdx.json').read_bytes())
        self.assertFalse(json.loads((self.target / 'build-evidence.json').read_text())['redistribution_ready'])

    def test_python_version_drift_blocks_evidence(self):
        self.dist.version = '2.0'
        with self.assertRaisesRegex(RuntimeError, 'lock mismatch'):
            self.run_evidence()
        self.assertFalse((self.target / 'sbom.cdx.json').exists())

    def test_npm_installed_version_drift_blocks_evidence(self):
        path = self.root / 'desktop-ui/web/node_modules/example'
        path.mkdir(parents=True)
        (path / 'package.json').write_text('{"version":"2.0"}')
        with self.assertRaisesRegex(RuntimeError, 'npm lock mismatch'):
            self.run_evidence()
