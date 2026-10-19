import unittest
from unittest.mock import Mock, patch

from audio_idle import inspect_idle


class IdleChecks(unittest.TestCase):
    def check(self, state=0, error=None):
        device = Mock()
        manager = device.Activate.return_value.QueryInterface.return_value
        sessions = manager.GetSessionEnumerator.return_value
        sessions.GetCount.return_value = 1
        session = sessions.GetSession.return_value.QueryInterface.return_value
        session.GetState.return_value = state
        session.GetProcessId.return_value = 123
        enum = Mock()
        enum.GetDevice.return_value = device
        if error:
            enum.GetDevice.side_effect = error
        with patch('pycaw.pycaw.AudioUtilities.GetDeviceEnumerator', return_value=enum):
            return inspect_idle({'render': {'id': 'test-render'}, 'capture': {'id': 'test-capture'}})

    def test_inactive_metadata_permits_idle(self):
        self.assertTrue(self.check()['idle'])

    def test_expired_metadata_permits_idle(self):
        self.assertTrue(self.check(2)['idle'])

    def test_active_session_blocks(self):
        self.assertFalse(self.check(1)['idle'])

    def test_unknown_state_blocks(self):
        self.assertFalse(self.check(99)['idle'])

    def test_metadata_failure_blocks(self):
        self.assertFalse(self.check(error=PermissionError('denied'))['idle'])

    def test_busy_prevents_probe_from_opening_stream(self):
        from audio_route import _probe, RouteError
        from test_audio_route import fake_catalog
        from pathlib import Path
        with patch('audio_idle.inspect_idle', return_value={'idle': False}), patch('audio_route.probe') as probe:
            with self.assertRaises(RouteError):
                _probe(fake_catalog(), Path('unused'))
            probe.assert_not_called()
