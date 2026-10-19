"""Approved RC003-derived ATVV experiment; exact TX UUID, no arbitrary command interface."""
import argparse
import asyncio
from datetime import datetime
from pathlib import Path
import time

from atvv_protocol import TX,AUDIO,CONTROL,CAPABILITIES,capabilities,mic_open,mic_close,COMMIT
from phase2_readonly import run_test,ROOT

class Controller:
    def __init__(self,rec,stop,updates):
        self.rec=rec; self.stop=stop; self.updates=updates
        self.tx=None; self.queue=asyncio.Queue(); self.caps_event=asyncio.Event()
        self.caps=None; self.opened=False; self.streaming=False; self.session_id=0
        self.requested=False; self.opens=0; self.open_deadline=None
        self.last_audio=None; self.last_stop=None; self.closed=False; self.initialized=False
        rec.emit('business_authorization',source='User explicitly agreed in current chat',
                 target=TX,source_commit=COMMIT,allowed='GET_CAPABILITIES, negotiated MIC_OPEN, conditional MIC_CLOSE')

    def bind(self,chars,loop):
        self.tx=chars[TX]
        if str(self.tx.uuid)!=TX or not int(self.tx.characteristic_properties)&4:
            raise RuntimeError('Exact TX UUID with WRITE_WITHOUT_RESPONSE is required')

    def receive(self,key,data,perf):
        if self.closed: return
        if key==AUDIO:
            if data:
                self.last_audio=perf
                recent_stop=self.last_stop is not None and perf-self.last_stop<300_000_000
                if self.caps and not recent_stop:
                    self.streaming=True; self.open_deadline=None
            return
        if key!=CONTROL or not data: return
        try:
            op=data[0]
            if op==0x0b:
                if not self.requested:
                    raise RuntimeError('Unsolicited capabilities before our single request')
                parsed=capabilities(data)
                if parsed.codec!=2 or parsed.raw_frame_size==0 or parsed.raw_frame_size>4096:
                    raise RuntimeError('Unsupported/ambiguous capability response; refusing MIC_OPEN')
                if self.caps is not None and self.caps!=parsed:
                    raise RuntimeError('Capabilities changed during test')
                self.caps=parsed; self.caps_event.set()
                self.rec.emit('capabilities_accepted',**vars(parsed),interpretation='RC003 source layout; G10 codec semantics to be verified')
            elif op==0x08:
                if self.caps is None or not self.initialized or self.opened or self.streaming:
                    self.rec.emit('trigger_ignored',reason='not ready or session already active')
                else:
                    if self.opens>=3:
                        raise RuntimeError('Three-session experiment limit reached')
                    self.opened=True; self.opens+=1; self.session_id=0
                    self.open_deadline=time.monotonic()+5
                    self.queue.put_nowait(('MIC_OPEN',mic_open(self.caps)))
            elif op==0x04:
                # RC003 accepts START after capabilities even without a preceding host OPEN.
                # Keep a documented conservative length check, without inventing an OPEN prerequisite.
                if self.caps is None or len(data)<3 or data[2]!=2:
                    raise RuntimeError('Unexpected/truncated/unsupported START response')
                self.session_id=data[3] if len(data)>=4 else 0
                self.streaming=True
                self.open_deadline=time.monotonic()+5
                self.last_audio=None
                self.rec.emit('stream_start',session_id=self.session_id,preceded_by_host_open=self.opened)
            elif op==0x00:
                self.rec.emit('stream_stop',session_id=self.session_id)
                self.streaming=False; self.opened=False; self.open_deadline=None
                self.last_stop=perf
                self.last_audio=None
            elif op==0x0a:
                if len(data)>=7:
                    self.rec.emit('codec_sync_candidate',predictor=int.from_bytes(data[4:6],'big',signed=True),
                                  step_index=data[6])
            else:
                self.rec.emit('unhandled_control',hex=data.hex(' '),interpretation='unknown, no speculative response')
        except Exception as exc:
            self.rec.errors.append(repr(exc)); self.rec.emit('protocol_error',error=repr(exc)); self.stop.set()
            self.caps_event.set()

    async def send(self,name,data):
        # Only this whitelist can reach the one bound characteristic. No arbitrary write command option.
        allowed={'GET_CAPABILITIES':CAPABILITIES}
        if self.caps:
            allowed.update(MIC_OPEN=mic_open(self.caps),MIC_CLOSE=mic_close(self.caps.version,self.session_id))
        if name not in allowed or data!=allowed[name] or str(self.tx.uuid)!=TX:
            raise RuntimeError('Command rejected by exact-byte whitelist')
        from winrt.windows.storage.streams import DataWriter
        from winrt.windows.devices.bluetooth.genericattributeprofile import GattWriteOption
        writer=DataWriter()
        try:
            writer.write_bytes(data)
            buffer=writer.detach_buffer()
            self.rec.emit('tx_attempt',name=name,uuid=TX,hex=data.hex(' '),mode='WRITE_WITHOUT_RESPONSE')
            status=await asyncio.wait_for(self.tx.write_value_with_option_async(buffer,GattWriteOption.WRITE_WITHOUT_RESPONSE),5)
            self.rec.emit('tx_result',name=name,status=int(status))
            if int(status)!=0:
                raise RuntimeError(f'{name} returned GATT status {status}')
        finally:
            writer.close()

    async def initialize(self):
        self.updates.put('正在发送已授权的单次能力请求；暂时不要按红键。')
        self.requested=True
        await self.send('GET_CAPABILITIES',CAPABILITIES)
        try:
            await asyncio.wait_for(self.caps_event.wait(),10)
        except TimeoutError:
            raise RuntimeError('No supported capabilities within 10 seconds; no retry or MIC_OPEN')
        if self.stop.is_set() or self.caps is None:
            raise RuntimeError('Capability negotiation failed; no MIC_OPEN')
        self.initialized=True
        self.updates.put(f'能力响应已收到：版本 {self.caps.version:#06x}，codec {self.caps.codec:#04x}，帧长字段 {self.caps.frame_size}。')

    async def tick(self):
        while not self.queue.empty() and not self.stop.is_set():
            name,data=self.queue.get_nowait()
            # Ignore a queued OPEN if a STOP overtook it before the loop could send it.
            if name=='MIC_OPEN' and not self.opened:
                self.rec.emit('tx_skipped',name=name,reason='STOP arrived before queued OPEN'); continue
            await self.send(name,data)
        if self.open_deadline is not None and time.monotonic()>self.open_deadline:
            raise RuntimeError('No audio within 5 seconds after OPEN; ending without retry')
        if self.streaming and self.last_audio and time.perf_counter_ns()-self.last_audio>5_000_000_000:
            raise RuntimeError('Audio stalled for 5 seconds; ending without retry')

    async def close(self):
        self.closed=True
        if self.caps and (self.opened or self.streaming):
            await self.send('MIC_CLOSE',mic_close(self.caps.version,self.session_id))
            self.rec.emit('close_attempted',session_id=self.session_id,note='GATT success is not a device acknowledgement')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--business-approval',action='store_true',help='Requires prior explicit approval of the exact documented commands')
    p.add_argument('--allow-cccd',action='store_true')
    p.add_argument('--address',default=__import__('local_config').address())
    p.add_argument('--max-seconds',type=int,default=600)
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    if not args.business_approval or not args.allow_cccd:
        p.error('Both explicit business-command and notification-descriptor approval required; no BLE access')
    args.address=__import__('local_config').require_address(args.address)
    if args.address!=__import__('local_config').require_address():
        p.error('This approval is limited to the identified G10 address')
    args.output=args.output or ROOT/'output'/('phase2-handshake-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    run_test(args,Controller)

if __name__=='__main__': main()
