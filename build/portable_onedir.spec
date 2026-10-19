# Initial build draft only. This does not produce a release-ready portable app.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()
if SPEC_DIR.is_file():
    SPEC_DIR = SPEC_DIR.parent
ROOT = SPEC_DIR.parent
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

common_hiddenimports = WINRT_IMPORTS
main_analysis = Analysis(
    [str(ROOT / "desktop-ui" / "app.py")],
    pathex=[str(ROOT), str(ROOT / "desktop-ui")],
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
    [str(ROOT / "g10_audio_bridge.py")],
    pathex=[str(ROOT)],
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

# Keep two entry-point executables in one onedir output tree. This is only a
# build-layout draft: runtime subprocess discovery has not been integrated.
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
