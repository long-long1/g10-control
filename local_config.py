"""Machine-specific identities stay local and are never committed."""
import json
import os
from pathlib import Path
import re
import sys

def config_path():
    if getattr(sys, 'frozen', False):
        from portable_paths import runtime_paths
        return runtime_paths().data_path('local-settings.json')
    return Path(__file__).resolve().parent/'local-settings.json'


CONFIG=config_path()


def _value(key,environment):
    value=os.environ.get(environment)
    if value is not None:return value.strip()
    if not CONFIG.exists():return ''
    try:
        data=json.loads(CONFIG.read_text(encoding='utf-8-sig'))
        if not isinstance(data,dict):return ''
    except (OSError,ValueError):
        # Fail closed; DeviceSetup reports corruption without replacing the file.
        return ''
    value=data.get(key,'')
    if not isinstance(value,str):raise ValueError(f'{key} must be a string')
    return value.strip()


def normalize_address(value):
    value=value.replace(':','').replace('-','').strip().upper()
    if value and not re.fullmatch('[0-9A-F]{12}',value):
        raise ValueError('蓝牙地址应为12位十六进制字符，可包含冒号或连字符。')
    return value


def peer_address_from_windows_id(device_id):
    """Decode the peer in a WinRT BLE interface ID, never the local radio.

    BluetoothLE#BluetoothLE<local MAC>-<peer MAC> is an interface ID,
    not a MAC address. Unknown/PnP/AEP ID formats must use address properties
    instead of guessing which embedded hex string identifies the peer.
    """
    mac = r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}'
    match = re.fullmatch(rf'BluetoothLE#BluetoothLE{mac}-({mac})',
                         str(device_id or ''), re.IGNORECASE)
    return normalize_address(match.group(1)) if match else ''


def address():return normalize_address(_value('bluetooth_address','G10_BLUETOOTH_ADDRESS'))


def paired_device_id(explicit_address=None):
    """Return the saved Windows BLE device ID only for the matching paired address."""
    target = normalize_address(explicit_address) if explicit_address is not None else address()
    if not target or not CONFIG.exists():
        return ''
    try:
        data = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return ''
    if not isinstance(data, dict):
        return ''
    selected = data.get('selected_device')
    if not isinstance(selected, dict) or selected.get('paired') is not True:
        return ''
    try:
        selected_address = normalize_address(str(selected.get('address') or ''))
    except ValueError:
        return ''
    device_id = selected.get('winrt_device_id')
    return device_id if selected_address == target and isinstance(device_id, str) else ''


def require_address(explicit=None):
    value=normalize_address(explicit) if explicit is not None else address()
    if not value or value=='000000000000':
        raise ValueError('请先配置本机 G10 地址：python configure_local.py --address 你的设备地址')
    return value


def cable_capture_id():return _value('cable_capture_id','G10_CABLE_CAPTURE_ID')


def require_cable_capture_id():
    value=cable_capture_id()
    if not value:raise ValueError('请先运行 configure_local.py 配置本机 CABLE Output。')
    if not re.fullmatch(r'\{0\.0\.1\.00000000\}\.\{[0-9a-fA-F-]{36}\}',value):
        raise ValueError('配置的 CABLE Output 不是有效的 Windows 录音端点 ID。')
    return value
