"""G10 session -> Doubao IME status-bar mic button. No global input hooks."""
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import queue
import threading
import time

import comtypes
import psutil
from pycaw.pycaw import AudioUtilities
from pycaw.api.audiopolicy import IAudioSessionManager2, IAudioSessionControl2

from local_config import cable_capture_id
CABLE_ID=cable_capture_id()
CONFIG=Path(os.environ['APPDATA'])/'DoubaoIme/conf/config.json'

def check_config():
    voice=json.loads(CONFIG.read_text(encoding='utf-8'))['voice']
    if voice.get('selectedMicrophoneId','').lower()!=CABLE_ID.lower():
        raise RuntimeError('请先在豆包输入法设置中将麦克风选择为 CABLE Output。')
    if not voice.get('enableVoiceShortcut') or voice.get('voiceLongPressShortcut')!={'keyCode':0,'modifierFlags':2049}:
        raise RuntimeError('当前原型要求豆包输入法启用长按快捷键“右 Alt”；不会自动改动快捷键。')

u=c.WinDLL('user32',use_last_error=True)
k=c.WinDLL('kernel32',use_last_error=True)
class MOUSEINPUT(c.Structure):
    _fields_=[('dx',w.LONG),('dy',w.LONG),('mouseData',w.DWORD),('dwFlags',w.DWORD),('time',w.DWORD),('dwExtraInfo',c.c_size_t)]
class KEYBDINPUT(c.Structure):
    _fields_=[('wVk',w.WORD),('wScan',w.WORD),('dwFlags',w.DWORD),('time',w.DWORD),('dwExtraInfo',c.c_size_t)]
class HARDWAREINPUT(c.Structure):
    _fields_=[('uMsg',w.DWORD),('wParamL',w.WORD),('wParamH',w.WORD)]
class INPUTUNION(c.Union):
    _fields_=[('mi',MOUSEINPUT),('ki',KEYBDINPUT),('hi',HARDWAREINPUT)]
class INPUT(c.Structure):
    _anonymous_=('data',)
    _fields_=[('type',w.DWORD),('data',INPUTUNION)]
u.SendInput.argtypes=[w.UINT,c.POINTER(INPUT),c.c_int];u.SendInput.restype=w.UINT
u.GetForegroundWindow.restype=w.HWND
u.GetWindowThreadProcessId.argtypes=[w.HWND,c.POINTER(w.DWORD)];u.GetWindowThreadProcessId.restype=w.DWORD
u.SetForegroundWindow.argtypes=[w.HWND];u.SetForegroundWindow.restype=w.BOOL
u.IsWindow.argtypes=[w.HWND];u.IsWindow.restype=w.BOOL
u.GetAsyncKeyState.argtypes=[c.c_int];u.GetAsyncKeyState.restype=w.SHORT
u.EnumWindows.argtypes=[c.c_void_p,w.LPARAM];u.EnumWindows.restype=w.BOOL
u.GetClassNameW.argtypes=[w.HWND,w.LPWSTR,c.c_int];u.GetClassNameW.restype=c.c_int
u.IsWindowVisible.argtypes=[w.HWND];u.IsWindowVisible.restype=w.BOOL
u.GetWindowRect.argtypes=[w.HWND,c.POINTER(w.RECT)];u.GetWindowRect.restype=w.BOOL
u.GetWindowThreadProcessId.argtypes=[w.HWND,c.POINTER(w.DWORD)];u.GetWindowThreadProcessId.restype=w.DWORD
u.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];u.PostMessageW.restype=w.BOOL
try:u.GetDpiForWindow.argtypes=[w.HWND];u.GetDpiForWindow.restype=w.UINT
except AttributeError:pass

def send_key(vk,up=False):
    # This is used only to dismiss the Windows Search panel after the known
    # G10 Consumer AC Search event. Never synthesize the Doubao trigger key.
    if vk != 0x1b:
        raise ValueError('Only Escape to dismiss the G10-triggered Search panel is supported.')
    event=INPUT(type=1)
    event.ki=KEYBDINPUT(vk,0,0x0002 if up else 0,0,0x473130)
    if u.SendInput(1,c.byref(event),c.sizeof(INPUT))!=1:
        raise RuntimeError('Windows 拒绝模拟按键；请在普通权限的文本窗口中测试。')

