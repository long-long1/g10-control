"""G10 Control WebView2 desktop shell with a separately supervised audio service."""
from __future__ import annotations

import ctypes
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog

from app_runtime import (BridgeSupervisor, G10_ADDRESS, PROJECT_ROOT, RAW_INPUT, SettingsStore,
                         PATHS, _local_data, autostart_command, default_settings, normalize_settings, require_address)

APP = Path(__file__).resolve().parent
LOGS = _local_data() / 'logs'
LOGS.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=LOGS / 'desktop.log', encoding='utf-8', level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('g10control')

class SingleInstance:
    def __init__(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        self.kernel.CreateMutexW.restype = ctypes.c_void_p
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        ctypes.set_last_error(0)
        self.handle = self.kernel.CreateMutexW(None, True, 'Local\\G10Control.Desktop')
        self.already_running = ctypes.get_last_error() == 183
    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle); self.handle = None

class Application:
    def __init__(self, nonbusiness=False):
        self._nonbusiness = nonbusiness
        self._store = SettingsStore()
        self._supervisor = BridgeSupervisor(self._store)
        self._keys = KeyDetection()
        self._window = None
        self._tray = None
        self.exit_allowed = False
        self.exit_requested = False
        self.exit_lock = threading.Lock()

    def get_status(self):
        state = self._supervisor.snapshot()
        state['settings'] = self._store.load()
        state['runtime'] = {'log_directory': str(self._supervisor.logs),
                            'service_log_directory': str(self._supervisor.run_dir) if self._supervisor.run_dir else None}
        state['shell'] = {'key_observer_available': not PATHS.frozen and PYTHON_PATH.is_file() and not getattr(self, '_nonbusiness', False),
                          'key_observer_reason': 'Portable 版本未包含按键观察器。' if PATHS.frozen else '需要源码 Python 环境及明确设备配置。',
                          'nonbusiness': getattr(self, '_nonbusiness', False)}
        state['startup'] = self.autostart_status() if not getattr(self, '_nonbusiness', False) else {'enabled': False, 'repair_needed': False}
        return state

    def _require_business(self):
        if getattr(self, '_nonbusiness', False):
            raise RuntimeError('隔离诊断禁止 BLE、音频、按键及启动项写入操作。')

    def start_service(self):
        self._require_business()
        result = self._supervisor.start()
        log.info('Audio service start requested: %s', result)
        return result

    def stop_service(self):
        result = self._supervisor.stop()
        log.info('Audio service stopped: %s', result)
        return result

    def scan_ble_devices(self):
        self._require_business()
        with self._supervisor.lock:
            self._require_audio_idle()
            return self._supervisor.devices.scan()

    def detect_environment(self):
        return self._supervisor.wizard.detect_environment()

    def set_setup_step(self, step):
        return self._supervisor.wizard.set_step(step)

    def complete_setup(self):
        return self._supervisor.wizard.complete()

    def select_ble_device(self, identity):
        self._require_business()
        with self._supervisor.lock:
            self._require_audio_idle()
            return self._supervisor.devices.select(identity)

    def check_ble_compatibility(self, confirmed=False):
        self._require_business()
        with self._supervisor.lock:
            self._require_audio_idle()
            return self._supervisor.devices.check(confirmed)

    def save_settings(self, value):
        current = self._store.load()
        incoming = normalize_settings(value)
        # OS autostart is intentionally not changed by importing ordinary app settings.
        incoming['behavior']['close_to_tray'] = bool(value.get('behavior', {}).get('close_to_tray', current['behavior']['close_to_tray']))
        saved = self._store.save(incoming)
        log.info('Application preferences saved')
        return saved

    def reset_settings(self):
        value = self._store.save(default_settings())
        log.info('Application preferences reset')
        return value

    def export_settings(self):
        return json.dumps(self._store.load(), ensure_ascii=False, indent=2)

    def import_settings(self, contents):
        if not isinstance(contents, str) or len(contents.encode('utf-8')) > 1024 * 1024:
            raise ValueError('配置文件超过 1 MB 或格式无效。')
        try:
            value = json.loads(contents)
        except json.JSONDecodeError as exc:
            raise ValueError('所选文件不是有效的 JSON 配置。') from exc
        return self.save_settings(value)

    def get_audio_devices(self):
        route = self.detect_audio_route()
        capture = (route.get('pair') or {}).get('capture')
        return ([{'name': capture['name'], 'channels': capture['mix_format']['nChannels'],
                  'id': capture['id'], 'validated': route['validated']}] if capture else [])

    def _require_audio_idle(self):
        if ((self._supervisor.proc and self._supervisor.proc.poll() is None)
                or self._supervisor._external_bridge_processes()):
            raise RuntimeError('请先安全停止所有 G10 音频桥接，再检测或验证 VB-CABLE。')

    def detect_audio_route(self):
        self._require_business()
        with self._supervisor.lock:
            self._require_audio_idle()
            return self._supervisor.routes.detect()

    def verify_audio_route(self, token, confirmed=False):
        self._require_business()
        with self._supervisor.lock:
            self._require_audio_idle()
            return self._supervisor.routes.verify(token, confirmed)

    def get_logs(self):
        return self._supervisor.logs_tail(120)

    def get_autostart(self):
        return False if getattr(self, '_nonbusiness', False) else self.is_autostart()

    def get_diagnostics(self):
        return self._supervisor.export_diagnostics()

    def start_key_detection(self):
        self._require_business()
        return self._keys.start()

    def stop_key_detection(self):
        return self._keys.stop()

    def get_key_events(self):
        return self._keys.snapshot()

    def set_autostart(self, enabled, confirmed=False):
        self._require_business()
        import winreg
        if enabled and not confirmed:
            raise ValueError('启用登录后启动前需要在确认框中同意修改当前用户的启动项。')
        key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
            if enabled:
                command = autostart_command()
                winreg.SetValueEx(key, 'G10Control', 0, winreg.REG_SZ, command)
            else:
                try: winreg.DeleteValue(key, 'G10Control')
                except FileNotFoundError: pass
        return self.is_autostart()

    @staticmethod
    def is_autostart():
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
                value, _ = winreg.QueryValueEx(key, 'G10Control')
                return bool(value)
        except FileNotFoundError:
            return False

    @staticmethod
    def autostart_status():
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
                value, _ = winreg.QueryValueEx(key, 'G10Control')
                return {'enabled': bool(value), 'repair_needed': bool(value) and value != autostart_command()}
        except FileNotFoundError:
            return {'enabled': False, 'repair_needed': False}
        except OSError as exc:
            return {'enabled': False, 'repair_needed': False, 'error': f'无法读取 Windows 启动项：{exc}'}

    def set_close_to_tray(self, enabled):
        value = self._store.load(); value['behavior']['close_to_tray'] = bool(enabled)
        self._store.save(value); return value['behavior']['close_to_tray']

    def save(self, contents, suggested='G10-Control-config.json'):
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        path = filedialog.asksaveasfilename(parent=root, initialfile=suggested,
                    defaultextension='.json', filetypes=[('JSON', '*.json')])
        root.destroy()
        if not path:return {'saved': False}
        Path(path).write_text(contents, encoding='utf-8')
        return {'saved': True, 'path': path}

    def save_diagnostics(self, report):
        if not isinstance(report, str) or len(report.encode('utf-8')) > 4 * 1024 * 1024:
            raise ValueError('诊断报告格式无效或超过 4 MB。')
        return self.save(report, 'G10-Control-diagnostics.json')

    def request_exit(self):
        with self.exit_lock:
            if self.exit_requested:return {'exiting': True}
            self.exit_requested = True
        threading.Thread(target=self._exit_when_safe, name='G10ControlExit', daemon=True).start()
        return {'exiting': True}

    def _exit_when_safe(self):
        try:
            self._keys.stop()
            self._supervisor.stop()
        except Exception:
            log.exception('Safe shutdown did not complete')
            self.exit_requested = False
            if self._window:
                self._window.evaluate_js("window.g10SetExitError && window.g10SetExitError('后台服务仍在安全清理，请稍后重试。')")
            return
        self.exit_allowed = True
        if self._tray:
            self._tray.stop()
        if self._window:
            self._window.destroy()

    def on_window_closing(self):
        if self.exit_allowed:
            return True
        if self._store.load()['behavior']['close_to_tray']:
            threading.Timer(.05, self._window.hide).start()
        else:
            self.request_exit()
        return False

    def show_window(self):
        if self._window:
            self._window.show()
            self._window.restore()
            self._window.maximize()

    def create_tray(self):
        import pystray
        from PIL import Image, ImageDraw
        image = Image.new('RGBA', (64, 64), (24, 37, 54, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((4, 4, 60, 60), radius=17, fill=(36, 62, 83, 255))
        draw.arc((13, 13, 51, 51), 205, 335, fill=(75, 220, 190, 255), width=4)
        draw.arc((18, 18, 46, 46), 205, 335, fill=(110, 184, 255, 255), width=3)
        draw.ellipse((29, 28, 35, 34), fill=(235, 245, 250, 255))
        self._tray = pystray.Icon('G10Control', image, 'G10 Control', menu=pystray.Menu(
            pystray.MenuItem('打开 G10 Control', lambda *_: self.show_window(), default=True),
            pystray.MenuItem('安全退出', lambda *_: self.request_exit())))
        self._tray.run_detached()

class KeyDetection:
    def __init__(self):
        self.root = _local_data() / 'key-detection'; self.root.mkdir(parents=True, exist_ok=True)
        self.proc = None; self.events_path = self.root / 'events.jsonl'; self.stop_path = self.root / 'stop.signal'
        self.lock = threading.RLock()

    def start(self):
        with self.lock:
            if PATHS.frozen:
                raise RuntimeError('Portable 版本尚未包含按键观察器，请使用源码版。')
            if self.proc and self.proc.poll() is None:return {'running': True}
            if getattr(self, '_log', None) and not self._log.closed:
                self._log.close()
            self.proc = None
            target = require_address()
            if not PYTHON_PATH.exists():raise RuntimeError('项目虚拟环境找不到 python.exe。')
            self.events_path.unlink(missing_ok=True); self.stop_path.unlink(missing_ok=True)
            self.ready_path = self.root / 'ready.signal'; self.ready_path.unlink(missing_ok=True)
            self.log_path = self.root / 'observer.log'
            self._log = self.log_path.open('ab', buffering=0)
            subprocess = __import__('subprocess')
            try:
                self.proc = subprocess.Popen(
                    [str(PYTHON_PATH), str(RAW_INPUT),
                     '--match', target.lower(), '--seconds', '86400', '--events-jsonl', str(self.events_path),
                     '--ready-file', str(self.ready_path), '--stop-file', str(self.stop_path),
                     '--output', str(self.root/'summary.json')],
                    cwd=PROJECT_ROOT, stdin=subprocess.DEVNULL,
                    stdout=self._log, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except OSError:
                self._log.close()
                raise
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.ready_path.exists():
                return {'running': True}
            if self.proc and self.proc.poll() is not None:
                code = self.proc.returncode
                with self.lock:
                    self.proc = None
                    if not self._log.closed:self._log.close()
                detail = self.log_path.read_text(encoding='utf-8', errors='replace')[-1200:]
                raise RuntimeError(f'G10 按键观察器未能启动（退出码 {code}）。{detail}')
            time.sleep(.05)
        return {'running': bool(self.proc and self.proc.poll() is None), 'starting': True}

    def stop(self):
        with self.lock:
            process = self.proc
            if not process or process.poll() is not None:
                self.proc = None
                if getattr(self, '_log', None) and not self._log.closed:self._log.close()
                return {'stopped': True}
            self.stop_path.write_text('stop\n', encoding='ascii')
        process.wait(timeout=5)
        with self.lock:
            self.proc = None
            self._log.close()
        return {'stopped': True}

    def snapshot(self):
        with self.lock:
            running = bool(self.proc and self.proc.poll() is None)
        events=[]
        if self.events_path.exists():
            try:events=[json.loads(line) for line in self.events_path.read_text(encoding='utf-8').splitlines()[-80:]]
            except (OSError,ValueError):pass
        return {'running':running,'events':events,'device_filter':G10_ADDRESS}

PYTHON_PATH = PROJECT_ROOT / '.venv' / 'Scripts' / 'python.exe'

def main(lifecycle_report=None):
    import webview
    instance = SingleInstance()
    if instance.already_running:
        instance.close()
        if lifecycle_report:
            Path(lifecycle_report).write_text(json.dumps({'ok': True, 'already_running': True,
                'business_started': False}), encoding='utf-8')
        return
    app = None
    lifecycle = {'ok': False, 'business_started': False}
    lifecycle_done = threading.Event()
    try:
        app = Application(nonbusiness=lifecycle_report is not None)
        bundle = PATHS.web_index
        if not bundle.is_file():
            raise RuntimeError(f'找不到已构建的界面资源：{bundle}')
        from startup_diagnostics import check_webview
        check_webview()
        window = webview.create_window('G10 Control', str(bundle), js_api=app,
                                       width=1280, height=850, min_size=(980, 680), background_color='#f4f7fb')
        app._window = window
        window.events.closing += lambda: app.on_window_closing()
        app.create_tray()
        if lifecycle_report:
            from lifecycle_diagnostics import exercise_lifecycle
            def on_loaded():
                try:
                    lifecycle.update(exercise_lifecycle(app, Path(lifecycle_report)))
                except Exception:
                    import traceback
                    lifecycle['error'] = traceback.format_exc()
                finally:
                    lifecycle_done.set()
                    app._tray.menu.items[1](app._tray)
            window.events.loaded += on_loaded
            def watchdog():
                if not lifecycle_done.wait(25):
                    lifecycle['error'] = 'Lifecycle diagnostic timed out'
                    app.request_exit()
            threading.Thread(target=watchdog, daemon=True).start()
        webview.start(gui='edgechromium', debug=False, private_mode=False,
                      storage_path=str(PATHS.data_path('webview')))
    finally:
        try:
            if app:
                try:
                    app._keys.stop()
                finally:
                    app._supervisor.stop()
        finally:
            if app and app._tray:
                app._tray.stop()
            instance.close()
            if lifecycle_report:
                lifecycle['safe_exit'] = bool(app and app.exit_allowed)
                lifecycle['ok'] = lifecycle['ok'] and lifecycle['safe_exit'] and 'error' not in lifecycle
                Path(lifecycle_report).write_text(json.dumps(lifecycle, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
