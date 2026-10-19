"""Local Windows BLE diagnostics. No pairing, characteristic writes or audio drivers."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
ATVV = 'ab5e0001-5a21-4f05-bc7d-af01f617b664'
ATVV_AUDIO = 'ab5e0003-5a21-4f05-bc7d-af01f617b664'
ATVV_CONTROL = 'ab5e0004-5a21-4f05-bc7d-af01f617b664'
INFO = {'00002a24','00002a25','00002a26','00002a27','00002a28','00002a29','00002a50'}

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def inventory(output):
    result = subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass',
        '-File',str(ROOT / 'inventory.ps1')], capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
    rows = json.loads(result.stdout.decode('utf-8-sig'))
    save(output, {'time':datetime.now().astimezone().isoformat(), 'devices':rows})
    for d in rows:
        if d['class'] == 'Bluetooth' and re.search(r'^BTH(?:LE|ENUM)\\DEV_', d['instance_id']):
            print(d['name'], d['instance_id'])
    print('Windows capture endpoints (PnP present, not proof of active audio):')
    for d in rows:
        if d['capture_endpoint']:
            print(' ', d['name'])
    print('Saved:', output)

async def gatt(args):
    from winrt.windows.devices.bluetooth import BluetoothLEDevice, BluetoothCacheMode
    from winrt.windows.devices.enumeration import DeviceInformation
    from winrt.windows.devices.bluetooth.genericattributeprofile import (
        GattCharacteristicProperties as P, GattClientCharacteristicConfigurationDescriptorValue as C)
    report = {'time':datetime.now().astimezone().isoformat(), 'name_filter':args.name,
              'services':[], 'errors':[], 'monitor':{'state':'not_run'}}
    device = None
    opened = []
    subscriptions = []
    loop = asyncio.get_running_loop()
    try:
        devices = await asyncio.wait_for(DeviceInformation.find_all_async_aqs_filter(BluetoothLEDevice.get_device_selector_from_pairing_state(True)), 20)
        candidates = [d for d in devices if d.name.casefold() == args.name.casefold()]
        if len(candidates) != 1:
            raise RuntimeError(f'Expected exactly one target; found {len(candidates)}. Available: '+str([(d.name,d.id) for d in devices]))
        target = candidates[0]
        report.update(device_id=target.id, name=target.name, paired=True,
                      pairing_evidence='Windows paired-state device selector; interface pairing flag is not authoritative')
        device = await asyncio.wait_for(BluetoothLEDevice.from_id_async(target.id), 20)
        if device is None:
            raise RuntimeError('Windows returned no BluetoothLEDevice (access/privacy/unavailable).')
        report.update(address=f'{device.bluetooth_address:012X}', connection_status=str(device.connection_status))
        cache = BluetoothCacheMode.UNCACHED if args.uncached else BluetoothCacheMode.CACHED
        report['cache_mode'] = str(cache)
        result = await asyncio.wait_for(device.get_gatt_services_with_cache_mode_async(cache), 35)
        report['gatt_status'] = str(result.status)
        if int(result.status) != 0:
            raise RuntimeError(f'Service discovery failed: {result.status}; protocol_error={result.protocol_error}')
        notify_chars = []
        for service in result.services:
            opened.append(service)
            row = {'uuid':str(service.uuid), 'handle':service.attribute_handle, 'characteristics':[]}
            report['services'].append(row)
            try:
                cr = await asyncio.wait_for(service.get_characteristics_with_cache_mode_async(cache), 15)
                row['status'] = str(cr.status)
                row['protocol_error'] = cr.protocol_error
                for char in cr.characteristics:
                    props = char.characteristic_properties
                    item = {'uuid':str(char.uuid), 'handle':char.attribute_handle, 'properties':int(props),
                            'property_names':[p.name for p in P if p != P.NONE and props & p]}
                    row['characteristics'].append(item)
                    if props & (P.NOTIFY | P.INDICATE):
                        notify_chars.append((service, char))
                    if str(service.uuid).startswith('0000180a') and str(char.uuid)[:8] in INFO and props & P.READ:
                        rr = await asyncio.wait_for(char.read_value_with_cache_mode_async(cache), 8)
                        item['read_status'] = str(rr.status)
                        if int(rr.status) == 0:
                            data = bytes(rr.value)
                            item['value_hex'] = data.hex()
                            if str(char.uuid).startswith('00002a50') and len(data) == 7:
                                item['pnp_id'] = {'vendor_source':data[0], 'vendor_id':int.from_bytes(data[1:3],'little'),
                                    'product_id':int.from_bytes(data[3:5],'little'), 'version':int.from_bytes(data[5:7],'little')}
                            else:
                                item['text'] = data.decode('utf-8', errors='replace')
            except Exception as exc:
                row['error'] = repr(exc)
        report['atvv_uuid_present'] = any(s['uuid'] == ATVV for s in report['services'])
        save(args.output, report)
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        if args.notify:
            # Explicit selected UUIDs only. CCCD is a descriptor write, never a vendor command.
            selected = {str(uuid.UUID(s)) for s in args.notify}
            found = {str(c.uuid) for _, c in notify_chars}
            if not selected <= found:
                raise RuntimeError(f'Not notifiable or unavailable: {selected - found}')
            monitor = report['monitor'] = {'state':'subscribing','subscriptions':[], 'events':[], 'counts':{},
                'payload_policy':'control bytes only; all other payloads discarded', 'duration_seconds':args.seconds}
            counts = Counter()
            start = time.monotonic()
            def record(key, handle, data):
                counts[key] += 1
                event = {'seconds':round(time.monotonic()-start,4), 'uuid':key,'handle':handle,'length':len(data)}
                if key == ATVV_CONTROL:
                    event['hex'] = data[:32].hex()
                if len(monitor['events']) < 20000:
                    monitor['events'].append(event)
                # Never print or persist audio bytes.
                if counts[key] <= 5 or key == ATVV_CONTROL:
                    print('NOTIFY', event, flush=True)
            for _, char in notify_chars:
                if str(char.uuid) not in selected:
                    continue
                previous = await asyncio.wait_for(char.read_client_characteristic_configuration_descriptor_async(), 8)
                if int(previous.status) != 0:
                    raise RuntimeError(f'Cannot read original CCCD for {char.uuid}; refusing to change subscription')
                original = previous.client_characteristic_configuration_descriptor
                def callback(sender, event, key=str(char.uuid), handle=char.attribute_handle):
                    loop.call_soon_threadsafe(record, key, handle, bytes(event.characteristic_value))
                token = char.add_value_changed(callback)
                subscriptions.append((char, token, original))
                mode = C.NOTIFY if char.characteristic_properties & P.NOTIFY else C.INDICATE
                status = await asyncio.wait_for(char.write_client_characteristic_configuration_descriptor_async(mode), 10)
                monitor['subscriptions'].append({'uuid':str(char.uuid),'status':str(status),'original_cccd':int(original)})
                if int(status) != 0:
                    raise RuntimeError(f'Notification subscription failed: {char.uuid} status={status}')
            start = time.monotonic()
            monitor['state'] = 'listening'
            print('READY: notification monitor active', flush=True)
            save(args.output, report)
            await asyncio.sleep(args.seconds)
            monitor['state'] = 'completed'
            monitor['counts'] = dict(counts)
    except Exception as exc:
        report['errors'].append(repr(exc))
        print('ERROR:', repr(exc), flush=True)
    finally:
        for char, token, original in subscriptions:
            try:
                status = await asyncio.wait_for(char.write_client_characteristic_configuration_descriptor_async(original), 5)
                report.setdefault('cccd_cleanup',[]).append({'uuid':str(char.uuid),'restored':int(original),'status':str(status)})
                if int(status) != 0:
                    report['errors'].append(f'CCCD restore returned status {status}')
            except Exception as exc:
                report['errors'].append('CCCD cleanup: '+repr(exc))
            char.remove_value_changed(token)
        for service in opened:
            service.close()
        if device is not None:
            device.close()  # Release this process's reference, no unpair or forced disconnect.
        save(args.output, report)
    return 1 if report['errors'] else 0

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    inv = sub.add_parser('inventory')
    inv.add_argument('--output',type=Path,default=ROOT/'output/inventory.json')
    g = sub.add_parser('gatt')
    g.add_argument('--name',default='G10')
    g.add_argument('--uncached',action='store_true',help='Request live discovery instead of Windows cache')
    g.add_argument('--notify',action='append',help='Opt in to CCCD subscription for this exact UUID (descriptor writes)')
    g.add_argument('--seconds',type=int,default=45)
    g.add_argument('--output',type=Path,default=ROOT/'output/gatt.json')
    args = parser.parse_args()
    if args.command == 'inventory':
        inventory(args.output)
        return 0
    return asyncio.run(gatt(args))

if __name__ == '__main__':
    sys.exit(main())
