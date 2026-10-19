"""Read-only Doubao capture-route and foreground-process observer; never sends input."""
import ctypes as c
from ctypes import wintypes as w
import threading
import time

import comtypes
import psutil
from inspect_audio_sessions import inspect

class ImeRouteMonitor:
    def __init__(self,rec):
        self.rec=rec;self.stop=threading.Event();self.status='正在观察豆包的实际录音设备…'
        self.threads=[threading.Thread(target=self.audio,name='ImeAudioObserver',daemon=True),
                      threading.Thread(target=self.focus,name='ForegroundObserver',daemon=True)]
        for worker in self.threads:worker.start()
    def audio(self):
        comtypes.CoInitializeEx(0);previous=None
        try:
            while not self.stop.is_set():
                snapshot=inspect();routes=[]
                for device in snapshot['capture_endpoints']:
                    for session in device['sessions']:
                        if session.get('process','').lower()=='imeservice.exe' and session['state']==1:
                            routes.append({'id':device['id'],'name':device['name'],'pid':session['pid']})
                signature=tuple((r['id'],r['pid']) for r in routes)
                if signature!=previous:
                    self.rec.emit('ime_capture_state',active_routes=routes)
                    previous=signature
                self.status='豆包实际正在读取：'+ '、'.join(r['name'] for r in routes) if routes else '豆包当前没有活动的录音通道'
                self.stop.wait(.1)
        except Exception as exc:
            self.status='录音设备观察失败：'+str(exc)
            if not self.stop.is_set():self.rec.emit('ime_observer_error',error=repr(exc))
        finally:comtypes.CoUninitialize()
    def focus(self):
        user=c.WinDLL('user32',use_last_error=True)
        user.GetForegroundWindow.restype=w.HWND
        user.GetWindowThreadProcessId.argtypes=[w.HWND,c.POINTER(w.DWORD)]
        previous=None;cache={}
        while not self.stop.is_set():
            try:
                hwnd=user.GetForegroundWindow();pid=w.DWORD()
                user.GetWindowThreadProcessId(hwnd,c.byref(pid))
                current=(int(hwnd or 0),pid.value)
                if current!=previous:
                    if pid.value not in cache:
                        try:cache[pid.value]=psutil.Process(pid.value).name()
                        except psutil.Error:cache[pid.value]='unavailable'
                    self.rec.emit('foreground_process',pid=pid.value,process=cache[pid.value])
                    previous=current
            except Exception as exc:
                if not self.stop.is_set():self.rec.emit('focus_observer_error',error=repr(exc))
            self.stop.wait(.025)
    def close(self):
        self.stop.set()
        for worker in self.threads:worker.join(3)
