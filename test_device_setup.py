import asyncio
import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

from atvv_protocol import SERVICE, TX, AUDIO, CONTROL, CAPABILITIES
from device_setup import DeviceSetup, CapabilityOnly, PROFILE, validate_evidence


def candidate():
    return {'id': '112233445566', 'address': '112233445566', 'name': 'G10', 'advertised_services': [SERVICE]}


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
        dev = Mock(address='11:22:33:44:55:66', name='G10')
        adv = Mock(local_name='G10', service_uuids=[SERVICE])
        with patch('bleak.BleakScanner.discover', new=AsyncMock(return_value={'test': (dev, adv)})) as discover:
            found = asyncio.run(scan_candidates())
        self.assertEqual(found[0]['address'], '112233445566')
        discover.assert_awaited_once_with(timeout=5, return_adv=True)
