"""Local G10 -> low-first IMA ADPCM -> WASAPI CABLE Input bridge. No input remapping."""
import argparse
import asyncio
from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk

import numpy as np
import sounddevice as sd

from analyze_audio import Decoder,write_wav
from atvv_protocol import AUDIO,CONTROL
from phase2_handshake import Controller
from phase2_readonly import Recorder,observe,ROOT
from virtual_audio_probe import catalog,select_devices,defaults,correlate

class AudioBuffer:
    def __init__(self,rate=48000,prebuffer_ms=48,max_ms=500,gate_on_start=False):
        self.rate=rate;self.threshold=int(rate*prebuffer_ms/1000);self.limit=int(rate*max_ms/1000)
        self.lock=threading.Lock();self.chunks=deque();self.offset=0;self.frames=0
        self.active=False;self.playing=False;self.overflows=0;self.underruns=0;self.rendered=0
        self.gate_on_start=gate_on_start;self.gate_open=not gate_on_start
        self.startup={}
    def start(self,perf_ns=None):
        with self.lock:
            self.chunks.clear();self.frames=0;self.offset=0;self.playing=False;self.active=True
            self.gate_open=not self.gate_on_start
            self.startup={'start_ns':perf_ns if perf_ns is not None else time.perf_counter_ns(),
                          'first_audio_ns':None,'first_pcm_ns':None,'first_output_callback_ns':None}
    def note_audio(self,perf_ns):
        with self.lock:
            if self.startup and self.startup['first_audio_ns'] is None:
                self.startup['first_audio_ns']=perf_ns
    def startup_snapshot(self):
        with self.lock:result=dict(self.startup)
        for label,left,right in (
            ('start_to_first_audio_ms','start_ns','first_audio_ns'),
            ('first_audio_to_pcm_ms','first_audio_ns','first_pcm_ns'),
            ('first_pcm_to_output_callback_ms','first_pcm_ns','first_output_callback_ns'),
            ('start_to_output_callback_ms','start_ns','first_output_callback_ns')):
            a,b=result.get(left),result.get(right)
            result[label]=(b-a)/1e6 if a is not None and b is not None else None
        return result
    def allow_output(self):
        with self.lock:self.gate_open=True
    def end(self):
        with self.lock:self.active=False
    def push(self,mono):
        with self.lock:
            if self.frames+len(mono)>self.limit:
                self.overflows+=1
                raise RuntimeError(f'More than {self.limit/self.rate:.1f}s queued audio; stopping')
            self.chunks.append(mono);self.frames+=len(mono)
            if len(mono) and self.startup and self.startup['first_pcm_ns'] is None:
                self.startup['first_pcm_ns']=time.perf_counter_ns()
    def read_into(self,out):
        out.fill(0)
        with self.lock:
            if not self.gate_open:return
            if not self.playing and self.frames<self.threshold and self.active:return
            self.playing=True
            position=0
            while position<len(out) and self.chunks:
                chunk=self.chunks[0];n=min(len(out)-position,len(chunk)-self.offset)
                out[position:position+n,:]=chunk[self.offset:self.offset+n,None]
                position+=n;self.offset+=n;self.frames-=n;self.rendered+=n
                if self.offset==len(chunk):self.chunks.popleft();self.offset=0
            if position and self.startup and self.startup['first_output_callback_ns'] is None:
                self.startup['first_output_callback_ns']=time.perf_counter_ns()
            if position<len(out) and self.active and position:
                self.underruns+=1;self.playing=False

class Upsample3:
    """Stateful linear interpolation. Exactly three output samples per input sample."""
    def __init__(self):self.previous=None
    def convert(self,values):
        x=np.asarray(values,dtype=np.float32)
        if not len(x):return x
        prior=np.empty_like(x)
        prior[0]=x[0] if self.previous is None else self.previous
        prior[1:]=x[:-1]
        self.previous=float(x[-1])
        return (prior[:,None]+(x-prior)[:,None]*np.array([1/3,2/3,1],dtype=np.float32)).reshape(-1).astype(np.float32)

