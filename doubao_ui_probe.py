"""One-shot local Doubao UI permission probe. Read-only unless --activate is passed.

The optional activation experiment must be authorized separately before elevation.
Button mode posts messages to the known Doubao status-bar mic window. The
separately selected right-alt comparison injects a paired key sequence; mouse
mode requires separate authorization to move the pointer and click that button.
No mode stores audio or changes Windows/Doubao settings.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import threading
import time

import comtypes
import psutil

from doubao_voice import WindowsBackend, check_config, u, INPUT, KEYBDINPUT, MOUSEINPUT, _voice_button_point


def click_statusbar_with_mouse(hwnd):
    """Only for a separately authorized pointer-moving experiment.

    Reject hidden/occluded targets before moving the pointer. Restore its old
    position only if the user has not moved it since the test click.
    """
    u.SetThreadDpiAwarenessContext.argtypes=[c.c_void_p]
    u.SetThreadDpiAwarenessContext.restype=c.c_void_p
    u.ClientToScreen.argtypes=[w.HWND,c.POINTER(w.POINT)]
    u.ClientToScreen.restype=w.BOOL
    u.WindowFromPoint.argtypes=[w.POINT];u.WindowFromPoint.restype=w.HWND
    u.GetCursorPos.argtypes=[c.POINTER(w.POINT)];u.GetCursorPos.restype=w.BOOL
    u.SetCursorPos.argtypes=[c.c_int,c.c_int];u.SetCursorPos.restype=w.BOOL
    previous=u.SetThreadDpiAwarenessContext(c.c_void_p(-4))
    original=w.POINT();position=w.POINT();moved=False
    try:
        if not u.IsWindowVisible(hwnd):raise RuntimeError('豆包状态栏不可见，未移动鼠标。')
        if WindowsBackend._find_voice_button_window()!=hwnd:
            raise RuntimeError('豆包按钮窗口身份已变化，未移动鼠标。')
        if any(u.GetAsyncKeyState(v)&0x8000 for v in (1,2,4,0x10,0x11,0x12,0x5b,0x5c)):
            raise RuntimeError('请先松开鼠标按钮和电脑修饰键。')
        rect=w.RECT()
        if not u.GetWindowRect(hwnd,c.byref(rect)):raise RuntimeError('无法确认豆包按钮尺寸。')
        point=_voice_button_point(rect.right-rect.left,rect.bottom-rect.top,u.GetDpiForWindow(hwnd))
        position.x=point&0xffff;position.y=point>>16
        if not u.ClientToScreen(hwnd,c.byref(position)):raise RuntimeError('无法确认按钮屏幕坐标。')
        if u.WindowFromPoint(position)!=hwnd:
            raise RuntimeError('豆包麦克风位置被其他窗口遮挡，未移动鼠标。')
        if not u.GetCursorPos(c.byref(original)):raise RuntimeError('无法读取鼠标原位置。')
        if not u.SetCursorPos(position.x,position.y):raise RuntimeError('无法移动到豆包按钮。')
        moved=True
        if u.WindowFromPoint(position)!=hwnd:raise RuntimeError('目标窗口已变化，已取消点击。')
        events=(INPUT*2)()
        events[0].type=0;events[0].mi=MOUSEINPUT(0,0,0,0x0002,0,0x473130)
        events[1].type=0;events[1].mi=MOUSEINPUT(0,0,0,0x0004,0,0x473130)
        sent=u.SendInput(2,events,c.sizeof(INPUT))
        if sent!=2:
            error=c.get_last_error()
            if sent==1:
                release=events[1]
                if u.SendInput(1,c.byref(release),c.sizeof(INPUT))!=1:
                    raise RuntimeError('鼠标释放发送失败，请松开并再点一次实体鼠标左键。')
            raise RuntimeError(f'定点鼠标点击未完成，Windows 错误 {error}。')
    finally:
        if moved:
            current=w.POINT()
            if u.GetCursorPos(c.byref(current)) and (current.x,current.y)==(position.x,position.y):
                u.SetCursorPos(original.x,original.y)
        if previous:u.SetThreadDpiAwarenessContext(previous)


class MouseButtonProbeBackend(WindowsBackend):
    def down(self):
        hwnd=self._find_voice_button_window()
        if not hwnd:raise RuntimeError('未找到可见豆包状态栏，未移动鼠标。')
        click_statusbar_with_mouse(hwnd)
        self.voice_button_hwnd=hwnd
        self.rec.emit('pointer_mic_click',action='start',hwnd=int(hwnd))

    def up(self):
        hwnd=self.voice_button_hwnd
        self.voice_button_hwnd=None
        if not hwnd:raise RuntimeError('未记录本轮豆包按钮，取消结束点击。')
        click_statusbar_with_mouse(hwnd)
        self.rec.emit('pointer_mic_click',action='stop',hwnd=int(hwnd))


class RightAltProbeBackend(WindowsBackend):
    """Authorized one-shot comparison only; not enabled in the bridge."""
    def __init__(self,rec):
        super().__init__(rec)
        self.key_held=False

    def _send_alt(self,release):
        event=INPUT(type=1)
        event.ki=KEYBDINPUT(0,0x38,0x09|(0x02 if release else 0),0,0x473130)
        c.set_last_error(0)
        if u.SendInput(1,c.byref(event),c.sizeof(INPUT))!=1:
            raise RuntimeError(f'右 Alt 对照发送失败，Windows 错误 {c.get_last_error()}。')

    def down(self):
        if any(u.GetAsyncKeyState(v)&0x8000 for v in (0x10,0x11,0x12,0x5b,0x5c)):
            raise RuntimeError('请先松开电脑 Shift、Ctrl、Alt、Win 键。')
        self._send_alt(False)
        self.key_held=True
        self.rec.emit('same_integrity_right_alt_down')

    def up(self):
        if self.key_held:
            self._send_alt(True)
            self.key_held=False
            self.rec.emit('same_integrity_right_alt_up')


def process_security(pid):
    kernel=c.WinDLL('kernel32',use_last_error=True)
    advapi=c.WinDLL('advapi32',use_last_error=True)
    kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD]
    kernel.OpenProcess.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE]
    advapi.OpenProcessToken.argtypes=[w.HANDLE,w.DWORD,c.POINTER(w.HANDLE)]
    advapi.GetTokenInformation.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD,c.POINTER(w.DWORD)]
    advapi.GetSidSubAuthorityCount.argtypes=[c.c_void_p]
    advapi.GetSidSubAuthorityCount.restype=c.POINTER(c.c_ubyte)
    advapi.GetSidSubAuthority.argtypes=[c.c_void_p,w.DWORD]
    advapi.GetSidSubAuthority.restype=c.POINTER(w.DWORD)
    process=kernel.OpenProcess(0x1000,False,pid)
    if not process:raise c.WinError(c.get_last_error())
    token=w.HANDLE()
    try:
        if not advapi.OpenProcessToken(process,8,c.byref(token)):
            raise c.WinError(c.get_last_error())
        length=w.DWORD()
        advapi.GetTokenInformation(token,25,None,0,c.byref(length))
        buf=c.create_string_buffer(length.value)
        if not advapi.GetTokenInformation(token,25,buf,length.value,c.byref(length)):
            raise c.WinError(c.get_last_error())
        sid=c.cast(buf,c.POINTER(c.c_void_p))[0]
        count=advapi.GetSidSubAuthorityCount(sid)[0]
        rid=advapi.GetSidSubAuthority(sid,count-1)[0]
        result={'integrity_rid':rid,'integrity_hex':hex(rid)}
        for key,kind in (('ui_access',26),('elevated',20)):
            value=w.DWORD()
            if not advapi.GetTokenInformation(token,kind,c.byref(value),c.sizeof(value),c.byref(length)):
                raise c.WinError(c.get_last_error())
            result[key]=bool(value.value)
        return result
    finally:
        if token:kernel.CloseHandle(token)
        kernel.CloseHandle(process)


class ProbeLog:
    def __init__(self,activate):
        self.root=Path(__file__).resolve().parent/'output'/'doubao-ui-probe'
        self.root.mkdir(parents=True,exist_ok=True)
        self.data={'time':datetime.now().astimezone().isoformat(),
                   'activation_requested':activate,'events':[], 'stores_audio':False}
        self.archive=self.root/('probe-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
    def emit(self,kind,**values):
        self.data['events'].append({'kind':kind,'time':datetime.now().astimezone().isoformat(),**values})
        self.save()
    def save(self):
        target=self.root/'latest.json'
        temp=target.with_suffix('.tmp')
        temp.write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(target)
        self.archive.write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding='utf-8')


def wait_for_f8(rec,timeout=60):
    rec.emit('waiting_for_f8',timeout_seconds=timeout)
    deadline=time.monotonic()+timeout
    released=False
    while time.monotonic()<deadline:
        pressed=bool(u.GetAsyncKeyState(0x77)&0x8000)
        if not pressed:released=True
        elif released:
            rec.emit('f8_ready')
            return
        time.sleep(.05)
    raise RuntimeError('等待 F8 超时，未发送点击。')


def run(activate=False,delay=8,wait_f8=False,trigger='button'):
    rec=ProbeLog(activate)
    backend=None
    started=False
    comtypes.CoInitialize()
    try:
        own=process_security(os.getpid())
        rec.emit('probe_security',**own)
        for process in psutil.process_iter(['pid','name']):
            if (process.info['name'] or '').casefold()=='imeservice.exe':
                try:
                    if '\\doubaoime\\' in process.exe().casefold():
                        rec.emit('doubao_security',**process_security(process.pid))
                except (psutil.Error,OSError) as error:
                    rec.emit('security_query_error',error=str(error))
        rec.emit('probe_trigger',trigger=trigger)
        backend_type={'button':WindowsBackend,'right-alt':RightAltProbeBackend,'mouse':MouseButtonProbeBackend}[trigger]
        backend=backend_type(rec)
        rec.emit('read_only_check',capture_active=backend.capture_active(),
                 visible_voice_window=bool(backend._find_voice_button_window()))
        if not activate:return 0
        if own['integrity_rid']<0x3000:
            raise RuntimeError('激活实验要求另获用户明确授权后以管理员权限运行。')
        check_config()
        if wait_f8:
            wait_for_f8(rec)
            # Do not turn the readiness key into an Alt+F8 shortcut.
            deadline=time.monotonic()+3
            while u.GetAsyncKeyState(0x77)&0x8000:
                if time.monotonic()>=deadline:
                    raise RuntimeError('F8 尚未松开，取消本轮激活。')
                time.sleep(.05)
        else:
            rec.emit('waiting_for_user_focus',seconds=delay)
            time.sleep(delay)
        if backend.capture_active():
            raise RuntimeError('豆包已有录音会话，已取消实验，未发送点击。')
        backend.down()
        started=True
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            if backend.capture_active():
                rec.emit('capture_started')
                time.sleep(2)
                break
            time.sleep(.1)
        else:
            rec.emit('capture_not_observed',note='不重试点击；请检查是否出现录音界面。')
            return 2
        return 0
    except Exception as error:
        rec.emit('probe_error',error=str(error))
        return 1
    finally:
        try:
            # Stop only when this attempt clicked start and the verified CABLE
            # capture is active. Never toggle a mic on in timeout cleanup.
            if started and backend and (trigger=='right-alt' or backend.capture_active()):
                backend.up()
                deadline=time.monotonic()+3
                while time.monotonic()<deadline and backend.capture_active():
                    time.sleep(.1)
                rec.emit('cleanup_capture_state',active=backend.capture_active())
        except Exception as error:
            rec.emit('cleanup_error',error=str(error))
        finally:
            if backend:backend.manager=None
            comtypes.CoUninitialize()
            rec.emit('probe_finished')


def interactive_test(trigger):
    """Visible, user-initiated one-shot test; no dependence on transient F8 polling."""
    import tkinter as tk
    from tkinter import ttk
    root=tk.Tk()
    root.title('G10 豆包唤起验证 · 临时管理员')
    root.geometry(f'450x320+{max(20,root.winfo_screenwidth()-490)}+80')
    root.attributes('-topmost',True)
    root.resizable(False,False)
    frame=ttk.Frame(root,padding=20);frame.pack(fill='both',expand=True)
    title='豆包麦克风定点点击测试' if trigger=='mouse' else '右 Alt 同权限对照测试'
    action='短暂移动鼠标并点击豆包麦克风，再恢复原位置' if trigger=='mouse' else '发送右 Alt'
    ttk.Label(frame,text=title,font=('Microsoft YaHei UI',14,'bold')).pack(anchor='w')
    ttk.Label(frame,text=f'点击开始后，5秒内点回豆包输入框。本轮将{action}。\n随后先不要操作鼠标或键盘。',
              wraplength=400,font=('Microsoft YaHei UI',10)).pack(anchor='w',pady=(12,8))
    status=tk.StringVar(value='等待你点击「开始测试」。本程序只执行一次。')
    ttk.Label(frame,textvariable=status,wraplength=400,font=('Microsoft YaHei UI',10)).pack(anchor='w',pady=8)
    results=queue.Queue();started=False;finished=False;close_pending=False

    def worker():
        try:results.put(run(activate=True,delay=5,trigger=trigger))
        except Exception as error:results.put(str(error))

    def start():
        nonlocal started
        if started:return
        started=True;start_button.configure(state='disabled')
        status.set('5秒后开始。现在请点击目标输入框。')
        threading.Thread(target=worker,name='AuthorizedDoubaoProbe',daemon=False).start()
        for seconds in range(4,0,-1):
            root.after((5-seconds)*1000,lambda n=seconds:status.set(f'{n}秒后开始。请保持目标输入框有焦点。'))
        root.after(5000,lambda:status.set('正在执行一次测试；请稍候…'))

    def close():
        nonlocal close_pending
        if started and not finished:
            close_pending=True;status.set('正在安全释放按键，请稍候…')
        else:root.destroy()

    def poll():
        nonlocal finished
        try:result=results.get_nowait()
        except queue.Empty:
            root.after(150,poll);return
        finished=True
        if close_pending:root.destroy();return
        if result==0:
            try:
                data=json.loads((Path(__file__).resolve().parent/'output/doubao-ui-probe/latest.json').read_text(encoding='utf-8'))
                unfinished=any(e['kind']=='cleanup_error' or (e['kind']=='cleanup_capture_state' and e.get('active')) for e in data['events'])
            except (OSError,ValueError,KeyError):unfinished=True
            status.set('已打开录音，但未确认自动结束；请用实体右 Alt 结束。' if unfinished else '已检测到录音开始和结束。请反馈你看到的界面。')
        elif result==2:status.set('触发动作已执行，但没有检测到豆包录音。')
        else:status.set('测试未完成，详细原因已写入本机日志。')
        root.after(30000,close)

    start_button=ttk.Button(frame,text='开始测试（5秒后触发）',command=start)
    start_button.pack(anchor='w',pady=6)
    ttk.Button(frame,text='关闭',command=close).pack(anchor='e')
    root.protocol('WM_DELETE_WINDOW',close)
    root.after(150,poll)
    root.after(300000,close)
    root.mainloop()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate',action='store_true',help='授权后使用：临时开启并尝试结束一次豆包录音')
    parser.add_argument('--delay',type=int,choices=range(3,16),default=8)
    parser.add_argument('--wait-f8',action='store_true',help='等待用户在目标输入框按 F8 确认开始，60秒超时')
    parser.add_argument('--trigger',choices=['button','right-alt','mouse'],default='button')
    parser.add_argument('--interactive',action='store_true',help='显示一次性验证窗口，由用户点击开始')
    args=parser.parse_args()
    if args.interactive:
        if not args.activate:parser.error('--interactive requires explicit --activate')
        interactive_test(args.trigger)
        raise SystemExit(0)
    raise SystemExit(run(args.activate,args.delay,args.wait_f8,args.trigger))
