"""Explicit BLE discovery and capability-only checking using the existing transport."""
import asyncio
from datetime import datetime, timedelta, timezone
import re
import json
from pathlib import Path
import queue
import threading
from types import SimpleNamespace

from atvv_protocol import SERVICE, TX, AUDIO, CONTROL, CAPABILITIES, capabilities
from local_config import normalize_address, config_path, address as active_address
from phase2_handshake import Controller

PROFILE = 'atvv-g10-128-v1'
AEP_DEVICE_ADDRESS = 'System.Devices.Aep.DeviceAddress'
AEP_IS_CONNECTED = 'System.Devices.Aep.IsConnected'
AEP_IS_PRESENT = 'System.Devices.Aep.IsPresent'


def _address_from_device_id(device_id):
    """Fallback for Windows IDs that embed the peer Bluetooth address."""
    match = re.search(r'(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}', str(device_id or ''))
    if not match:
        return ''
    try:
        return normalize_address(match.group(0))
    except ValueError:
        return ''


async def enumerate_paired_devices():
    """Read Windows' paired BLE identities without scanning for advertisements."""
    from winrt.windows.devices.bluetooth import BluetoothLEDevice
    from winrt.windows.devices.enumeration import DeviceInformation

    selector = BluetoothLEDevice.get_device_selector_from_pairing_state(True)
    devices = await asyncio.wait_for(
        DeviceInformation.find_all_async_aqs_filter_and_additional_properties(
            selector, [AEP_DEVICE_ADDRESS, AEP_IS_CONNECTED, AEP_IS_PRESENT]),
        20)
    result, unresolved = [], 0
    for device in devices:
        properties = device.properties
        address_value = properties.get(AEP_DEVICE_ADDRESS)
        try:
            address = normalize_address(str(address_value or '')) if address_value else ''
        except ValueError:
            address = ''
        address = address or _address_from_device_id(device.id)
        if not address or address == '000000000000':
            unresolved += 1
            continue
        connected = properties.get(AEP_IS_CONNECTED)
        present = properties.get(AEP_IS_PRESENT)
        result.append({
            'id': address,
            'address': address,
            'name': str(device.name or ''),
            'advertised_services': [],
            'paired': True,
            'connected': bool(connected) if connected is not None else None,
            'present': bool(present) if present is not None else None,
            'winrt_device_id': str(device.id),
            'name_source': 'windows' if device.name else '',
        })
    warnings = []
    if unresolved:
        warnings.append(f'Windows 返回了 {unresolved} 个已配对 BLE 设备，但未提供可关联的蓝牙地址。')
    return result, warnings


def merge_device_candidates(paired, advertisements):
    """Merge Windows pairing identities and transient Bleak advertisement rows by address."""
    merged = {}
    for row in paired:
        address = normalize_address(str(row.get('address') or ''))
        if not address or address == '000000000000':
            continue
        item = dict(row)
        item.update(id=address, address=address, paired=True)
        item['advertised_services'] = list(item.get('advertised_services') or [])
        item['name'] = str(item.get('name') or '')
        item['name_source'] = item.get('name_source') or ('windows' if item['name'] else '')
        previous = merged.get(address)
        if previous:
            services = sorted(set(previous['advertised_services'] + item['advertised_services']))
            preferred = item if item.get('connected') is True and previous.get('connected') is not True else previous
            if not preferred['name']:
                other = item if preferred is previous else previous
                preferred['name'], preferred['name_source'] = other['name'], other['name_source']
            if not preferred.get('winrt_device_id'):
                other = item if preferred is previous else previous
                preferred['winrt_device_id'] = other.get('winrt_device_id', '')
            if preferred.get('connected') is None:
                other = item if preferred is previous else previous
                preferred['connected'] = other.get('connected')
            if preferred.get('present') is None:
                other = item if preferred is previous else previous
                preferred['present'] = other.get('present')
            preferred['advertised_services'] = services
            merged[address] = preferred
        else:
            merged[address] = item
    for row in advertisements:
        try:
            address = normalize_address(str(row.get('address') or ''))
        except ValueError:
            continue
        if not address or address == '000000000000':
            continue
        item = merged.get(address)
        adv_name = str(row.get('name') or '')
        services = [str(value).lower() for value in row.get('advertised_services', [])]
        if item is None:
            merged[address] = {
                'id': address, 'address': address, 'name': adv_name,
                'advertised_services': services, 'paired': False,
                'connected': None, 'present': True, 'winrt_device_id': '',
                'name_source': 'advertisement' if adv_name else '',
            }
            continue
        item['advertised_services'] = sorted(set(item['advertised_services'] + services))
        item['present'] = True
        if not item['name'] and adv_name:
            item['name'] = adv_name
            item['name_source'] = 'advertisement'
    return sorted(merged.values(), key=lambda row: (
        not (row['paired'] and 'g10' in row['name'].casefold()),
        row['connected'] is not True,
        not row['paired'],
        row['name'].casefold(),
        row['address']))


