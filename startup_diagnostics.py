"""Opt-in local startup checks. Never calls BLE, endpoint, stream or input APIs."""
from __future__ import annotations

import argparse
from dataclasses import replace
import importlib
import json
from pathlib import Path
import sys
import threading
import tempfile
import time
import traceback
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from portable_paths import runtime_paths


class _Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('src'):
            self.urls.append(attrs['src'])
        if tag == 'link' and attrs.get('rel') == 'stylesheet' and attrs.get('href'):
            self.urls.append(attrs['href'])


def check_assets(index: Path) -> list[str]:
    parser = _Assets()
    parser.feed(index.read_text(encoding='utf-8'))
    if not parser.urls:
        raise RuntimeError('React JS/CSS assets are missing from index.html')
    for url in parser.urls:
        parts = urlsplit(url)
        relative = Path(unquote(parts.path))
        if parts.scheme or parts.netloc or relative.is_absolute():
            raise RuntimeError(f'Expected a local relative asset: {url}')
        target = (index.parent / relative).resolve()
        target.relative_to(index.parent.resolve())
        if not target.is_file():
            raise FileNotFoundError(target)
    return parser.urls


def check_webview() -> dict:
    # Use the same pythonnet/WinForms/loader paths as pywebview. Importing the
    # backend checks .NET; GetAvailableBrowserVersionString does not open a UI.
    from webview.platforms import winforms
    if winforms.renderer != 'edgechromium':
        raise RuntimeError('需要 Microsoft Edge WebView2 Runtime 和 .NET Framework 4.6.2 或更新版本。'
                           '请手动安装后重试：https://developer.microsoft.com/microsoft-edge/webview2/')
    from Microsoft.Web.WebView2.Core import CoreWebView2Environment
    return {'renderer': winforms.renderer,
            'browser_version': str(CoreWebView2Environment.GetAvailableBrowserVersionString(None))}


def _webview_probe(index: Path) -> dict:
    import webview
    result = check_webview()
    # No js_api: the real React bundle runs without access to business methods.
    window = webview.create_window('G10 Control startup diagnostic', str(index), hidden=True)
    done = threading.Event()

    def loaded():
        try:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                dom = window.evaluate_js('''({
                    react_children: document.getElementById('root')?.childElementCount || 0,
                    stylesheets: document.styleSheets.length,
                    text_length: document.body.innerText.length,
                    resources: performance.getEntriesByType('resource').map(x => x.name)
                })''')
                if dom and dom['react_children'] and dom['stylesheets'] and dom['text_length']:
                    result['dom'] = dom
                    break
                time.sleep(.1)
            else:
                result['error'] = 'React did not mount with its stylesheet'
            if 'dom' in result:
                # Navigate only to the route settings preview. There is no
                # js_api, and no endpoint detection/verification button is used.
                window.evaluate_js("Array.from(document.querySelectorAll('.side-nav button')).find(x => x.textContent === '语音设置')?.click()")
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    route_ui = window.evaluate_js('''({
                        visible: document.body.innerText.includes('本机 VB-CABLE 路由'),
                        verify_disabled: Array.from(document.querySelectorAll('button'))
                            .some(x => x.textContent === '确认并验证路由' && x.disabled)
                    })''')
                    if route_ui and route_ui['visible'] and route_ui['verify_disabled']:
                        result['audio_route_ui'] = route_ui
                        break
                    time.sleep(.1)
                else:
                    result['error'] = 'Route settings preview did not show a disabled verification action'
        except Exception:
            result['error'] = traceback.format_exc()
        finally:
            done.set()
            window.destroy()

    def watchdog():
        if not done.wait(20):
            result['error'] = 'WebView2 startup timed out'
            window.destroy()

    window.events.loaded += loaded
    webview.start(watchdog, gui='edgechromium', private_mode=False,
                  storage_path=str(runtime_paths().data_path('webview-diagnostic')))
    if 'dom' not in result or result.get('error'):
        raise RuntimeError(str(result))
    return result


