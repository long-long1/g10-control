import unittest
import numpy as np
from virtual_audio_probe import correlate,select_devices,test_signal

class VirtualAudioTests(unittest.TestCase):
    def test_known_signal_at_offset_and_silence_rejection(self):
        signal=test_signal(48000)
        capture=np.concatenate((np.zeros(19200),signal*.7,np.zeros(8000)))
        r=correlate(signal,capture)
        self.assertGreater(r['correlation'],.999)
        self.assertEqual(r['capture_offset_frames'],19200)
        self.assertEqual(correlate(signal,np.zeros_like(capture))['correlation'],0)

    def test_no_default_or_physical_fallback(self):
        physical={'name':'Speakers (Realtek Audio)','index':1,'max_output_channels':2,'max_input_channels':0}
        info={'wasapi_devices':[physical],'core_audio_endpoints':[]}
        with self.assertRaises(RuntimeError):select_devices(info)
        with self.assertRaises(RuntimeError):select_devices(info,'vbcable')

if __name__=='__main__':unittest.main()
