"""ATVV observer with a local timing UI. No GATT characteristic write API exists here."""
import argparse
import asyncio
from collections import Counter
import ctypes
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import uuid
import winsound

from atvv_protocol import AUDIO, CONTROL, SERVICE, capabilities, command_plan
from local_config import normalize_address, peer_address_from_windows_id

ROOT=Path(__file__).resolve().parent
AEP_DEVICE_ADDRESS='System.Devices.Aep.DeviceAddress'


def _address_from_windows_id(device_id):
    return peer_address_from_windows_id(device_id)


def resolve_paired_device(devices, address, device_id=''):
    """Resolve a paired Windows BLE record by saved ID or authoritative AEP address."""
    expected=normalize_address(address)
    if not expected:raise RuntimeError('所选设备没有有效的蓝牙地址，请重新扫描 Windows 配对列表。')
    if device_id:
        targets=[item for item in devices if str(item.id)==str(device_id)]
        if len(targets)!=1:
            raise RuntimeError('保存的 Windows 配对设备 ID 已失效；请重新扫描并选择 G10。')
        item=targets[0]
        props=getattr(item,'properties',{}) or {}
        value=props.get(AEP_DEVICE_ADDRESS)
        try:actual=normalize_address(str(value or '')) if value else ''
        except ValueError:actual=''
        actual=actual or _address_from_windows_id(item.id)
        if actual and actual!=expected:
            raise RuntimeError('保存的 Windows 设备 ID 当前对应另一蓝牙地址；为防止连接错设备，请重新扫描并选择。')
        return item
    matches=[]
    for item in devices:
        props=getattr(item,'properties',{}) or {}
        value=props.get(AEP_DEVICE_ADDRESS)
        try:actual=normalize_address(str(value or '')) if value else ''
        except ValueError:actual=''
        actual=actual or _address_from_windows_id(item.id)
        if actual==expected:matches.append(item)
    if len(matches)==1:return matches[0]
    if len(matches)>1:
        raise RuntimeError('多个 Windows 配对条目映射到同一蓝牙地址；请在 Windows 蓝牙设置中移除重复配对后重新扫描。')
    raise RuntimeError('Windows 已配对设备中没有与所选蓝牙地址关联的 BLE 条目；名称和广播提示不参与关联，请重新扫描已配对 G10。')

class Recorder:
    def __init__(self, directory, save_audio=True):
        self.directory=directory
        directory.mkdir(parents=True,exist_ok=False)
        self.stream=(directory/'events.jsonl').open('w',encoding='utf-8',buffering=1)
        self.audio=(directory/'audio-notifications.bin').open('wb') if save_audio else None
        self.lock=threading.Lock()
        self.origin=time.perf_counter_ns()
        self.counts=Counter()
        self.audio_bytes=0
        self.errors=[]

    def emit(self, kind, *, perf_ns=None, unix_ns=None, **fields):
        perf_ns=perf_ns or time.perf_counter_ns()
        unix_ns=unix_ns or time.time_ns()
        row={'kind':kind,'perf_ns':perf_ns,'unix_ns':unix_ns,
             'utc':datetime.fromtimestamp(unix_ns/1e9,timezone.utc).isoformat(),
             'relative_s':(perf_ns-self.origin)/1e9,**fields}
        with self.lock:
            self.counts[kind]+=1
            self.stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        return row

    def notification(self, key, data, perf_ns, unix_ns, device_time):
        fields={'uuid':key,'length':len(data),'winrt_timestamp':device_time}
        if key==AUDIO:
            with self.lock:
                if self.audio is not None and self.audio_bytes+len(data)>16*1024*1024:
                    raise RuntimeError('16 MiB capture limit reached; stopping')
                if self.audio is not None:
                    fields['binary_offset']=self.audio_bytes
                    self.audio.write(data)
                    self.audio.flush()
                else:
                    fields['payload_saved']=False
                self.audio_bytes+=len(data)
        else:
            fields['hex']=data.hex(' ')
            if data[:1]==b'\x0b':
                try:
                    fields['rc003_candidate_capabilities']=vars(capabilities(data))
                except ValueError as exc:
                    fields['parse_error']=str(exc)
        self.emit('audio' if key==AUDIO else 'control',perf_ns=perf_ns,unix_ns=unix_ns,**fields)

    def close(self):
        with self.lock:
            if self.audio is not None:self.audio.close()
            self.stream.close()

