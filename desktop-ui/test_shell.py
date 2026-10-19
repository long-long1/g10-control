import tempfile
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch, MagicMock

import app
from app import Application, SingleInstance


class ShellTests(unittest.TestCase):
    def test_nonbusiness_mode_blocks_all_hardware_and_registry_writes(self):
        instance = Application.__new__(Application)
        instance._nonbusiness = True
        with patch('winreg.SetValueEx') as write:
            for action in (instance.start_service, instance.scan_ble_devices, instance.detect_audio_route,
                           instance.start_key_detection, lambda: instance.set_autostart(True, True),
                           lambda: instance.check_ble_compatibility(True), lambda: instance.verify_audio_route('test', True)):
                with self.assertRaisesRegex(RuntimeError, '隔离诊断'):
                    action()
            write.assert_not_called()

    def test_failed_cleanup_keeps_window_and_can_retry(self):
        instance = Application.__new__(Application)
        instance._window, instance._tray = Mock(), Mock()
        instance._keys, instance._supervisor = Mock(), Mock()
        instance.exit_allowed, instance.exit_requested = False, True
        instance._supervisor.stop.side_effect = RuntimeError('still cleaning')
        instance._exit_when_safe()
        self.assertFalse(instance.exit_allowed)
        instance._window.destroy.assert_not_called()
        instance._supervisor.stop.side_effect = None
        instance._exit_when_safe()
        self.assertTrue(instance.exit_allowed)
        instance._window.destroy.assert_called_once()

    def test_close_hides_and_restore_uses_same_window(self):
        instance = Application.__new__(Application)
        instance.exit_allowed = False
        instance._store = Mock()
        instance._store.load.return_value = {'behavior': {'close_to_tray': True}}
        instance._window = Mock()
        with patch.object(app.threading, 'Timer') as timer:
            self.assertFalse(instance.on_window_closing())
            timer.assert_called_once_with(.05, instance._window.hide)
        instance.show_window()
        instance._window.show.assert_called_once()
        instance._window.restore.assert_called_once()

    def test_moved_startup_path_requires_explicit_repair(self):
        key = MagicMock()
        with patch('winreg.OpenKey', return_value=key), patch('winreg.QueryValueEx', return_value=('old/path.exe', 1)), \
                patch('winreg.SetValueEx') as write:
            self.assertTrue(Application.autostart_status()['repair_needed'])
            write.assert_not_called()

    def test_unconfirmed_startup_cannot_write(self):
        instance = Application.__new__(Application)
        with patch('winreg.SetValueEx') as write:
            with self.assertRaises(ValueError):
                instance.set_autostart(True, False)
            write.assert_not_called()

    def test_confirmed_startup_writes_only_mock_current_user_key(self):
        instance = Application.__new__(Application)
        key = MagicMock()
        with patch('winreg.OpenKey', return_value=key), patch('winreg.SetValueEx') as write, \
                patch.object(app, 'autostart_command', return_value='test-only-new/path.exe'), \
                patch.object(instance, 'is_autostart', return_value=True):
            self.assertTrue(instance.set_autostart(True, True))
        self.assertEqual(write.call_args.args[-1], 'test-only-new/path.exe')

    def test_registry_read_permission_error_has_chinese_status(self):
        with patch('winreg.OpenKey', side_effect=PermissionError('denied')):
            self.assertIn('无法读取', Application.autostart_status()['error'])

    def test_missing_webview_fails_before_window_or_tray_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as folder:
            index = Path(folder) / 'index.html'
            index.touch()
            paths = Mock(web_index=index)
            singleton = Mock(already_running=False)
            instance = Mock(_tray=None)
            with patch.object(app, 'PATHS', paths), patch.object(app, 'SingleInstance', return_value=singleton), \
                    patch.object(app, 'Application', return_value=instance), \
                    patch('startup_diagnostics.check_webview', side_effect=RuntimeError('缺少 WebView2')), \
                    patch('webview.create_window') as create:
                with self.assertRaisesRegex(RuntimeError, '缺少 WebView2'):
                    app.main()
                create.assert_not_called()
                instance.create_tray.assert_not_called()
                singleton.close.assert_called_once()

    def test_actual_mutex_rejects_second_owner(self):
        # Private test name: no interference with another running UI.
        original = app.ctypes.WinDLL
        kernel = original('kernel32', use_last_error=True)
        # Production constructor/close functions, substitute only the name.
        from uuid import uuid4
        name = 'Local\\G10Control.Unit.' + uuid4().hex
        kernel.CreateMutexW.argtypes = [app.ctypes.c_void_p, app.ctypes.c_bool, app.ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = app.ctypes.c_void_p
        kernel.CloseHandle.argtypes = [app.ctypes.c_void_p]
        first = kernel.CreateMutexW(None, True, name)
        try:
            second = kernel.CreateMutexW(None, True, name)
            try:
                self.assertEqual(app.ctypes.get_last_error(), 183)
            finally:
                kernel.CloseHandle(second)
        finally:
            kernel.CloseHandle(first)
