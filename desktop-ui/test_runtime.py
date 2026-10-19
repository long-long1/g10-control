import json
import tempfile
import unittest
from pathlib import Path

from app_runtime import CABLE_ID, SettingsStore, default_settings, normalize_settings
from app import Application


class SettingsTests(unittest.TestCase):
    def test_defaults_keep_auto_wake_and_reconnect_off(self):
        settings = default_settings()
        self.assertFalse(settings['voice']['auto_wake_doubao'])
        self.assertFalse(settings['behavior']['auto_reconnect'])
        self.assertEqual(settings['voice']['virtual_microphone_id'], CABLE_ID)

    def test_rejects_unverified_microphone_and_invalid_gain(self):
        value = default_settings()
        value['voice']['virtual_microphone_id'] = 'unverified-device'
        with self.assertRaises(ValueError):
            normalize_settings(value)
        value = default_settings()
        value['voice']['gain_db'] = 31
        with self.assertRaises(ValueError):
            normalize_settings(value)

    def test_settings_round_trip_is_atomic_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            store = SettingsStore(path)
            value = default_settings()
            value['voice']['auto_wake_doubao'] = True
            value['voice']['gain_db'] = 6
            saved = store.save(value)
            self.assertTrue(path.exists())
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), saved)
            self.assertTrue(store.load()['voice']['auto_wake_doubao'])
            self.assertEqual(store.load()['voice']['gain_db'], 6)
            self.assertFalse(path.with_suffix('.json.tmp').exists())

    def test_application_import_keeps_os_autostart_out_of_config(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Application.__new__(Application)
            app._store = SettingsStore(Path(directory) / 'settings.json')
            app._store.save(default_settings())
            changed = default_settings()
            changed['voice']['auto_wake_doubao'] = True
            changed['behavior']['close_to_tray'] = False
            saved = app.save_settings(changed)
            self.assertTrue(saved['voice']['auto_wake_doubao'])
            self.assertFalse(saved['behavior']['close_to_tray'])
            self.assertNotIn('autostart', saved)

    def test_api_runtime_objects_are_private_to_webview_inspector(self):
        app = Application.__new__(Application)
        app._store = SettingsStore(Path(tempfile.gettempdir()) / 'g10-control-api-test.json')
        exposed = [name for name in dir(app) if not name.startswith('_') and callable(getattr(app, name))]
        self.assertIn('get_status', exposed)
        self.assertNotIn('window', exposed)
        self.assertFalse(hasattr(app, 'window'))


if __name__ == '__main__':
    unittest.main()