async def observe(rec, stop, ready, updates, args, controller=None):
    from winrt.windows.devices.bluetooth import BluetoothLEDevice as B, BluetoothCacheMode as Cache
    from winrt.windows.devices.enumeration import DeviceInformation as D
    from winrt.windows.devices.bluetooth.genericattributeprofile import GattClientCharacteristicConfigurationDescriptorValue as C
    device=None; services=[]; subscriptions=[]; session=None; connection_token=None; session_token=None
    loop=asyncio.get_running_loop()
    rec.emit('mode',mode='controlled_handshake' if controller else 'readonly',business_writes_enabled=controller is not None,cccd_consent=args.allow_cccd,
             physical_marker='F8 manual proxy; not remote hardware timestamp',poll_ms=10)
    try:
        selector=B.get_device_selector_from_pairing_state(True)
        ds=await asyncio.wait_for(D.find_all_async_aqs_filter_and_additional_properties(
            selector,[AEP_DEVICE_ADDRESS]),20)
        target=resolve_paired_device(ds,args.address,getattr(args,'device_id',''))
        device=await asyncio.wait_for(B.from_id_async(target.id),20)
        if device is None:
            raise RuntimeError('Windows denied device access')
        actual_address=f'{int(device.bluetooth_address):012X}'
        if normalize_address(actual_address)!=normalize_address(args.address):
            device.close()
            device=None
            raise RuntimeError('Windows 配对设备 ID 打开的 BLE 设备地址与所选地址不一致；已停止，未访问 GATT。')
        rec.emit('device',id=target.id,address=actual_address,name=target.name,status=int(device.connection_status))
        def connection_changed(sender, unused):
            try:
                status=int(sender.connection_status)
                rec.emit('connection_status',status=status)
                if status==0:
                    rec.errors.append('BLE disconnected')
                    stop.set()
            except Exception as exc:
                rec.emit('callback_error',source='connection',error=repr(exc))
                stop.set()
        connection_token=device.add_connection_status_changed(connection_changed)
        result=await asyncio.wait_for(device.get_gatt_services_for_uuid_with_cache_mode_async(uuid.UUID(SERVICE),Cache.UNCACHED),35)
        if int(result.status)!=0:
            raise RuntimeError(f'ATVV discovery status={result.status}, protocol_error={result.protocol_error}')
        services=list(result.services)
        if len(services)!=1:
            raise RuntimeError(f'Expected one ATVV service, got {len(services)}')
        session=services[0].session
        def session_changed(sender, event):
            try:
                rec.emit('gatt_session_status',status=int(event.status),error=int(event.error))
                if int(event.status)==0:
                    rec.errors.append('GATT session closed')
                    stop.set()
            except Exception as exc:
                rec.emit('callback_error',source='session',error=repr(exc)); stop.set()
        session_token=session.add_session_status_changed(session_changed)
        cr=await asyncio.wait_for(services[0].get_characteristics_with_cache_mode_async(Cache.UNCACHED),15)
        if int(cr.status)!=0:
            raise RuntimeError(f'Characteristics status={cr.status}')
        chars={str(c.uuid):c for c in cr.characteristics}
        if controller:
            controller.bind(chars, loop)
        # Match the RC003 source subscription order; no TX subscription or command.
        for key in (AUDIO,CONTROL):
            char=chars[key]
            if not int(char.characteristic_properties)&16:
                raise RuntimeError(f'{key} is not notifiable')
            old=await asyncio.wait_for(char.read_client_characteristic_configuration_descriptor_async(),8)
            if int(old.status)!=0:
                raise RuntimeError(f'Cannot read original CCCD {key}: {old.status}')
            original=old.client_characteristic_configuration_descriptor
            def callback(sender,event,key=key):
                perf=time.perf_counter_ns(); wall=time.time_ns()
                try:
                    data=bytes(event.characteristic_value)
                    device_time=event.timestamp.isoformat()
                    rec.notification(key,data,perf,wall,device_time)
                    if controller:
                        loop.call_soon_threadsafe(controller.receive,key,data,perf)
                except Exception as exc:
                    rec.errors.append('Notification callback: '+repr(exc))
                    rec.emit('callback_error',source=key,error=repr(exc)); stop.set()
            token=char.add_value_changed(callback)
            subscriptions.append((char,token,original))
            rec.emit('cccd_before',uuid=key,value=int(original))
            status=await asyncio.wait_for(char.write_client_characteristic_configuration_descriptor_async(C.NOTIFY),10)
            rec.emit('cccd_subscribe',uuid=key,status=int(status))
            if int(status)!=0:
                raise RuntimeError(f'CCCD subscription failed {key}: {status}')
        if controller:
            await controller.initialize()
        rec.emit('ble_ready')
        ready.set()
        updates.put(getattr(args,'ready_message','BLE 通知已就绪；正在等待 HID 观察器。'))
        last=None
        while not stop.is_set():
            status=int(device.connection_status)
            if status!=last:
                rec.emit('connection_poll',status=status); last=status
            if status==0:
                raise RuntimeError('BLE connection lost')
            if session is not None and int(session.session_status)==0:
                raise RuntimeError('GATT session closed')
            if controller:
                await controller.tick()
            await asyncio.sleep(.1)
    except Exception as exc:
        rec.errors.append(repr(exc)); rec.emit('error',error=repr(exc)); stop.set()
        updates.put('检测异常：'+str(exc))
    finally:
        ready.clear()
        if controller:
            try:
                await controller.close()
            except Exception as exc:
                rec.errors.append('Session close: '+repr(exc)); rec.emit('cleanup_error',error=repr(exc))
        for char,token,original in reversed(subscriptions):
            try:
                status=await asyncio.wait_for(char.write_client_characteristic_configuration_descriptor_async(original),5)
                rec.emit('cccd_restore',uuid=str(char.uuid),value=int(original),status=int(status))
                if int(status)!=0:
                    rec.errors.append(f'CCCD restore failed: {char.uuid}, {status}')
            except Exception as exc:
                rec.errors.append('CCCD restore: '+repr(exc)); rec.emit('cleanup_error',error=repr(exc))
            try:
                char.remove_value_changed(token)
            except Exception as exc:
                rec.emit('cleanup_error',error=repr(exc)); rec.errors.append(repr(exc))
        if session is not None and session_token is not None:
            try: session.remove_session_status_changed(session_token)
            except Exception as exc: rec.errors.append(repr(exc))
        if device is not None and connection_token is not None:
            try: device.remove_connection_status_changed(connection_token)
            except Exception as exc: rec.errors.append(repr(exc))
        for service in services:
            try: service.close()
            except Exception as exc: rec.errors.append(repr(exc))
        if device is not None:
            try: device.close()
            except Exception as exc: rec.errors.append(repr(exc))
        rec.emit('ble_cleanup_complete',errors=list(rec.errors))

