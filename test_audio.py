import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from analyze_audio import Decoder,analyze,tables

class AudioTests(unittest.TestCase):
    def test_decoder_does_not_read_external_reference_files(self):
        with patch.object(Path,'read_text',side_effect=AssertionError('External file read')):
            steps,indices=tables()
            self.assertEqual((len(steps),len(indices)),(89,8))
            self.assertEqual(Decoder(False).decode(bytes.fromhex('7f')),[-11,19])

    def test_nibble_order_distinguishes_source_and_candidate(self):
        self.assertEqual(Decoder().decode(bytes.fromhex('7f')),[11,-19])
        self.assertEqual(Decoder(False).decode(bytes.fromhex('7f')),[-11,19])

    def test_independent_callback_order_preserves_first_packet(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t)
            events=[
                {'kind':'capabilities_accepted','perf_ns':1,'version':256,'codec':2,'frame_size':128,'raw_frame_size':128},
                {'kind':'audio','perf_ns':1000000,'relative_s':.001,'length':128,'binary_offset':0},
                {'kind':'control','perf_ns':1100000,'relative_s':.0011,'hex':'04 03 02 04'},
                {'kind':'audio','perf_ns':17000000,'relative_s':.017,'length':128,'binary_offset':128},
                {'kind':'control','perf_ns':20000000,'relative_s':.02,'hex':'00 02'}]
            (d/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events),encoding='utf-8')
            (d/'audio-notifications.bin').write_bytes(bytes(256))
            result=analyze(d)
            self.assertEqual(len(result['sessions']),1)
            s=result['sessions'][0]
            self.assertEqual((s['packets'],s['bytes']),(2,256))
            self.assertAlmostEqual(s['audio_preceded_start_callback_ms'],.1)
            self.assertNotIn('candidate_wavs',s)
            (d/'audio-notifications.bin').write_bytes(bytes(255))
            with self.assertRaises(RuntimeError): analyze(d)

if __name__=='__main__':unittest.main()