class LiveDecoder:
    def __init__(self,sink,rec,verify):
        self.sink=sink;self.rec=rec;self.verify=verify;self.active=False;self.pending=bytearray();self.orphans=deque(maxlen=4)
        self.decoder=Decoder(False);self.resampler=Upsample3();self.gain_db=0.;self.level=0.
        self.sessions=0;self.stops=0;self.last_stop_time=None;self.expected=[];self.expected_frames=0;self.samples=0
        self.waiting_for_start=False;self.unanchored_since=None;self.last_stop_perf=None;self.unanchored_packets=0
    def event(self,key,data,perf):
        if key==CONTROL:
            if data[:1]==b'\x04':
                if len(data)<3 or data[2]!=2:raise RuntimeError('Unsupported START for verified G10 profile')
                self.active=True;self.sessions+=1;self.pending.clear();self.decoder=Decoder(False);self.resampler=Upsample3();self.sink.start(perf)
                self.waiting_for_start=False;self.unanchored_since=None
                self.rec.emit('pcm_session_start',session=self.sessions)
                for stamp,packet in list(self.orphans):
                    if abs(perf-stamp)<50_000_000:
                        self.sink.note_audio(stamp);self.audio(packet)
                self.orphans.clear()
            elif data[:1]==b'\x00':
                self.active=False;self.stops+=1;self.last_stop_time=time.monotonic();self.sink.end();self.level=0
                self.last_stop_perf=perf;self.waiting_for_start=False;self.unanchored_since=None;self.orphans.clear()
                self.rec.emit('pcm_session_end',session=self.sessions,pending_bytes=len(self.pending));self.pending.clear()
            elif data[:1]==b'\x0a' and len(data)>=7:
                self.pending.clear();self.decoder.predictor=int.from_bytes(data[4:6],'big',signed=True);self.decoder.index=min(88,data[6])
        elif key==AUDIO:
            if self.active:
                self.sink.note_audio(perf);self.audio(data)
            elif self.last_stop_perf is None or perf-self.last_stop_perf>=300_000_000:
                self.orphans.append((perf,data));self.unanchored_packets+=1
                if not self.waiting_for_start:
                    self.unanchored_since=perf
                    self.rec.emit('awaiting_fresh_start',reason='Audio arrived without START; release and press red key again')
                self.waiting_for_start=True
    def audio(self,data):
        self.pending.extend(data)
        while len(self.pending)>=128:
            frame=bytes(self.pending[:128]);del self.pending[:128]
            values=np.asarray(self.decoder.decode(frame),dtype=np.float32)
            smoothed=values.copy();smoothed[1:-1]=np.floor((values[:-2]+2*values[1:-1]+values[2:])/4)
            mono=np.clip(smoothed/32768*10**(self.gain_db/20),-1,1)
            self.level=float(np.sqrt(np.mean(mono**2)));self.samples+=len(mono)
            output=self.resampler.convert(mono)
            if self.verify:
                if self.expected_frames+len(output)>48000*60:raise RuntimeError('60-second local verification capture limit')
                self.expected.append(output);self.expected_frames+=len(output)
            self.sink.push(output)

