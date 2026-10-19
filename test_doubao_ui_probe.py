import unittest
import itertools
from unittest.mock import Mock, patch
import doubao_ui_probe as probe


class ProbeSafetyTests(unittest.TestCase):
    def test_hidden_statusbar_cannot_move_or_click_pointer(self):
        api=Mock()
        api.IsWindowVisible.return_value=False
        with patch.object(probe,'u',api):
            with self.assertRaisesRegex(RuntimeError,'未移动鼠标'):
                probe.click_statusbar_with_mouse(123)
        api.SetCursorPos.assert_not_called()
        api.SendInput.assert_not_called()

    def test_occluded_statusbar_cannot_move_or_click_pointer(self):
        api=Mock()
        api.IsWindowVisible.return_value=True
        api.GetAsyncKeyState.return_value=0
        api.GetDpiForWindow.return_value=96
        api.WindowFromPoint.return_value=456
        def rectangle(hwnd,pointer):
            pointer._obj.left=pointer._obj.top=0
            pointer._obj.right=156;pointer._obj.bottom=45
            return True
        api.GetWindowRect.side_effect=rectangle
        api.ClientToScreen.return_value=True
        with patch.object(probe,'u',api), patch.object(probe.WindowsBackend,'_find_voice_button_window',return_value=123):
            with self.assertRaisesRegex(RuntimeError,'遮挡'):
                probe.click_statusbar_with_mouse(123)
        api.SetCursorPos.assert_not_called()
        api.SendInput.assert_not_called()

    def test_f8_requires_release_then_new_press(self):
        rec=Mock()
        with patch.object(probe.u,'GetAsyncKeyState',side_effect=[0x8000,0,0x8000]), \
             patch.object(probe.time,'sleep'):
            probe.wait_for_f8(rec)
        self.assertEqual(rec.emit.call_args.args[0],'f8_ready')

    def test_f8_timeout_aborts(self):
        with patch.object(probe.time,'monotonic',side_effect=[0,61]):
            with self.assertRaisesRegex(RuntimeError,'未发送点击'):
                probe.wait_for_f8(Mock())

    def invoke(self,activate):
        backend=Mock()
        backend.capture_active.return_value=False
        backend._find_voice_button_window.return_value=None
        with patch.object(probe,'ProbeLog'), patch.object(probe,'WindowsBackend',return_value=backend), \
             patch.object(probe,'process_security',return_value={'integrity_rid':0x2000}), \
             patch.object(probe.psutil,'process_iter',return_value=[]), \
             patch.object(probe.comtypes,'CoInitialize'), patch.object(probe.comtypes,'CoUninitialize') as uninitialize:
            result=probe.run(activate=activate)
        backend.down.assert_not_called()
        backend.up.assert_not_called()
        uninitialize.assert_called_once()
        self.assertIsNone(backend.manager)
        return result

    def test_default_probe_does_not_activate_microphone(self):
        self.assertEqual(self.invoke(False),0)

    def test_activation_refuses_lower_integrity_process(self):
        self.assertEqual(self.invoke(True),1)

    def test_right_alt_is_released_even_when_capture_does_not_start(self):
        backend=Mock()
        backend.capture_active.return_value=False
        clock=itertools.count(0,5)
        with patch.object(probe,'ProbeLog'), patch.object(probe,'RightAltProbeBackend',return_value=backend), \
             patch.object(probe,'process_security',return_value={'integrity_rid':0x3000}), \
             patch.object(probe.psutil,'process_iter',return_value=[]), patch.object(probe,'check_config'), \
             patch.object(probe.comtypes,'CoInitialize'), patch.object(probe.comtypes,'CoUninitialize'), \
             patch.object(probe.time,'sleep'), patch.object(probe.time,'monotonic',side_effect=lambda:next(clock)):
            result=probe.run(activate=True,trigger='right-alt')
        self.assertEqual(result,2)
        backend.down.assert_called_once()
        backend.up.assert_called_once()


if __name__=='__main__':unittest.main()
