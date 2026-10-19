import shutil
import tempfile
import unittest
from pathlib import Path

from portable_paths import resolve_paths
from unittest.mock import patch
import sys


class PortablePathTests(unittest.TestCase):
    def test_frozen_bundle_and_companion_roots_are_independent_of_cwd(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(sys, 'frozen', True, create=True), patch.object(
                    sys, '_MEIPASS', str(root / 'program/_internal'), create=True):
                paths = resolve_paths(executable=root / 'program/G10-Control.exe',
                                      local_app_data=root / 'local')
            self.assertTrue(paths.frozen)
            self.assertEqual(paths.web_index, root / 'program/_internal/web/dist/index.html')
            self.assertEqual(paths.executable_dir, root / 'program')
            self.assertEqual(paths.data_dir, root / 'local/G10Control')
            self.assertFalse(paths.portable)

    def test_failure_of_both_data_roots_is_not_suppressed(self):
        with tempfile.TemporaryDirectory() as temp:
            def deny(_):
                raise PermissionError('no writable data root')
            with self.assertRaisesRegex(PermissionError, 'no writable'):
                resolve_paths(executable=Path(temp) / 'app.exe', portable=True,
                              local_app_data=temp, probe_writable=deny)

    def test_portable_data_survives_moving_program_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "first location"
            original.mkdir()
            (original / "portable.marker").touch()
            first = resolve_paths(
                module_file=original / "portable_paths.py",
                executable=original / "G10-Control.exe",
                frozen=True,
                bundle_dir=original / "_internal",
                local_app_data=root / "local",
            )
            first.data_path("settings/settings.json").write_text("portable", encoding="utf-8")

            moved = root / "moved location"
            shutil.copytree(original, moved)
            second = resolve_paths(
                module_file=moved / "portable_paths.py",
                executable=moved / "G10-Control.exe",
                frozen=True,
                bundle_dir=moved / "_internal",
                local_app_data=root / "local",
            )
            self.assertTrue(second.portable)
            self.assertEqual(second.data_path("settings/settings.json").read_text(encoding="utf-8"), "portable")

    def test_unwritable_portable_directory_falls_back_to_local_app_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            program = root / "program"
            program.mkdir()
            (program / "portable.marker").touch()

            def deny_portable_data(directory):
                if directory == program / "data":
                    raise PermissionError("simulated read-only program directory")
                directory.mkdir(parents=True, exist_ok=True)

            paths = resolve_paths(
                executable=program / "G10-Control.exe",
                frozen=True,
                bundle_dir=program / "_internal",
                local_app_data=root / "local",
                probe_writable=deny_portable_data,
            )
            self.assertFalse(paths.portable)
            self.assertEqual(paths.data_dir, (root / "local" / "G10Control").resolve())
            self.assertIn("read-only", paths.fallback_reason)
            paths.data_path("settings.json").write_text("fallback", encoding="utf-8")
            self.assertEqual(paths.data_path("settings.json").read_text(encoding="utf-8"), "fallback")

    def test_source_mode_separates_resources_from_executable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            scripts = root / "venv" / "Scripts"
            project.mkdir()
            scripts.mkdir(parents=True)
            paths = resolve_paths(
                module_file=project / "portable_paths.py",
                executable=scripts / "python.exe",
                frozen=False,
                local_app_data=root / "local",
            )
            self.assertEqual(paths.resource_dir, project.resolve())
            self.assertEqual(paths.executable_dir, scripts.resolve())
            self.assertEqual(paths.resource("assets/icon.svg"), (project / "assets" / "icon.svg").resolve())

    def test_resource_and_data_paths_reject_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            paths = resolve_paths(
                module_file=project / "portable_paths.py",
                executable=root / "python.exe",
                frozen=False,
                local_app_data=root / "local",
            )
            with self.assertRaises(ValueError):
                paths.resource("../outside.txt")
            with self.assertRaises(ValueError):
                paths.data_path("../outside.txt")


if __name__ == "__main__":
    unittest.main()
