"""Snapshot defaults; restore only the explicitly saved endpoints after authorized installation."""
import argparse
from datetime import datetime
import json
from pathlib import Path

from virtual_audio_probe import defaults

def snapshot(path):
    result={'time':datetime.now().astimezone().isoformat(),'defaults':defaults()}
    if any(not isinstance(v,str) for v in result['defaults'].values()):
        raise RuntimeError('Cannot capture all six defaults; refusing incomplete backup')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    return result

def restore(path):
    import comtypes
    from pycaw.pycaw import AudioUtilities
    from pycaw.api.mmdeviceapi import IMMEndpoint
    from pycaw.api.policyconfig import IPolicyConfig
    from pycaw.constants import CLSID_CPolicyConfigClient
    saved=json.loads(path.read_text(encoding='utf-8'))['defaults']
    if set(saved)!={f'{flow}:{role}' for flow in (0,1) for role in (0,1,2)}:
        raise RuntimeError('Backup does not contain exactly six endpoint roles')
    before=defaults(); changed=[]
    enum=AudioUtilities.GetDeviceEnumerator()
    for key,value in saved.items():
        if not isinstance(value,str):raise RuntimeError('Invalid saved endpoint')
        dev=enum.GetDevice(value)
        flow=int(key.split(':')[0])
        if dev.GetState()!=1 or dev.QueryInterface(IMMEndpoint).GetDataFlow()!=flow:
            raise RuntimeError('An original endpoint is no longer active; refusing substitute')
    policy=None
    for key,value in saved.items():
        if before.get(key)!=value:
            if policy is None:
                policy=comtypes.CoCreateInstance(CLSID_CPolicyConfigClient,IPolicyConfig,comtypes.CLSCTX_INPROC_SERVER)
            policy.SetDefaultEndpoint(value,int(key.split(':')[1]))
            changed.append(key)
    after=defaults()
    return {'time':datetime.now().astimezone().isoformat(),'before':before,'changed_roles':changed,'after':after,'restored':after==saved}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('snapshot','restore','check'))
    p.add_argument('backup',type=Path)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.action=='snapshot':r=snapshot(a.backup)
    elif a.action=='restore':r=restore(a.backup)
    else:
        saved=json.loads(a.backup.read_text(encoding='utf-8'))['defaults'];current=defaults()
        r={'unchanged':saved==current,'current':current}
    if a.output:a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(r,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
