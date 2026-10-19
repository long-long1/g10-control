"""Observe only a selected Raw Input device. No hooks, suppression or exclusive handles."""
import argparse
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import time

u = c.WinDLL('user32', use_last_error=True)
k = c.WinDLL('kernel32', use_last_error=True)
PTR = c.c_size_t
LRESULT = c.c_ssize_t
WNDPROC = c.WINFUNCTYPE(LRESULT,w.HWND,w.UINT,w.WPARAM,w.LPARAM)
class WC(c.Structure):
    _fields_=[('style',w.UINT),('proc',WNDPROC),('cls',c.c_int),('wnd',c.c_int),('instance',w.HINSTANCE),('icon',w.HICON),('cursor',w.HANDLE),('brush',w.HBRUSH),('menu',w.LPCWSTR),('name',w.LPCWSTR)]
class RID(c.Structure):
    _fields_=[('page',w.USHORT),('usage',w.USHORT),('flags',w.DWORD),('target',w.HWND)]
class DEV(c.Structure):
    _fields_=[('handle',w.HANDLE),('kind',w.DWORD)]
class HEADER(c.Structure):
    _fields_=[('kind',w.DWORD),('size',w.DWORD),('device',w.HANDLE),('param',w.WPARAM)]

u.DefWindowProcW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]; u.DefWindowProcW.restype=LRESULT
u.CreateWindowExW.argtypes=[w.DWORD,w.LPCWSTR,w.LPCWSTR,w.DWORD,c.c_int,c.c_int,c.c_int,c.c_int,w.HWND,w.HMENU,w.HINSTANCE,c.c_void_p]; u.CreateWindowExW.restype=w.HWND
u.GetRawInputDeviceInfoW.argtypes=[w.HANDLE,w.UINT,c.c_void_p,c.POINTER(w.UINT)]
u.GetRawInputData.argtypes=[w.HANDLE,w.UINT,c.c_void_p,c.POINTER(w.UINT),w.UINT]
u.RegisterRawInputDevices.argtypes=[c.POINTER(RID),w.UINT,w.UINT]
u.RegisterClassW.argtypes=[c.POINTER(WC)]
u.DestroyWindow.argtypes=[w.HWND]
u.PeekMessageW.argtypes=[c.POINTER(w.MSG),w.HWND,w.UINT,w.UINT,w.UINT]
u.TranslateMessage.argtypes=[c.POINTER(w.MSG)]
u.DispatchMessageW.argtypes=[c.POINTER(w.MSG)]; u.DispatchMessageW.restype=LRESULT
k.GetModuleHandleW.argtypes=[w.LPCWSTR]; k.GetModuleHandleW.restype=w.HMODULE

