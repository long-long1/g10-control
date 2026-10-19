import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import app_runtime as runtime
from app import Application, KeyDetection
from portable_paths import RuntimePaths
import startup_diagnostics as diagnostics


class PortableRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='g10 portable test ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = RuntimePaths(self.root / '_internal', self.root, self.root / 'data', True, frozen=True)
        self.store = runtime.SettingsStore(self.paths.data_path('settings.json'))

    def supervisor(self):
        return runtime.BridgeSupervisor(self.store, self.paths)

    def launch(self, supervisor, **kwargs):
        process = Mock()
        process.poll.return_value = None
        process.returncode = 0
        process.wait.return_value = 0
        with patch.object(runtime, 'require_address'), patch.object(runtime, 'require_cable_capture_id', return_value=runtime.CABLE_ID), \
                patch.object(supervisor.routes, 'require_verified', return_value=(None, None, {'capture': {'id': runtime.CABLE_ID}})), \
                patch.object(runtime.BridgeSupervisor, '_external_bridge_processes', return_value=[]), \
                patch.object(runtime.subprocess, 'Popen', return_value=process, **kwargs) as popen:
            supervisor.start()
        return process, popen

    def test_default_runtime_files_share_resolved_data_root(self):
        with patch.object(runtime, 'PATHS', self.paths):
            store = runtime.SettingsStore()
            supervisor = runtime.BridgeSupervisor(store)
            self.assertEqual(store.path, self.paths.data_dir / 'settings.json')
            self.assertEqual(runtime._app_data(), self.paths.data_dir)
            self.assertEqual(runtime._local_data(), self.paths.data_dir)
            self.assertEqual(supervisor.status_path, self.paths.data_dir / 'runtime/bridge-status.json')
            self.assertEqual(supervisor.logs, self.paths.data_dir / 'logs')

    def test_frozen_command_preserves_arguments_without_python(self):
        helper = self.root / 'G10-AudioBridge.exe'
        helper.touch()
        settings = runtime.default_settings()
        settings['voice'].update(gain_db=6, auto_wake_doubao=True)
        self.store.save(settings)
        supervisor = self.supervisor()
        process, popen = self.launch(supervisor)
        args = popen.call_args.args[0]
        self.assertEqual(args[0], str(helper))
        self.assertEqual(args[1:], ['--business-approval', '--allow-cccd', '--headless',
            '--monitor-output', '--observe-ime', '--max-seconds', '0',
            '--status-path', str(supervisor.status_path), '--stop-file', str(supervisor.stop_path),
            '--output', str(supervisor.run_dir / 'events'), '--gain-db', '6.0', '--doubao-ime'])
        self.assertEqual(popen.call_args.kwargs['cwd'], self.root)
        self.assertTrue(popen.call_args.kwargs['stdout'].closed)
        with patch.object(runtime, 'require_address'), patch.object(runtime, 'require_cable_capture_id'):
            self.assertEqual(supervisor.start()['already_running'], True)
        process.wait.assert_not_called()

    def test_source_still_launches_python_script(self):
        self.paths = RuntimePaths(self.root, self.root, self.root / 'data', False)
        pythonw = self.root / 'pythonw.exe'
        pythonw.touch()
        with patch.object(runtime, 'PYTHONW', pythonw):
            supervisor = self.supervisor()
            _, popen = self.launch(supervisor)
        self.assertEqual(popen.call_args.args[0][:2], [str(pythonw), str(runtime.BRIDGE)])
        self.assertEqual(popen.call_args.kwargs['cwd'], runtime.PROJECT_ROOT)
        self.assertNotIn('--doubao-ime', popen.call_args.args[0])

    def test_safe_stop_writes_signal_and_waits_without_force(self):
        supervisor = self.supervisor()
        process = Mock(returncode=0)
        process.poll.return_value = None
        supervisor.proc = process
        result = supervisor.stop(timeout=7)
        self.assertEqual(supervisor.stop_path.read_text(encoding='ascii'), 'safe-shutdown\n')
        process.wait.assert_called_once_with(timeout=7)
        process.kill.assert_not_called()
        process.terminate.assert_not_called()
        self.assertEqual(result, {'stopped': True, 'exit_code': 0})
        self.assertIsNone(supervisor.proc)

    def test_stop_timeout_keeps_ownership_for_retry(self):
        supervisor = self.supervisor()
        process = Mock(returncode=0)
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired('fake bridge', 1)
        supervisor.proc = process
        with self.assertRaisesRegex(RuntimeError, '安全清理'):
            supervisor.stop(timeout=1)
        self.assertIs(supervisor.proc, process)
        process.kill.assert_not_called()
        process.terminate.assert_not_called()
        process.wait.side_effect = None
        supervisor.stop()
        self.assertIsNone(supervisor.proc)

    def test_exited_process_is_cleared_without_new_stop_signal(self):
        supervisor = self.supervisor()
        supervisor.proc = Mock()
        supervisor.proc.poll.return_value = 1
        self.assertEqual(supervisor.stop(), {'stopped': True})
        self.assertFalse(supervisor.stop_path.exists())

    def test_missing_helper_and_failed_spawn_are_reported(self):
        supervisor = self.supervisor()
        with self.assertRaisesRegex(RuntimeError, 'G10-AudioBridge.exe'):
            self.launch(supervisor)
        (self.root / 'G10-AudioBridge.exe').touch()
        with self.assertRaisesRegex(OSError, 'spawn failed'):
            self.launch(supervisor, side_effect=OSError('spawn failed'))
        self.assertIsNone(supervisor.proc)
        # Failed spawn releases the file handle, so it can be removed on Windows.
        supervisor.stdout_path.unlink()

    def test_detects_script_and_frozen_bridges_including_other_copies(self):
        processes = [SimpleNamespace(info=info) for info in [
            {'pid': 11, 'cmdline': ['pythonw.exe', str(runtime.BRIDGE).upper()], 'name': 'pythonw.exe'},
            {'pid': 12, 'cmdline': [], 'exe': str(self.root / 'other/G10-AudioBridge.exe')},
            {'pid': 13, 'cmdline': None, 'name': 'G10-AudioBridge.exe'},
            {'pid': 14, 'cmdline': ['G10-Control.exe'], 'name': 'G10-Control.exe'},
            {'pid': runtime.os.getpid(), 'name': 'G10-AudioBridge.exe'},
        ]]
        with patch.object(runtime.psutil, 'process_iter', return_value=processes):
            self.assertEqual([p['pid'] for p in runtime.BridgeSupervisor._external_bridge_processes()],
                             [11, 12, 13])

    def test_external_bridge_blocks_start_without_killing_it(self):
        with patch.object(runtime, 'require_address'), patch.object(runtime, 'require_cable_capture_id'), \
                patch.object(runtime.BridgeSupervisor, '_external_bridge_processes', return_value=[{'pid': 12}]), \
                patch.object(runtime.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(RuntimeError, '12'):
                self.supervisor().start()
            popen.assert_not_called()

    def test_frozen_autostart_has_no_script_and_key_observer_fails_explicitly(self):
        import app
        with patch.object(runtime, 'PATHS', self.paths), patch.object(app, 'PATHS', self.paths), \
                patch.object(runtime.sys, 'executable', str(self.root / 'G10-Control.exe')):
            self.assertEqual(runtime.autostart_command(), subprocess.list2cmdline([str(self.root / 'G10-Control.exe')]))
            keys = KeyDetection.__new__(KeyDetection)
            keys.lock = runtime.threading.RLock()
            with self.assertRaisesRegex(RuntimeError, '尚未包含按键观察器'):
                keys.start()

    def test_assets_require_local_existing_files(self):
        index = self.root / 'index.html'
        (self.root / 'app.js').touch()
        index.write_text('<script src="./app.js"></script>', encoding='utf-8')
        self.assertEqual(diagnostics.check_assets(index), ['./app.js'])
        for url in ['https://example.com/app.js', '../outside.js', './missing.js']:
            index.write_text(f'<script src="{url}"></script>', encoding='utf-8')
            with self.subTest(url=url), self.assertRaises((ValueError, RuntimeError, FileNotFoundError)):
                diagnostics.check_assets(index)

    def test_windowed_bridge_stdio_can_use_supervisor_service_log(self):
        path = self.paths.data_path('logs/bridge-run/service.log')
        with patch.object(diagnostics.sys, 'stdout', None), patch.object(diagnostics.sys, 'stderr', None):
            diagnostics.prepare_windowed_streams(path)
            stream = diagnostics.sys.stdout
            self.assertIs(stream, diagnostics.sys.stderr)
            stream.write('windowed child output\n')
            stream.close()
        self.assertEqual(path.read_text(encoding='utf-8'), 'windowed child output\n')

    def test_safe_control_diagnosis_never_calls_business_methods(self):
        import g10_audio_bridge as bridge
        report = self.root / 'diagnostic.json'
        index = self.paths.web_index
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text('<script src="./app.js"></script>', encoding='utf-8')
        (index.parent / 'app.js').touch()
        with patch.object(diagnostics, 'runtime_paths', return_value=self.paths), \
                patch.object(runtime, 'PATHS', self.paths), \
                patch.object(runtime.sys, 'argv', ['G10-Control.exe', '--diagnose-startup', str(report)]), \
                patch.object(diagnostics, 'check_webview', return_value={'renderer': 'fake'}), \
                patch.object(runtime.BridgeSupervisor, 'start', side_effect=AssertionError('business start')) as start, \
                patch.object(KeyDetection, 'start', side_effect=AssertionError('input start')) as keys, \
                patch.object(Application, 'get_audio_devices', side_effect=AssertionError('endpoint access')) as audio, \
                patch.object(bridge, 'select_verified_pair', side_effect=AssertionError('route access')) as route, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(diagnostics.diagnose('control'), 0)
        for method in (start, keys, audio, route):
            method.assert_not_called()
        result = json.loads(report.read_text(encoding='utf-8'))
        self.assertTrue(result['ok'])
        self.assertFalse(result['business_started'])
        self.assertFalse(result['service_running'])


if __name__ == '__main__':
    unittest.main()