class TestUI:
    def __init__(self, rec, stop, ble_ready, updates, hid, args):
        self.rec=rec; self.stop=stop; self.ready=ble_ready; self.updates=updates; self.hid=hid; self.args=args
        controlled=getattr(args,'business_approval',False)
        self.root=tk.Tk(); self.root.title('G10 第二阶段：'+('已授权 ATVV 握手测试' if controlled else '只读按键与语音通知验证'))
        self.root.geometry('730x350+180+100'); self.root.attributes('-topmost',True)
        self.title=tk.StringVar(value='连接中，请先不要按红键或 F8')
        self.detail=tk.StringVar(value='已授权：先单次能力请求，确认兼容后等待红键开麦。音频仅保存在本机。' if controlled else '只设置已同意的通知开关；不发送能力查询或开麦命令。')
        tk.Label(self.root,textvariable=self.title,font=('Microsoft YaHei UI',18),wraplength=700).pack(pady=20)
        tk.Label(self.root,textvariable=self.detail,font=('Microsoft YaHei UI',12),wraplength=700,justify='left').pack(pady=12)
        tk.Label(self.root,text='F8 仅作人工时间标记：与遥控器红键同时按下、同时松开。\n搜索面板弹出时无需关闭，工具仍在后台观察。\n短按 → 按住说话 5 秒 → 按住说话 10 秒；每组之间等待提示。',font=('Microsoft YaHei UI',11),justify='left').pack()
        tk.Button(self.root,text='停止测试并恢复本次通知状态',command=self.stop.set).pack(pady=14)
        self.root.protocol('WM_DELETE_WINDOW',self.stop.set)
        self.key=ctypes.WinDLL('user32',use_last_error=True).GetAsyncKeyState
        self.key.argtypes=[ctypes.c_int]; self.key.restype=ctypes.c_short
        self.previous=bool(self.key(0x77)&0x8000)
        self.stage='waiting'; self.trial=0; self.down=None; self.deadline=None; self.beeped=False
        self.started=time.perf_counter(); self.total=[.25,5.,10.]; self.finished=False

    def tick(self):
        while True:
            try: self.detail.set(self.updates.get_nowait())
            except queue.Empty: break
        now=time.perf_counter()
        pressed=bool(self.key(0x77)&0x8000)
        if self.hid.poll() is not None and not self.stop.is_set():
            self.rec.errors.append('Raw Input process exited before test finished'); self.stop.set()
        if now-self.started>self.args.max_seconds:
            self.rec.emit('operator_timeout'); self.stop.set()
        if self.stop.is_set():
            self.title.set('测试已停止，正在恢复通知状态和保存结果')
            self.root.after(200,self.root.destroy)
            return
        if self.stage=='waiting' and self.ready.is_set() and (self.rec.directory/'hid.ready').exists() and not pressed:
            self.stage='baseline'; self.deadline=now+3
            self.title.set('已就绪：静置 3 秒，随后开始第一组')
            self.rec.emit('baseline_begin')
        elif self.stage in ('baseline','cooldown') and now>=self.deadline and not pressed:
            if self.trial>=3:
                self.finished=True; self.rec.emit('all_trials_complete'); self.stop.set()
            else:
                self.stage='armed'
                label=['短按一下','按住 5 秒并持续说话','按住 10 秒并持续说话'][self.trial]
                self.title.set(f'第 {self.trial+1} 组：{label}')
                self.detail.set('现在可以同时按下 F8 和红键。等待提示后同时松开。')
                self.rec.emit('trial_armed',trial=self.trial+1,target_seconds=self.total[self.trial])
        elif self.stage=='armed' and pressed and not self.previous:
            self.down=now; self.stage='holding'; self.beeped=False
            self.rec.emit('manual_down',trial=self.trial+1,target_seconds=self.total[self.trial],source='F8 polling')
        elif self.stage=='holding':
            elapsed=now-self.down
            if elapsed>=self.total[self.trial] and not self.beeped:
                self.title.set('现在同时松开红键和 F8')
                self.rec.emit('release_cue',trial=self.trial+1)
                winsound.PlaySound('SystemAsterisk',winsound.SND_ALIAS|winsound.SND_ASYNC)
                self.beeped=True
            elif not self.beeped:
                self.title.set(f'第 {self.trial+1} 组：已按住 {elapsed:.1f} 秒 / {self.total[self.trial]:g} 秒')
            if not pressed and self.previous:
                self.rec.emit('manual_up',trial=self.trial+1,held_seconds=elapsed,source='F8 polling')
                self.trial+=1; self.stage='cooldown'; self.deadline=now+6
                self.title.set('本组已记录，请静置 6 秒')
                self.detail.set('这段时间仍在记录松开后的通知；请等待下一组提示。')
        self.previous=pressed
        self.root.after(10,self.tick)

    def run(self):
        self.root.after(10,self.tick)
        self.root.mainloop()

