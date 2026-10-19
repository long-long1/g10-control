"""User-approved temporary capture-default switch with GUI, external completion file, and timeout restore."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import time
import tkinter as tk

from audio_defaults import snapshot,restore
from virtual_audio_probe import defaults,catalog,select_devices

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--temporary-capture-approval',action='store_true')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=int,default=600)
    a=p.parse_args()
    if not a.temporary_capture_approval:p.error('Explicit temporary capture-default change approval is required')
    a.output.mkdir(parents=True,exist_ok=False)
    backup=a.output/'defaults-before.json'
    before=snapshot(backup)['defaults']
    status={'time':datetime.now().astimezone().isoformat(),'state':'initializing','backup':str(backup.resolve()),
            'authorization':'User explicitly allowed temporary Windows default capture and communications microphone switch; restore after test',
            'playback_defaults_changed_by_tool':False}
    def persist():
        (a.output/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    persist();root=None
    try:
        import comtypes
        from pycaw.api.policyconfig import IPolicyConfig
        from pycaw.constants import CLSID_CPolicyConfigClient
        info=catalog();capture,_=select_devices(info,'vbcable')
        candidates=[d for d in info['core_audio_endpoints'] if d['name']==capture['name'] and d['flow']==1 and d['state']==1]
        if len(candidates)!=1:raise RuntimeError('Ambiguous CABLE Output endpoint')
        device_id=candidates[0]['id']
        expected={**before,**{f'1:{r}':device_id for r in (0,1,2)}}
        policy=comtypes.CoCreateInstance(CLSID_CPolicyConfigClient,IPolicyConfig,comtypes.CLSCTX_INPROC_SERVER)
        for role in (0,1,2):policy.SetDefaultEndpoint(device_id,role)
        after=defaults()
        if after!=expected:raise RuntimeError('Capture defaults did not match requested device, or playback defaults changed')
        status.update(state='ready',capture_device=capture['name'],capture_id=device_id,after_switch=after)
        persist()
        root=tk.Tk();root.title('ChatGPT 麦克风测试：临时切换中');root.geometry('620x260+1100+120')
        label=tk.StringVar(value='默认录音设备已临时切换到 CABLE Output')
        tk.Label(root,textvariable=label,font=('Microsoft YaHei UI',14),wraplength=590).pack(pady=15)
        tk.Label(root,text='保持 G10 桥接窗口运行。\n在 ChatGPT 点输入框旁的麦克风，\n再按住遥控器红键说话，松开后完成听写；先不要发送。\n如弹出搜索面板，可按电脑 Esc 关闭。',font=('Microsoft YaHei UI',11),justify='left').pack(pady=10)
        tk.Button(root,text='测试完成，恢复原麦克风',command=root.destroy).pack(pady=12)
        start=time.monotonic()
        def tick():
            remaining=max(0,int(a.seconds-(time.monotonic()-start)))
            label.set(f'已临时选 CABLE Output；{remaining} 秒后自动恢复')
            if remaining==0 or (a.output/'finish.signal').exists():root.destroy()
            else:root.after(250,tick)
        root.protocol('WM_DELETE_WINDOW',root.destroy)
        root.after(250,tick);root.mainloop()
        status['state']='finished'
    except Exception as exc:
        status.update(state='error',error=repr(exc))
        raise
    finally:
        try:
            result=restore(backup)
            (a.output/'restoration.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            status['restored']=result['restored']
        except Exception as exc:
            status['restore_error']=repr(exc);status['restored']=False
        persist()
        print(json.dumps(status,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
