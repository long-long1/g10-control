from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from onboarding import SetupWizard, step_statuses
from portable_paths import RuntimePaths


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.paths = RuntimePaths(root, root, root / 'data', False, 'read-only portable directory')
        self.devices = Mock()
        self.devices.snapshot.return_value = {'compatible': False, 'busy': False, 'state': 'not_checked', 'selected': None}
        self.routes = Mock()
        self.routes.snapshot.return_value = {'validated': False, 'pair': None, 'state': 'missing'}
        self.environment = Mock(return_value=[{'name': 'test environment', 'passed': True, 'detail': 'simulated'}])
        self.wizard = SetupWizard(self.paths, self.devices, self.routes, environment=self.environment)

    def test_startup_reads_no_hardware(self):
        self.assertFalse(self.wizard.snapshot()['ready'])
        self.environment.assert_not_called()
        self.assertEqual(self.wizard.snapshot()['fallback_reason'], 'read-only portable directory')

    def test_step_survives_restart_but_validation_is_not_faked(self):
        self.wizard.set_step(3)
        restart = SetupWizard(self.paths, self.devices, self.routes)
        self.assertEqual(restart.snapshot()['step'], 3)
        self.assertFalse(restart.snapshot()['completed'])

    def test_invalid_step_rejected(self):
        for value in (-1, 5, True, '3'):
            with self.assertRaises(ValueError):
                self.wizard.set_step(value)

    def test_only_all_live_gates_can_complete(self):
        with self.assertRaises(RuntimeError):
            self.wizard.complete()
        self.wizard.detect_environment()
        self.devices.snapshot.return_value.update(compatible=True)
        self.routes.snapshot.return_value.update(validated=True, pair={'test': True})
        self.assertTrue(self.wizard.complete()['completed'])
        self.routes.snapshot.return_value.update(validated=False, state='expired')
        self.assertFalse(self.wizard.snapshot()['completed'])

    def test_environment_failure_prevents_success(self):
        self.environment.return_value = [{'name': 'WebView2', 'passed': False, 'detail': 'missing'}]
        self.assertEqual(self.wizard.detect_environment()['statuses'][0], 'failed')

    def test_scanning_and_expiry_are_distinct(self):
        device = {'busy': True, 'compatible': False, 'state': 'scanning', 'selected': None}
        route = {'pair': None, 'validated': False, 'state': 'expired'}
        self.assertEqual(step_statuses([], device, route)[1:4], ['checking', 'failed', 'failed'])