class WindowsBackend:
    def __init__(self,rec,stop=None):
        self.rec=rec;self.last_target=None;self.cache={};self.last_seen=0.
        self.stop=stop
        self.voice_button_hwnd=None
        device=AudioUtilities.GetDeviceEnumerator().GetDevice(CABLE_ID)
        self.manager=device.Activate(IAudioSessionManager2._iid_,comtypes.CLSCTX_ALL,None).QueryInterface(IAudioSessionManager2)
    def window(self):
        hwnd=u.GetForegroundWindow()
        if not hwnd:return None
        pid=w.DWORD();u.GetWindowThreadProcessId(hwnd,c.byref(pid))
        key=(int(hwnd),pid.value)
        # Cache by both HWND and PID; never read window titles or input contents.
        if key not in self.cache:
            try:self.cache[key]=psutil.Process(pid.value).exe().lower()
            except psutil.Error:self.cache[key]=''
        return (*key,self.cache[key])
    @staticmethod
    def is_search(window):
        return bool(window and window[2].startswith(os.environ['WINDIR'].lower()+'\\systemapps\\') and
                    Path(window[2]).name in ('searchhost.exe','searchapp.exe'))
    def poll_target(self):
        current=self.window()
        if current and not self.is_search(current):
            self.last_target=current;self.last_seen=time.monotonic()
    def target(self):
        current=self.window()
        if current and not self.is_search(current):return current
        return self.last_target if time.monotonic()-self.last_seen<2 else None
    def prepare(self,target):
        current=self.window()
        if self.is_search(current):
            # Dismiss only the foreground Windows Search, during this G10 session.
            # This is not suppression: the panel may flash before being dismissed.
            if u.GetAsyncKeyState(0x1b)&0x8000:raise RuntimeError('请先松开电脑 Esc 键。')
            send_key(0x1b);send_key(0x1b,True)
            if u.IsWindow(target[0]):u.SetForegroundWindow(target[0])
            self.rec.emit('doubao_search_dismissed',target_pid=target[1])
            return False
        if not current or current[:2]!=target[:2]:
            raise RuntimeError('输入焦点已变化：请重新点击文本框，再按红键。')
        return True
    def down(self):
        if self.stop is not None and self.stop.is_set():raise RuntimeError('正在退出，不再唤起语音。')
        if any(u.GetAsyncKeyState(v)&0x8000 for v in (0x10,0x11,0x12,0x5b,0x5c)):
            raise RuntimeError('请松开电脑 Shift、Ctrl、Alt、Win 键后再按红键。')
        # Synthetic Right Alt failed in hardware tests. A subsequent token
        # check found a higher-integrity Doubao process; filtering was never
        # proven. Try its own visible mic button instead. The target
        # is constrained by executable path, window class and the shipped
        # status-bar dimensions; no global mouse or keyboard input is emitted.
        hwnd=self._find_voice_button_window()
        if not hwnd:
            raise RuntimeError('当前文本框未显示豆包输入法麦克风状态栏。请先在该文本框切换到豆包输入法；为避免 Alt 快捷键干扰，此模式不会模拟键盘。')
        self._click_voice_button(hwnd)
        self.voice_button_hwnd=hwnd
        self.rec.emit('doubao_voice_button_clicked',hwnd=int(hwnd),action='start')
    def up(self):
        hwnd=self.voice_button_hwnd
        self.voice_button_hwnd=None
        if not hwnd or not u.IsWindow(hwnd):
            raise RuntimeError('豆包麦克风按钮窗口已关闭，无法通过状态栏结束录音。')
        self._click_voice_button(hwnd)
        self.rec.emit('doubao_voice_button_clicked',hwnd=int(hwnd),action='stop')
    @staticmethod
    def _find_voice_button_window():
        candidates=[]
        callback_type=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
        @callback_type
        def visit(hwnd,_):
            if not u.IsWindowVisible(hwnd):return True
            class_name=c.create_unicode_buffer(128)
            if not u.GetClassNameW(hwnd,class_name,128) or class_name.value!='OimeDirectUIWindow':return True
            pid=w.DWORD();u.GetWindowThreadProcessId(hwnd,c.byref(pid))
            try:
                process=psutil.Process(pid.value)
                if process.name().casefold()!='imeservice.exe' or '\\doubaoime\\' not in process.exe().casefold():return True
            except psutil.Error:return True
            rect=w.RECT()
            if not u.GetWindowRect(hwnd,c.byref(rect)):return True
            width=rect.right-rect.left;height=rect.bottom-rect.top
            ratio=width/height if height else 0
            # The installed 0.9.2.7 status_bar_window.xml is 156x45 DIPs;
            # permit common Windows scaling while excluding candidate panels.
            if 3.15<=ratio<=3.8 and 140<=width<=240 and 38<=height<=80:
                candidates.append((width*height,int(hwnd)))
            return True
        u.EnumWindows(visit,0)
        return max(candidates,default=(0,None))[1]
    @staticmethod
    def _click_voice_button(hwnd):
        if not u.IsWindow(hwnd):raise RuntimeError('豆包麦克风状态栏已关闭。')
        rect=w.RECT()
        if not u.GetWindowRect(hwnd,c.byref(rect)):raise RuntimeError('无法读取豆包麦克风状态栏位置。')
        width=rect.right-rect.left;height=rect.bottom-rect.top
        if not (3.15<=width/height<=3.8 and 140<=width<=240 and 38<=height<=80):
            raise RuntimeError('豆包状态栏尺寸与已识别版本不符，已取消点击以避免误触。')
        dpi=u.GetDpiForWindow(hwnd) if hasattr(u,'GetDpiForWindow') else 96
        point=_voice_button_point(width,height,dpi)
        for message,param,action in ((0x0200,0,'移动'),(0x0201,1,'按下'),(0x0202,0,'释放')):
            c.set_last_error(0)
            if not u.PostMessageW(hwnd,message,param,point):
                code=c.get_last_error()
                detail='Windows 权限隔离拒绝访问豆包窗口；需另行确认临时同权限测试。' if code==5 else c.FormatError(code).strip()
                raise RuntimeError(f'豆包按钮{action}失败（Windows 错误 {code}）：{detail}')

    def capture_active(self):
        sessions=self.manager.GetSessionEnumerator()
        for i in range(sessions.GetCount()):
            session=sessions.GetSession(i).QueryInterface(IAudioSessionControl2)
            if session.GetState()!=1:continue
            try:
                process=psutil.Process(session.GetProcessId())
                path=process.exe().lower()
                if process.name().lower()=='imeservice.exe' and '\\doubaoime\\' in path:return True
            except psutil.Error:continue
        return False

