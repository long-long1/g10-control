"""Read-only capture-session diagnostics. No recording, settings writes, or process injection."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import warnings

import comtypes
import psutil
from pycaw.pycaw import AudioUtilities
from pycaw.api.audiopolicy import IAudioSessionManager2,IAudioSessionControl2

def inspect():
    enum=AudioUtilities.GetDeviceEnumerator();collection=enum.EnumAudioEndpoints(1,1)
    endpoints=[]
    for i in range(collection.GetCount()):
        device=collection.Item(i)
        with warnings.catch_warnings(record=True):view=AudioUtilities.CreateDevice(device)
        row={'id':device.GetId(),'name':view.FriendlyName,'sessions':[]}
        try:
            manager=device.Activate(IAudioSessionManager2._iid_,comtypes.CLSCTX_ALL,None).QueryInterface(IAudioSessionManager2)
            sessions=manager.GetSessionEnumerator()
            for j in range(sessions.GetCount()):
                session=sessions.GetSession(j).QueryInterface(IAudioSessionControl2)
                pid=session.GetProcessId()
                item={'pid':pid,'state':session.GetState()}
                try:
                    process=psutil.Process(pid);item.update(process=process.name(),path=process.exe())
                except psutil.Error:pass
                row['sessions'].append(item)
        except Exception as exc:row['error']=repr(exc)
        endpoints.append(row)
    return {'time':datetime.now().astimezone().isoformat(),'capture_endpoints':endpoints}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path)
    a=p.parse_args();r=inspect()
    if a.output:a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(r,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
