"""RC003 source-derived command planner. This module has NO Bluetooth transport."""
from dataclasses import dataclass

COMMIT='a8c23b98fc6468013c9647a8b27646e5a9821303'
SERVICE='ab5e0001-5a21-4f05-bc7d-af01f617b664'
TX='ab5e0002-5a21-4f05-bc7d-af01f617b664'
AUDIO='ab5e0003-5a21-4f05-bc7d-af01f617b664'
CONTROL='ab5e0004-5a21-4f05-bc7d-af01f617b664'
CAPABILITIES=bytes.fromhex('0a 01 00 00 03 03')

@dataclass
class Capabilities:
    version:int
    codec:int
    frame_size:int
    raw_frame_size:int
    raw_codec_bits:int

def capabilities(data):
    if len(data)<7 or data[0]!=0x0b:
        raise ValueError('Not a complete RC003-format capabilities response')
    version=int.from_bytes(data[1:3],'big')
    bits=data[3]
    if version>=0x0100 and bits==0 and data[4]&3:
        bits=data[4]
    codec=2 if bits&2 else 1
    raw_frame=int.from_bytes(data[5:7],'big')
    return Capabilities(version,codec,raw_frame or 120,raw_frame,bits)

def mic_open(caps):
    if caps.codec!=2:
        raise ValueError('AxonKey Windows supports codec 0x02 only')
    return bytes.fromhex('0c 00') if caps.version>=0x0100 else bytes([0x0c,0,caps.codec])

def mic_close(version,session_id):
    if not 0<=session_id<=255:
        raise ValueError('Invalid session ID')
    return bytes([0x0d,session_id]) if version>=0x0100 else bytes([0x0d])

def command_plan():
    return {'mode':'PLAN_ONLY_NO_WRITES','commit':COMMIT,'target':TX,
        'commands':[
            {'name':'GET_CAPABILITIES','hex':CAPABILITIES.hex(' '),'source':'windows.rs:623','when':'after AUDIO then CONTROL CCCD success'},
            {'name':'MIC_OPEN v>=1.0','hex':'0c 00','source':'windows.rs:875-890','when':'after valid codec=02 capabilities AND control 08, once per session'},
            {'name':'MIC_OPEN v<1.0','hex':'0c 00 02','source':'windows.rs:875-890','when':'same guard; only negotiated legacy version'},
            {'name':'MIC_CLOSE v>=1.0','hex':'0d SS','source':'windows.rs:673-687','when':'shutdown if microphone_opened or streaming; SS from start message byte 3, default 00'},
            {'name':'MIC_CLOSE v<1.0','hex':'0d','source':'windows.rs:673-687','when':'same shutdown guard, negotiated legacy version'}],
        'note':'Readonly runner never sends business commands; approved exact-command transport is isolated in phase2_handshake.py.'}