async def scan_candidates():
    warnings = []
    try:
        paired, warnings = await enumerate_paired_devices()
    except Exception as exc:
        paired = []
        warnings = [f'Windows 已配对设备列表读取失败：{exc}']
    advertisements = []
    try:
        from bleak import BleakScanner
        found = await BleakScanner.discover(timeout=5, return_adv=True)
        for device, adv in found.values():
            address = normalize_address(device.address)
            advertisements.append({'address': address, 'name': adv.local_name or device.name or '',
                                   'advertised_services': [str(value).lower() for value in adv.service_uuids]})
    except Exception as exc:
        warnings.append(f'BLE 广播扫描失败；仍显示 Windows 配对列表：{exc}')
    return {'candidates': merge_device_candidates(paired, advertisements), 'warnings': warnings}


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
    # Names and advertisement hints are optional labels. Resolve the peer via
    # Windows' paired identity, then let live GATT/capability evidence decide.
    if candidate.get('paired') is not True:
        raise RuntimeError('此项仅来自 BLE 广播，尚未关联到 Windows 已配对设备；请先在 Windows 蓝牙设置中配对，再扫描。')
    if not candidate.get('winrt_device_id'):
        raise RuntimeError('Windows 配对项没有可用的设备 ID，无法可靠关联 GATT 设备；请在 Windows 蓝牙设置中移除并重新配对后再扫描。')
    if not candidate.get('address'):
        raise RuntimeError('Windows 配对项未提供可验证的蓝牙地址，无法安全关联 GATT 设备。')
    from phase2_readonly import observe
    rec = _Evidence()
    stop, ready = threading.Event(), threading.Event()
    updates = queue.Queue()
    controller = CapabilityOnly(rec, stop, updates)
    args = SimpleNamespace(address=candidate['address'], device_id=candidate['winrt_device_id'], allow_cccd=True)
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
        self.active_address = None if path else active_address
        self.scanner = scanner or scan_candidates
        self.checker = checker or check_candidate
        self.lock = threading.RLock()
        self.candidates = []
        self.busy = False
        self.state = 'not_checked'
        self.message = '请点击扫描，选择本机设备；兼容性需单独检查。'
        self.scan_warnings = []

    def _load(self):
        try:
            value = json.loads(self.path.read_text(encoding='utf-8-sig'))
            if not isinstance(value, dict):
                raise ValueError('expected an object')
            return value
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
            mismatch = False
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
                    if self.active_address and self.active_address() != selected['address']:
                        compatible = False
                        mismatch = True
            except (ValueError, TypeError, KeyError, AttributeError):
                compatible = False
            except RuntimeError as exc:
                return {'state': 'failed', 'message': str(exc), 'selected': None, 'compatible': False,
                        'candidates': self.candidates, 'busy': self.busy, 'warnings': self.scan_warnings}
            compatible = compatible and self.state != 'failed' and not self.busy
            state, message = self.state, self.message
            if compatible:
                state, message = 'compatible', '已保存的设备身份与有效 ATVV 能力证据匹配。'
            elif mismatch:
                state, message = 'failed', '实际蓝牙地址或环境变量覆盖与选择的设备不一致，请移除旧覆盖并重新检查。'
            elif selected and state in ('compatible', 'not_checked'):
                state, message = 'selected', '已保存设备，但兼容性证据未确认或已失效，请重新检查。'
            return {'state': state, 'message': message,
                    'selected': selected, 'compatible': bool(compatible),
                    'candidates': self.candidates, 'busy': self.busy, 'warnings': self.scan_warnings}

    def _begin(self, state, message):
        with self.lock:
            if self.busy:
                raise RuntimeError('设备操作仍在进行，请等待安全清理完成。')
            self.busy, self.state, self.message = True, state, message

    def scan(self):
        self._begin('scanning', '正在扫描 BLE 设备…')
        self.candidates = []
        self.scan_warnings = []
        try:
            result = asyncio.run(self.scanner())
            if isinstance(result, dict):
                rows = result.get('candidates', [])
                self.scan_warnings = [str(item) for item in result.get('warnings', [])]
            else:  # Backwards-compatible injection seam for existing offline tests.
                rows = result
            normalized = []
            for row in rows:
                try:
                    address = normalize_address(str(row.get('address') or ''))
                except ValueError:
                    continue
                if not address or address == '000000000000':
                    continue
                item = {'id': address, 'address': address, 'name': str(row.get('name') or ''),
                        'advertised_services': list(row.get('advertised_services') or []),
                        'paired': row.get('paired') is True,
                        'connected': row.get('connected'), 'present': row.get('present'),
                        'winrt_device_id': str(row.get('winrt_device_id') or ''),
                        'name_source': str(row.get('name_source') or '')}
                normalized.append(item)
            with self.lock:
                self.candidates = merge_device_candidates(
                    [row for row in normalized if row['paired']],
                    [row for row in normalized if not row['paired']])
                paired_g10 = [row for row in self.candidates if row['paired'] and 'g10' in row['name'].casefold()]
                paired_count = sum(row['paired'] for row in self.candidates)
                if paired_g10:
                    self.state, self.message = 'scanned', '已从 Windows 配对设备中找到 G10 候选；仍需连接后验证 ATVV 服务、特征和 codec 2 / 128 字节能力。'
                elif paired_count:
                    self.state, self.message = 'scanned', f'已读取 {paired_count} 个 Windows 配对 BLE 设备，但没有名称含 G10 的项目；可按已配对身份查看候选，名称缺失不代表不兼容。'
                else:
                    self.state, self.message = 'scanned', '未找到可关联的 Windows 配对 BLE 设备；先在 Windows 设置中确认 G10 已配对，再刷新。广播设备名称和 ATVV 提示都不是兼容性结论。'
                if self.scan_warnings:
                    self.message += ' ' + ' '.join(self.scan_warnings)
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
            if rows[0].get('paired') is not True or not rows[0].get('winrt_device_id'):
                raise ValueError('该项尚未关联到 Windows 配对设备；请先在 Windows 蓝牙设置中配对，然后扫描已配对列表。')
            try:
                data = self._load()
            except RuntimeError:
                # Explicit selection recovers identity; preserve corrupt input.
                backup = self.path.with_name(self.path.name + '.corrupt-' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f'))
                with backup.open('xb') as handle:
                    handle.write(self.path.read_bytes())
                data = {}
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
