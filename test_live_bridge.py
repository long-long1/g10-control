from pathlib import Path
import tempfile
import unittest
import numpy as np
from g10_audio_bridge import AudioBuffer,Upsample3,LiveDecoder
from phase2_readonly import Recorder
from atvv_protocol import AUDIO,CONTROL

class LiveBridgeTests(unittest.TestCase):
    def test_resampling_is_chunk_invariant_and_exact_rate(self):
        x=np.array([.1,.4,-.2,.8,-.3],dtype=np.float32)
        full=Upsample3().convert(x)
        r=Upsample3();chunks=np.concatenate([r.convert(x[:2]),r.convert(x[2:])])
        np.testing.assert_allclose(full,chunks)
        self.assertEqual(len(full),len(x)*3)
    def test_prebuffer_then_drain_tail_after_stop(self):
        b=AudioBuffer(rate=1000,prebuffer_ms=4,max_ms=20);b.start()
        b.push(np.array([1.,2.],dtype=np.float32));out=np.empty((3,2),dtype=np.float32)
        b.read_into(out);self.assertTrue(np.all(out==0));self.assertEqual(b.frames,2)
        b.push(np.array([3.,4.],dtype=np.float32));b.read_into(out)
        np.testing.assert_allclose(out[:,0],[1,2,3]);b.end();b.read_into(out)
        np.testing.assert_allclose(out[:,0],[4,0,0]);self.assertEqual(b.frames,0)
        self.assertEqual(b.rendered,4)
        with self.assertRaises(RuntimeError):b.push(np.zeros(21,dtype=np.float32))
    def test_audio_callback_before_start_preserves_first_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec=Recorder(Path(tmp)/'test',save_audio=False)
            try:
                sink=AudioBuffer();decoder=LiveDecoder(sink,rec,False)
                decoder.event(AUDIO,bytes(128),1_000_000)
                decoder.event(CONTROL,bytes.fromhex('04 03 02 04'),1_100_000)
                self.assertEqual(decoder.samples,256);self.assertEqual(sink.frames,768)
                decoder.event(CONTROL,bytes.fromhex('00 02'),2_000_000)
                self.assertFalse(decoder.active);self.assertFalse(sink.active)
                self.assertEqual(decoder.stops,1)
            finally:rec.close()

    def test_midstream_audio_waits_for_fresh_start_and_does_not_claim_forwarding(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec=Recorder(Path(tmp)/'test',save_audio=False)
            try:
                sink=AudioBuffer();decoder=LiveDecoder(sink,rec,False)
                for i in range(8):decoder.event(AUDIO,bytes(128),1_000_000_000+i*16_000_000)
                self.assertTrue(decoder.waiting_for_start)
                self.assertEqual((decoder.samples,sink.frames),(0,0))
                decoder.event(CONTROL,bytes.fromhex('00 02'),2_000_000_000)
                decoder.event(CONTROL,bytes.fromhex('04 03 02 04'),3_000_000_000)
                decoder.event(AUDIO,bytes(128),3_010_000_000)
                self.assertFalse(decoder.waiting_for_start)
                self.assertEqual(decoder.samples,256)
                self.assertFalse((Path(tmp)/'test/audio-notifications.bin').exists())
            finally:rec.close()

if __name__=='__main__':unittest.main()