def _voice_button_point(width,height,dpi):
    if height<=0 or not (3.15<=width/height<=3.8 and 140<=width<=240 and 38<=height<=80):
        raise RuntimeError('豆包状态栏尺寸与已识别版本不符，已取消点击以避免误触。')
    scale=max(.75,min(2.0,(dpi or 96)/96.0))
    # The bundled 156x45-DIP layout places btn_voice at x=55,y=20.
    x=round(55*scale);y=round(20*scale)
    return (y<<16)|(x&0xffff)

class VoiceSession:
    """UI-thread state machine; backend and monotonic clock are replaceable in tests."""
    def __init__(self,backend,sink,rec,clock=time.monotonic):
        self.backend=backend;self.sink=sink;self.rec=rec;self.clock=clock
        self.events=queue.Queue();self.state='idle';self.held=False;self.status='就绪：先点击下方文本框并切换到豆包输入法'
        self.requested_stop=None;self.target_window=None;self.completed=0;self.failures=0
    def enqueue(self,data):
        if data[:1] in (b'\x04',b'\x00'):self.events.put(bytes(data))
    def release(self):
        if self.held:
            self.held=False
            self.backend.up();self.rec.emit('doubao_voice_activation_stopped')
    def fail(self,error):
        self.failures+=1;self.status=str(error);self.state='failed'
        try:self.release()
        except Exception as cleanup_error:
            self.rec.emit('doubao_voice_stop_error',error=str(cleanup_error))
        finally:self.sink.allow_output();self.rec.emit('doubao_voice_error',error=str(error))
    def begin(self):
        self.release();self.requested_stop=None;self.target_window=self.backend.target()
        if self.target_window is None:raise RuntimeError('请先关闭搜索面板，点击目标文本框，再按红键。')
        if self.backend.capture_active():raise RuntimeError('豆包已有录音会话，请先结束它，再按红键。')
        self.started=self.clock();self.settled=self.started+.18;self.state='settling';self.status='正在唤起豆包输入法语音…'
        self.rec.emit('doubao_voice_requested',target_pid=self.target_window[1],target_process=Path(self.target_window[2]).name)
    def tick(self):
        try:
            if self.state in ('idle','failed'):self.backend.poll_target()
            while not self.events.empty():
                data=self.events.get_nowait()
                if data[:1]==b'\x04':self.begin()
                elif self.state not in ('idle','failed'):
                    self.requested_stop=self.clock();self.rec.emit('doubao_stop_received')
            now=self.clock()
            if self.state=='settling':
                if not self.backend.prepare(self.target_window):self.settled=max(self.settled,now+.08)
                elif now>=self.settled:
                    self.backend.down();self.held=True;self.opened=now;self.state='opening'
                    self.rec.emit('doubao_voice_activation_started')
            elif self.state=='opening':
                if self.backend.capture_active():
                    self.sink.allow_output();self.state='recording';self.status='豆包正在收音：继续按住红键说话'
                    self.rec.emit('doubao_capture_active',startup_ms=round((now-self.started)*1000))
                elif now-self.opened>2.5:
                    raise RuntimeError('豆包未打开 CABLE Output。请确认文本框中已切换到豆包输入法，再重试。')
            elif self.state in ('recording','draining','releasing'):
                if self.requested_stop is not None:
                    if self.state=='recording':self.state='draining';self.status='已松开红键，正在送完尾音…'
                    if self.state=='draining' and self.sink.frames==0 and now-self.requested_stop>.1:
                        self.state='releasing';self.release_at=now+.15
                    elif self.state=='releasing':
                        if self.sink.frames:self.state='draining'
                        elif now>=self.release_at:
                            self.release();self.state='idle';self.completed+=1
                            self.status='本轮已结束，等待豆包输出文字；可再次按住红键'
                            self.rec.emit('doubao_voice_completed',completed=self.completed)
                elif now-self.started>60:raise RuntimeError('单次语音超过60秒，已释放快捷键。请松开红键。')
        except Exception as exc:self.fail(exc)
    def close(self):self.release()

