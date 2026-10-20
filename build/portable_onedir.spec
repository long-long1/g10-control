# Local onedir build. Hardware/new-machine acceptance is still required.
from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()
if SPEC_DIR.is_file():
    SPEC_DIR = SPEC_DIR.parent
ROOT = SPEC_DIR.parent
# Explicit opt-in for a user's modified LGPL library during recombination.
# Default builds use only the locked environment. Never alter installed files.
PYSTRAY_PATHS = []
if os.environ.get('G10_BUILD_PYSTRAY_SOURCE'):
    library = Path(os.environ['G10_BUILD_PYSTRAY_SOURCE']).resolve() / 'lib'
    if not (library / 'pystray' / '__init__.py').is_file():
        raise SystemExit('Modified pystray source must contain lib/pystray/__init__.py')
    PYSTRAY_PATHS.append(str(library))
WEB_DIST = ROOT / "desktop-ui" / "web" / "dist"
if not (WEB_DIST / "index.html").is_file():
    raise SystemExit("Build desktop-ui/web first: npm ci && npm run build")

WINRT_IMPORTS = []
for package in (
    "winrt.windows.devices.bluetooth",
    "winrt.windows.devices.bluetooth.genericattributeprofile",
    "winrt.windows.devices.enumeration",
    "winrt.windows.storage.streams",
):
    WINRT_IMPORTS += collect_submodules(package)

common_hiddenimports = WINRT_IMPORTS + ['pycaw.pycaw']

def windows_audio_only(entries):
    # The upstream hook collects every wheel variant, including ASIO/macOS/ARM.
    # This candidate supports x64 shared WASAPI only; retain that exact binary.
    return [entry for entry in entries if not Path(entry[0]).name.lower().startswith('libportaudio')
            or Path(entry[0]).name.lower() == 'libportaudio64bit.dll']
main_analysis = Analysis(
    [str(ROOT / "desktop-ui" / "control_entry.py")],
    pathex=PYSTRAY_PATHS + [str(ROOT), str(ROOT / "desktop-ui")],
    binaries=[],
    datas=[(str(WEB_DIST), "web/dist")],
    hiddenimports=common_hiddenimports + ["webview", "pystray", "PIL"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Analysis writes the same warning filename for both entry points. Keep each
# report so the bridge analysis cannot hide the control's dependency warnings.
Path(WARNFILE).with_name('warn-control.txt').write_text(Path(WARNFILE).read_text(encoding='utf-8'), encoding='utf-8')
main_analysis.binaries = windows_audio_only(main_analysis.binaries)
main_analysis.datas = windows_audio_only(main_analysis.datas)
main_pyz = PYZ(main_analysis.pure)
main_exe = EXE(
    main_pyz,
    main_analysis.scripts,
    [],
    exclude_binaries=True,
    name="G10-Control",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

bridge_analysis = Analysis(
    [str(ROOT / "bridge_entry.py")],
    pathex=PYSTRAY_PATHS + [str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=common_hiddenimports + ["sounddevice", "_sounddevice_data"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
Path(WARNFILE).with_name('warn-bridge.txt').write_text(Path(WARNFILE).read_text(encoding='utf-8'), encoding='utf-8')
bridge_analysis.binaries = windows_audio_only(bridge_analysis.binaries)
bridge_analysis.datas = windows_audio_only(bridge_analysis.datas)
bridge_pyz = PYZ(bridge_analysis.pure)
bridge_exe = EXE(
    bridge_pyz,
    bridge_analysis.scripts,
    [],
    exclude_binaries=True,
    name="G10-AudioBridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

# Keep two entry points in one onedir output tree with a shared _internal.
COLLECT(
    main_exe,
    bridge_exe,
    main_analysis.binaries + bridge_analysis.binaries,
    main_analysis.datas + bridge_analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="G10-Control",
)
(Path(DISTPATH) / 'G10-Control' / 'portable.marker').write_text('', encoding='utf-8')
