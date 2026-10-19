"""Local WASAPI route verification. No driver install, default changes, or physical mic fallback."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import time
import warnings

import numpy as np
import sounddevice as sd

ROOT=Path(__file__).resolve().parent
RENDER_NAME='扬声器 (网易虚拟音频设备)'
CAPTURE_NAME='麦克风阵列 (网易虚拟音频设备)'
RENDER_ID=''
CAPTURE_ID=''

def defaults():
    from pycaw.pycaw import AudioUtilities
    enum=AudioUtilities.GetDeviceEnumerator()
    result={}
    for flow in (0,1):
        for role in (0,1,2):
            try: result[f'{flow}:{role}']=enum.GetDefaultAudioEndpoint(flow,role).GetId()
            except Exception as exc: result[f'{flow}:{role}']={'error':str(exc)}
    return result

def catalog():
    from pycaw.pycaw import AudioUtilities
    from pycaw.api.mmdeviceapi import IMMEndpoint
    from pycaw.api.endpointvolume import IAudioEndpointVolume
    from pycaw.api.audioclient import IAudioClient
    import comtypes
    import ctypes
    enum=AudioUtilities.GetDeviceEnumerator()
    collection=enum.EnumAudioEndpoints(2,15)
    rows=[]
    for i in range(collection.GetCount()):
        device=collection.Item(i)
        row={'id':device.GetId(),'state':device.GetState(),'flow':device.QueryInterface(IMMEndpoint).GetDataFlow()}
        with warnings.catch_warnings(record=True) as ws:
            view=AudioUtilities.CreateDevice(device)
            row['name']=view.FriendlyName
            row['property_warnings']=[str(w.message) for w in ws]
        if row['id'].lower() in (RENDER_ID,CAPTURE_ID) or ('VB-Audio Virtual Cable' in (row['name'] or '')):
            try:
                volume=device.Activate(IAudioEndpointVolume._iid_,comtypes.CLSCTX_ALL,None).QueryInterface(IAudioEndpointVolume)
                row.update(muted=bool(volume.GetMute()),volume_scalar=volume.GetMasterVolumeLevelScalar())
                client=device.Activate(IAudioClient._iid_,comtypes.CLSCTX_ALL,None).QueryInterface(IAudioClient)
                ptr=client.GetMixFormat()
                try:
                    mix=ptr.contents
                    row['mix_format']={field:getattr(mix,field) for field in ('wFormatTag','nChannels','nSamplesPerSec','wBitsPerSample','nBlockAlign')}
                finally:
                    ctypes.windll.ole32.CoTaskMemFree.argtypes=[ctypes.c_void_p]
                    ctypes.windll.ole32.CoTaskMemFree(ptr)
            except Exception as exc: row['read_error']=repr(exc)
        rows.append(row)
    hosts=sd.query_hostapis()
    return {'time':datetime.now().astimezone().isoformat(),'core_audio_endpoints':rows,'defaults':defaults(),
            'wasapi_devices':[{**d,'host':hosts[d['hostapi']]['name']} for d in sd.query_devices() if hosts[d['hostapi']]['name']=='Windows WASAPI']}

def select_devices(info,profile='netease'):
    wasapi=info['wasapi_devices']
    if profile=='vbcable':
        def cable(direction,tag,channel_key):
            candidates=[d for d in wasapi if tag in d['name'] and 'VB-Audio Virtual Cable' in d['name'] and d[channel_key]>=2]
            if len(candidates)!=1:
                raise RuntimeError(f'Expected one standard VB-CABLE {tag} endpoint; no fallback')
            endpoint=[d for d in info['core_audio_endpoints'] if d['name']==candidates[0]['name'] and d['flow']==direction and d['state']==1]
            if len(endpoint)!=1:raise RuntimeError('Ambiguous VB-CABLE Core Audio identity')
            if endpoint[0].get('muted') or endpoint[0].get('volume_scalar',1)==0:
                raise RuntimeError(f'{tag} is muted or zero volume; no setting changes attempted')
            return candidates[0]
        return cable(1,'CABLE Output','max_input_channels'),cable(0,'CABLE Input','max_output_channels')
    def exact(name,channel_key,endpoint_id):
        devices=[d for d in wasapi if d['name']==name and d[channel_key]>=2]
        endpoints=[d for d in info['core_audio_endpoints'] if d['id'].lower()==endpoint_id and d['name']==name and d['state']==1]
        if len(devices)!=1 or len(endpoints)!=1:
            raise RuntimeError(f'Expected one active, exact-identity WASAPI endpoint {name}; refusing fallback')
        if endpoints[0].get('muted') or endpoints[0].get('volume_scalar',1)==0:
            raise RuntimeError(f'{name} is muted or volume is zero; no volume changes attempted')
        return devices[0]
    return exact(CAPTURE_NAME,'max_input_channels',CAPTURE_ID),exact(RENDER_NAME,'max_output_channels',RENDER_ID)

def test_signal(rate):
    # Deterministic, speech-band multi-tone sequence; low amplitude and distinguishable sections.
    segments=[]
    for frequency in (733,1187,1873,941):
        n=int(rate*.28); t=np.arange(n)/rate
        fade=np.minimum(np.minimum(t/.015,(n/rate-t)/.015),1)
        tone=.025*fade*(np.sin(2*np.pi*frequency*t)+.35*np.sin(2*np.pi*(frequency+173)*t))
        segments.extend((tone,np.zeros(int(rate*.09))))
    return np.concatenate(segments).astype(np.float32)

def correlate(reference,received):
    reference=np.asarray(reference,dtype=np.float64)
    received=np.asarray(received,dtype=np.float64)
    if len(received)<len(reference):return {'correlation':0,'reason':'capture shorter than reference'}
    reference=reference-reference.mean()
    nfft=1<<(len(received)+len(reference)-2).bit_length()
    conv=np.fft.irfft(np.fft.rfft(received,nfft)*np.fft.rfft(reference[::-1],nfft),nfft)
    dots=conv[len(reference)-1:len(received)]
    sums=np.concatenate(([0],np.cumsum(received)))
    squares=np.concatenate(([0],np.cumsum(received**2)))
    energy=squares[len(reference):]-squares[:-len(reference)]-(sums[len(reference):]-sums[:-len(reference)])**2/len(reference)
    norms=np.sqrt(np.maximum(energy,0)*np.dot(reference,reference))
    scores=np.divide(dots,norms,out=np.zeros_like(dots),where=norms>1e-15)
    offset=int(np.argmax(np.abs(scores)))
    return {'correlation':float(scores[offset]),'capture_offset_frames':offset,
            'capture_rms':float(np.sqrt(np.mean(received**2))),'peak':float(np.max(np.abs(received))),
            'nonzero_samples':int(np.count_nonzero(received))}

def probe(info,directory,profile='netease'):
    capture,render=select_devices(info,profile)
    rate=int(capture['default_samplerate'])
    if rate!=int(render['default_samplerate']):raise RuntimeError('Mix rates differ; do not guess a shared format')
    settings=sd.WasapiSettings(exclusive=False)
    sd.check_input_settings(device=capture['index'],channels=2,dtype='float32',samplerate=rate,extra_settings=settings)
    sd.check_output_settings(device=render['index'],channels=2,dtype='float32',samplerate=rate,extra_settings=settings)
    signal=test_signal(rate)
    captured=np.zeros((rate*6,2),dtype=np.float32)
    position=0; status_flags=[]
    def callback(indata,frames,clock,status):
        nonlocal position
        if status:status_flags.append(str(status))
        n=min(frames,len(captured)-position)
        if n>0:captured[position:position+n]=indata[:n];position+=n
    before=defaults()
    try:
        with sd.InputStream(device=capture['index'],channels=2,samplerate=rate,dtype='float32',extra_settings=settings,callback=callback) as input_stream:
            time.sleep(.5)
            with sd.OutputStream(device=render['index'],channels=2,samplerate=rate,dtype='float32',extra_settings=settings) as output_stream:
                underflow=output_stream.write(np.repeat(signal[:,None],2,axis=1))
                latency=output_stream.latency
            time.sleep(1.)
        results=[correlate(signal,captured[:position,channel]) for channel in (0,1)]
        result={'samplerate':rate,'capture_name':capture['name'],'render_name':render['name'],
                'capture_frames':position,'test_seconds':len(signal)/rate,'input_status':status_flags,
                'output_underflow':bool(underflow),'output_latency_s':latency,'channels':results,
                'passed':any(abs(r['correlation'])>.8 for r in results),
                'profile':profile,
                'policy':'synthetic signal only; selected virtual endpoints only; no physical microphone/speaker fallback; no global settings changed'}
        # Do not preserve captured content by default: it could contain unrelated audio.
        return result
    finally:
        after=defaults()
        (directory/'defaults-after.json').write_text(json.dumps(after,ensure_ascii=False,indent=2),encoding='utf-8')
        if before!=after:
            raise RuntimeError('Default endpoints changed during probe; no default-setting API was called by this tool')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--probe',action='store_true',help='Send local synthetic signal only to exact NetEase render endpoint and inspect exact NetEase capture endpoint')
    p.add_argument('--profile',choices=('netease','vbcable'),default='netease')
    p.add_argument('--output',type=Path,default=ROOT/'output/phase3-virtual-probe')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    info=catalog()
    (a.output/'endpoints.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    if not a.probe:
        print(json.dumps(info,ensure_ascii=False,indent=2));return
    try: result=probe(info,a.output,a.profile)
    except Exception as exc: result={'passed':False,'error':repr(exc)}
    (a.output/'route-test.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
