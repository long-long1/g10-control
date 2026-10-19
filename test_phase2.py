"""Protocol plan and time/binary evidence tests; these never access Bluetooth."""
import ast
import tempfile
import unittest
from pathlib import Path
from atvv_protocol import capabilities,mic_open,mic_close,CAPABILITIES
from phase2_readonly import Recorder,AUDIO,CONTROL

class Phase2Tests(unittest.TestCase):
    def test_negotiated_layout_and_version_specific_commands(self):
        c=capabilities(bytes.fromhex('0b 01 00 02 00 00 78'))
        self.assertEqual((c.version,c.codec,c.frame_size),(0x100,2,120))
        self.assertEqual(mic_open(c),bytes.fromhex('0c 00'))
        c=capabilities(bytes.fromhex('0b 00 01 02 00 00 f0'))
        self.assertEqual(mic_open(c),bytes.fromhex('0c 00 02'))
        self.assertEqual(mic_close(c.version,5),bytes.fromhex('0d'))
        self.assertEqual(mic_close(0x100,5),bytes.fromhex('0d 05'))

    def test_short_and_unsupported_capabilities_cannot_open(self):
        for data in (b'',bytes.fromhex('0b 01 00'),bytes.fromhex('08 01 00 02 00 00 78')):
            with self.assertRaises(ValueError): capabilities(data)
        with self.assertRaises(ValueError): mic_open(capabilities(bytes.fromhex('0b 01 00 01 00 00 78')))
        c=capabilities(bytes.fromhex('0b 01 00 00 02 00 00'))
        self.assertEqual((c.codec,c.frame_size,c.raw_frame_size),(2,120,0))

    def test_only_source_derived_constants(self):
        self.assertEqual(CAPABILITIES.hex(),'0a0100000303')
        tree=ast.parse((Path(__file__).parent/'phase2_readonly.py').read_text(encoding='utf-8'))
        forbidden={'write_value_async','write_value_with_option_async','write_value_with_result_async',
                   'write_value_with_result_and_option_async','write_gatt_char'}
        self.assertFalse([n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute) and n.attr in forbidden])

    def test_optional_reference_checkout(self):
        path=Path(__file__).parent.parent/'axonkey-reference/src-tauri/src/audio_service/windows.rs'
        if not path.exists():self.skipTest('Optional reference checkout is not vendored')
        self.assertIn('&[0x0a, 0x01, 0x00, 0x00, 0x03, 0x03]',path.read_text(encoding='utf-8'))

    def test_binary_boundaries_and_original_timestamps_preserved(self):
        import json
        with tempfile.TemporaryDirectory() as t:
            rec=Recorder(Path(t)/'capture')
            wall=1792400000000000000
            try:
                rec.notification(AUDIO,b'\x01\x02',100,wall,'timestamp1')
                rec.notification(AUDIO,b'\x03',110,wall+10,'timestamp2')
                rec.notification(CONTROL,b'\x08',120,wall+20,'timestamp3')
            finally:
                rec.close()
            path=Path(t)/'capture'
            self.assertEqual((path/'audio-notifications.bin').read_bytes(),b'\x01\x02\x03')
            rows=[json.loads(s) for s in (path/'events.jsonl').read_text().splitlines()]
            self.assertEqual([r.get('binary_offset') for r in rows],[0,2,None])
            self.assertEqual([r['perf_ns'] for r in rows],[100,110,120])
            self.assertNotIn('hex',rows[0])
            self.assertEqual(rows[2]['hex'],'08')

if __name__=='__main__': unittest.main()