def run_test(args, controller_factory=None):
    directory=args.output or ROOT/'output'/('phase2-readonly-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    rec=Recorder(directory)
    stop=threading.Event(); ready=threading.Event(); updates=queue.Queue()
    controller=controller_factory(rec,stop,updates) if controller_factory else None
    log=(directory/'hid-process.log').open('w',encoding='utf-8')
    hid=subprocess.Popen([sys.executable,'-u',str(ROOT/'raw_input.py'),'--match',args.address.lower(),
        '--seconds',str(args.max_seconds+30),'--events-jsonl',str(directory/'hid.jsonl'),
        '--ready-file',str(directory/'hid.ready'),'--stop-file',str(directory/'hid.stop'),
        '--output',str(directory/'hid-summary.json')],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    worker=threading.Thread(target=lambda:asyncio.run(observe(rec,stop,ready,updates,args,controller)),daemon=False)
    worker.start()
    ui=None
    try:
        ui=TestUI(rec,stop,ready,updates,hid,args)
        ui.run()
    finally:
        stop.set(); (directory/'hid.stop').touch()
        worker.join(timeout=60)
        if worker.is_alive():
            print('Cleanup still running; process remains alive until WinRT cleanup finishes',flush=True)
            worker.join()
        try: hid.wait(timeout=5)
        except subprocess.TimeoutExpired:
            hid.terminate(); hid.wait(timeout=5); rec.errors.append('Raw Input did not stop cooperatively')
        log.close()
        if hid.returncode!=0:
            rec.errors.append(f'Raw Input exited with code {hid.returncode}')
        hid_summary=directory/'hid-summary.json'
        if hid_summary.exists():
            for error in json.loads(hid_summary.read_text(encoding='utf-8')).get('errors',[]):
                rec.errors.append('Raw Input: '+error)
        rec.emit('test_end',completed=bool(ui and ui.finished),hid_exit_code=hid.returncode)
        summary={'directory':str(directory),'completed':bool(ui and ui.finished),'errors':rec.errors,
                 'counts':dict(rec.counts),'audio_bytes':rec.audio_bytes,
                 'mode':'controlled_handshake' if controller else 'readonly','business_writes':rec.counts['tx_attempt'],
                 'manual_marker_notice':'F8 is a human proxy; 10ms polling plus scheduling/coordination delay, not physical truth'}
        (directory/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        rec.close()
        print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--allow-cccd',action='store_true',help='Use ONLY after explicit approval of notification descriptor writes/restoration')
    p.add_argument('--address',default=__import__('local_config').address())
    p.add_argument('--max-seconds',type=int,default=600)
    p.add_argument('--plan',action='store_true',help='Print source-derived future command plan; performs NO Bluetooth access')
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    if args.plan:
        print(json.dumps(command_plan(),ensure_ascii=False,indent=2)); return
    if not args.allow_cccd:
        p.error('Explicit CCCD approval required; no Bluetooth operations performed')
    args.address=__import__('local_config').require_address(args.address)
    args.device_id=__import__('local_config').paired_device_id(args.address)
    run_test(args)

if __name__=='__main__':
    main()
