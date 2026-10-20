import type {SetupStatus,Snapshot} from './api';
export function statusLabel(value:string):string{
  return ({not_checked:'未检测',checking:'检测中',passed:'通过',failed:'失败',waiting_user:'待用户操作'} as Record<string,string>)[value]??'待用户操作';
}
export function canFinish(state:SetupStatus):boolean{
  return state.ready&&state.statuses.length===5&&state.statuses.every(value=>value==='passed');
}
export function unavailableSnapshot(state:Snapshot):Snapshot{
  return {...state,
    service:{...state.service,connection:'unknown',detail:'无法读取桌面状态，连接与音频状态未知；请重试或安全停止。',audio_active:false,input_level_dbfs:-120,cable_level_dbfs:-120,cable_peak:0},
    device_setup:{...state.device_setup,compatible:false},
    audio_route:{...state.audio_route,validated:false},
    microphone:{...state.microphone,validated:false,is_active:false},
    setup:{...state.setup,ready:false,completed:false,statuses:Array(5).fill('not_checked')},
  };
}
