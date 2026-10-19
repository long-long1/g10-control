"""Resolve application resources, executable, and writable user data locations.

This module is intentionally standalone. The current desktop runtime does not
import it yet; callers can inject paths and a write probe for offline tests.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
import tempfile
from typing import Callable


WriteProbe = Callable[[Path], None]


def _probe_writable(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".g10-write-check-", dir=directory, delete=True):
        pass


@dataclass(frozen=True)
class RuntimePaths:
    """Resolved locations; resource and executable roots are kept distinct."""

    resource_dir: Path
    executable_dir: Path
    data_dir: Path
    portable: bool
    fallback_reason: str | None = None

    def resource(self, relative: str | Path) -> Path:
        """Return a resource path constrained to the resolved resource root."""
        return _within(self.resource_dir, relative)

    def data_path(self, relative: str | Path) -> Path:
        """Return a writable-data path constrained to the resolved data root."""
        target = _within(self.data_dir, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target


def _within(root: Path, relative: str | Path) -> Path:
    value = Path(relative)
    if value.is_absolute():
        raise ValueError("Expected a relative path")
    root = root.resolve()
    target = (root / value).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Path escapes its configured directory") from exc
    return target


def resolve_paths(
    *,
    module_file: str | Path | None = None,
    executable: str | Path | None = None,
    frozen: bool | None = None,
    bundle_dir: str | Path | None = None,
    portable: bool | None = None,
    portable_marker: str = "portable.marker",
    local_app_data: str | Path | None = None,
    probe_writable: WriteProbe | None = None,
) -> RuntimePaths:
    """Resolve paths for source mode and PyInstaller onedir mode.

    Portable mode is enabled by an explicit ``portable=True`` or by a marker
    next to the executable. Its ``data`` directory is preferred. If creation
    or a real write probe fails, data falls back to LocalAppData/G10Control.
    The write probe is injectable so tests can simulate ACL/readonly failures
    without changing filesystem permissions or system settings.
    """
    executable_path = Path(executable or sys.executable).resolve()
    executable_dir = executable_path.parent
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen

    if is_frozen:
        candidate_resource = bundle_dir or getattr(sys, "_MEIPASS", executable_dir)
        resource_dir = Path(candidate_resource).resolve()
    else:
        source_file = Path(module_file or __file__).resolve()
        resource_dir = source_file.parent

    marker_path = _within(executable_dir, portable_marker)
    portable_mode = (marker_path.is_file() if portable is None else portable)
    probe = probe_writable or _probe_writable

    fallback_reason = None
    if portable_mode:
        portable_data = executable_dir / "data"
        try:
            probe(portable_data)
            return RuntimePaths(resource_dir, executable_dir, portable_data.resolve(), True)
        except OSError as exc:
            fallback_reason = str(exc) or exc.__class__.__name__

    if local_app_data is None:
        local_app_data = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    fallback_data = Path(local_app_data).resolve() / "G10Control"
    probe(fallback_data)
    return RuntimePaths(resource_dir, executable_dir, fallback_data, False, fallback_reason)