class LiveRecorder(Recorder):
    """Bounded asynchronous metadata writer; disk I/O never gates notification dispatch."""
    def __init__(self,path,events,stop=None):
        super().__init__(path,save_audio=False);self.live_events=events
        self.log_events=queue.Queue(maxsize=512);self.write_error=None;self.queue_overflow=False;self.stop=stop
        self.closed=False
        self.writer=threading.Thread(target=self._write_events,name='BridgeEventWriter',daemon=False)
        self.writer.start()
    def emit(self,kind,*,perf_ns=None,unix_ns=None,**fields):
        # Logging failure stops the bridge but must not throw out of the BLE
        # finally block: CCCD restoration and resource release still run.
        if self.write_error is not None or self.queue_overflow:return
        if self.closed:raise RuntimeError('Event log writer is closed')
        # Capture at the producer, not when a potentially slow disk catches up.
        item=(kind,perf_ns if perf_ns is not None else time.perf_counter_ns(),
              unix_ns if unix_ns is not None else time.time_ns(),fields)
        try:self.log_events.put_nowait(item)
        except queue.Full:
            self.queue_overflow=True;self.errors.append('Event log queue full; stopping, evidence incomplete')
            if self.stop is not None:self.stop.set()
    def _write_events(self):
        while True:
            item=self.log_events.get()
            try:
                if item is None:return
                if self.write_error is None:
                    kind,perf,wall,fields=item
                    row={'kind':kind,'perf_ns':perf,'unix_ns':wall,
                         'utc':datetime.fromtimestamp(wall/1e9,timezone.utc).isoformat(),
                         'relative_s':(perf-self.origin)/1e9,**fields}
                    with self.lock:self.counts[kind]+=1
                    # Only this thread owns stream writes. Never hold the
                    # notification/audio-byte lock during a filesystem call.
                    self.stream.write(json.dumps(row,ensure_ascii=False)+'\n')
            except Exception as exc:
                self.write_error=repr(exc);self.errors.append('Event log writer: '+repr(exc))
                if self.stop is not None:self.stop.set()
            finally:self.log_events.task_done()
    def flush(self):
        self.log_events.join()
    def close(self):
        if self.closed:return
        self.closed=True
        self.log_events.put(None);self.writer.join()
        super().close()
    def notification(self,key,data,perf_ns,unix_ns,device_time):
        super().notification(key,data,perf_ns,unix_ns,device_time)
        self.live_events.put_nowait((key,data,perf_ns))

class BridgeController(Controller):
    async def initialize(self):
        await super().initialize()
        if self.caps.frame_size!=128 or self.caps.codec!=2:
            raise RuntimeError('Capabilities differ from the user-confirmed 128-byte G10 decoder profile')
    def receive(self,key,data,perf):
        super().receive(key,data,perf)
        if key==AUDIO and data and self.caps and not self.streaming and not self.closed:
            self.rec.emit('unexpected_audio',note='Audio outside accepted session')

