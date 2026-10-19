import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import local_config as config


class LocalConfigTests(unittest.TestCase):
    def test_missing_identity_refuses_connection(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(config,'CONFIG',Path(folder)/'missing.json'), patch.dict(os.environ,{},clear=True):
            self.assertEqual(config.address(),'')
            with self.assertRaises(ValueError):config.require_address()
            with self.assertRaises(ValueError):config.require_cable_capture_id()

    def test_address_normalization_and_rejection(self):
        self.assertEqual(config.normalize_address('AA:BB:CC:DD:EE:FF'),'AABBCCDDEEFF')
        with self.assertRaises(ValueError):config.require_address('000000000000')
        with self.assertRaises(ValueError):config.normalize_address('all-keyboards')

    def test_environment_overrides_local_file(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'local.json'
            file.write_text(json.dumps({'bluetooth_address':'112233445566'}),encoding='utf-8')
            with patch.object(config,'CONFIG',file), patch.dict(os.environ,{'G10_BLUETOOTH_ADDRESS':'AABBCCDDEEFF'}):
                self.assertEqual(config.address(),'AABBCCDDEEFF')


if __name__=='__main__':unittest.main()
