from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import app_runtime as runtime
from app import Application
from audio_route import AudioRoute, RouteError
from portable_paths import RuntimePaths
from test_audio_route import fake_catalog, fake_result


class RouteRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.paths = RuntimePaths(root / '_internal', root, root / 'data', True, frozen=True)
        (root / 'G10-AudioBridge.exe').touch()
        self.info = fake_catalog()
        self.catalog = Mock(side_effect=lambda: self.info)
        self.probe = Mock(side_effect=lambda *_: fake_result())
        store = runtime.SettingsStore(self.paths.data_path('settings.json'))
        self.supervisor = runtime.BridgeSupervisor(store, self.paths)
        self.supervisor.routes = AudioRoute(self.paths, catalog_fn=self.catalog, probe_fn=self.probe)

    def prove(self):
        token = self.supervisor.routes.detect()['confirmation_token']
        self.supervisor.routes.verify(token, True)

    def test_missing_proof_blocks_popen_without_audio_enumeration(self):
        with patch.object(runtime, 'require_address'), \
                patch.object(self.supervisor, '_external_bridge_processes', return_value=[]), \
                patch.object(runtime.subprocess, 'Popen') as popen:
            with self.assertRaises(RouteError):
                self.supervisor.start()
        popen.assert_not_called()
        self.catalog.assert_not_called()
        self.assertFalse(self.supervisor.snapshot()['microphone']['validated'])

    def test_new_endpoint_id_blocks_popen_until_reverified(self):
        self.prove()
        self.info['core_audio_endpoints'][0]['id'] = 'new-test-id'
        with patch.object(runtime, 'require_address'), \
                patch.object(self.supervisor, '_external_bridge_processes', return_value=[]), \
                patch.object(runtime.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(RouteError, '端点 ID'):
                self.supervisor.start()
        popen.assert_not_called()
        self.assertFalse(self.supervisor.snapshot()['microphone']['validated'])

    def test_manual_bridge_uses_proof_without_legacy_capture_config(self):
        self.prove()
        process = Mock()
        process.poll.return_value = None
        with patch.object(runtime, 'require_address'), \
                patch.object(runtime, 'require_cable_capture_id', side_effect=AssertionError('legacy ID')) as legacy, \
                patch.object(self.supervisor.devices, 'require_compatible'), \
                patch.object(self.supervisor, '_external_bridge_processes', return_value=[]), \
                patch.object(runtime.subprocess, 'Popen', return_value=process) as popen:
            self.assertTrue(self.supervisor.start()['started'])
        legacy.assert_not_called()
        popen.assert_called_once()
        self.assertEqual(self.supervisor.snapshot()['microphone']['id'], 'test-only-endpoint-1')

    def test_experimental_auto_wake_still_requires_matching_explicit_id(self):
        self.prove()
        value = runtime.default_settings()
        value['voice']['auto_wake_doubao'] = True
        self.supervisor.settings.save(value)
        with patch.object(runtime, 'require_address'), \
                patch.object(runtime, 'require_cable_capture_id', return_value='stale-id'), \
                patch.object(self.supervisor.devices, 'require_compatible'), \
                patch.object(self.supervisor, '_external_bridge_processes', return_value=[]), \
                patch.object(runtime.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(RuntimeError, '自动唤起配置'):
                self.supervisor.start()
        popen.assert_not_called()

    def test_application_detection_and_confirmation_use_route_policy(self):
        app = Application.__new__(Application)
        app._supervisor = self.supervisor
        app._store = self.supervisor.settings
        with patch.object(self.supervisor, '_external_bridge_processes', return_value=[]):
            token = app.detect_audio_route()['confirmation_token']
            self.probe.assert_not_called()
            with self.assertRaises(RouteError):
                app.verify_audio_route(token, False)
            token = app.detect_audio_route()['confirmation_token']
            result = app.verify_audio_route(token, True)
        self.assertTrue(result['validated'])
        self.assertTrue(app.get_status()['microphone']['validated'])

    def test_detection_and_probe_rejected_during_bridge_use(self):
        app = Application.__new__(Application)
        app._supervisor = self.supervisor
        self.supervisor.proc = Mock()
        self.supervisor.proc.poll.return_value = None
        for method in (app.detect_audio_route, lambda: app.verify_audio_route('anything', True)):
            with self.assertRaisesRegex(RuntimeError, '安全停止'):
                method()
        self.catalog.assert_not_called()
        self.probe.assert_not_called()


if __name__ == '__main__':
    unittest.main()