def select_verified_pair():
    from audio_route import AudioRoute
    capture,render,_=AudioRoute().require_verified()
    return capture,render

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--business-approval',action='store_true');p.add_argument('--allow-cccd',action='store_true')
    p.add_argument('--verify-session',action='store_true',help='Locally record CABLE Output during one red-key session, then stop')
    p.add_argument('--monitor-output',action='store_true',help='Read CABLE Output meter locally without saving audio')
    p.add_argument('--doubao-ime',action='store_true',help='Experimental Doubao auto-wake diagnostic; has not passed hardware tests')
    p.add_argument('--local-input-test',action='store_true',help='Show local text box without sending any keyboard input')
    p.add_argument('--observe-ime',action='store_true',help='Read-only monitoring of Doubao recording endpoints and foreground process names')
    p.add_argument('--gain-db',type=float,default=0.0,help='Local audio gain from -30 to +30 dB')
    p.add_argument('--max-seconds',type=int,default=0,help='0 runs until a safe stop signal is received')
    p.add_argument('--headless',action='store_true',help='Hide the legacy diagnostic window for a desktop manager')
    p.add_argument('--status-path',type=Path,help='Write atomic local JSON state for the desktop manager')
    p.add_argument('--stop-file',type=Path,help='Safe stop signal from the desktop manager')
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    if not args.business_approval or not args.allow_cccd:p.error('Prior ATVV and CCCD approval required')
    from local_config import require_address, paired_device_id
    args.address=require_address()
    args.device_id=paired_device_id(args.address)
    if not -30.0<=args.gain_db<=30.0:p.error('--gain-db must be in range -30 to +30')
    args.ready_message='请在应用中选择 CABLE Output (VB-Audio Virtual Cable)，然后按住红键说话。'
    capture,render=select_verified_pair()
    if args.doubao_ime:
        from doubao_voice import check_config,ThreadedVoiceSession
        check_config()
    before=defaults()
    events=queue.Queue(maxsize=64);stop=threading.Event();ready=threading.Event();updates=queue.Queue()
    directory=args.output or ROOT/'output'/('g10-live-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    rec=LiveRecorder(directory,events,stop);sink=AudioBuffer(max_ms=3000 if args.doubao_ime else 500,gate_on_start=args.doubao_ime);decoder=LiveDecoder(sink,rec,args.verify_session)
    decoder.gain_db=args.gain_db
    rec.emit('bridge_config',capture=capture['name'],render=render['name'],profile='G10-128-byte-low-first-IMA-16k',
             output_rate=48000,raw_audio_saved=False,local_verification_recording=args.verify_session,
             metadata_logging='bounded-worker-v1')
    output_status=[];input_status=[];callback_errors=[]
    cable_level=0.;cable_peak=0.;cable_nonzero_frames=0
    def output_callback(outdata,frames,clock,status):
        try:
            if status:output_status.append(str(status))
            sink.read_into(outdata)
        except Exception as exc:
            outdata.fill(0);callback_errors.append(repr(exc));stop.set()
    verification=np.zeros((48000*90,2),dtype=np.float32) if args.verify_session else None
    position=0
    def input_callback(indata,frames,clock,status):
        nonlocal position,cable_level,cable_peak,cable_nonzero_frames
        if status:input_status.append(str(status))
        cable_level=float(np.sqrt(np.mean(indata**2)))
        cable_peak=max(cable_peak,float(np.max(np.abs(indata))))
        cable_nonzero_frames+=int(np.count_nonzero(np.max(np.abs(indata),axis=1)>.0001))
        if verification is None:return
        n=min(frames,len(verification)-position)
        if n>0:verification[position:position+n]=indata[:n];position+=n
        elif n==0:callback_errors.append('Verification capture full');stop.set()
    voice=None;ime_monitor=None
    def decode_worker():
        while not stop.is_set() or not events.empty():
            try:key,data,perf=events.get(timeout=.1)
            except queue.Empty:continue
            try:
                decoder.event(key,data,perf)
                if voice is not None and key==CONTROL:voice.enqueue(data)
            except Exception as exc:
                rec.errors.append(repr(exc));rec.emit('decode_error',error=repr(exc));stop.set()
    worker=None;decoding=None;output=None;input_stream=None;root=None
    started=time.monotonic()
    try:
        settings=sd.WasapiSettings(exclusive=False)
        output=sd.OutputStream(device=render['index'],channels=2,samplerate=48000,dtype='float32',blocksize=480,
                               extra_settings=settings,callback=output_callback)
        if args.verify_session or args.monitor_output:
            input_stream=sd.InputStream(device=capture['index'],channels=2,samplerate=48000,dtype='float32',
                                        extra_settings=settings,callback=input_callback)
            input_stream.start()
        output.start()
        if args.doubao_ime:voice=ThreadedVoiceSession(sink,rec)
        if args.observe_ime:
            from ime_route_monitor import ImeRouteMonitor
            ime_monitor=ImeRouteMonitor(rec)
        decoding=threading.Thread(target=decode_worker,daemon=False);decoding.start()
        controller=BridgeController(rec,stop,updates)
        worker=threading.Thread(target=lambda:asyncio.run(observe(rec,stop,ready,updates,args,controller)),daemon=False);worker.start()
        root=tk.Tk();root.title('G10 遥控器麦克风 → CABLE Output');root.geometry('680x300+180+100');root.attributes('-topmost',True)
        if args.headless:root.withdraw()
        if voice:
            root.title('G10 红键 → 豆包输入法语音');root.geometry('760x490+180+100');root.attributes('-topmost',False)
        elif args.local_input_test:
            root.title('G10 收音检查：手动唤起豆包输入法');root.geometry('800x520+180+100');root.attributes('-topmost',False)
        title=tk.StringVar(value='正在连接 G10，请先松开红键')
        detail=tk.StringVar(value='应用的麦克风请选择 CABLE Output (VB-Audio Virtual Cable)')
        level=tk.StringVar(value='等待声音')
        tk.Label(root,textvariable=title,font=('Microsoft YaHei UI',17),wraplength=650).pack(pady=16)
        tk.Label(root,textvariable=detail,font=('Microsoft YaHei UI',11),wraplength=650).pack(pady=10)
        tk.Label(root,textvariable=level,font=('Microsoft YaHei UI',11)).pack(pady=10)
        help_text=('红键开始时关闭它唤出的 Windows 搜索并返回原输入窗口。\n识别由豆包输入法完成；本工具不保存文字或录音，不改默认麦克风。' if voice else
                   '红键仍保留系统搜索行为。松开后音频缓冲会短暂排空。\n此工具不设置默认麦克风、不上传声音。')
        tk.Label(root,text=help_text,font=('Microsoft YaHei UI',10)).pack()
        voice_status=tk.StringVar()
        ime_status=tk.StringVar()
        if ime_monitor:
            tk.Label(root,textvariable=ime_status,font=('Microsoft YaHei UI',11),wraplength=770,fg='#135b93').pack(pady=8)
        if voice:
            tk.Label(root,textvariable=voice_status,font=('Microsoft YaHei UI',11),wraplength=730,fg='#135b93').pack(pady=8)
        if voice or args.local_input_test:
            instruction=('本地测试框：点击这里，用 Win+空格切换到“豆包输入法”，再按住红键说话。' if voice else
                         '先按住红键，再点击测试框，用右 Alt+空格手动开启豆包语音，继续说话。')
            tk.Label(root,text=instruction,font=('Microsoft YaHei UI',10)).pack()
            local_text=tk.Text(root,height=5,font=('Microsoft YaHei UI',13),wrap='word');local_text.pack(fill='x',padx=20,pady=8)
        tk.Button(root,text='停止桥接并退出',command=stop.set).pack(pady=14)
        root.protocol('WM_DELETE_WINDOW',stop.set)
        def tick():
            if voice:voice.tick();voice_status.set(voice.status)
            if ime_monitor:ime_status.set(ime_monitor.status)
            while True:
                try:detail.set(updates.get_nowait())
                except queue.Empty:break
            if args.max_seconds>0 and time.monotonic()-started>args.max_seconds:stop.set()
            if (directory/'stop.signal').exists():stop.set()
            if args.stop_file and args.stop_file.exists():stop.set()
            if ready.is_set():
                if decoder.active:title.set('正在向 CABLE Output 发送遥控器声音')
                elif decoder.waiting_for_start and time.perf_counter_ns()-decoder.unanchored_since>50_000_000:
                    title.set('缺少开始消息：请松开红键后重新按下')
                else:title.set('已就绪：按住红键说话约 5 秒后松开' if args.verify_session else '已就绪：按住红键说话，松开结束')
            text=f'输入 {20*np.log10(max(decoder.level,1e-6)):.1f} dBFS  |  已处理 {decoder.samples/16000:.2f} 秒  |  已输出 {sink.rendered/48000:.2f} 秒'
            if args.monitor_output:text+=f'\n虚拟麦克风实读 {20*np.log10(max(cable_level,1e-6)):.1f} dBFS'
            level.set(text)
            startup=sink.startup_snapshot()
            if startup.get('first_output_callback_ns') is not None and startup['start_ns']!=getattr(tick,'last_startup',None):
                tick.last_startup=startup['start_ns']
                rec.emit('audio_startup_timing',session=decoder.sessions,**startup,
                         boundary='host START callback to PCM copied into output callback; not physical key or DAC time')
            if args.monitor_output and int(time.monotonic()-started)!=getattr(tick,'last_meter_second',None):
                tick.last_meter_second=int(time.monotonic()-started)
                rec.emit('cable_output_meter',level=cable_level,peak=cable_peak,nonzero_frames=cable_nonzero_frames,
                         processed_seconds=decoder.samples/16000,rendered_seconds=sink.rendered/48000)
            if output is not None and not output.active:
                callback_errors.append('WASAPI output stream stopped');stop.set()
            if args.verify_session and decoder.stops>=1 and decoder.last_stop_time is not None and time.monotonic()-decoder.last_stop_time>1:
                stop.set()
            if args.headless and args.status_path and time.monotonic()-getattr(tick,'last_status_time',-1)>=.2:
                tick.last_status_time=time.monotonic()
                snapshot={
                    'time':datetime.now().astimezone().isoformat(),
                    'ready':ready.is_set() and not stop.is_set(),
                    'connected':ready.is_set() and not stop.is_set(),
                    'audio_active':decoder.active,'waiting_for_start':decoder.waiting_for_start,
                    'processed_audio_seconds':round(decoder.samples/16000,3),
                    'rendered_audio_seconds':round(sink.rendered/48000,3),
                    'input_level_dbfs':round(20*np.log10(max(decoder.level,1e-6)),1),
                    'cable_level_dbfs':round(20*np.log10(max(cable_level,1e-6)),1),
                    'cable_peak':round(cable_peak,5),'sessions':decoder.sessions,
                    'error_count':len(rec.errors),'last_error':rec.errors[-1] if rec.errors else None,
                    'startup_timing':startup,
                }
                args.status_path.parent.mkdir(parents=True,exist_ok=True)
                temporary=args.status_path.with_suffix(args.status_path.suffix+'.tmp')
                temporary.write_text(json.dumps(snapshot,ensure_ascii=False),encoding='utf-8')
                try:
                    temporary.replace(args.status_path)
                except PermissionError:
                    # Windows may briefly deny replacement while another process
                    # inspects the status file. Keep the UI heartbeat alive and
                    # retry on the next tick instead of aborting Tk's timer loop.
                    try: temporary.unlink(missing_ok=True)
                    except OSError: pass
            if stop.is_set():root.after(200,root.destroy)
            else:root.after(25 if voice else 100,tick)
        root.after(100,tick);root.mainloop()
    finally:
        stop.set()
        if voice:
            try:voice.close()
            except Exception as exc:callback_errors.append('Right Alt release failed: '+repr(exc))
        if ime_monitor:ime_monitor.close()
        if worker:worker.join()
        if decoding:decoding.join()
        if output:output.stop();output.close()
        if input_stream:input_stream.stop();input_stream.close()
        rec.flush()  # Counts and errors must be complete before building the summary.
        result={'time':datetime.now().astimezone().isoformat(),'sessions':decoder.sessions,'stops':decoder.stops,
                'pcm_samples_16k':decoder.samples,'forwarded_seconds':decoder.samples/16000,
                'rendered_frames_48k':sink.rendered,'buffer_overflows':sink.overflows,'buffer_underruns':sink.underruns,
                'wasapi_output_status':output_status,'wasapi_input_status':input_status,'callback_errors':callback_errors,
                'errors':rec.errors,'business_writes':rec.counts['tx_attempt'],'audio_notifications':rec.counts['audio'],
                'audio_bytes':rec.audio_bytes,'default_devices_unchanged':defaults()==before}
        result.update(unanchored_packets=decoder.unanchored_packets,cable_output_peak=cable_peak,cable_output_nonzero_frames=cable_nonzero_frames)
        result['last_startup_timing']=sink.startup_snapshot()
        if voice:result.update(doubao_sessions_completed=voice.completed,doubao_failures=voice.failures)
        if args.verify_session and decoder.expected and position:
            expected=np.concatenate(decoder.expected)
            checks=[correlate(expected,verification[:position,c]) for c in (0,1)]
            result['cable_output_checks']=checks
            result['route_verified']=any(abs(c['correlation'])>.8 for c in checks)
            local=directory/'CABLE-Output-verification.wav'
            # Preserve mono capture for local listening; no physical mic or cloud is involved.
            first=int(np.argmax(np.max(np.abs(verification[:position]),axis=1)>.0001))
            samples=np.clip(verification[first:position,0]*32767,-32768,32767).astype(np.int16)
            write_wav(local,samples.tolist(),48000)
            result['verification_wav']=str(local.resolve())
        rec.emit('bridge_end',**result)
        (directory/'bridge-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        rec.close();print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        import traceback
        from tkinter import messagebox
        directory=ROOT/'output';directory.mkdir(exist_ok=True)
        path=directory/'g10-bridge-last-error.txt'
        path.write_text(traceback.format_exc(),encoding='utf-8')
        error_root=tk.Tk();error_root.withdraw()
        messagebox.showerror('G10 麦克风桥接未能启动',str(exc)+'\n\n错误已保存在：'+str(path),parent=error_root)
        error_root.destroy()
        sys.exit(1)
