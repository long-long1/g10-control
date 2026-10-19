import type {AudioRouteStatus} from './api';
export function RoutePanel({route,busy,onDetect,onVerify,allowVerify=true}:{route:AudioRouteStatus;busy:boolean;onDetect:()=>void;onVerify:()=>void;allowVerify?:boolean}){
  return <section className="panel settings-panel">
    <div className="panel-head"><div><h3>本机 VB-CABLE 路由</h3><p>播放端 CABLE Input 接收合成信号；录音端 CABLE Output 供豆包等软件读取。</p></div><button className="button outline small" disabled={busy} onClick={onDetect}>检测 VB-CABLE</button></div>
    <div className="inline-note"><span>{busy?'正在检测或验证，请等待操作完成。':route.message}</span></div>
    {route.pair&&(['render','capture'] as const).map(role=>{const item=route.pair![role];return <div className="action-row" key={role}><div><b>{role==='render'?'播放端（写入）':'录音端（读取）'}：{item.name}</b><small>{item.id} · {item.samplerate} Hz</small></div></div>;})}
    {allowVerify&&<div className="action-row"><div><b>合成音频路由验证</b><small>确认后才打开虚拟端点，不采集物理麦克风、不保存录音、不修改默认设备；证明有效期 30 天。</small></div><button className="button outline small" disabled={busy||!route.confirmation_token} onClick={onVerify}>确认并验证路由</button></div>}
    <p>状态：{route.validated?'当前端点与有效证明匹配':'尚未通过当前本机路由验证'}。证明位置：{route.proof_path||'实际数据目录内'}。缺失、过期或端点变化时必须重新验证。</p>
  </section>;
}
