import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from audio_route import AudioRoute, MAX_AGE, RouteError, select_pair
from portable_paths import RuntimePaths, resolve_paths


def fake_catalog():
    rows = []
    devices = []
    for flow, tag, index in [(1, 'CABLE Output', 10), (0, 'CABLE Input', 11)]:
        name = f'{tag} (VB-Audio Virtual Cable)'
        rows.append({'id': f'test-only-endpoint-{flow}', 'flow': flow, 'state': 1, 'name': name,
                     'muted': False, 'volume_scalar': 1.,
                     'mix_format': {'nSamplesPerSec': 48000, 'nChannels': 2,
                                    'wFormatTag': 65534, 'wBitsPerSample': 32, 'nBlockAlign': 8}})
        devices.append({'index': index, 'name': name, 'default_samplerate': 48000,
                        'max_input_channels': 2 if flow == 1 else 0,
                        'max_output_channels': 2 if flow == 0 else 0})
    return {'wasapi_devices': devices, 'core_audio_endpoints': rows,
            'defaults': {f'{flow}:{role}': f'test-default-{flow}-{role}'
                         for flow in (0, 1) for role in (0, 1, 2)}}


def fake_result():
    info = fake_catalog()
    return {'profile': 'vbcable', 'passed': True, 'samplerate': 48000,
            'capture_name': info['wasapi_devices'][0]['name'], 'render_name': info['wasapi_devices'][1]['name'],
            'input_status': [], 'output_underflow': False, 'capture_frames': 144000, 'test_seconds': 1.48,
            'channels': [{'correlation': .98}, {'correlation': -.97}]}


class AudioRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='g10 audio route test ')
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.paths = RuntimePaths(root / '_internal', root, root / 'data', True, frozen=True)
        self.now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.info = fake_catalog()
        self.catalog = Mock(side_effect=lambda: copy.deepcopy(self.info))
        self.probe = Mock(side_effect=lambda *_: fake_result())
        self.route = self.create_route()

    def create_route(self, paths=None):
        return AudioRoute(paths or self.paths, catalog_fn=self.catalog, probe_fn=self.probe,
                          now=lambda: self.now)

    def verify(self):
        detected = self.route.detect()
        self.assertIsNotNone(detected['confirmation_token'])
        return self.route.verify(detected['confirmation_token'], True)

    def test_no_implicit_device_access_and_missing_proof_refuses_start(self):
        self.assertEqual(self.route.snapshot()['state'], 'missing')
        with self.assertRaisesRegex(RouteError, '尚无本机'):
            self.route.require_verified()
        self.catalog.assert_not_called()
        self.probe.assert_not_called()

    def test_detect_distinguishes_both_directions_without_stream_or_proof(self):
        state = self.route.detect()
        self.assertEqual(state['pair']['capture']['flow'], 1)
        self.assertIn('CABLE Output', state['pair']['capture']['name'])
        self.assertEqual(state['pair']['render']['flow'], 0)
        self.assertIn('CABLE Input', state['pair']['render']['name'])
        self.assertFalse(state['validated'])
        self.assertFalse(self.route.proof_path.exists())
        self.probe.assert_not_called()

    def test_explicit_confirmation_required_single_use_and_expires(self):
        token = self.route.detect()['confirmation_token']
        with self.assertRaises(RouteError):
            self.route.verify(token, False)
        with self.assertRaises(RouteError):
            self.route.verify(token, True)
        token = self.route.detect()['confirmation_token']
        with self.assertRaises(RouteError):
            self.route.verify('wrong-token', True)
        token = self.route.detect()['confirmation_token']
        self.now += timedelta(minutes=5)
        with self.assertRaises(RouteError):
            self.route.verify(token, True)
        token = self.route.detect()['confirmation_token']
        with self.assertRaises(RouteError):
            self.route.verify(token, 'true')
        self.probe.assert_not_called()
        self.assertFalse(self.route.proof_path.exists())

    def test_success_is_atomic_persistent_and_rechecked_on_restart(self):
        state = self.verify()
        self.assertTrue(state['validated'])
        self.assertIsNone(state['confirmation_token'])
        proof = json.loads(self.route.proof_path.read_text(encoding='utf-8'))
        self.assertEqual(proof['pair'], state['pair'])
        self.assertTrue(proof['defaults_unchanged'])
        self.assertEqual(list(self.route.proof_path.parent.iterdir()), [self.route.proof_path])
        restarted = self.create_route()
        self.assertEqual(restarted.snapshot()['state'], 'needs_detection')
        capture, render, pair = restarted.require_verified()
        self.assertEqual(capture['index'], 10)
        self.assertEqual(render['index'], 11)
        self.assertEqual(pair, state['pair'])
        self.assertTrue(restarted.snapshot()['validated'])
        self.assertEqual(self.probe.call_count, 1)

    def test_proof_moves_with_portable_directory(self):
        self.verify()
        moved = self.paths.executable_dir / 'moved 中文'
        shutil.copytree(self.paths.data_dir, moved / 'data')
        paths = RuntimePaths(moved / '_internal', moved, moved / 'data', True, frozen=True)
        self.assertEqual(self.create_route(paths).require_verified()[2], self.route.snapshot()['pair'])

    def test_source_and_fallback_use_same_data_policy(self):
        for frozen in (False, True):
            with self.subTest(frozen=frozen):
                paths = resolve_paths(module_file=self.paths.resource_dir / 'portable_paths.py',
                    executable=self.paths.executable_dir / 'app.exe', frozen=frozen,
                    portable=True, local_app_data=self.paths.executable_dir / 'local',
                    probe_writable=lambda path: (_ for _ in ()).throw(PermissionError())
                        if path.name == 'data' else path.mkdir(parents=True, exist_ok=True))
                self.route = self.create_route(paths)
                self.verify()
                self.assertEqual(self.route.proof_path, paths.data_dir / 'audio/route-proof.json')
                self.create_route(paths).require_verified()

    def test_driver_missing_or_physical_only_never_falls_back(self):
        self.info['wasapi_devices'] = [{'name': 'Physical Microphone', 'index': 1, 'max_input_channels': 2}]
        self.assertEqual(self.route.detect()['state'], 'missing_driver')
        self.probe.assert_not_called()

    def test_duplicate_wasapi_or_core_endpoints_are_rejected(self):
        for collection in ('wasapi_devices', 'core_audio_endpoints'):
            self.info = fake_catalog()
            self.info[collection].append(copy.deepcopy(self.info[collection][0]))
            with self.subTest(collection=collection):
                self.assertIsNone(self.route.detect()['confirmation_token'])
        self.probe.assert_not_called()

    def test_muted_zero_volume_unreadable_and_inactive_are_rejected(self):
        for changes in ({'muted': True}, {'volume_scalar': 0}, {'read_error': 'denied'},
                        {'state': 2}, {'flow': 0}, {'mix_format': {}}):
            self.info = fake_catalog()
            self.info['core_audio_endpoints'][0].update(changes)
            with self.subTest(changes=changes):
                self.assertIsNone(self.route.detect()['confirmation_token'])
        self.probe.assert_not_called()

    def test_shared_and_portaudio_rates_and_channels_must_match(self):
        for core, key, value in [(True, 'nSamplesPerSec', 44100), (True, 'nChannels', 1),
                                 (False, 'default_samplerate', 44100)]:
            self.info = fake_catalog()
            target = self.info['core_audio_endpoints'][0]['mix_format'] if core else self.info['wasapi_devices'][1]
            target[key] = value
            with self.subTest(key=key):
                self.assertEqual(self.route.detect()['state'], 'sample_rate')

    def test_identity_change_after_confirmation_opens_no_stream(self):
        token = self.route.detect()['confirmation_token']
        self.info['core_audio_endpoints'][0]['id'] = 'changed-id'
        with self.assertRaisesRegex(RouteError, '尚未打开音频流'):
            self.route.verify(token, True)
        self.probe.assert_not_called()

    def test_probe_failure_invalidates_previous_success(self):
        self.verify()
        self.probe.side_effect = RuntimeError('fake stream open failed')
        token = self.route.detect()['confirmation_token']
        with self.assertRaisesRegex(RuntimeError, 'fake stream'):
            self.route.verify(token, True)
        self.assertFalse(self.route.proof_path.exists())
        with self.assertRaises(RouteError):
            self.create_route().require_verified()

    def test_false_pass_bad_correlation_status_and_nan_are_rejected(self):
        variants = [{'passed': False}, {'channels': [{'correlation': 0}, {'correlation': 0}]},
                    {'channels': [{'correlation': float('nan')}, {'correlation': .99}]},
                    {'input_status': ['overflow']}, {'output_underflow': True},
                    {'samplerate': 44100}, {'capture_frames': 0}, {'profile': 'netease'}]
        for changes in variants:
            result = fake_result()
            result.update(changes)
            self.probe.side_effect = lambda *_: result
            with self.subTest(changes=changes), self.assertRaises(RouteError):
                self.verify()
            self.assertFalse(self.route.proof_path.exists())

    def test_defaults_changed_or_incomplete_and_hotplug_do_not_save_proof(self):
        for change in ('defaults', 'incomplete', 'identity'):
            self.info = fake_catalog()
            def probe_change(*_):
                if change == 'defaults':
                    self.info['defaults']['0:0'] = 'changed-default'
                elif change == 'incomplete':
                    self.info['defaults'].pop('0:0')
                else:
                    self.info['core_audio_endpoints'][1]['id'] = 'changed-render'
                return fake_result()
            self.probe.side_effect = probe_change
            with self.subTest(change=change), self.assertRaises(RouteError):
                self.verify()
            self.assertFalse(self.route.proof_path.exists())

    def test_unreadable_defaults_prevent_probe(self):
        self.info['defaults']['0:0'] = {'error': 'cannot read'}
        with self.assertRaises(RouteError):
            self.verify()
        self.probe.assert_not_called()

    def test_expired_future_wrong_version_and_corrupt_proofs_rejected_without_enumeration(self):
        self.verify()
        original = self.route.proof_path.read_text(encoding='utf-8')
        self.now += MAX_AGE
        self.assertEqual(self.create_route().snapshot()['state'], 'expired')
        self.now -= MAX_AGE
        for changes in ({'verified_at': (self.now + timedelta(days=1)).isoformat()},
                        {'validator_version': 'old'}, {'schema_version': 9}, {'defaults_unchanged': False},
                        {'verified_at': 'bad-time'}):
            value = json.loads(original)
            value.update(changes)
            self.route.proof_path.write_text(json.dumps(value), encoding='utf-8')
            self.catalog.reset_mock()
            with self.subTest(changes=changes), self.assertRaises(RouteError):
                self.create_route().require_verified()
            self.catalog.assert_not_called()
        for contents in ('{', 'null', '[]', '{"passed":true}'):
            self.route.proof_path.write_text(contents, encoding='utf-8')
            with self.subTest(contents=contents), self.assertRaises(RouteError):
                self.create_route().require_verified()

    def test_changed_identity_and_format_rejected_but_indices_may_reorder(self):
        self.verify()
        original = copy.deepcopy(self.info)
        for key, value in [('id', 'different-id'), ('name', 'CABLE Output different (VB-Audio Virtual Cable)')]:
            self.info = copy.deepcopy(original)
            self.info['core_audio_endpoints'][0][key] = value
            if key == 'name':
                self.info['wasapi_devices'][0]['name'] = value
            with self.subTest(key=key), self.assertRaises(RouteError):
                self.create_route().require_verified()
        self.info = copy.deepcopy(original)
        self.info['core_audio_endpoints'][0]['mix_format']['wBitsPerSample'] = 24
        with self.assertRaises(RouteError):
            self.create_route().require_verified()
        self.info = copy.deepcopy(original)
        self.info['wasapi_devices'][0]['index'] = 37
        self.assertEqual(self.create_route().require_verified()[0]['index'], 37)

    def test_atomic_replace_failure_leaves_no_success_or_temp_file(self):
        self.verify()
        token = self.route.detect()['confirmation_token']
        with patch.object(Path, 'replace', side_effect=PermissionError('read-only')):
            with self.assertRaises(PermissionError):
                self.route.verify(token, True)
        self.assertEqual(list(self.route.proof_path.parent.iterdir()), [])

    def test_bridge_selection_uses_new_proof_gate(self):
        import g10_audio_bridge as bridge
        with patch('audio_route.AudioRoute', return_value=self.route):
            with self.assertRaises(RouteError):
                bridge.select_verified_pair()
            self.verify()
            capture, render = bridge.select_verified_pair()
            self.assertEqual((capture['index'], render['index']), (10, 11))

    def test_existing_synthetic_probe_with_fake_streams_produces_real_metrics(self):
        import audio_route
        import virtual_audio_probe as original
        callback = None

        class Input:
            def __init__(inner, **kwargs):
                nonlocal callback
                self.assertEqual(kwargs['device'], 10)
                self.assertEqual(kwargs['samplerate'], 48000)
                callback = kwargs['callback']
            def __enter__(inner):
                return inner
            def __exit__(inner, *_):
                pass

        class Output:
            latency = .02
            def __init__(inner, **kwargs):
                self.assertEqual(kwargs['device'], 11)
                self.assertEqual(kwargs['samplerate'], 48000)
            def __enter__(inner):
                return inner
            def __exit__(inner, *_):
                pass
            def write(inner, signal):
                self.assertEqual(signal.shape[1], 2)
                callback(signal * .7, len(signal), None, False)
                return False

        self.route._probe = audio_route._probe
        with patch.object(original.sd, 'InputStream', Input), patch.object(original.sd, 'OutputStream', Output), \
                patch.object(original.sd, 'WasapiSettings'), patch.object(original.sd, 'check_input_settings'), \
                patch.object(original.sd, 'check_output_settings'), patch.object(original.time, 'sleep'), \
                patch.object(original, 'defaults', side_effect=lambda: copy.deepcopy(self.info['defaults'])):
            self.verify()
        record = json.loads(self.route.proof_path.read_text(encoding='utf-8'))
        self.assertGreater(record['result']['channels'][0]['correlation'], .999)
        self.assertEqual(record['result']['test_seconds'], 1.48)
        self.assertFalse(any(p.suffix in ('.wav', '.pcm') for p in self.paths.data_dir.rglob('*')))


if __name__ == '__main__':
    unittest.main()
