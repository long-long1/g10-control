import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from build.check_release import check_bundle, safe_file


class ReleaseCheckTests(unittest.TestCase):
    def test_manifest_traversal_cannot_read_outside_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'candidate'
            root.mkdir()
            (root.parent / 'private.txt').write_text('not release material')
            with self.assertRaises(ValueError):
                safe_file(root, '../private.txt')

    def test_modified_payload_is_rejected_before_trusting_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'payload.dll').write_bytes(b'modified')
            (root / 'manifest.json').write_text(json.dumps({'files': [{
                'path': 'payload.dll', 'bytes': 8,
                'sha256': hashlib.sha256(b'original').hexdigest()}]}))
            with self.assertRaisesRegex(ValueError, 'content mismatch'):
                check_bundle(root)

    def test_unlisted_file_rejects_previously_valid_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifest.json').write_text('{"files":[]}')
            (root / 'route-proof.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Unexpected/missing'):
                check_bundle(root)
