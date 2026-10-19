"""Explicit BLE discovery and capability-only checking using the existing transport."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import queue
import threading
from types import SimpleNamespace

from atvv_protocol import SERVICE, TX, AUDIO, CONTROL, CAPABILITIES, capabilities
from local_config import normalize_address, config_path
from phase2_handshake import Controller

PROFILE = 'atvv-g10-128-v1'


async def scan_candidates():
    from bleak import BleakScanner
    found = await BleakScanner.discover(timeout=5, return_adv=True)
    result = []
    for device, adv in found.values():
        address = normalize_address(device.address)
        result.append({'id': address, 'address': address, 'name': adv.local_name or device.name or '',
                       'advertised_services': [str(value).lower() for value in adv.service_uuids]})
    return result


class CapabilityOnly(Controller):
    """Only GET_CAPABILITIES may reach the inherited exact-byte transport."""
    def bind(self, chars, loop):
        super().bind(chars, loop)
        self.identity = {key: int(chars[key].characteristic_properties) for key in (TX, AUDIO, CONTROL)}

    async def send(self, name, data):
        if name != 'GET_CAPABILITIES' or data != CAPABILITIES:
            raise RuntimeError('兼容性检查禁止开麦、关麦或其他业务命令。')
        await super().send(name, data)

    def receive(self, key, data, perf):
        if key == CONTROL and data[:1] == b'\x0b':
            self.raw_capabilities = data.hex()
            super().receive(key, data, perf)

    async def initialize(self):
        try:
            await super().initialize()
            if self.caps.codec != 2 or self.caps.frame_size != 128 or self.caps.raw_frame_size != 128:
                raise RuntimeError('能力条件不符合已验证的 128 字节 / codec 2 配置。')
        finally:
            self.stop.set()

    async def close(self):
        self.closed = True  # No MIC_CLOSE: this checker never owns a mic session.


class _Evidence:
    def __init__(self):
        self.errors = []
        self.device_address = None
        self.cleanup = False

    def emit(self, kind, **fields):
        if kind == 'device':
            self.device_address = fields['address']
        elif kind == 'ble_cleanup_complete':
            self.cleanup = not fields['errors']

    def notification(self, *_):
        pass  # Never saves audio or notifications.


async def check_candidate(candidate):
    # The proven transport deliberately requires a Windows-paired G10 name and
    # exact address. Do not broaden that hardware boundary silently.
    if candidate['name'] != 'G10':
        raise RuntimeError('现有受控传输仅支持 Windows 已配对且名称为 G10 的候选设备；名称本身不代表兼容。')
    from phase2_readonly import observe
    rec = _Evidence()
    stop, ready = threading.Event(), threading.Event()
    updates = queue.Queue()
    controller = CapabilityOnly(rec, stop, updates)
    args = SimpleNamespace(address=candidate['address'], allow_cccd=True)
    await observe(rec, stop, ready, updates, args, controller)
    if rec.errors or not rec.cleanup or rec.device_address != candidate['address'] or controller.caps is None:
        raise RuntimeError('能力检查或安全清理失败：' + '; '.join(rec.errors or ['设备身份未确认']))
    return {'profile': PROFILE, 'address': rec.device_address, 'service': SERVICE,
            'characteristics': controller.identity, 'capabilities_hex': controller.raw_capabilities,
            'cleanup_complete': True}


def validate_evidence(evidence, address):
    try:
        caps = capabilities(bytes.fromhex(evidence['capabilities_hex']))
        props = evidence['characteristics']
        return (evidence['profile'] == PROFILE and evidence['address'] == address
                and evidence['service'] == SERVICE and evidence['cleanup_complete'] is True
                and caps.codec == 2 and caps.frame_size == 128 and caps.raw_frame_size == 128
                and props[TX] & 4 != 0 and props[AUDIO] & 16 != 0 and props[CONTROL] & 16 != 0)
    except (KeyError, ValueError, TypeError):
        return False


class DeviceSetup:
    def __init__(self, path=None, *, scanner=None, checker=None):
        self.path = Path(path) if path else config_path()
        self.scanner = scanner or scan_candidates
        self.checker = checker or check_candidate
        self.lock = threading.RLock()
        self.candidates = []
        self.busy = False
        self.state = 'not_checked'
        self.message = '请点击扫描，选择本机设备；兼容性需单独检查。'

    def _load(self):
        try:
            value = json.loads(self.path.read_text(encoding='utf-8-sig'))
            return value if isinstance(value, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            raise RuntimeError('本机设备配置无法读取，请检查文件或权限。') from exc

    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        try:
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def snapshot(self):
        with self.lock:
            selected, compatible = None, False
            try:
                data = self._load()
                selected = data.get('selected_device')
                record = data.get('device_compatibility', {})
                if selected is not None and (not isinstance(selected, dict) or not isinstance(selected.get('address'), str)):
                    selected = None
                    raise ValueError('invalid selected device')
                compatible = False
                if selected and data.get('bluetooth_address') == selected['address']:
                    stamp = datetime.fromisoformat(record.get('verified_at', ''))
                    age = datetime.now(timezone.utc) - stamp
                    compatible = (timedelta(0) <= age < timedelta(days=30)
                                  and validate_evidence(record, selected['address']))
            except (ValueError, TypeError, KeyError, AttributeError):
                compatible = False
            except RuntimeError as exc:
                return {'state': 'failed', 'message': str(exc), 'selected': None, 'compatible': False,
                        'candidates': self.candidates, 'busy': self.busy}
            compatible = compatible and self.state != 'failed'
            return {'state': self.state if not compatible else 'compatible', 'message': self.message,
                    'selected': selected, 'compatible': bool(compatible),
                    'candidates': self.candidates, 'busy': self.busy}

    def _begin(self, state, message):
        with self.lock:
            if self.busy:
                raise RuntimeError('设备操作仍在进行，请等待安全清理完成。')
            self.busy, self.state, self.message = True, state, message

    def scan(self):
        self._begin('scanning', '正在扫描 BLE 设备…')
        self.candidates = []
        try:
            rows = asyncio.run(self.scanner())
            unique = {}
            for row in rows:
                address = normalize_address(row['address'])
                if not address or address == '000000000000':
                    continue
                unique[address] = {'id': address, 'address': address, 'name': str(row.get('name') or ''),
                                   'advertised_services': list(row.get('advertised_services', []))}
            with self.lock:
                self.candidates = list(unique.values())
                self.state, self.message = 'scanned', '请选择设备；广播名称或服务提示不代表已兼容。'
        except Exception as exc:
            self.state, self.message = 'failed', f'扫描失败，请检查蓝牙、权限和 Windows 配对状态：{exc}'
        finally:
            self.busy = False
        return self.snapshot()

    def select(self, identity):
        with self.lock:
            if self.busy:
                raise RuntimeError('请等待设备操作完成。')
            rows = [row for row in self.candidates if row['id'] == identity]
            if len(rows) != 1:
                raise ValueError('请从当前扫描列表中选择唯一设备。')
            data = self._load()
            data.update(bluetooth_address=rows[0]['address'], selected_device=rows[0], device_compatibility={})
            self._save(data)
            self.state, self.message = 'selected', '设备已保存，兼容性尚未验证。'
            return self.snapshot()

    def check(self, confirmed=False):
        if confirmed is not True:
            raise ValueError('检查将连接设备、临时订阅通知并发送一次能力请求，需要明确确认。')
        self._begin('checking', '正在检查 ATVV 服务、特征和能力；不会发送开麦命令。')
        try:
            data = self._load()
            selected = data.get('selected_device')
            if not selected:
                raise ValueError('请先选择设备。')
            data['device_compatibility'] = {}
            self._save(data)  # A failed recheck must not keep old compatibility.
            evidence = asyncio.run(self.checker(selected))
            if not validate_evidence(evidence, selected['address']):
                raise RuntimeError('服务、特征、设备身份或能力未通过验证。')
            evidence['verified_at'] = datetime.now(timezone.utc).isoformat()
            data['device_compatibility'] = evidence
            self._save(data)
            self.state, self.message = 'compatible', '设备身份、ATVV 服务/特征及已验证协议能力检查通过。'
        except Exception as exc:
            self.state, self.message = 'failed', f'设备兼容性未通过：{exc}'
        finally:
            self.busy = False
        return self.snapshot()

    def require_compatible(self, address):
        state = self.snapshot()
        if not state['compatible'] or state['selected']['address'] != address:
            raise RuntimeError('本机设备尚未通过有效的 ATVV 兼容性检查，请在设置向导中重新检查。')
