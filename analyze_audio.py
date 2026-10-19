"""Offline evidence analysis and explicitly labelled RC003-decoder candidate WAVs. No network."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics
import struct
import wave

# Standard IMA/DVI quantizer adaptation data, not device-negotiated parameters.
# Kept locally so runtime decoding never reads an external reference checkout.
# Numerical cross-reference: https://ffmpeg.org/doxygen/7.0/adpcm__data_8c.html
IMA_STEP_SIZES=(
    7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,
    55,60,66,73,80,88,97,107,118,130,143,157,173,190,209,230,253,
    279,307,337,371,408,449,494,544,598,658,724,796,876,963,1060,
    1166,1282,1411,1552,1707,1878,2066,2272,2499,2749,3024,3327,
    3660,4026,4428,4871,5358,5894,6484,7132,7845,8630,9493,10442,
    11487,12635,13899,15289,16818,18500,20350,22385,24623,27086,
    29794,32767,
)
IMA_INDEX_ADJUSTMENTS=(-1,-1,-1,-1,2,4,6,8)

def tables():
    return list(IMA_STEP_SIZES),list(IMA_INDEX_ADJUSTMENTS)

class Decoder:
    def __init__(self, high_first=True):
        self.steps,self.indices=tables()
        self.predictor=0; self.index=0; self.high_first=high_first; self.clipped=0
    def nibble(self,n):
        step=self.steps[self.index]
        delta=(step>>3)+(step>>2 if n&1 else 0)+(step>>1 if n&2 else 0)+(step if n&4 else 0)
        raw=self.predictor+(-delta if n&8 else delta)
        self.clipped+=not -32768<=raw<=32767
        self.predictor=max(-32768,min(32767,raw))
        self.index=max(0,min(88,self.index+self.indices[n&7]))
        return self.predictor
    def decode(self,data):
        output=[]
        for byte in data:
            ns=(byte>>4,byte&15) if self.high_first else (byte&15,byte>>4)
            output.extend(self.nibble(n) for n in ns)
        return output

def metrics(samples,clipped):
    if not samples:return {}
    dc=sum(samples)/len(samples)
    rms=math.sqrt(sum((x-dc)**2 for x in samples)/len(samples))
    diff=math.sqrt(sum((b-a)**2 for a,b in zip(samples,samples[1:]))/max(1,len(samples)-1))
    return {'samples':len(samples),'dc':dc,'ac_rms':rms,'clipping_ratio':clipped/len(samples),
            'difference_to_rms':diff/max(rms,1),'peak':max(abs(x) for x in samples)}

def write_wav(path,samples,rate):
    with wave.open(str(path),'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate)
        out.writeframes(struct.pack('<'+'h'*len(samples),*samples))

def analyze(directory,export=False):
    events=[json.loads(s) for s in (directory/'events.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
    events.sort(key=lambda e:e['perf_ns'])
    blob=(directory/'audio-notifications.bin').read_bytes()
    caps=[e for e in events if e['kind']=='capabilities_accepted']
    cap=caps[-1] if caps else None
    if cap is None:raise RuntimeError('No accepted capability response')
    frame=cap['raw_frame_size']
    sessions=[]; current=None
    for e in events:
        if e['kind']=='control' and e.get('hex','').startswith('04 '):
            if current and current['start'].get('kind')=='audio' and abs(e['perf_ns']-current['start']['perf_ns'])<50_000_000:
                # Independent Windows characteristic callbacks can arrive in the opposite order.
                current['audio_preceded_start_callback_ms']=(e['perf_ns']-current['start']['perf_ns'])/1e6
                current['start']=e
            else:
                if current: sessions.append(current)
                current={'start':e,'packets':[],'sync':[],'stop':None}
        elif e['kind']=='control' and e.get('hex','').startswith('0a '):
            if current: current['sync'].append(e)
        elif e['kind']=='control' and e.get('hex','').split(' ')[0]=='00':
            if current: current['stop']=e; sessions.append(current);current=None
        elif e['kind']=='audio':
            if current is None: current={'start':e,'packets':[],'sync':[],'stop':None}
            current['packets'].append(e)
    if current: sessions.append(current)
    result={'capabilities':{k:cap[k] for k in ('version','codec','frame_size','raw_frame_size')},
            'raw_audio_bytes':len(blob),'sessions':[],
            'interpretation':'codec=02 and measured rate support RC003 IMA ADPCM 16k candidate; intelligibility and nibble order require listening'}
    for number,session in enumerate(sessions,1):
        ps=session['packets']
        if not ps:continue
        for p in ps:
            if p['binary_offset']+p['length']>len(blob):raise RuntimeError('Truncated binary evidence')
        data=b''.join(blob[p['binary_offset']:p['binary_offset']+p['length']] for p in ps)
        span=(ps[-1]['perf_ns']-ps[0]['perf_ns'])/1e9
        byte_rate=(len(data)-ps[0]['length'])/span if span>0 else 0
        row={'session_number':number,'start_hex':session['start'].get('hex'),'start_s':session['start']['relative_s'],
             'stop_s':session['stop']['relative_s'] if session['stop'] else None,
             'packets':len(ps),'bytes':len(data),'lengths':dict(Counter(p['length'] for p in ps)),
             'notification_span_s':span,'observed_bytes_per_second':byte_rate,'candidate_4bit_sample_rate':2*byte_rate,
             'sync_messages':[s['hex'] for s in session['sync']], 'candidate_decoders':{}}
        if 'audio_preceded_start_callback_ms' in session:
            row['audio_preceded_start_callback_ms']=session['audio_preceded_start_callback_ms']
        if session['sync']:
            row['export_blocked']='Sync present; offline candidate decoder must implement exact frame-boundary synchronization first'
            result['sessions'].append(row);continue
        for name,high in (('axonkey_high_first',True),('comparison_low_first',False)):
            decoder=Decoder(high)
            decoded=[]
            for offset in range(0,len(data)//frame*frame,frame):
                decoded.extend(decoder.decode(data[offset:offset+frame]))
            score=metrics(decoded,decoder.clipped)
            stable=metrics(decoded[1600:],0) if len(decoded)>1600 else score
            score['stable_dc_to_ac_rms']=abs(stable['dc'])/max(stable['ac_rms'],1)
            row['candidate_decoders'][name]=score
            # Compare nibble order offline, without claiming either is negotiated by codec=02.
            # Reject the strong DC drift observed with an incompatible stream interpretation.
            compatible=(cap['codec']==2 and frame>0 and len(data)%frame==0 and span>=2 and
                        abs(2*byte_rate-16000)/16000<.15 and score.get('clipping_ratio',1)<.01 and
                        score['stable_dc_to_ac_rms']<.5)
            if export and compatible:
                smooth=[]
                for offset in range(0,len(decoded),frame*2):
                    src=decoded[offset:offset+frame*2]; dst=src.copy()
                    for i in range(1,len(src)-1):dst[i]=(src[i-1]+2*src[i]+src[i+1])>>2
                    smooth.extend(dst)
                label='axonkey-high-first' if high else 'ima-low-first'
                path=directory/f'session-{number}-candidate-{label}-16k.wav'
                write_wav(path,smooth,16000)
                row.setdefault('candidate_wavs',{})[name]=str(path.resolve())
                row['candidate_duration_s']=len(smooth)/16000
                row['wav_notice']='Candidate IMA ADPCM with measured nibble-order comparison; pending user intelligibility confirmation; no upload'
        result['sessions'].append(row)
    (directory/'audio-analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('--export-candidate',action='store_true')
    a=p.parse_args()
    print(json.dumps(analyze(a.directory,a.export_candidate),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
