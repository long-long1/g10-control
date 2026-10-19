import type {SetupStatus} from './api';
export function statusLabel(value:string):string{
  return ({not_checked:'未检测',checking:'检测中',passed:'通过',failed:'失败',waiting_user:'待用户操作'} as Record<string,string>)[value]??'待用户操作';
}
export function canFinish(state:SetupStatus):boolean{
  return state.ready&&state.statuses.length===5&&state.statuses.every(value=>value==='passed');
}
