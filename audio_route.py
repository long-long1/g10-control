"""Local VB-CABLE route proof policy; no BLE, default setters or microphone fallback.

The existing WASAPI probe and correlation algorithm remain in virtual_audio_probe.
Only explicit detect/verify calls enumerate devices; snapshot reads local JSON.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import secrets
import tempfile
import threading

from portable_paths import runtime_paths
from virtual_audio_probe import catalog, probe, select_devices

SCHEMA_VERSION = 1
VALIDATOR_VERSION = 'vbcable-synthetic-1'
SAMPLE_RATE = 48000
MAX_AGE = timedelta(days=30)
CONFIRM_AGE = timedelta(minutes=5)


class RouteError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@contextmanager
def _com_thread():
    # pywebview dispatches API calls on worker threads, not the UI COM thread.
    import comtypes
    comtypes.CoInitialize()
    try:
        yield
    finally:
        comtypes.CoUninitialize()


def _catalog():
    with _com_thread():
        return catalog()


def _probe(info, directory):
    with _com_thread():
        return probe(info, directory, 'vbcable')


def select_pair(info):
    """Retain the original selection checks and bind both Core Audio identities."""
    devices = info['wasapi_devices']
    endpoints = info['core_audio_endpoints']
    standard = [d for d in devices if 'VB-Audio Virtual Cable' in d.get('name', '')]
    counts = [sum(tag in d['name'] and d.get(channels, 0) > 0 for d in standard)
              for tag, channels in [('CABLE Output', 'max_input_channels'),
                                    ('CABLE Input', 'max_output_channels')]]
    if 0 in counts:
        raise RouteError('missing_driver', '未检测到完整的标准 VB-CABLE 播放/录音端点。请自行检查驱动安装，不会自动安装或选用其他设备。')
    if counts != [1, 1]:
        raise RouteError('ambiguous', '检测到重复的 VB-CABLE 端点，无法唯一确定路由；请先解决重复端点。')
    if any(sum(e['name'] == device['name'] and e['flow'] == flow and e['state'] == 1
               for e in endpoints) > 1 for device in standard for flow in (0, 1)):
        raise RouteError('ambiguous', '检测到重复的 VB-CABLE Core Audio 端点身份，请先解决重复端点。')
    try:
        capture, render = select_devices(info, 'vbcable')
    except RuntimeError as exc:
        raise RouteError('endpoint_unavailable', f'VB-CABLE 端点不可用或身份有歧义：{exc}') from exc
    pair = {}
    for role, device, flow in [('capture', capture, 1), ('render', render, 0)]:
        matches = [e for e in endpoints if e['name'] == device['name'] and e['flow'] == flow and e['state'] == 1]
        if len(matches) != 1:
            raise RouteError('ambiguous', 'VB-CABLE Core Audio 身份不唯一。')
        endpoint = matches[0]
        mix = endpoint.get('mix_format', {})
        if endpoint.get('read_error') or not isinstance(endpoint.get('muted'), bool) or not mix:
            raise RouteError('endpoint_unavailable', '无法读取 VB-CABLE 的静音、音量或共享格式；不会猜测或更改设置。')
        volume = endpoint.get('volume_scalar')
        if not isinstance(volume, (int, float)) or not math.isfinite(volume) or volume <= 0:
            raise RouteError('endpoint_unavailable', 'VB-CABLE 音量不可读或为零，请手动检查。')
        if device['default_samplerate'] != SAMPLE_RATE or mix.get('nSamplesPerSec') != SAMPLE_RATE:
            raise RouteError('sample_rate', 'CABLE Input 和 CABLE Output 都必须为 48000 Hz；请手动调整后重新检测。')
        if mix.get('nChannels', 0) < 2:
            raise RouteError('sample_rate', 'VB-CABLE 共享格式必须支持双声道；不会自动更改设备格式。')
        if not isinstance(endpoint.get('id'), str) or not endpoint['id']:
            raise RouteError('endpoint_unavailable', 'VB-CABLE 缺少可绑定的端点 ID。')
        pair[role] = {'id': endpoint['id'], 'name': device['name'], 'flow': flow,
                      'samplerate': SAMPLE_RATE, 'mix_format': dict(mix)}
    return capture, render, pair


def _defaults_complete(info):
    value = info.get('defaults', {})
    if set(value) != {f'{flow}:{role}' for flow in (0, 1) for role in (0, 1, 2)} or any(
            not isinstance(item, str) or not item for item in value.values()):
        raise RouteError('defaults_unreadable', '无法读取全部 Windows 默认端点，拒绝运行验证。')
    return value


def _check_result(result, pair):
    if not isinstance(result, dict) or result.get('passed') is not True:
        raise RouteError('failed', '合成信号路由验证未通过，请检查 VB-CABLE 后重新验证。')
    channels = result.get('channels')
    if (result.get('profile') != 'vbcable' or result.get('samplerate') != SAMPLE_RATE
            or result.get('capture_name') != pair['capture']['name']
            or result.get('render_name') != pair['render']['name']
            or result.get('input_status') != [] or result.get('output_underflow') is not False
            or not isinstance(channels, list) or len(channels) != 2):
        raise RouteError('failed', '验证结果的端点、格式或流状态不符合安全要求，请重新验证。')
    scores = [channel.get('correlation') if isinstance(channel, dict) else None for channel in channels]
    if any(type(score) not in (int, float) or not math.isfinite(score) or abs(score) > 1.000001 for score in scores):
        raise RouteError('failed', '路由相关性结果无效。')
    if not any(abs(score) > .8 for score in scores):
        raise RouteError('failed', '未收到匹配的合成信号（相关性需大于 0.8），请重新验证。')
    frames = result.get('capture_frames')
    seconds = result.get('test_seconds')
    if (type(frames) is not int or not round(SAMPLE_RATE * 1.48) <= frames <= SAMPLE_RATE * 6
            or type(seconds) not in (int, float) or not math.isfinite(seconds)
            or abs(seconds - 1.48) > .001):
        raise RouteError('failed', '合成验证的采集长度不完整。')


def _check_proof(record, now, pair=None):
    try:
        if (record['schema_version'] != SCHEMA_VERSION or record['validator_version'] != VALIDATOR_VERSION
                or record['defaults_unchanged'] is not True):
            raise ValueError('version or defaults check')
        created = datetime.fromisoformat(record['verified_at'])
        if created.tzinfo is None or created > now + timedelta(minutes=5):
            raise ValueError('timestamp')
        if now - created >= MAX_AGE:
            raise RouteError('expired', '本机路由证明已超过 30 天，请重新验证。')
        stored = record['pair']
        for role, flow, tag in [('capture', 1, 'CABLE Output'), ('render', 0, 'CABLE Input')]:
            endpoint = stored[role]
            if (not isinstance(endpoint['id'], str) or not endpoint['id'] or endpoint['flow'] != flow
                    or tag not in endpoint['name'] or 'VB-Audio Virtual Cable' not in endpoint['name']
                    or endpoint['samplerate'] != SAMPLE_RATE
                    or endpoint['mix_format']['nSamplesPerSec'] != SAMPLE_RATE
                    or endpoint['mix_format']['nChannels'] < 2):
                raise ValueError('endpoint identity/format')
        _check_result(record['result'], stored)
        if pair is not None and pair != stored:
            raise RouteError('changed', 'VB-CABLE 端点 ID、名称或共享格式已变化，请重新验证。')
        return record
    except RouteError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise RouteError('invalid', '本机路由证明无效或版本不兼容，请重新验证。') from exc


class AudioRoute:
    def __init__(self, paths=None, *, catalog_fn=None, probe_fn=None, now=None):
        self.paths = paths or runtime_paths()
        self.proof_path = self.paths.data_path('audio/route-proof.json')
        self._catalog = catalog_fn or _catalog
        self._probe = probe_fn or _probe
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.lock = threading.RLock()
        self._pair = None
        self._confirmation = None
        self._error = None

    def _read(self, pair=None):
        try:
            value = json.loads(self.proof_path.read_text(encoding='utf-8'))
        except FileNotFoundError as exc:
            raise RouteError('missing', '尚无本机 VB-CABLE 路由证明，请检测并确认合成验证。') from exc
        except (OSError, ValueError) as exc:
            raise RouteError('invalid', '本机路由证明无法读取，请重新验证。') from exc
        return _check_proof(value, self._now(), pair)

    def snapshot(self):
        with self.lock:
            try:
                proof = self._read(self._pair)
                state = 'verified' if self._pair else 'needs_detection'
                message = '本机路由证明有效。' if self._pair else '已保存路由证明；需重新检测当前端点，启动桥接时也会复核。'
                verified_at = proof['verified_at']
            except RouteError as exc:
                state, message, verified_at = exc.code, str(exc), None
            if self._error:
                state, message = self._error
            return {'state': state, 'message': message, 'validated': state == 'verified',
                    'pair': self._pair, 'verified_at': verified_at, 'proof_path': str(self.proof_path),
                    'confirmation_token': self._confirmation[0] if self._confirmation else None}

    def detect(self):
        with self.lock:
            self._pair = self._confirmation = self._error = None
            try:
                _, _, self._pair = select_pair(self._catalog())
                self._confirmation = (secrets.token_urlsafe(24), self._now(), self._pair)
            except Exception as exc:
                self._error = (getattr(exc, 'code', 'endpoint_unavailable'), str(exc))
            return self.snapshot()

    def require_verified(self):
        """Fresh enumeration is mandatory before every actual bridge launch."""
        with self.lock:
            self._error = None
            # Missing/expired/corrupt proof is rejected before touching audio APIs.
            self._read()
            try:
                capture, render, pair = select_pair(self._catalog())
                self._pair = pair
                self._read(pair)
                return capture, render, pair
            except Exception as exc:
                self._error = (getattr(exc, 'code', 'endpoint_unavailable'), str(exc))
                raise

    def verify(self, token, confirmed=False):
        with self.lock:
            confirmation = self._confirmation
            self._confirmation = None  # Single use, including rejected requests.
            if (confirmed is not True or not confirmation or not isinstance(token, str)
                    or not secrets.compare_digest(token, confirmation[0])
                    or not timedelta(0) <= self._now() - confirmation[1] < CONFIRM_AGE):
                raise RouteError('confirmation', '请重新检测端点，并在确认框中同意合成验证。')
            self._error = None
            try:
                # A failed revalidation must not leave an older success usable.
                self.proof_path.unlink(missing_ok=True)
                info = self._catalog()
                _, _, pair = select_pair(info)
                if pair != confirmation[2]:
                    raise RouteError('changed', '确认后端点已变化，尚未打开音频流；请重新检测。')
                before = _defaults_complete(info)
                with tempfile.TemporaryDirectory(prefix='route-', dir=self.proof_path.parent) as folder:
                    result = self._probe(info, Path(folder))
                _check_result(result, pair)
                after_info = self._catalog()
                _, _, after_pair = select_pair(after_info)
                if pair != after_pair:
                    raise RouteError('changed', '验证期间端点或格式变化，证明未保存。')
                if before != _defaults_complete(after_info):
                    raise RouteError('defaults_changed', '验证期间 Windows 默认端点变化，证明未保存；程序不会更改或恢复系统设置。')
                record = {'schema_version': SCHEMA_VERSION, 'validator_version': VALIDATOR_VERSION,
                          'verified_at': self._now().isoformat(), 'pair': pair,
                          'defaults_unchanged': True, 'result': result}
                _check_proof(record, self._now(), pair)
                self._save(record)
                self._pair = pair
                return self.snapshot()
            except Exception as exc:
                self._pair = None
                self._error = (getattr(exc, 'code', 'failed'), f'验证未完成：{exc}')
                raise

    def _save(self, record):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.tmp',
                                             dir=self.proof_path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(record, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.proof_path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
