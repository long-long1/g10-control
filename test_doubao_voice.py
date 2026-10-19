import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import numpy as np
from doubao_voice import VoiceSession, WindowsBackend, _voice_button_point
from g10_audio_bridge import AudioBuffer
from phase2_readonly import Recorder

class Backend:
    def __init__(self):self.keys=[];self.recording=False;self.focus=True
    def poll_target(self):pass
    def target(self):return (123,456,'test.exe')
    def prepare(self,target):return self.focus
    def down(self):self.keys.append('down')
    def up(self):self.keys.append('up')
    def capture_active(self):return self.recording

class DoubaoVoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.rec=Recorder(Path(self.temp.name)/'case',save_audio=False)
        self.backend=Backend();self.sink=AudioBuffer(rate=1000,prebuffer_ms=1,max_ms=3000,gate_on_start=True)
        self.now=0.;self.voice=VoiceSession(self.backend,self.sink,self.rec,lambda:self.now)
    def tearDown(self):
        self.voice.close();self.rec.close();self.temp.cleanup()
    def start(self):
        self.sink.start();self.voice.enqueue(bytes.fromhex('04 03 02 05'));self.voice.tick()
        self.now=.2;self.voice.tick()
    def test_waits_for_ime_capture_and_drains_before_releasing(self):
        self.start();self.assertEqual(self.backend.keys,['down'])
        self.sink.push(np.ones(3,dtype=np.float32));out=np.empty((3,2),dtype=np.float32)
        self.sink.read_into(out);self.assertTrue(np.all(out==0));self.assertEqual(self.sink.frames,3)
        self.backend.recording=True;self.now=.5;self.voice.tick()
        self.sink.end();self.voice.enqueue(b'\x00\x02');self.voice.tick()
        self.now=.8;self.voice.tick();self.assertEqual(self.backend.keys,['down'])
        self.sink.read_into(out);self.assertTrue(np.all(out==1));self.voice.tick()
        self.now=1.;self.voice.tick();self.assertEqual(self.backend.keys,['down','up'])
        self.assertEqual(self.voice.completed,1)
    def test_missing_ime_releases_key_and_records_failure(self):
        self.start();self.now=3.;self.voice.tick()
        self.assertEqual(self.backend.keys,['down','up']);self.assertEqual(self.voice.failures,1)
        self.assertTrue(self.sink.gate_open)
    def test_close_releases_only_our_held_key_once(self):
        self.start();self.voice.close();self.voice.close()
        self.assertEqual(self.backend.keys,['down','up'])
    def test_existing_ime_recording_is_left_alone(self):
        self.backend.recording=True;self.start()
        self.assertEqual(self.backend.keys,[]);self.assertEqual(self.voice.failures,1)
    def test_stop_failure_does_not_recurse_or_block_audio_fallback(self):
        self.start()
        self.backend.up=Mock(side_effect=RuntimeError('window closed'))
        self.now=3.;self.voice.tick()
        self.assertFalse(self.voice.held)
        self.assertTrue(self.sink.gate_open)
        self.assertEqual(self.voice.state,'failed')
        self.voice.close()
        self.backend.up.assert_called_once()
    def test_stop_while_opening_still_drains_and_releases(self):
        self.start();self.voice.enqueue(b'\x00\x02');self.voice.tick()
        self.backend.recording=True;self.now=.5;self.voice.tick();self.voice.tick()
        self.now=.7;self.voice.tick();self.assertEqual(self.backend.keys,['down','up'])

    def test_voice_button_coordinate_scales_for_status_bar_dpi(self):
        self.assertEqual(_voice_button_point(156,45,96),(20<<16)|55)
        self.assertEqual(_voice_button_point(195,56,120),(25<<16)|69)

    def test_unknown_window_dimensions_are_rejected(self):
        with self.assertRaises(RuntimeError):_voice_button_point(500,300,96)

    def test_access_denied_on_mouse_move_never_posts_button_down(self):
        user32=Mock()
        user32.IsWindow.return_value=True
        user32.GetDpiForWindow.return_value=96
        user32.PostMessageW.return_value=0
        def rectangle(hwnd,pointer):
            pointer._obj.left=0;pointer._obj.top=0
            pointer._obj.right=156;pointer._obj.bottom=45
            return True
        user32.GetWindowRect.side_effect=rectangle
        with patch('doubao_voice.u',user32), patch('doubao_voice.c.get_last_error',return_value=5):
            with self.assertRaisesRegex(RuntimeError,'Windows 错误 5'):
                WindowsBackend._click_voice_button(123)
        user32.PostMessageW.assert_called_once_with(123,0x0200,0,(20<<16)|55)

    def test_real_windows_backend_checks_capture_before_activation(self):
        backend=WindowsBackend.__new__(WindowsBackend)
        backend.manager=Mock()
        backend.manager.GetSessionEnumerator.return_value.GetCount.return_value=0
        backend.target=Mock(return_value=(123,456,'test.exe'))
        backend.poll_target=Mock()
        backend.prepare=Mock(return_value=True)
        backend.down=Mock()
        backend.up=Mock()
        voice=VoiceSession(backend,self.sink,self.rec,lambda:self.now)
        voice.enqueue(b'\x04');voice.tick()
        self.now=.2;voice.tick()
        self.assertEqual(voice.state,'opening')
        self.assertEqual(voice.failures,0)
        backend.manager.GetSessionEnumerator.assert_called_once()
        backend.down.assert_called_once()
        voice.close()

if __name__=='__main__':unittest.main()
