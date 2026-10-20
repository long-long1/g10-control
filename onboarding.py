"""Resumable setup progress. Completion is derived from live backend gates."""
import json
from pathlib import Path
import platform
import struct
import sys
import threading


def environment_checks():
    checks = []
    windows = sys.platform == 'win32'
    try:
        build = int(platform.version().split('.')[-1])
    except ValueError:
        build = 0
    checks.append({'name': 'Windows 11 x64', 'passed': windows and build >= 22000 and struct.calcsize('P') == 8,
                   'detail': f'{platform.system()} {platform.version()} / {platform.machine()}'})
    release = 0
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full') as key:
            release = int(winreg.QueryValueEx(key, 'Release')[0])
        checks.append({'name': '.NET Framework', 'passed': release >= 394802,
                       'detail': f'Release {release}；需 4.6.2 或更新版本'})
    except Exception as exc:
        checks.append({'name': '.NET Framework', 'passed': False, 'detail': f'无法读取依赖，请检查安装或权限：{exc}'})
    try:
        from startup_diagnostics import check_webview
        result = check_webview()
        checks.append({'name': 'WebView2', 'passed': bool(result['browser_version']),
                       'detail': result['browser_version']})
    except Exception as exc:
        checks.append({'name': 'WebView2', 'passed': False,
                       'detail': f'请手动安装 Microsoft Edge WebView2 Runtime 后重试：{exc}'})
    return checks


def step_statuses(environment, devices, route):
    env = ('passed' if environment and all(item['passed'] for item in environment)
           else 'failed' if environment else 'not_checked')
    device = ('checking' if devices['busy'] else 'passed' if devices['compatible']
              else 'failed' if devices['state'] == 'failed' else 'waiting_user' if devices['selected'] else 'not_checked')
    endpoints = ('passed' if route['pair'] else 'not_checked' if route['state'] in ('missing', 'needs_detection') else 'failed')
    proof = ('passed' if route['validated'] else 'failed' if route['state'] in ('expired', 'invalid', 'changed', 'failed')
             else 'waiting_user' if route['pair'] or route['state'] == 'needs_detection' else 'not_checked')
    first = [env, device, endpoints, proof]
    return first + ['passed' if all(item == 'passed' for item in first) else 'waiting_user']


class SetupWizard:
    def __init__(self, paths, devices, routes, *, environment=None):
        self.paths, self.devices, self.routes = paths, devices, routes
        self.path = paths.data_path('setup-progress.json')
        self.environment_fn = environment or environment_checks
        self.checks = []
        self.checking = False
        self.lock = threading.RLock()

    def _load(self):
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if type(value.get('step')) is not int or not 0 <= value['step'] <= 4:
                raise ValueError()
            return value
        except (OSError, ValueError, TypeError, AttributeError):
            return {'step': 0, 'completed': False}

    def _save(self, value):
        temporary = self.path.with_suffix('.tmp')
        try:
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def snapshot(self):
        with self.lock:
            saved = self._load()
            statuses = step_statuses(self.checks, self.devices.snapshot(), self.routes.snapshot())
            if self.checking:
                statuses[0] = 'checking'
            ready = all(value == 'passed' for value in statuses)
            return {'step': saved['step'], 'completed': saved.get('completed') is True and ready,
                    'ready': ready, 'statuses': statuses, 'environment': self.checks,
                    'data_directory': str(self.paths.data_dir), 'portable': self.paths.portable,
                    'fallback_reason': self.paths.fallback_reason}

    def set_step(self, step):
        if type(step) is not int or not 0 <= step <= 4:
            raise ValueError('向导步骤无效。')
        with self.lock:
            value = self._load()
            value['step'] = step
            self._save(value)
            return self.snapshot()

    def detect_environment(self):
        self.checking = True
        self.checks = []
        try:
            self.checks = self.environment_fn()
        except Exception as exc:
            self.checks = [{'name': '运行环境', 'passed': False, 'detail': f'检测失败，请重试：{exc}'}]
        finally:
            self.checking = False
        return self.snapshot()

    def complete(self):
        with self.lock:
            if not self.snapshot()['ready']:
                raise RuntimeError('环境、设备兼容性或本机音频路由尚未通过，不能完成配置。')
            self._save({'step': 4, 'completed': True})
            return self.snapshot()
