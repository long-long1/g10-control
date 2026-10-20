from pathlib import Path
import tempfile
import unittest
import zipfile

from build.stage_beta import audit_files


class CandidateAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_empty_candidate_has_no_private_data(self):
        (self.root / 'data').mkdir()
        self.assertTrue(audit_files(self.root)['passed'])

    def test_developer_directories_recordings_and_proofs_are_rejected(self):
        for relative in ('output/events.jsonl', '.venv/python.exe', 'node_modules/a.js', '.git/HEAD',
                         'data/audio/route-proof.json', 'voice.wav', '_internal/libportaudio64bit-asio.dll'):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        self.assertFalse(audit_files(self.root)['passed'])
        self.assertGreaterEqual(len(audit_files(self.root)['forbidden_files']), 7)

    def test_known_private_identity_detected_in_binary_and_zip(self):
        secret = b'test-private-endpoint'
        (self.root / 'app.exe').write_bytes(b'prefix' + secret)
        with zipfile.ZipFile(self.root / 'base_library.zip', 'w') as archive:
            archive.writestr('module.pyc', secret)
        result = audit_files(self.root, {'test endpoint': [secret]})
        self.assertFalse(result['passed'])
        self.assertTrue(any(hit['file'] == 'app.exe' for hit in result['sensitive_hits']))
        self.assertTrue(any(hit['file'].endswith(':module.pyc') for hit in result['sensitive_hits']))

    def test_report_does_not_repeat_private_identity_value(self):
        (self.root / 'a.dll').write_bytes(b'private-test-id')
        result = audit_files(self.root, {'endpoint': [b'private-test-id']})
        self.assertNotIn('private-test-id', str(result))
