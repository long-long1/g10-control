import type {Snapshot} from './api';
import {DevicePanel} from './DevicePanel';
import {RoutePanel} from './RoutePanel';
import {canFinish,statusLabel} from './setup_state';

type Props={state:Snapshot;busy:boolean;onStep:(step:number)=>void;onEnvironment:()=>void;onScan:()=>void;onSelect:(id:string)=>void;onCompatibility:()=>void;onDetectAudio:()=>void;onVerify:()=>void;onFinish:()=>void;onLater:()=>void};
export function SetupWizard(props:Props){
  const {state,busy,onStep,onEnvironment,onScan,onSelect,onCompatibility,onDetectAudio,onVerify,onFinish,onLater}=props;
  const setup=state.setup;
  const labels=['欢迎与运行环境','选择蓝牙设备','检查 VB-CABLE','验证音频路由','完成与使用说明'];
  return <div className="page-stack" data-testid="setup-wizard">
    <section className="panel settings-panel"><div className="panel-head"><div><h2>首次运行向导</h2><p>第 {setup.step+1} / 5 步：{labels[setup.step]}</p></div><button className="button outline small" disabled={busy} onClick={onLater}>稍后继续</button></div>
      <div className="inline-actions">{labels.map((label,index)=><button className="button outline small" disabled={busy} key={label} onClick={()=>onStep(index)}>{index+1}. {label} · {statusLabel(setup.statuses[index]??'not_checked')}</button>)}</div>
      <p>数据保存位置：{setup.data_directory||'等待桌面服务读取'}。{setup.portable?'正在使用便携目录。':'当前使用本机用户数据目录。'}{setup.fallback_reason&&`便携目录无法写入，已回退 LocalAppData。原因：${setup.fallback_reason}`}</p>
    </section>
    {setup.step===0&&<section className="panel settings-panel"><h3>欢迎使用 G10 Control</h3><p>先检测依赖，再选择设备并验证虚拟音频路由。不会自动安装驱动、更改默认音频设备或开启豆包录音。</p><button className="button outline small" disabled={busy} onClick={onEnvironment}>{busy?'正在检测…':'检测 / 重新检测运行环境'}</button>{setup.environment.map(check=><div className="action-row" key={check.name}><div><b>{check.name}：{check.passed?'通过':'失败 / 需处理'}</b><small>{check.detail}</small></div></div>)}</section>}
    {setup.step===1&&<DevicePanel state={state.device_setup} busy={busy||state.service.running} onScan={onScan} onSelect={onSelect} onCheck={onCompatibility}/>}
    {(setup.step===2||setup.step===3)&&<RoutePanel route={state.audio_route} busy={busy||state.service.running} onDetect={onDetectAudio} onVerify={onVerify} allowVerify={setup.step===3}/>}
    {setup.step===4&&<section className="panel settings-panel"><h3>{canFinish(setup)?'关键检查通过，可以完成配置':'尚有关键检查未通过'}</h3><p>{setup.completed?'配置已完成。':'只有环境、设备兼容性和当前路由证明全部通过后才能完成。未检测、失败或证明过期时请返回对应步骤。'}</p><ol><li>在豆包输入法中手动选择 CABLE Output 录音端。</li><li>手动开启豆包语音输入，不由本程序自动开启。</li><li>明确启动 G10 服务后，再按住遥控器红键说话，松开结束。</li></ol><p>退出向导后进度仍保存在本机；重启后会重新确认关键状态。</p></section>}
    <section className="panel settings-panel"><div className="inline-actions"><button className="button outline small" disabled={busy||setup.step===0} onClick={()=>onStep(setup.step-1)}>上一步</button>{setup.step<4?<button className="button primary" disabled={busy} onClick={()=>onStep(setup.step+1)}>下一步</button>:<button className="button primary" disabled={busy||!canFinish(setup)} onClick={onFinish}>完成配置</button>}</div></section>
  </div>;
}
