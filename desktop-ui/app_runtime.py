"""Desktop application state and subprocess supervision; deliberately separate from its web UI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from datetime import datetime

import psutil

APP_NAME = 'G10 Control'
APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent
BRIDGE = PROJECT_ROOT / 'g10_audio_bridge.py'
RAW_INPUT = PROJECT_ROOT / 'raw_input.py'
PYTHONW = PROJECT_ROOT / '.venv' / 'Scripts' / 'pythonw.exe'
sys.path.insert(0, str(PROJECT_ROOT))
from portable_paths import RuntimePaths, runtime_paths
from local_config import address, cable_capture_id, require_address, require_cable_capture_id
PATHS = runtime_paths()
CABLE_ID = cable_capture_id()
G10_ADDRESS = address()
G10_NAME = 'G10'

def _app_data() -> Path:
    return PATHS.data_dir

def _local_data() -> Path:
    return PATHS.data_dir


def bridge_command(paths: RuntimePaths) -> list[str]:
    if paths.frozen:
        return [str(paths.executable_dir / 'G10-AudioBridge.exe')]
    return [str(PYTHONW), str(BRIDGE)]


def autostart_command() -> str:
    args = [str(Path(sys.executable).resolve())]
    if not PATHS.frozen:
        args.append(str(APP_ROOT / 'app.py'))
    return subprocess.list2cmdline(args)

def default_settings() -> dict:
    return {
        'schema_version': 1,
        'voice': {'auto_wake_doubao': False, 'virtual_microphone_id': CABLE_ID, 'gain_db': 0.0},
        'behavior': {'close_to_tray': True, 'auto_reconnect': False},
        'key_detection': {'target_address': G10_ADDRESS},
    }

class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or _app_data() / 'settings.json'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def load(self) -> dict:
        with self.lock:
            if not self.path.exists():
                return default_settings()
            try:
                loaded = json.loads(self.path.read_text(encoding='utf-8'))
                return normalize_settings(loaded)
            except (OSError, ValueError, TypeError):
                return default_settings()

    def save(self, value: dict) -> dict:
        normalized = normalize_settings(value)
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.path)
        return normalized

def normalize_settings(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError('配置文件格式无效。')
    defaults = default_settings()
    voice = value.get('voice', {})
    behavior = value.get('behavior', {})
    if not isinstance(voice, dict) or not isinstance(behavior, dict):
        raise ValueError('语音或行为设置格式无效。')
    microphone = voice.get('virtual_microphone_id', CABLE_ID)
    if not isinstance(microphone, str) or microphone.lower() != CABLE_ID.lower():
        raise ValueError('当前版本只允许使用已经验证的 CABLE Output。')
    try:
        gain = float(voice.get('gain_db', 0))
    except (TypeError, ValueError) as exc:
        raise ValueError('麦克风增益必须是数字。') from exc
    if not -30 <= gain <= 30:
        raise ValueError('麦克风增益需在 -30 dB 到 +30 dB 之间。')
    defaults['voice'].update(auto_wake_doubao=bool(voice.get('auto_wake_doubao', False)),
                             virtual_microphone_id=CABLE_ID, gain_db=gain)
    defaults['behavior'].update(close_to_tray=bool(behavior.get('close_to_tray', True)),
                                auto_reconnect=bool(behavior.get('auto_reconnect', False)))
    return defaults

class BridgeSupervisor:
    """Owns only the G10 service process. The UI can close without owning BLE resources."""
    def __init__(self, settings: SettingsStore, paths: RuntimePaths | None = None):
        self.settings = settings
        self.paths = paths or PATHS
        self.root = self.paths.data_dir
        self.logs = self.root / 'logs'
        self.state_dir = self.root / 'runtime'
        self.root.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.status_path = self.state_dir / 'bridge-status.json'
        self.stop_path = self.state_dir / 'bridge-stop.signal'
        self.proc: subprocess.Popen | None = None
        self.run_dir: Path | None = None
        self.stdout_path: Path | None = None
        self.lock = threading.RLock()
        self.last_message: str | None = None
        self.started_at: str | None = None

    @staticmethod
    def _external_bridge_processes() -> list[dict]:
        own_pid = os.getpid()
        results = []
        target = str(BRIDGE.resolve()).casefold()
        for process in psutil.process_iter(['pid', 'cmdline', 'name', 'exe']):
            try:
                if process.info['pid'] == own_pid:
                    continue
                command = process.info.get('cmdline') or []
                executable = process.info.get('exe') or (command[0] if command else '')
                # Block another frozen bridge even if it belongs to a moved/copy
                # of the portable directory. Never terminate processes we found.
                frozen_bridge = (Path(executable).name.casefold() == 'g10-audiobridge.exe'
                                 or str(process.info.get('name') or '').casefold() == 'g10-audiobridge.exe')
                if frozen_bridge or any(str(arg).casefold() == target for arg in command):
                    results.append({'pid': process.info['pid'], 'name': process.info.get('name') or 'python'})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return results

    def start(self) -> dict:
        require_address()
        require_cable_capture_id()
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return {'started': True, 'already_running': True}
            external = self._external_bridge_processes()
            if external:
                names = ', '.join(str(item['pid']) for item in external)
                raise RuntimeError(f'检测到另一实例正在运行蓝牙桥接（进程 {names}）。请先在它的窗口中退出，再由 G10 Control 启动。')
            launcher = bridge_command(self.paths)
            if not Path(launcher[0]).is_file():
                raise RuntimeError(f'找不到桥接运行程序：{launcher[0]}')
            self.run_dir = self.logs / datetime.now().strftime('bridge-%Y%m%d-%H%M%S-%f')
            self.run_dir.mkdir(parents=True, exist_ok=False)
            self.status_path.unlink(missing_ok=True)
            self.stop_path.unlink(missing_ok=True)
            self.stdout_path = self.run_dir / 'service.log'
            handle = self.stdout_path.open('ab', buffering=0)
            args = launcher + ['--business-approval', '--allow-cccd',
                    '--headless', '--monitor-output', '--observe-ime', '--max-seconds', '0',
                    '--status-path', str(self.status_path), '--stop-file', str(self.stop_path),
                    '--output', str(self.run_dir / 'events')]
            current = self.settings.load()
            args.extend(['--gain-db', str(current['voice']['gain_db'])])
            if current['voice']['auto_wake_doubao']:
                args.append('--doubao-ime')
            try:
                cwd = self.paths.executable_dir if self.paths.frozen else PROJECT_ROOT
                self.proc = subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL,
                                             stdout=handle, stderr=subprocess.STDOUT,
                                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except OSError:
                handle.close()
                raise
            handle.close()
            self.started_at = datetime.now().astimezone().isoformat()
            self.last_message = '正在启动 BLE 与音频服务…'
            return {'started': True, 'already_running': False}

    def stop(self, timeout: float = 35) -> dict:
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                self.proc = None
                return {'stopped': True}
            self.stop_path.write_text('safe-shutdown\n', encoding='ascii')
            process = self.proc
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            # Do not kill the process: it must restore the GATT notification state and release WinRT.
            raise RuntimeError('蓝牙服务仍在安全清理。窗口保持开启，可以稍后查看状态。') from exc
        with self.lock:
            self.proc = None
        return {'stopped': True, 'exit_code': process.returncode}

    def snapshot(self) -> dict:
        with self.lock:
            proc = self.proc
        backend = {}
        try:
            if self.status_path.exists():
                backend = json.loads(self.status_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            backend = {}
        running = bool(proc and proc.poll() is None)
        stale = not backend or time.time() - _timestamp(backend.get('time')) > 4
        if not running:
            connection = 'stopped'
            detail = self.last_message or '服务已停止'
        elif stale:
            connection = 'starting'
            detail = '正在连接 G10…'
        elif backend.get('connected'):
            connection = 'connected'
            detail = 'G10 已连接，ATVV 音频通知已就绪'
        else:
            connection = 'starting'
            detail = backend.get('last_error') or '正在发现 ATVV 服务…'
        return {
            'application': {'name': APP_NAME, 'version': '0.1.0', 'single_instance': True},
            'paths': {'data_directory': str(self.root), 'portable': self.paths.portable,
                      'fallback_reason': self.paths.fallback_reason},
            'service': {'running': running, 'connection': connection, 'detail': detail,
                        'started_at': self.started_at,
                        'audio_active': bool(backend.get('audio_active')),
                        'processed_audio_seconds': backend.get('processed_audio_seconds', 0),
                        'input_level_dbfs': backend.get('input_level_dbfs', -120),
                        'cable_level_dbfs': backend.get('cable_level_dbfs', -120),
                        'cable_peak': backend.get('cable_peak', 0),
                        'error_count': backend.get('error_count', 0),
                        'error': backend.get('last_error')},
            'device': {'name': G10_NAME, 'address': G10_ADDRESS, 'transport': 'Bluetooth LE',
                       'vid': '0x620A', 'pid': '0x0407', 'battery': None},
            'microphone': {'name': 'CABLE Output (VB-Audio Virtual Cable)', 'id': CABLE_ID,
                           'validated': True, 'is_active': bool(backend.get('audio_active'))},
        }

    def logs_tail(self, limit: int = 80) -> list[dict]:
        path = self.run_dir / 'events' / 'events.jsonl' if self.run_dir else None
        if not path or not path.exists():
            return []
        try:
            lines = path.read_text(encoding='utf-8').splitlines()[-max(1, min(limit, 250)):]
            return [json.loads(line) for line in lines]
        except (OSError, ValueError):
            return []

    def export_diagnostics(self) -> dict:
        state = self.snapshot()
        # Notification payloads are not present in the event log. HID data is only
        # available through the opt-in Raw Input monitor and can be reviewed locally.
        return {'generated_at': datetime.now().astimezone().isoformat(), 'state': state,
                'recent_events': self.logs_tail(250), 'service_output': self._stdout_tail(),
                'contains_audio_or_recognized_text': False}

    def _stdout_tail(self) -> list[str]:
        if not self.stdout_path or not self.stdout_path.exists():
            return []
        try:
            return self.stdout_path.read_text(encoding='utf-8', errors='replace').splitlines()[-80:]
        except OSError:
            return []

def _timestamp(value) -> float:
    if not value:
        return 0
    try:
        return datetime.fromisoformat(value).timestamp()
    except (ValueError, TypeError):
        return 0
