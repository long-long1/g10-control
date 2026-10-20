"""Offline failure matrix. All device/stream/process operations are fake."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import app_runtime as runtime
from audio_route import AudioRoute, MAX_AGE, RouteError
from device_setup import DeviceSetup
import local_config
from onboarding import SetupWizard
from portable_paths import RuntimePaths
from test_audio_route import fake_catalog, fake_result
from test_device_setup import candidate, evidence


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.paths = RuntimePaths(root / '_internal', root, root / 'data', True, frozen=True)
        (root / 'G10-AudioBridge.exe').touch()
        self.store = runtime.SettingsStore(self.paths.data_path('settings.json'))
        self.supervisor = runtime.BridgeSupervisor(self.store, self.paths)
        self.now = datetime.now(timezone.utc)
        self.catalog = Mock(return_value=fake_catalog())
        self.probe = Mock(return_value=fake_result())
        self.routes = AudioRoute(self.paths, catalog_fn=self.catalog, probe_fn=self.probe, now=lambda: self.now)
        self.devices = DeviceSetup(self.paths.data_path('local-settings.json'),
                                   scanner=AsyncMock(return_value=[candidate()]),
                                   checker=AsyncMock(return_value=evidence()))
        self.supervisor.routes, self.supervisor.devices = self.routes, self.devices
        self.wizard = SetupWizard(self.paths, self.devices, self.routes,
                                  environment=lambda: [{'name': 'fake Windows', 'passed': True}])
        self.supervisor.wizard = self.wizard
        self.popen = patch.object(runtime.subprocess, 'Popen', side_effect=AssertionError('Unexpected process launch')).start()
        self.addCleanup(patch.stopall)

    def ready(self):
        self.devices.scan()
        self.devices.select(candidate()['id'])
        self.devices.check(True)
        self.routes.verify(self.routes.detect()['confirmation_token'], True)
        self.wizard.detect_environment()
        self.assertTrue(self.wizard.complete()['completed'])

    def blocked(self):
        self.assertFalse(self.wizard.snapshot()['ready'])
        self.assertFalse(self.wizard.snapshot()['completed'])
        with self.assertRaises(RuntimeError):
            self.wizard.complete()
        with patch.object(runtime, 'require_address', return_value=candidate()['address']), \
                patch.object(self.supervisor, '_external_bridge_processes', return_value=[]):
            with self.assertRaises(RuntimeError):
                self.supervisor.start()
        self.popen.assert_not_called()

    def test_route_expiry_revokes_saved_completion_then_explicit_recovery(self):
        self.ready()
        self.now += MAX_AGE
        self.blocked()
        self.routes.verify(self.routes.detect()['confirmation_token'], True)
        self.assertTrue(self.wizard.complete()['completed'])
        self.popen.assert_not_called()

    def test_endpoint_change_recheck_revokes_completion_without_stream(self):
        self.ready()
        self.catalog.return_value['core_audio_endpoints'][0]['id'] = 'fake-changed'
        self.routes.detect()
        count = self.probe.call_count
        self.blocked()
        self.assertEqual(count, self.probe.call_count)

    def test_device_identity_change_revokes_completion(self):
        self.ready()
        self.devices.active_address = lambda: 'AABBCCDDEEFF'
        self.blocked()

    def test_ble_disconnect_during_recheck_does_not_keep_old_evidence(self):
        self.ready()
        self.devices.checker.side_effect = ConnectionError('fake BLE disconnect')
        self.assertFalse(self.devices.check(True)['compatible'])
        self.blocked()

    def test_missing_cable_and_webview_are_failures_then_retry_is_explicit(self):
        self.ready()
        self.wizard.environment_fn = lambda: [{'name': 'WebView2', 'passed': False, 'detail': '模拟缺失；请手动安装'}]
        self.assertFalse(self.wizard.detect_environment()['ready'])
        self.catalog.return_value = {'wasapi_devices': [], 'core_audio_endpoints': [], 'defaults': {}}
        self.routes.detect()
        self.blocked()
        self.popen.assert_not_called()

    def test_corrupt_application_settings_visible_and_reset_recovers(self):
        for blob in ('{broken', '[]', '{"voice":null}'):
            with self.subTest(blob=blob):
                self.store.path.write_text(blob, encoding='utf-8')
                self.assertEqual(self.store.load(), runtime.default_settings())
                self.assertIn('原文件保留', self.store.warning)
                self.assertEqual(self.store.path.read_text(encoding='utf-8'), blob)
        self.store.save(runtime.default_settings())
        self.store.load()
        self.assertIsNone(self.store.warning)

    def test_corrupt_identity_keeps_diagnostics_and_wizard_available(self):
        self.ready()
        self.devices.path.write_text('{broken', encoding='utf-8')
        with patch.object(local_config, 'CONFIG', self.devices.path), patch.dict(runtime.os.environ, {}, clear=True):
            self.assertEqual(local_config.address(), '')
            with self.assertRaises(ValueError):
                local_config.require_address()
            state = self.supervisor.export_diagnostics()
        self.assertEqual(state['state']['device_setup']['state'], 'failed')
        self.assertFalse(state['state']['setup']['completed'])
        self.assertFalse(state['contains_audio_or_recognized_text'])
        self.assertEqual(self.devices.path.read_text(), '{broken')
        self.devices.select(candidate()['id'])
        backups = list(self.devices.path.parent.glob('local-settings.json.corrupt-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), '{broken')
        self.assertFalse(self.devices.snapshot()['compatible'])
        self.assertTrue(self.devices.check(True)['compatible'])

    def test_stale_disconnected_exited_and_corrupt_status_never_show_active_audio(self):
        process = Mock(returncode=7)
        self.supervisor.proc = process
        for running, connected, offset in [(True, False, 0), (True, True, -10), (False, True, 0), (True, True, 100)]:
            with self.subTest(running=running, connected=connected, offset=offset):
                process.poll.return_value = None if running else 7
                backend = {'connected': connected, 'audio_active': True, 'cable_level_dbfs': -3,
                           'time': (datetime.now(timezone.utc) + timedelta(seconds=offset)).isoformat()}
                self.supervisor.status_path.write_text(json.dumps(backend), encoding='utf-8')
                state = self.supervisor.snapshot()
                self.assertNotEqual(state['service']['connection'], 'connected')
                self.assertFalse(state['service']['audio_active'])
                self.assertFalse(state['microphone']['is_active'])
                self.assertEqual(state['service']['cable_level_dbfs'], -120)
        for blob in ('[]', 'null', '{broken'):
            self.supervisor.status_path.write_text(blob)
            self.assertFalse(self.supervisor.snapshot()['service']['audio_active'])
        self.popen.assert_not_called()

    def test_safe_stop_timeout_retains_process_and_retry_never_kills(self):
        process = Mock(returncode=0)
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired('fake', 1)
        self.supervisor.proc = process
        with self.assertRaisesRegex(RuntimeError, '安全清理'):
            self.supervisor.stop(1)
        self.assertIs(self.supervisor.proc, process)
        process.wait.side_effect = None
        self.assertTrue(self.supervisor.stop(1)['stopped'])
        process.kill.assert_not_called()
        process.terminate.assert_not_called()

    def test_fresh_connected_heartbeat_preserves_live_audio_display(self):
        self.supervisor.proc = Mock()
        self.supervisor.proc.poll.return_value = None
        self.supervisor.status_path.write_text(json.dumps({'connected': True, 'audio_active': True,
            'cable_level_dbfs': -12, 'time': datetime.now(timezone.utc).isoformat()}))
        state = self.supervisor.snapshot()
        self.assertEqual(state['service']['connection'], 'connected')
        self.assertTrue(state['service']['audio_active'])
        self.assertEqual(state['service']['cable_level_dbfs'], -12)

    def test_spawn_failure_is_stopped_and_requires_manual_retry(self):
        self.ready()
        self.popen.side_effect = OSError('fake spawn failure')
        with patch.object(runtime, 'require_address', return_value=candidate()['address']), \
                patch.object(self.supervisor, '_external_bridge_processes', return_value=[]):
            with self.assertRaises(OSError):
                self.supervisor.start()
        self.assertFalse(self.supervisor.snapshot()['service']['running'])
        self.supervisor.snapshot()
        self.popen.assert_called_once()
