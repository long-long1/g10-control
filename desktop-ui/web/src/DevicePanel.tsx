import type { DeviceSetupStatus } from './api';

export function DevicePanel({state,busy,onScan,onSelect,onCheck}:{state:DeviceSetupStatus;busy:boolean;onScan:()=>void;onSelect:(id:string)=>void;onCheck:()=>void}){
  return <section className="panel settings-panel">
    <div className="panel-head"><div><h3>蓝牙设备发现与兼容性</h3><p>请先在 Windows 配对 G10。扫描仅在点击按钮后执行，名称和广播服务提示不代表兼容。</p></div><button className="button outline small" disabled={busy} onClick={onScan}>{busy?'正在处理…':'扫描 / 刷新设备'}</button></div>
    <div className="inline-note"><span>{busy?'设备操作进行中，请等待安全清理完成。':state.message}</span></div>
    {state.candidates.map(item=><div className="action-row" key={item.id}><div><b>{item.name||'未命名 BLE 设备'}</b><small>{item.address} · {item.advertised_services.length?'广播包含服务提示，仍需检查':'未提供 ATVV 广播提示'}</small></div><button className="button outline small" disabled={busy} onClick={()=>onSelect(item.id)}>{state.selected?.id===item.id?'重新选择':'选择设备'}</button></div>)}
    <div className="action-row"><div><b>当前选择：{state.selected?.name||'未选择'}</b><small>{state.selected?.address||'请扫描并选择候选设备'} · {state.compatible?'协议兼容性已通过':'尚未通过协议兼容性检查'}</small></div><button className="button outline small" disabled={busy||!state.selected} onClick={onCheck}>检查兼容性</button></div>
    <p>检查会连接选中设备、临时订阅通知并发送一次 ATVV 能力请求；会恢复原订阅，不发送开麦指令。请勿按遥控器红键。当前受控传输仅支持名称为 G10 的已配对设备，仍必须满足服务、特征和 codec 2 / 128 字节能力条件。</p>
  </section>;
}
