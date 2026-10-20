import type { DeviceSetupStatus } from './api';

export function DevicePanel({state,busy,onScan,onSelect,onCheck}:{state:DeviceSetupStatus;busy:boolean;onScan:()=>void;onSelect:(id:string)=>void;onCheck:()=>void}){
  return <section className="panel settings-panel">
    <div className="panel-head"><div><h3>蓝牙设备发现与兼容性</h3><p>优先读取 Windows 已配对 BLE 设备，再补充附近广播设备。名称和广播服务提示都不代表兼容。</p></div><button className="button outline small" disabled={busy} onClick={onScan}>{busy?'正在处理…':'扫描 / 刷新设备'}</button></div>
    <div className="inline-note"><span>{busy?'设备操作进行中，请等待安全清理完成。':state.message}</span></div>
    {state.candidates.map(item=>{
      const selected=state.selected?.id===item.id;
      const displayName=item.name?(item.name_source==='advertisement'?`${item.name}（广播名称）`:item.name):(item.paired?'已配对 BLE 设备（Windows 未提供名称）':'未命名 BLE 广播设备');
      const windowsState=!item.paired?'未关联 Windows 配对设备':item.connected===true?'Windows 已连接':item.connected===false?'Windows 已配对 · 当前未连接':'Windows 已配对 · 连接状态未知';
      const radioHint=item.advertised_services.length?'本次广播含服务提示':'本次广播无 ATVV 提示，不代表不兼容';
      const result=selected?(state.compatible?'兼容性检查通过':state.state==='failed'?`兼容性检查未通过：${state.message}`:'兼容性尚未验证'):'尚未检查协议兼容性';
      const selectable=item.paired===true&&Boolean(item.winrt_device_id);
      return <div className="action-row device-candidate" key={item.id}>
        <div style={{flex:1,minWidth:0}}><b>{displayName}</b><small>{windowsState} · {item.address||'Windows 未提供地址'}</small><small>{radioHint} · {result}</small></div>
        <button className="button outline small" disabled={busy||!selectable} onClick={()=>onSelect(item.id)}>{selected?'重新选择':selectable?'选择已配对设备':'先在 Windows 配对'}</button>
      </div>;
    })}
    <div className="action-row"><div style={{flex:1,minWidth:0}}><b>当前选择：{state.selected?.name||(state.selected?.paired?'已配对 BLE 设备（无名称）':'未选择')}</b><small>{state.selected?.address||'请扫描并选择 Windows 配对设备'} · {state.compatible?'ATVV 服务、特征及 codec 2 / 128 字节能力已验证':'兼容性尚未通过实际 GATT 与能力检查'}</small></div><button className="button outline small" disabled={busy||!state.selected||state.selected.paired!==true} onClick={onCheck}>检查兼容性</button></div>
    <p>确认检查后，程序会通过保存的 Windows 配对设备 ID 读取 GATT 服务/特征并验证 codec 2 / 128 字节能力；不会仅凭名称或广播提示判定兼容。检查会按现有流程临时订阅通知并发送一次 ATVV 能力请求、随后恢复原订阅，不发送开麦命令。</p>
  </section>;
}