def device_name(handle):
    n=w.UINT()
    u.GetRawInputDeviceInfoW(handle,0x20000007,None,c.byref(n))
    b=c.create_unicode_buffer(n.value+1)
    u.GetRawInputDeviceInfoW(handle,0x20000007,b,c.byref(n))
    return b.value

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--match',default=__import__('local_config').address().lower())
    p.add_argument('--seconds',type=int,default=45)
    p.add_argument('--list',action='store_true')
    p.add_argument('--events-jsonl',type=Path)
    p.add_argument('--ready-file',type=Path)
    p.add_argument('--stop-file',type=Path)
    p.add_argument('--output',type=Path,default=Path(__file__).parent/'output/raw-input.json')
    a=p.parse_args()
    count=w.UINT()
    u.GetRawInputDeviceList(None,c.byref(count),c.sizeof(DEV))
    devs=(DEV*count.value)()
    if u.GetRawInputDeviceList(devs,c.byref(count),c.sizeof(DEV)) == -1:
        raise c.WinError(c.get_last_error())
    names={d.handle:device_name(d.handle) for d in devs}
    if a.list:
        print(json.dumps(list(names.values()),ensure_ascii=False,indent=2)); return
    if not a.match.strip():p.error('Set a verified --match or configure the G10 Bluetooth address first; refusing to observe all devices.')
    selected={h:n for h,n in names.items() if a.match.casefold() in n.casefold()}
    if not selected:
        raise SystemExit('No matching Raw Input device. Run --list and select a verified device path substring.')
    events=[]
    errors=[]
    stream = None
    if a.events_jsonl:
        a.events_jsonl.parent.mkdir(parents=True,exist_ok=True)
        stream=a.events_jsonl.open('w',encoding='utf-8',buffering=1)
    start=time.monotonic()
    @WNDPROC
    def proc(hwnd,msg,wp,lp):
        if msg==0x00ff:
            try:
                n=w.UINT()
                u.GetRawInputData(lp,0x10000003,None,c.byref(n),c.sizeof(HEADER))
                b=c.create_string_buffer(n.value)
                if u.GetRawInputData(lp,0x10000003,b,c.byref(n),c.sizeof(HEADER)) != n.value:
                    raise RuntimeError('GetRawInputData failed')
                hdr=HEADER.from_buffer_copy(b)
                if hdr.device in selected and len(events)<20000:
                    data=b.raw[c.sizeof(HEADER):]
                    # Keyboard data: make code, flags, reserved, virtual key, message, extra info.
                    e={'seconds':round(time.monotonic()-start,4),'perf_ns':time.perf_counter_ns(),'unix_ns':time.time_ns(),'device':selected[hdr.device],'kind':hdr.kind}
                    if hdr.kind==1 and len(data)>=16:
                        import struct
                        make,flags,_,vk,message,_=struct.unpack_from('<HHHHII',data)
                        e.update(make_code=make,flags=flags,virtual_key=vk,message=message,edge='up' if flags&1 else 'down')
                    elif hdr.kind==2 and len(data)>=8:
                        import struct
                        size,number=struct.unpack_from('<II',data)
                        e.update(report_size=size,report_count=number,hex=data[8:40].hex())
                    else:
                        # Movement metadata only; no screen position capture.
                        e['bytes']=len(data)
                    events.append(e)
                    if stream:
                        stream.write(json.dumps(e,ensure_ascii=False)+'\n')
                    if hdr.kind!=0:
                        print(e,flush=True)
            except Exception as exc:
                errors.append(repr(exc))
        return u.DefWindowProcW(hwnd,msg,wp,lp)
    instance=k.GetModuleHandleW(None)
    wc=WC(0,proc,0,0,instance,None,None,None,None,'Diagnostic3KRawInput')
    if not u.RegisterClassW(c.byref(wc)):
        raise c.WinError(c.get_last_error())
    hwnd=u.CreateWindowExW(0,wc.name,'3K read-only observer',0,0,0,0,0,None,None,instance,None)
    if not hwnd:
        raise c.WinError(c.get_last_error())
    # INPUTSINK only. No NOLEGACY, EXINPUTSINK, hooks or input suppression.
    devices=(RID*3)(RID(1,6,0x100,hwnd),RID(1,2,0x100,hwnd),RID(12,1,0x100,hwnd))
    if not u.RegisterRawInputDevices(devices,3,c.sizeof(RID)):
        raise c.WinError(c.get_last_error())
    print('READY: Raw Input monitoring; target:',list(selected.values()),flush=True)
    if a.ready_file:
        a.ready_file.write_text(str(time.perf_counter_ns()),encoding='ascii')
    msg=w.MSG()
    try:
        while time.monotonic()-start<a.seconds:
            if a.stop_file and a.stop_file.exists():
                break
            while u.PeekMessageW(c.byref(msg),None,0,0,1):
                u.TranslateMessage(c.byref(msg)); u.DispatchMessageW(c.byref(msg))
            time.sleep(.01)
    finally:
        if stream:
            stream.close()
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps({'selected_devices':list(selected.values()),'registration_usages':[[1,6],[1,2],[12,1]],
            'duration_seconds':time.monotonic()-start,'events':events,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
        u.DestroyWindow(hwnd)

if __name__=='__main__':
    main()