class ThreadedVoiceSession:
    """Keep press/release timers independent of the target Tk window's native menus."""
    def __init__(self,sink,rec):
        self.stop=threading.Event();self.events=queue.Queue();self.voice=None
        self.status='正在准备豆包语音控制…';self.sink=sink;self.rec=rec
        self.worker=threading.Thread(target=self.run,name='DoubaoVoiceControl',daemon=False);self.worker.start()
    @property
    def completed(self):return self.voice.completed if self.voice else 0
    @property
    def failures(self):return self.voice.failures if self.voice else 0
    def enqueue(self,data):
        if data[:1] in (b'\x04',b'\x00'):self.events.put(bytes(data))
    def tick(self):pass
    def run(self):
        comtypes.CoInitializeEx(0)
        try:
            self.voice=VoiceSession(WindowsBackend(self.rec,self.stop),self.sink,self.rec)
            while not self.stop.is_set():
                while not self.events.empty():self.voice.enqueue(self.events.get_nowait())
                started=time.monotonic();self.voice.tick();self.status=self.voice.status
                if time.monotonic()-started>.25:
                    self.rec.emit('doubao_slow_tick',seconds=round(time.monotonic()-started,3),state=self.voice.state)
                self.stop.wait(.025)
        except Exception as exc:
            self.status=str(exc);self.rec.errors.append('Doubao control: '+repr(exc))
            self.rec.emit('doubao_control_error',error=repr(exc));self.sink.allow_output()
        finally:
            if self.voice:
                self.voice.close();self.voice.backend.manager=None
            comtypes.CoUninitialize()
    def close(self):
        self.stop.set();self.worker.join(5)
        if self.worker.is_alive():
            if self.voice:self.voice.release()
            raise RuntimeError('豆包控制线程尚未结束，已尝试释放右 Alt。')
