import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import local_config as config
from portable_paths import RuntimePaths


class LocalConfigTests(unittest.TestCase):
    def test_frozen_identity_uses_writable_data_not_bundled_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = RuntimePaths(root / '_internal', root, root / 'data', True, frozen=True)
            with patch.object(config.sys, 'frozen', True, create=True), patch(
                    'portable_paths.runtime_paths', return_value=paths):
                self.assertEqual(config.config_path(), root / 'data/local-settings.json')

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

    def test_paired_device_id_is_returned_only_for_matching_saved_address(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'local.json'
            file.write_text(json.dumps({'selected_device':{
                'address':'11:22:33:44:55:66','paired':True,'winrt_device_id':'WindowsPairId'}}),encoding='utf-8')
            with patch.object(config,'CONFIG',file):
                self.assertEqual(config.paired_device_id('112233445566'),'WindowsPairId')
                self.assertEqual(config.paired_device_id('AABBCCDDEEFF'),'')
            file.write_text(json.dumps({'selected_device':{
                'address':'112233445566','paired':False,'winrt_device_id':'WindowsPairId'}}),encoding='utf-8')
            with patch.object(config,'CONFIG',file):
                self.assertEqual(config.paired_device_id('112233445566'),'')


if __name__=='__main__':unittest.main()
