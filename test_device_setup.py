import asyncio
import json
from pathlib import Path
import queue
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from atvv_protocol import SERVICE, TX, AUDIO, CONTROL, CAPABILITIES
from device_setup import DeviceSetup, CapabilityOnly, PROFILE, validate_evidence


def candidate():
    return {'id': '112233445566', 'address': '112233445566', 'name': 'G10', 'advertised_services': [],
            'paired': True, 'connected': True, 'present': True,
            'winrt_device_id': 'BluetoothLE#paired-device-1', 'name_source': 'windows'}


def evidence():
    return {'profile': PROFILE, 'address': candidate()['address'], 'service': SERVICE,
            'characteristics': {TX: 4, AUDIO: 16, CONTROL: 16},
            'capabilities_hex': '0b010002030080', 'cleanup_complete': True}


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'local-settings.json'
        self.scanner = AsyncMock(return_value=[candidate()])
        self.checker = AsyncMock(side_effect=lambda _: evidence())
        self.setup = DeviceSetup(self.path, scanner=self.scanner, checker=self.checker)

    def select(self):
        self.setup.scan()
        self.setup.select(candidate()['id'])

    def test_snapshot_never_scans_or_connects(self):
        self.assertFalse(self.setup.snapshot()['compatible'])
        self.scanner.assert_not_called()
        self.checker.assert_not_called()

    def test_name_and_advertised_service_do_not_prove_compatibility(self):
        self.select()
        self.assertFalse(self.setup.snapshot()['compatible'])
        with self.assertRaises(RuntimeError):
            self.setup.require_compatible(candidate()['address'])

    def test_choose_only_scanned_identity_and_persist_unknown(self):
        with self.assertRaises(ValueError):
            self.setup.select('112233445566')
        self.select()
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved['bluetooth_address'], candidate()['address'])
        self.assertFalse(DeviceSetup(self.path).snapshot()['compatible'])

    def test_confirmation_and_all_evidence_required(self):
        self.select()
        with self.assertRaises(ValueError):
            self.setup.check(False)
        self.checker.assert_not_called()
        self.checker.return_value = {}
        self.checker.side_effect = None
        self.assertFalse(self.setup.check(True)['compatible'])

    def test_complete_evidence_persists_and_wrong_address_rejected(self):
        self.select()
        self.assertTrue(self.setup.check(True)['compatible'])
        restart = DeviceSetup(self.path)
        self.assertTrue(restart.snapshot()['compatible'])
        restart.require_compatible(candidate()['address'])
        with self.assertRaises(RuntimeError):
            restart.require_compatible('AABBCCDDEEFF')

    def test_reselect_and_failed_recheck_remove_success(self):
        self.select()
        self.setup.check(True)
        self.checker.side_effect = RuntimeError('access denied')
        self.assertFalse(self.setup.check(True)['compatible'])
        self.assertFalse(DeviceSetup(self.path).snapshot()['compatible'])

    def test_environment_override_cannot_claim_another_device_is_compatible(self):
        self.select()
        self.setup.check(True)
        self.setup.active_address = lambda: 'AABBCCDDEEFF'
        self.assertFalse(self.setup.snapshot()['compatible'])

    def test_failure_refresh_clears_candidates(self):
        self.select()
        self.scanner.side_effect = PermissionError('denied')
        state = self.setup.scan()
        self.assertEqual(state['state'], 'failed')
        self.assertFalse(state['candidates'])

    def test_protocol_identity_properties_and_cleanup_are_mandatory(self):
        for key, value in [('service', 'unknown'), ('address', 'AABBCCDDEEFF'),
                           ('capabilities_hex', '0b010002030078'), ('cleanup_complete', False),
                           ('characteristics', {TX: 0, AUDIO: 16, CONTROL: 16})]:
            record = evidence()
            record[key] = value
            self.assertFalse(validate_evidence(record, candidate()['address']))

    def test_expiry_and_corrupt_file(self):
        self.select()
        self.setup.check(True)
        data = json.loads(self.path.read_text())
        data['device_compatibility']['verified_at'] = '2000-01-01T00:00:00+00:00'
        self.path.write_text(json.dumps(data))
        self.assertFalse(DeviceSetup(self.path).snapshot()['compatible'])
        self.path.write_text('{')
        self.assertEqual(DeviceSetup(self.path).snapshot()['state'], 'failed')

    def test_capability_only_controller_cannot_open_or_close_mic(self):
        rec = Mock(errors=[])
        controller = CapabilityOnly(rec, threading.Event(), queue.Queue())
        controller.receive(CONTROL, b'\x08', 0)
        controller.receive(CONTROL, bytes.fromhex('04000201'), 0)
        controller.receive(AUDIO, b'anything', 0)
        self.assertTrue(controller.queue.empty())
        self.assertFalse(controller.streaming)
        async def run():
            with self.assertRaises(RuntimeError):
                await controller.send('MIC_OPEN', b'\x0c\x00')
            await controller.close()
        asyncio.run(run())

    def test_scanner_adapter_is_called_only_on_request(self):
        from device_setup import scan_candidates
        dev = Mock(address='11:22:33:44:55:66', name='')
        adv = Mock(local_name='', service_uuids=[])
        with patch('device_setup.enumerate_paired_devices', new=AsyncMock(return_value=([candidate()], []))), \
             patch('bleak.BleakScanner.discover', new=AsyncMock(return_value={'test': (dev, adv)})) as discover:
            found = asyncio.run(scan_candidates())
        self.assertEqual(found['candidates'][0]['address'], '112233445566')
        self.assertEqual(found['candidates'][0]['name'], 'G10')
        self.assertTrue(found['candidates'][0]['paired'])
        self.assertTrue(found['candidates'][0]['connected'])
        self.assertEqual(found['candidates'][0]['advertised_services'], [])
        discover.assert_awaited_once_with(timeout=5, return_adv=True)

    def test_windows_pair_enumeration_uses_address_and_connection_properties(self):
        from device_setup import enumerate_paired_devices, AEP_DEVICE_ADDRESS, AEP_IS_CONNECTED, AEP_IS_PRESENT
        row = SimpleNamespace(id='WindowsPairId', name='G10', properties={
            AEP_DEVICE_ADDRESS: '11:22:33:44:55:66', AEP_IS_CONNECTED: True, AEP_IS_PRESENT: True})
        with patch('winrt.windows.devices.bluetooth.BluetoothLEDevice.get_device_selector_from_pairing_state',
                   return_value='paired-ble-selector') as selector, \
             patch('winrt.windows.devices.enumeration.DeviceInformation.find_all_async_aqs_filter_and_additional_properties',
                   new=AsyncMock(return_value=[row])) as find:
            rows, warnings = asyncio.run(enumerate_paired_devices())
        selector.assert_called_once_with(True)
        find.assert_awaited_once_with('paired-ble-selector', [AEP_DEVICE_ADDRESS, AEP_IS_CONNECTED, AEP_IS_PRESENT])
        self.assertEqual(warnings, [])
        self.assertEqual(rows[0]['address'], '112233445566')
        self.assertEqual(rows[0]['winrt_device_id'], 'WindowsPairId')
        self.assertTrue(rows[0]['paired'] and rows[0]['connected'] and rows[0]['present'])

    def test_pair_is_returned_when_bleak_advertising_scan_fails(self):
        from device_setup import scan_candidates
        with patch('device_setup.enumerate_paired_devices', new=AsyncMock(return_value=([candidate()], []))), \
             patch('bleak.BleakScanner.discover', new=AsyncMock(side_effect=RuntimeError('radio busy'))):
            result = asyncio.run(scan_candidates())
        self.assertEqual(len(result['candidates']), 1)
        self.assertTrue(result['candidates'][0]['paired'])
        self.assertIn('仍显示 Windows 配对列表', result['warnings'][0])

    def test_paired_g10_sorts_before_anonymous_advertisements(self):
        from device_setup import merge_device_candidates
        paired = candidate()
        paired['connected'] = True
        rows = merge_device_candidates([paired], [
            {'address': 'AA:BB:CC:DD:EE:FF', 'name': '', 'advertised_services': []}])
        self.assertEqual(rows[0]['address'], paired['address'])
        self.assertEqual(rows[1]['name'], '')
        self.assertFalse(rows[1]['paired'])

    def test_duplicate_windows_pair_rows_prefer_connected_identity(self):
        from device_setup import merge_device_candidates
        sleeping = candidate()
        sleeping.update(connected=False, winrt_device_id='old-id')
        connected = candidate()
        connected.update(connected=True, winrt_device_id='connected-id')
        rows = merge_device_candidates([sleeping, connected], [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['winrt_device_id'], 'connected-id')
        self.assertTrue(rows[0]['connected'])

    def test_paired_g10_is_not_rejected_when_name_and_advertising_are_missing(self):
        from device_setup import check_candidate
        paired = candidate()
        paired.update(name='', name_source='', advertised_services=[])

        async def fake_observe(rec, stop, ready, updates, args, controller):
            self.assertEqual(args.device_id, paired['winrt_device_id'])
            self.assertEqual(args.address, paired['address'])
            rec.device_address = paired['address']
            rec.cleanup = True
            controller.caps = Mock(codec=2, frame_size=128, raw_frame_size=128)
            controller.identity = {TX: 4, AUDIO: 16, CONTROL: 16}
            controller.raw_capabilities = '0b010002030080'

        with patch('phase2_readonly.observe', new=AsyncMock(side_effect=fake_observe)):
            result = asyncio.run(check_candidate(paired))
        self.assertEqual(result['address'], paired['address'])
        self.assertTrue(result['cleanup_complete'])

    def test_advertisement_only_candidate_cannot_be_selected_or_checked(self):
        from device_setup import check_candidate
        advertisement = candidate()
        advertisement.update(paired=False, connected=None, winrt_device_id='')
        self.setup = DeviceSetup(self.path, scanner=AsyncMock(return_value=[advertisement]), checker=self.checker)
        self.setup.scan()
        with self.assertRaisesRegex(ValueError, 'Windows 配对设备'):
            self.setup.select(advertisement['id'])
        with self.assertRaisesRegex(RuntimeError, '仅来自 BLE 广播'):
            asyncio.run(check_candidate(advertisement))

    def test_windows_pair_identity_matches_by_aep_address_without_name(self):
        from phase2_readonly import resolve_paired_device, AEP_DEVICE_ADDRESS
        row = Mock(id='WindowsDeviceId-without-address', name='', properties={AEP_DEVICE_ADDRESS: '11:22:33:44:55:66'})
        self.assertIs(resolve_paired_device([row], candidate()['address']), row)

    def test_saved_windows_id_is_stable_even_when_it_has_no_mac_in_text(self):
        from phase2_readonly import resolve_paired_device
        row = Mock(id='WindowsDeviceId-without-address', name='', properties={})
        self.assertIs(resolve_paired_device([row], candidate()['address'], row.id), row)

    def test_saved_windows_id_with_mismatched_address_is_rejected(self):
        from phase2_readonly import resolve_paired_device, AEP_DEVICE_ADDRESS
        row = Mock(id='WindowsDeviceId', name='G10', properties={AEP_DEVICE_ADDRESS: 'AA:BB:CC:DD:EE:FF'})
        with self.assertRaisesRegex(RuntimeError, '另一蓝牙地址'):
            resolve_paired_device([row], candidate()['address'], row.id)

    def test_windows_id_embedded_address_fallback(self):
        from phase2_readonly import resolve_paired_device
        row = Mock(id='BluetoothLE#BluetoothLEAA:BB:CC:DD:EE:FF-11:22:33:44:55:66', name='', properties={})
        self.assertIs(resolve_paired_device([row], candidate()['address']), row)

    def test_real_windows_interface_shape_survives_discovery_selection_and_resolution(self):
        from device_setup import enumerate_paired_devices
        from phase2_readonly import resolve_paired_device
        # Synthetic local/remote addresses; same two-address shape as the old
        # diagnostic's successful Windows record. AEP properties may be absent
        # on a DeviceInterface enumeration.
        row = SimpleNamespace(id='BluetoothLE#BluetoothLEAA:BB:CC:DD:EE:FF-11:22:33:44:55:66',
                              name='G10', properties={})
        with patch('winrt.windows.devices.bluetooth.BluetoothLEDevice.get_device_selector_from_pairing_state',
                   return_value='paired-selector'), \
             patch('winrt.windows.devices.enumeration.DeviceInformation.find_all_async_aqs_filter_and_additional_properties',
                   new=AsyncMock(return_value=[row])):
            pairs, warnings = asyncio.run(enumerate_paired_devices())
        self.assertEqual(warnings, [])
        self.assertEqual(pairs[0]['address'], candidate()['address'])
        self.setup.scanner = AsyncMock(return_value={'candidates': pairs, 'warnings': warnings})
        self.setup.scan()
        saved = self.setup.select(candidate()['address'])['selected']
        self.assertEqual(saved['winrt_device_id'], row.id)
        self.assertIs(resolve_paired_device([row], saved['address'], saved['winrt_device_id']), row)
        self.assertIs(resolve_paired_device([row], saved['address']), row)
        with self.assertRaises(RuntimeError):
            resolve_paired_device([row], 'AABBCCDDEEFF')

    def test_unknown_windows_ids_are_not_guessed_as_ble_addresses(self):
        from local_config import peer_address_from_windows_id
        for identity in ('', None, '11:22:33:44:55:66',
                         'BluetoothLE#BluetoothLEAA:BB:CC:DD:EE:FF',
                         r'BTHLE\DEV_112233445566',
                         'unrelated-11:22:33:44:55:66-id',
                         'BluetoothLE#BluetoothLEAA:BB:CC:DD:EE:FF-11:22:33:44:55:66-extra'):
            self.assertEqual(peer_address_from_windows_id(identity), '')

    def test_observe_stops_before_gatt_if_opened_device_address_differs(self):
        from phase2_readonly import observe
        row = SimpleNamespace(id=candidate()['winrt_device_id'], name='', properties={})
        device = Mock(bluetooth_address=int('AABBCCDDEEFF', 16))
        rec = Mock(errors=[])
        with patch('winrt.windows.devices.bluetooth.BluetoothLEDevice.get_device_selector_from_pairing_state',
                   return_value='paired-selector'), \
             patch('winrt.windows.devices.enumeration.DeviceInformation.find_all_async_aqs_filter_and_additional_properties',
                   new=AsyncMock(return_value=[row])), \
             patch('winrt.windows.devices.bluetooth.BluetoothLEDevice.from_id_async',
                   new=AsyncMock(return_value=device)) as opened:
            asyncio.run(observe(rec, threading.Event(), threading.Event(), queue.Queue(),
                                SimpleNamespace(address=candidate()['address'], device_id=row.id, allow_cccd=True)))
        opened.assert_awaited_once_with(row.id)
        device.get_gatt_services_for_uuid_with_cache_mode_async.assert_not_called()
        device.close.assert_called_once()
        self.assertTrue(rec.errors)

    def test_capability_check_uses_selected_peer_and_real_protocol_with_cleanup(self):
        from device_setup import check_candidate
        paired = candidate()
        paired.update(name='', winrt_device_id='BluetoothLE#BluetoothLEAA:BB:CC:DD:EE:FF-11:22:33:44:55:66')
        row = SimpleNamespace(id=paired['winrt_device_id'], name='', properties={})
        callbacks = {}
        chars = {}
        for key, props in ((TX, 4), (AUDIO, 16), (CONTROL, 16)):
            char = Mock(uuid=key, characteristic_properties=props)
            char.read_client_characteristic_configuration_descriptor_async = AsyncMock(
                return_value=SimpleNamespace(status=0, client_characteristic_configuration_descriptor=0))
            char.write_client_characteristic_configuration_descriptor_async = AsyncMock(return_value=0)
            char.add_value_changed.side_effect = lambda callback, key=key: callbacks.setdefault(key, callback)
            chars[key] = char

        async def reply(value, option):
            self.assertEqual(bytes(value), CAPABILITIES)
            callbacks[CONTROL](None, SimpleNamespace(characteristic_value=bytes.fromhex('0b0100020300800000'),
                                                     timestamp=SimpleNamespace(isoformat=lambda: 'offline')))
            return 0

        chars[TX].write_value_with_option_async = AsyncMock(side_effect=reply)
        service = Mock(session=Mock(session_status=1))
        service.get_characteristics_with_cache_mode_async = AsyncMock(
            return_value=SimpleNamespace(status=0, characteristics=list(chars.values())))
        device = Mock(bluetooth_address=int(paired['address'], 16), connection_status=1)
        device.get_gatt_services_for_uuid_with_cache_mode_async = AsyncMock(
            return_value=SimpleNamespace(status=0, services=[service]))
        with patch('winrt.windows.devices.bluetooth.BluetoothLEDevice.get_device_selector_from_pairing_state',
                   return_value='paired-selector'), \
             patch('winrt.windows.devices.enumeration.DeviceInformation.find_all_async_aqs_filter_and_additional_properties',
                   new=AsyncMock(return_value=[row])), \
             patch('winrt.windows.devices.bluetooth.BluetoothLEDevice.from_id_async',
                   new=AsyncMock(return_value=device)) as opened:
            result = asyncio.run(check_candidate(paired))
        self.assertTrue(validate_evidence(result, paired['address']))
        opened.assert_awaited_once_with(row.id)
        chars[TX].write_value_with_option_async.assert_awaited_once()
        for key in (AUDIO, CONTROL):
            self.assertEqual([int(call.args[0]) for call in chars[key].write_client_characteristic_configuration_descriptor_async.await_args_list], [1, 0])
            chars[key].remove_value_changed.assert_called_once()
        device.close.assert_called_once()
        service.close.assert_called_once()