def diagnose(component: str) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnose-startup', type=Path, required=True, metavar='REPORT_JSON')
    parser.add_argument('--diagnose-webview', action='store_true')
    args = parser.parse_args()
    report = {'component': component, 'ok': False, 'business_started': False, 'imports': {}}
    try:
        paths = runtime_paths()
        report['paths'] = {key: str(getattr(paths, key)) for key in
                           ('resource_dir', 'executable_dir', 'data_dir')}
        report.update(frozen=paths.frozen, portable=paths.portable, fallback_reason=paths.fallback_reason)
        modules = ['numpy', 'sounddevice', 'psutil', 'comtypes', 'pycaw.pycaw',
                   'winrt.windows.devices.bluetooth',
                   'winrt.windows.devices.bluetooth.genericattributeprofile',
                   'winrt.windows.devices.enumeration', 'winrt.windows.storage.streams',
                   'winrt.windows.foundation', 'winrt.windows.foundation.collections',
                   'g10_audio_bridge']
        if component == 'control':
            modules += ['webview', 'pystray', 'PIL.Image', 'app']
        for name in modules:
            try:
                importlib.import_module(name)
                report['imports'][name] = 'ok'
            except Exception:
                report['imports'][name] = traceback.format_exc()
        if any(value != 'ok' for value in report['imports'].values()):
            raise RuntimeError('One or more required imports failed')
        # In-memory native-extension checks, without opening hardware handles.
        import numpy as np
        from cffi import FFI
        from winrt.windows.storage.streams import DataReader, DataWriter
        if int(np.arange(4).sum()) != 6:
            raise RuntimeError('numpy native operation failed')
        FFI().cdef('int g10_diagnostic(int);')
        writer = DataWriter()
        reader = None
        try:
            writer.write_bytes(bytes([1, 2, 3]))
            reader = DataReader.from_buffer(writer.detach_buffer())
            data = bytearray(3)
            reader.read_bytes(data)
            if data != bytes([1, 2, 3]):
                raise RuntimeError('WinRT memory buffer round trip failed')
        finally:
            if reader:
                reader.close()
            writer.close()
        report['memory_checks'] = ['numpy', 'cffi/pycparser', 'WinRT DataWriter/DataReader']
        # Isolated missing-proof gate check: never enumerate real endpoints,
        # even when the user's normal data directory already has a proof.
        from audio_route import AudioRoute, RouteError
        def forbidden_catalog():
            raise AssertionError('Startup diagnosis must not enumerate audio endpoints')
        with tempfile.TemporaryDirectory(prefix='.route-diagnostic-', dir=paths.data_dir) as folder:
            routes = AudioRoute(replace(paths, data_dir=Path(folder)), catalog_fn=forbidden_catalog)
            try:
                routes.require_verified()
            except RouteError as exc:
                if exc.code != 'missing':
                    raise
                report['route_proof_gate'] = 'missing proof blocked before audio access'
            else:
                raise RuntimeError('Missing route proof did not block bridge startup')
        # Exercise the bridge's command parser, then exit before approvals,
        # configuration, route proof or any device operation is consulted.
        from g10_audio_bridge import main as bridge_main
        original = sys.argv
        try:
            sys.argv = [original[0], '--help']
            try:
                bridge_main()
            except SystemExit as exc:
                if exc.code != 0:
                    raise
                report['bridge_help'] = 'ok'
        finally:
            sys.argv = original
        if component == 'control':
            from app import Application
            app = Application()
            report['service_running'] = app._supervisor.snapshot()['service']['running']
            report['assets'] = check_assets(paths.web_index)
            report['webview'] = (_webview_probe(paths.web_index) if args.diagnose_webview
                                 else check_webview())
        elif args.diagnose_webview:
            raise ValueError('--diagnose-webview is only supported by G10-Control')
        report['ok'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    args.diagnose_startup.parent.mkdir(parents=True, exist_ok=True)
    args.diagnose_startup.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1


def prepare_windowed_streams(log_path: Path | None = None):
    """Windowed PyInstaller sets stdio to None, including child processes."""
    if sys.stdout is None or sys.stderr is None:
        target = log_path or runtime_paths().data_path('logs/bootstrap.log')
        target.parent.mkdir(parents=True, exist_ok=True)
        log = target.open('a', encoding='utf-8', buffering=1)
        if sys.stdout is None:
            sys.stdout = log
        if sys.stderr is None:
            sys.stderr = log
