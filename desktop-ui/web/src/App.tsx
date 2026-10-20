import { useCallback, useEffect, useMemo, useState, type ChangeEvent } from 'react';
import {
  AudioLines, AudioWaveform, Bluetooth, Check, ChevronRight, CircleHelp, CircleStop,
  ClipboardList, Download, FileUp, Home, Keyboard,
  ListFilter, Mic2, Moon, MoreHorizontal, Power, Radio, RefreshCw, RotateCcw,
  Settings2, ShieldCheck, Sparkles, TriangleAlert, Volume2, WandSparkles,
} from 'lucide-react';
import { nativeAPI, type EventRow, type KeySnapshot, type Settings, type Snapshot } from './api';
import { DevicePanel } from './DevicePanel';
import { SetupWizard } from './SetupWizard';
import { RoutePanel } from './RoutePanel';

type Page = 'home' | 'voice' | 'keys' | 'settings' | 'logs';
const DEFAULT_CABLE = '';
const starterSettings: Settings = {
  schema_version:1,
  voice:{auto_wake_doubao:false,virtual_microphone_id:DEFAULT_CABLE,gain_db:0},
  behavior:{close_to_tray:true,auto_reconnect:false},
  key_detection:{target_address:''},
};

const emptySnapshot: Snapshot = {
  application:{name:'G10 Control',version:'0.1.0-beta',single_instance:true},
  service:{running:false,connection:'stopped',detail:'等待启动',started_at:null,audio_active:false,processed_audio_seconds:0,input_level_dbfs:-120,cable_level_dbfs:-120,cable_peak:0,error_count:0,error:null},
  device:{name:'未选择设备',address:'',transport:'Bluetooth LE',vid:null,pid:null,battery:null},
  device_setup:{state:'not_checked',message:'请扫描并选择设备；兼容性尚未验证。',selected:null,compatible:false,candidates:[],busy:false},
  setup:{step:0,completed:false,ready:false,statuses:Array(5).fill('not_checked'),environment:[],data_directory:'',portable:false,fallback_reason:null},
  shell:{key_observer_available:false,key_observer_reason:'等待桌面服务读取；Portable 不提供按键观察。',nonbusiness:false},
  startup:{enabled:false,repair_needed:false},
  microphone:{name:'CABLE Output (VB-Audio Virtual Cable)',id:DEFAULT_CABLE,validated:false,is_active:false},
  audio_route:{state:'missing',message:'请检测本机 VB-CABLE 并确认合成验证。',validated:false,pair:null,verified_at:null,proof_path:'',confirmation_token:null},
  settings:starterSettings,runtime:{log_directory:'',service_log_directory:null},
};

const pages:{id:Page;label:string;icon:typeof Home}[]=[
  {id:'home',label:'设备主页',icon:Home},{id:'voice',label:'语音设置',icon:AudioWaveform},
  {id:'keys',label:'按键映射',icon:Keyboard},{id:'settings',label:'软件设置',icon:Settings2},
];

function Toggle({checked,onChange,disabled=false}:{checked:boolean;onChange:()=>void;disabled?:boolean}){
  return <button type="button" role="switch" aria-checked={checked} disabled={disabled} onClick={onChange} className={`toggle ${checked?'on':''}`}><span/></button>;
}
function Meter({value,label}:{value:number;label:string}){
  const width=Math.max(0,Math.min(100,(value+60)/60*100));
  return <div className="meter-wrap"><div className="meter-label"><span>{label}</span><span>{value<=-119?'静音':`${value.toFixed(1)} dBFS`}</span></div><div className="meter-track"><span style={{width:`${width}%`}}/></div></div>;
}
function IconButton({label,onClick,children}:{label:string;onClick:()=>void;children:React.ReactNode}){
  return <button className="icon-button" type="button" title={label} aria-label={label} onClick={onClick}>{children}</button>;
}

export default function App(){
  const [page,setPage]=useState<Page>('home');
  const [state,setState]=useState<Snapshot>(emptySnapshot);
  const [logs,setLogs]=useState<EventRow[]>([]);
  const [keyState,setKeyState]=useState<KeySnapshot>({running:false,device_filter:'',events:[]});
  const [autostart,setAutostart]=useState(false);
  const [connectedToHost,setConnectedToHost]=useState(false);
  const [busy,setBusy]=useState(false);
  const [wizardOpen,setWizardOpen]=useState<boolean|null>(null);
  const [toast,setToast]=useState('');
  const [exitError,setExitError]=useState('');
  const api=nativeAPI();
  const settings=state.settings;
  const pageInfo=pages.find(item=>item.id===page);

  const refresh=useCallback(async()=>{
    const bridge=nativeAPI();
    if(!bridge)return;
    try{
      const next=await bridge.get_status();
      setState(next);setConnectedToHost(true);
      if(page==='logs'||page==='voice')setLogs(await bridge.get_logs());
      if(page==='keys')setKeyState(await bridge.get_key_events());
    }catch(error){setToast(error instanceof Error?error.message:'无法读取本地设备状态');}
  },[page]);

  useEffect(()=>{
    const attach=()=>{
      setConnectedToHost(Boolean(nativeAPI()));
      void refresh();
      void nativeAPI()?.get_autostart().then(setAutostart).catch(()=>undefined);
    };
    if(nativeAPI())attach();
    window.addEventListener('pywebviewready',attach);
    const timer=window.setInterval(()=>void refresh(),1000);
    window.g10SetExitError=(message)=>setExitError(message);
    return()=>{window.removeEventListener('pywebviewready',attach);window.clearInterval(timer);delete window.g10SetExitError;};
  },[refresh]);

  useEffect(()=>{if(!toast)return;const timer=window.setTimeout(()=>setToast(''),3200);return()=>window.clearTimeout(timer);},[toast]);

  const liveMode=state.service.connection==='connected';
  const latestVoiceError=useMemo(()=>logs.find(row=>row.kind==='doubao_voice_error'),[logs]);

  async function changeSettings(next:Settings,message='设置已保存'){
    const bridge=nativeAPI();setState(current=>({...current,settings:next}));
    if(!bridge){setToast('设置在本地预览中，桌面版打开后可保存。');return;}
    try{const saved=await bridge.save_settings(next);setState(current=>({...current,settings:saved}));setToast(message);}
    catch(error){setToast(error instanceof Error?error.message:'设置保存失败');void refresh();}
  }
  async function startBridge(){
    if(!api)return setToast('桌面服务尚未连接。');
    setBusy(true);setExitError('');
    try{await api.start_service();setToast('正在连接 G10…');await refresh();}
    catch(error){setToast(error instanceof Error?error.message:'蓝牙服务启动失败');}
    finally{setBusy(false);}
  }
  async function deviceAction(action:'scan'|'select'|'check',identity=''){
    if(!api)return setToast('设备操作需要运行桌面版。');
    if(action==='check'&&!window.confirm('将连接选中的已配对设备，检查 ATVV 服务/特征，临时订阅通知并发送一次能力请求，随后恢复订阅。不会发送开麦命令。请勿按红键。是否继续？'))return;
    setBusy(true);
    try{
      const result=action==='scan'?await api.scan_ble_devices():action==='select'?await api.select_ble_device(identity):await api.check_ble_compatibility(true);
      setToast(result.message);await refresh();
    }catch(error){setToast(error instanceof Error?error.message:'设备操作失败');}
    finally{setBusy(false);}
  }
  async function setupAction(action:'environment'|'step'|'finish',step=0){
    if(!api)return setToast('向导需要运行桌面版。');
    setBusy(true);
    try{
      if(action==='environment')await api.detect_environment();
      else if(action==='step')await api.set_setup_step(step);
      else {await api.complete_setup();setWizardOpen(false);setToast('本机配置完成，请按说明手动使用豆包语音。');}
      await refresh();
    }catch(error){setToast(error instanceof Error?error.message:'向导操作失败');}
    finally{setBusy(false);}
  }
  async function stopBridge(){
    if(!api)return;
    setBusy(true);
    try{await api.stop_service();setToast('服务已安全停止');await refresh();}
    catch(error){setToast(error instanceof Error?error.message:'安全停止失败');}
    finally{setBusy(false);}
  }
  async function changeAutoWake(){
    const enabled=!settings.voice.auto_wake_doubao;
    const next={...settings,voice:{...settings.voice,auto_wake_doubao:enabled}};
    const bridge=nativeAPI();
    if(!bridge){await changeSettings(next,'设置已更新；桌面版打开后会保存。');return;}
    setBusy(true);
    try{
      const saved=await bridge.save_settings(next);setState(current=>({...current,settings:saved}));
      if(state.service.running){
        await bridge.stop_service();
        await bridge.start_service();
        setToast(enabled?'已启用自动唤起诊断模式，正在重新连接 G10。':'已切回手动模式，正在重新连接 G10。');
      }else setToast(enabled?'自动唤起试验版已启用，下次连接 G10 时生效。':'已切回手动唤起。');
      await refresh();
    }catch(error){setToast(error instanceof Error?error.message:'切换唤起方式失败；请检查服务状态。');await refresh();}
    finally{setBusy(false);}
  }
  async function changeGain(gain_db:number){
    await changeSettings({...settings,voice:{...settings.voice,gain_db}},'增益已保存；下次启动服务时生效。');
  }
  async function checkMicrophone(){
    if(!api)return setToast('本机端点检测需运行桌面版。');
    setBusy(true);
    try{const route=await api.detect_audio_route();setToast(route.message);await refresh();}
    catch(error){setToast(error instanceof Error?error.message:'音频设备枚举失败');}
    finally{setBusy(false);}
  }
  async function verifyRoute(){
    const route=state.audio_route;
    if(!api||!route.confirmation_token||!route.pair)return setToast('请先检测本机 VB-CABLE。');
    if(!window.confirm(`将仅打开检测到的播放端 ${route.pair.render.name} 和录音端 ${route.pair.capture.name}，使用 48000 Hz 双声道共享模式。\n\n发送约 1.48 秒低幅度合成信号，短时读取虚拟录音端（最多 6 秒），不读取物理麦克风、不保存录音、不更改默认设备。\n\n请先停止其他程序向 VB-CABLE 发送真实麦克风或私人音频。确认开始？`))return;
    setBusy(true);
    try{const result=await api.verify_audio_route(route.confirmation_token,true);setToast(result.message);}
    catch(error){setToast(error instanceof Error?error.message:'合成路由验证失败');}
    finally{await refresh();setBusy(false);}
  }
  async function toggleKeyDetection(){
    if(!api)return setToast('只读按键检测需运行桌面版。');
    try{
      if(keyState.running)await api.stop_key_detection();else await api.start_key_detection();
      setKeyState(await api.get_key_events());
      setToast(keyState.running?'按键观察已停止':'只读观察已启动，只监控指定的 G10 设备。');
    }catch(error){setToast(error instanceof Error?error.message:'按键观察启动失败');}
  }
  async function setLogin(enabled:boolean){
    if(!api){setToast('登录启动设置需运行桌面版。');return;}
    if(enabled&&!window.confirm('G10 Control 将在当前 Windows 用户登录时自动启动，并写入该用户的启动项。继续吗？'))return;
    try{setAutostart(await api.set_autostart(enabled,enabled));setToast(enabled?'已启用登录后启动':'已关闭登录后启动');}
    catch(error){setToast(error instanceof Error?error.message:'启动设置更新失败');}
  }
  async function exportSettings(){
    if(!api)return setToast('配置导出需运行桌面版。');
    try{const result=await api.save_diagnostics(JSON.stringify(JSON.parse(await api.export_settings()),null,2));if(result.saved)setToast('配置已导出到所选路径');}
    catch(error){setToast(error instanceof Error?error.message:'配置导出失败');}
  }
  async function exportDiagnostics(){
    if(!api)return setToast('诊断报告导出需运行桌面版。');
    try{const result=await api.save_diagnostics(JSON.stringify(await api.get_diagnostics(),null,2));if(result.saved)setToast(`诊断报告已保存：${result.path}`);}
    catch(error){setToast(error instanceof Error?error.message:'诊断报告导出失败');}
  }
  async function importSettings(event:ChangeEvent<HTMLInputElement>){
    const file=event.currentTarget.files?.[0];event.currentTarget.value='';if(!file||!api)return;
    try{const result=await api.import_settings(await file.text());setState(current=>({...current,settings:result}));setToast('配置已导入；Windows 启动项仍保持原值。');}
    catch(error){setToast(error instanceof Error?error.message:'配置导入失败');}
  }
  async function resetSettings(){
    if(!api||!window.confirm('恢复 G10 Control 应用内默认设置？Windows 默认设备与输入法配置不会更改。'))return;
    try{const result=await api.reset_settings();setState(current=>({...current,settings:result}));setToast('已恢复应用内默认设置');}
    catch(error){setToast(error instanceof Error?error.message:'恢复设置失败');}
  }
  async function exitApplication(){
    if(!api)return;
    setBusy(true);setExitError('正在安全关闭蓝牙服务…');
    try{await api.request_exit();}
    catch(error){setExitError(error instanceof Error?error.message:'无法安全退出');setBusy(false);}
  }

  const settingSwitch=(key:'auto_wake_doubao'|'close_to_tray')=>{
    if(key==='auto_wake_doubao')void changeAutoWake();
    else void changeSettings({...settings,behavior:{...settings.behavior,close_to_tray:!settings.behavior.close_to_tray}},'关闭窗口行为已更新。');
  };

  return <div className="app-frame">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><AudioWaveform size={21}/></div><div><strong>G10 <span>Control</span></strong><small>REMOTE CONSOLE</small></div></div>
      <div className="nav-group-label">设备管理</div>
      <nav className="side-nav" aria-label="主导航">
        <button className="nav-item" onClick={()=>setWizardOpen(true)}><ClipboardList size={18}/><span>设置向导 / 继续</span></button>
        {pages.map(item=>{const Icon=item.icon;return <button key={item.id} className={`nav-item ${page===item.id?'active':''}`} onClick={()=>{setWizardOpen(false);setPage(item.id);}}><Icon size={18}/><span>{item.label}</span>{item.id==='keys'&&<span className="nav-pill">只读</span>}</button>;})}
        <button className={`nav-item ${page==='logs'?'active':''}`} onClick={()=>{setWizardOpen(false);setPage('logs');}}><ClipboardList size={18}/><span>日志与诊断</span></button>
      </nav>
      <div className="sidebar-spacer"/>
      <div className="sidebar-device">
        <div className="sidebar-device-top"><span className={`status-dot ${liveMode?'good':state.service.connection==='starting'?'pending':''}`}/><span>{liveMode?'G10 已连接':state.service.connection==='starting'?'正在连接':'服务已停止'}</span><MoreHorizontal size={17}/></div>
        <div className="side-device-name"><span className="mini-remote"><Radio size={18}/></span><div><b>{state.device.name}</b><small>Bluetooth LE</small></div></div>
      </div>
      <div className="sidebar-footer"><span className="avatar">G</span><div><b>本机设备</b><small>数据保存在本地</small></div><button className="plain-icon" onClick={()=>setPage('settings')} aria-label="打开软件设置"><Settings2 size={16}/></button></div>
    </aside>

    <main className="main-area">
      <header className="topbar">
        <div><div className="breadcrumbs">G10 Control <ChevronRight size={13}/><span>{pageInfo?.label??'日志与诊断'}</span></div><h1>{pageInfo?.label??'日志与诊断'}</h1></div>
        <div className="topbar-right">
          <div className={`connection-chip ${liveMode?'connected':state.service.connection==='starting'?'connecting':''}`}><span className="status-dot"/>{liveMode?'蓝牙已连接':state.service.connection==='starting'?'连接中':'未连接'}</div>
          <IconButton label="刷新状态" onClick={()=>void refresh()}><RefreshCw size={17}/></IconButton>
          <button className="user-chip" aria-label="关于 G10 Control" onClick={()=>setPage('settings')}><span className="avatar">G</span><ChevronRight size={14}/></button>
        </div>
      </header>

      <div className="page-scroll">
        {(wizardOpen??!state.setup.completed)?<SetupWizard state={state} busy={busy} onStep={step=>void setupAction('step',step)} onEnvironment={()=>void setupAction('environment')} onScan={()=>void deviceAction('scan')} onSelect={id=>void deviceAction('select',id)} onCompatibility={()=>void deviceAction('check')} onDetectAudio={()=>void checkMicrophone()} onVerify={()=>void verifyRoute()} onFinish={()=>void setupAction('finish')} onLater={()=>setWizardOpen(false)}/>:<>
        {page==='home'&&<><DevicePanel state={state.device_setup} busy={busy||state.service.running} onScan={()=>void deviceAction('scan')} onSelect={id=>void deviceAction('select',id)} onCheck={()=>void deviceAction('check')}/><HomePage state={state} busy={busy} onStart={()=>void startBridge()} onStop={()=>void stopBridge()} onPage={setPage} onExit={()=>void exitApplication()}/></>}
        {page==='voice'&&<VoicePage state={state} busy={busy} gain={settings.voice.gain_db} onAuto={()=>void changeAutoWake()} onGain={changeGain} onCheck={()=>void checkMicrophone()} onVerify={()=>void verifyRoute()} latestError={latestVoiceError}/>}
        {page==='keys'&&<KeysPage state={keyState} available={state.shell.key_observer_available} reason={state.shell.key_observer_reason} onToggle={()=>void toggleKeyDetection()}/>}
        {page==='settings'&&(state.startup.repair_needed||state.startup.error)&&<section className="panel settings-panel"><p>{state.startup.error||'程序目录已移动或启动命令不匹配；现有 Windows 启动项需要修复。'}</p>{state.startup.repair_needed&&<button className="button outline small" onClick={()=>void setLogin(true)}>确认修复启动路径</button>}</section>}
        {page==='settings'&&<SettingsPage settings={settings} autostart={autostart} connected={connectedToHost} onAutostart={setLogin} onCloseChange={()=>settingSwitch('close_to_tray')} onChangeReconnect={()=>void changeSettings({...settings,behavior:{...settings.behavior,auto_reconnect:!settings.behavior.auto_reconnect}},'重连偏好已保存。')} onExport={()=>void exportSettings()} onImport={importSettings} onReset={()=>void resetSettings()} onReport={()=>void exportDiagnostics()} onExit={()=>void exitApplication()} error={exitError}/>}
        {page==='logs'&&<LogsPage rows={logs} path={state.runtime.service_log_directory} onRefresh={()=>void refresh()} onExport={()=>void exportDiagnostics()}/>}
        </>}
      </div>
      <footer className="statusbar"><div><span className="status-dot good"/>本地运行 <span className="status-sep">·</span> 蓝牙、语音与按键数据不会上传</div><div>G10 Control <span className="status-sep">·</span> v{state.application.version}</div></footer>
      {toast&&<div className="toast"><Check size={16}/>{toast}</div>}
      {!connectedToHost&&<div className="host-warning"><CircleHelp size={16}/>桌面服务尚未连接，当前为界面预览，不执行检测。</div>}
    </main>
  </div>;
}

export function HomePage({state,busy,onStart,onStop,onPage,onExit}:{state:Snapshot;busy:boolean;onStart:()=>void;onStop:()=>void;onPage:(page:Page)=>void;onExit:()=>void}){
  const live=state.service.connection==='connected';
  const connecting=state.service.connection==='starting';
  return <div className="content-grid">
    <section className="hero-card">
      <div className="hero-copy"><div className="eyebrow"><span className={`status-dot ${live?'good':connecting?'pending':''}`}/>{live?'已连接 · BLE 服务就绪':connecting?'正在连接设备':'G10 控制台'}</div><h2>{live?'遥控器已准备好':connecting?'正在寻找 G10 遥控器':'管理你的 G10 遥控器'}</h2><p>{live?'语音链路就绪，按住红键说话即可将声音送入虚拟麦克风。':connecting?'正在读取 GATT 服务并建立 ATVV 音频通知。':'连接后即可通过红键使用麦克风语音输入。'}</p>
        <div className="hero-actions">{live?<button className="button secondary" onClick={onStop} disabled={busy}><CircleStop size={16}/>{busy?'正在安全停止…':'安全停止服务'}</button>:<button className="button primary" onClick={onStart} disabled={busy}><Bluetooth size={16}/>{busy?'正在启动…':connecting?'重新连接 G10':'连接 G10'}</button>}<button className="button text-button" onClick={()=>onPage('voice')}><Mic2 size={16}/>语音设置<ChevronRight size={14}/></button></div>
        <div className="hero-meta"><span><span className="tiny-dot green"/>声音仅在本机处理</span><span><span className="tiny-dot violet"/>不修改默认麦克风</span></div>
      </div>
      <div className="hero-visual" aria-hidden="true"><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="signal-ring"><AudioWaveform size={54} strokeWidth={1.35}/></div><div className="orbit-node node-a"><Bluetooth size={14}/></div><div className="orbit-node node-b"><Mic2 size={14}/></div><div className="orbit-node node-c"><Volume2 size={14}/></div><span className="visual-glow"/></div>
      <div className="hero-legend"><span>G10</span><span className="legend-line"/><span>ATVV</span><span className="legend-line"/><span>CABLE</span></div>
    </section>

    <section className="device-card panel">
      <div className="panel-head"><div><span className="section-kicker">CONNECTED DEVICE</span><h3>设备信息</h3></div><span className={`badge ${live?'badge-green':'badge-muted'}`}>{live?'在线':connecting?'连接中':state.device_setup.compatible?'兼容性已验证':state.device_setup.selected?'待验证兼容性':'未选择设备'}</span></div>
      <div className="device-profile"><div className="remote-art"><div className="remote-top"/><div className="remote-pad"><span/><i/><b/></div><div className="remote-btns"><i/><i/><i/></div><div className="remote-mic"/></div><div className="profile-name"><b>{state.device.name}</b><small>{state.device.transport} · {state.device_setup.message}</small></div></div>
      <div className="device-facts"><Fact label="蓝牙地址" value={state.device.address}/><Fact label="VID / PID" value={state.device.vid&&state.device.pid?`${state.device.vid} / ${state.device.pid}`:'未检测 / 不适用'}/><Fact label="连接类型" value="Bluetooth Low Energy"/><Fact label="电量" value={state.device.battery===null?'设备未提供已验证数据':`${state.device.battery}%`}/></div>
      <div className="device-footer"><div className="service-indicator"><span className={`status-dot ${live?'good':connecting?'pending':''}`}/><span>{state.service.detail}</span></div><button className="inline-link" onClick={()=>onPage('logs')}>查看状态日志<ChevronRight size={14}/></button></div>
    </section>

    <section className="voice-card panel">
      <div className="panel-head"><div><span className="section-kicker">VOICE INPUT</span><h3>麦克风语音</h3></div><button className="circle-nav" onClick={()=>onPage('voice')} aria-label="语音设置"><ChevronRight size={17}/></button></div>
      <div className="voice-route"><div className="route-icon"><Mic2 size={21}/></div><div className="route-copy"><b>{state.service.audio_active?'正在接收遥控器声音':'G10 麦克风通道'}</b><small>{state.microphone.name}</small></div><span className={`badge ${state.service.audio_active?'badge-green':'badge-muted'}`}>{state.service.audio_active?'输入中':state.microphone.validated?'路由已验证':'待验证路由'}</span></div>
      <Meter value={state.service.cable_level_dbfs} label="虚拟麦克风电平"/>
      <div className="voice-stats"><span><AudioLines size={14}/>{state.service.processed_audio_seconds.toFixed(1)} 秒已解码</span><span><ShieldCheck size={14}/>{state.microphone.validated?'本机路由已验证':'本机路由待验证'}</span></div>
    </section>

    <section className="quick-card panel"><div className="panel-head"><div><span className="section-kicker">QUICK ACCESS</span><h3>快捷入口</h3></div></div><div className="quick-links"><QuickLink icon={<AudioWaveform size={18}/>} title="语音设置" detail="麦克风与唤起方式" onClick={()=>onPage('voice')}/><QuickLink icon={<Keyboard size={18}/>} title="按键检测" detail="仅监听 G10 原始报告" onClick={()=>onPage('keys')}/><QuickLink icon={<ClipboardList size={18}/>} title="诊断日志" detail="连接与音频状态" onClick={()=>onPage('logs')}/></div></section>
    <div className="home-hint"><Sparkles size={15}/><span>当前豆包工作流：在豆包输入法中选择 CABLE Output，手动唤起语音后按住 G10 红键。</span><button onClick={onExit}>退出应用</button></div>
  </div>;
}

function Fact({label,value}:{label:string;value:string}){return <div className="device-fact"><span>{label}</span><b>{value}</b></div>}
function QuickLink({icon,title,detail,onClick}:{icon:React.ReactNode;title:string;detail:string;onClick:()=>void}){return <button className="quick-link" onClick={onClick}><span className="quick-icon">{icon}</span><span><b>{title}</b><small>{detail}</small></span><ChevronRight size={16}/></button>}

function VoicePage({state,busy,gain,onAuto,onGain,onCheck,onVerify,latestError}:{state:Snapshot;busy:boolean;gain:number;onAuto:()=>void;onGain:(gain:number)=>void;onCheck:()=>void;onVerify:()=>void;latestError:EventRow|undefined}){
  const [localGain,setLocalGain]=useState(gain);
  useEffect(()=>setLocalGain(gain),[gain]);
  return <div className="page-stack">
    <div className="page-intro"><div><div className="section-kicker">VOICE PIPELINE</div><p>选择虚拟麦克风并控制红键行为。音频仍由已验证的本地桥接服务传输。</p></div><span className="badge badge-blue"><ShieldCheck size={13}/>本机处理</span></div>
    <RoutePanel route={state.audio_route} busy={busy||state.service.running} onDetect={onCheck} onVerify={onVerify}/>

    <section className="panel settings-panel"><div className="panel-head"><div><h3>红键自动唤起豆包输入法</h3><p>自动唤起尚未通过本机实测，当前开关仅用于诊断。</p></div><Toggle checked={state.settings.voice.auto_wake_doubao} onChange={onAuto}/></div>
      <div className={`auto-state ${state.settings.voice.auto_wake_doubao?'auto-experimental':''}`}><span className={`state-icon ${state.settings.voice.auto_wake_doubao?'amber':'teal'}`}>{state.settings.voice.auto_wake_doubao?<WandSparkles size={17}/>:<Keyboard size={17}/>}</span><div><b>{state.settings.voice.auto_wake_doubao?'诊断模式已开启，自动唤起尚未成功':'手动唤起已验证'}</b><small>实体右 Alt 可以打开豆包录音，但已测试的程序按键和按钮消息尚未可靠唤起豆包。关闭此项后可继续手动开启豆包语音，使用已经验证的 G10 → CABLE Output 音频桥接。</small></div><span className="badge badge-muted">{state.settings.voice.auto_wake_doubao?'实测未通过':'手动模式'}</span></div>
      {latestError&&<div className="warning-note"><TriangleAlert size={15}/><span>上一次自动唤起失败：{String(latestError.error??'详见本机日志')}。可关闭自动唤起后继续手动使用。</span></div>}
      <div className="setting-divider"/><div className="range-heading"><div><b>遥控器麦克风增益</b><small>只调整 G10 解码音频，不改变系统输入或播放音量。</small></div><span className="gain-value">{localGain>0?'+':''}{localGain} dB</span></div>
      <div className="range-input"><span>-30 dB</span><input type="range" min={-30} max={30} step={1} value={localGain} onChange={event=>setLocalGain(Number(event.target.value))} onPointerUp={()=>void onGain(localGain)} onKeyUp={()=>void onGain(localGain)}/><span>+30 dB</span></div>
    </section>

    <section className="panel level-panel"><div><div className="section-kicker">LIVE AUDIO</div><h3>音频状态</h3><p>服务运行时可观察解码和虚拟麦克风电平。</p></div><div className="live-levels"><Meter value={state.service.input_level_dbfs} label="G10 解码输入"/><Meter value={state.service.cable_level_dbfs} label="CABLE Output 实读"/></div><div className="level-foot"><span className={`status-dot ${state.service.running?'good':''}`}/>{state.service.running?'服务正在后台运行': '启动服务后显示实时电平'}<span>{state.service.processed_audio_seconds.toFixed(1)} 秒已处理</span></div></section>
  </div>;
}

function KeysPage({state,available,reason,onToggle}:{state:KeySnapshot;available:boolean;reason:string;onToggle:()=>void}){
  const known=[
    {name:'电源键',detail:'顶部红色电源图标',status:'待检测'},
    {name:'播放 / 暂停',detail:'左上媒体键',status:'待检测'},
    {name:'指针 / 返回',detail:'右上图标键',status:'待检测'},
    {name:'方向上',detail:'圆环上方向键',status:'待检测'},
    {name:'方向左',detail:'圆环左方向键',status:'待检测'},
    {name:'确认键',detail:'圆环中央 OK 键',status:'待检测'},
    {name:'方向右',detail:'圆环右方向键',status:'待检测'},
    {name:'方向下',detail:'圆环下方向键',status:'待检测'},
    {name:'主页',detail:'房屋图标键',status:'待检测'},
    {name:'菜单 / 列表',detail:'中间下排功能键',status:'待检测'},
    {name:'菜单',detail:'三横线图标键',status:'待检测'},
    {name:'PAGE + / −',detail:'左侧翻页键',status:'待检测'},
    {name:'红色麦克风键',detail:'ATVV 会话通知已观察；HID 功能仍保留原行为',status:'已观察'},
    {name:'VOL + / −',detail:'右侧音量键',status:'待检测'},
    {name:'删除键',detail:'DEL',status:'待检测'},
    {name:'静音键',detail:'扬声器静音图标',status:'待检测'},
  ];
  return <div className="page-stack">
    <div className="page-intro"><div><div className="section-kicker">INPUT INSPECTOR</div><p>监听 Windows Raw Input 中标识为 G10 的设备，只记录报告，不拦截或改写输入。</p></div><span className="badge badge-blue"><ShieldCheck size={13}/>设备过滤</span></div>
    <section className="panel detect-banner"><div className="detect-icon"><ListFilter size={23}/></div><div className="detect-copy"><b>{!available?'此版本的按键观察器不可用':state.running?'正在监听 G10 HID 报告':'按键检测模式'}</b><small>{!available?reason:state.running?'对普通键盘、鼠标和其他蓝牙设备不做操作。':'启动监听后按遥控器上的键，查看原始报告与事件类型。'}</small></div><button disabled={!available} className={`button ${state.running?'danger':'primary'}`} onClick={onToggle}>{state.running?<CircleStop size={16}/>:<Keyboard size={16}/ >}{!available?'此版本不可用':state.running?'停止检测':'开始检测'}</button></section>
    <section className="panel"><div className="panel-head"><div><div className="section-kicker">KEY INVENTORY</div><h3>按键识别</h3></div><span className="badge badge-muted">目前仅观察</span></div><div className="key-layout"><div className="remote-reference"><img src="./g10-remote.svg" alt="G10 遥控器按键示意图"/><span>G10 外观参考</span></div><div className="key-grid">{known.map(row=><article className="key-card" key={row.name}><div className="key-card-top"><span className={`key-symbol ${row.status==='已观察'?'key-symbol-mic':''}`}>{row.status==='已观察'?<Mic2 size={18}/>:<Keyboard size={18}/>}</span><span className={`badge ${row.status==='已观察'?'badge-green':'badge-muted'}`}>{row.status}</span></div><b>{row.name}</b><small>{row.detail}</small><button disabled title="当前版本用于采集与核对按键报告，尚未执行自定义动作">映射动作 <span>检测后开放</span></button></article>)}</div></div><div className="mapping-notice"><ShieldCheck size={16}/><div><b>当前只能检测，暂不能执行自定义映射</b><span>Raw Input 能识别 G10 报告，但不会阻止 Windows 原有功能。可靠识别后，可先评估保留原功能的附加动作；若要禁用原功能，需要单独确认设备级拦截方案。系统级按键注入和内核驱动目前均未启用。</span></div></div></section>
    <section className="panel events-panel"><div className="panel-head"><div><div className="section-kicker">LIVE REPORTS</div><h3>最近 HID 报告</h3></div><span className="badge badge-muted">来源：{state.device_filter}</span></div>
      {!state.events.length?<div className="empty-state"><div><Keyboard size={22}/></div><b>{state.running?'等待按键输入':'尚无检测记录'}</b><span>{state.running?'按遥控器的一个按键，报告会显示在这里。':'启动检测后，只有匹配 G10 地址的 Raw Input 事件会显示。'}</span></div>:<div className="report-list">{[...state.events].reverse().map((item,index)=><div className="report-row" key={`${item.perf_ns??item.seconds}-${index}`}><span className="report-time">{typeof item.seconds==='number'?`${item.seconds.toFixed(3)} s`:String(item.relative_s??'')}</span><span className="report-kind">{Number(item.kind)===1?'Keyboard':Number(item.kind)===2?'HID report':'Mouse'}</span><b>{item.virtual_key?`VK 0x${Number(item.virtual_key).toString(16).toUpperCase()}`:item.edge==='up'?'释放':item.edge==='down'?'按下':'原始报告'}</b><code>{typeof item.hex==='string'?item.hex:'—'}</code><span className="report-edge">{String(item.edge??'Raw Input')}</span></div>)}</div>}
    </section>
  </div>;
}

function SettingsPage({settings,autostart,connected,onAutostart,onCloseChange,onChangeReconnect,onExport,onImport,onReset,onReport,onExit,error}:{settings:Settings;autostart:boolean;connected:boolean;onAutostart:(value:boolean)=>void;onCloseChange:()=>void;onChangeReconnect:()=>void;onExport:()=>void;onImport:(event:ChangeEvent<HTMLInputElement>)=>void;onReset:()=>void;onReport:()=>void;onExit:()=>void;error:string}){
  return <div className="page-stack">
    <div className="page-intro"><div><div className="section-kicker">APPLICATION</div><p>管理后台运行、登录启动与本地配置。需修改 Windows 设置的操作会先显示确认框。</p></div><span className={`badge ${connected?'badge-green':'badge-muted'}`}>{connected?'桌面服务已连接':'预览模式'}</span></div>
    <section className="panel settings-panel"><div className="panel-head"><div><h3>窗口与后台</h3><p>关闭主窗口可以隐藏到托盘，蓝牙音频服务继续运行。</p></div></div>
      <SettingRow icon={<Moon size={17}/>} title="关闭窗口后保留在托盘" detail="可从托盘重新打开，或选择完全退出。"><Toggle checked={settings.behavior.close_to_tray} onChange={onCloseChange}/></SettingRow>
      <SettingRow icon={<Power size={17}/>} title="Windows 登录后启动" detail="只修改当前用户的启动项；启用前显示系统设置确认。"><Toggle checked={autostart} onChange={()=>onAutostart(!autostart)}/></SettingRow>
      <SettingRow icon={<Bluetooth size={17}/>} title="蓝牙断线后自动重连" detail="设置已保留，自动重连逻辑将在下一阶段接入。"><Toggle checked={settings.behavior.auto_reconnect} disabled onChange={onChangeReconnect}/></SettingRow>
    </section>
    <section className="panel settings-panel"><div className="panel-head"><div><h3>配置与诊断</h3><p>配置和日志留在本机，不上传。</p></div></div><div className="action-row"><span className="action-icon"><Download size={17}/></span><div><b>导入 / 导出配置</b><small>JSON 格式；导入不会修改 Windows 启动项或默认音频设备。</small></div><div className="inline-actions"><label className="button outline small file-button"> <FileUp size={14}/>导入<input type="file" accept=".json,application/json" onChange={onImport}/></label><button className="button outline small" onClick={onExport}><Download size={14}/>导出</button></div></div>
      <div className="action-row"><span className="action-icon"><ClipboardList size={17}/></span><div><b>诊断报告</b><small>连接状态、音频摘要与近期事件，不包含录音或识别文字。</small></div><button className="button outline small" onClick={onReport}><Download size={14}/>导出 JSON</button></div>
      <div className="action-row"><span className="action-icon muted-icon"><RotateCcw size={17}/></span><div><b>恢复默认设置</b><small>仅恢复 G10 Control 的应用内配置。</small></div><button className="button outline small" onClick={onReset}>恢复默认</button></div>
    </section>
    {error&&<div className="warning-note"><TriangleAlert size={16}/>{error}</div>}
    <section className="exit-card"><div><div className="section-kicker">SAFE SHUTDOWN</div><b>完全退出 G10 Control</b><small>先请求 BLE 服务恢复订阅并释放设备资源，再关闭窗口。</small></div><button className="button danger" onClick={onExit}><Power size={15}/>安全退出</button></section>
  </div>;
}

function SettingRow({icon,title,detail,children}:{icon:React.ReactNode;title:string;detail:string;children:React.ReactNode}){return <div className="setting-row"><span className="setting-icon">{icon}</span><div className="setting-main"><b>{title}</b><small>{detail}</small></div>{children}</div>}

function LogsPage({rows,path,onRefresh,onExport}:{rows:EventRow[];path:string|null;onRefresh:()=>void;onExport:()=>void}){
  const items=[...rows].reverse();
  const message=(row:EventRow)=>{
    const parts=[row.hex,row.status,row.connection_status,row.error].filter(Boolean);
    if(row.kind==='audio')return `G10 音频通知 · ${String(row.length??'')} 字节`;
    if(row.kind==='cable_output_meter')return `CABLE Output · ${String(row.level??-120)} dBFS · 已转发 ${String(row.processed_seconds??0)} 秒`;
    if(row.kind==='ime_capture_state')return (Array.isArray(row.active_routes)&&row.active_routes.length?`豆包正在读取：${(row.active_routes as {name:string}[]).map(item=>item.name).join('、')}`:'豆包当前没有打开录音设备');
    return parts.length?parts.join(' · '):row.kind??'状态事件';
  };
  return <div className="page-stack">
    <div className="page-intro"><div><div className="section-kicker">LOCAL DIAGNOSTICS</div><p>日志仅存储在本机，可用于检查 BLE、ATVV、音频端点和按键观察状态。</p></div><button className="button outline small" onClick={onRefresh}><RefreshCw size={14}/>刷新</button></div>
    <section className="panel diagnostic-summary"><div className="diag-symbol"><ClipboardList size={23}/></div><div><b>当前日志目录</b><small>{path||'启动服务后创建本地日志目录'}</small></div><button className="button outline small" onClick={onExport}><Download size={14}/>导出诊断报告</button></section>
    <section className="panel log-panel"><div className="panel-head"><div><div className="section-kicker">EVENTS</div><h3>近期事件</h3></div><span className="badge badge-muted">{items.length} 条</span></div>
      {items.length===0?<div className="empty-state"><div><ClipboardList size={22}/></div><b>暂无日志</b><span>启用桥接服务或 G10 按键检测后，本地记录会出现在这里。</span></div>:<div className="logs-list">{items.map((row,index)=><div className="log-row" key={`${row.perf_ns??index}-${index}`}><span className={`log-icon ${String(row.kind).includes('error')?'log-error':''}`}><Radio size={14}/></span><span className="log-time">{row.utc?new Date(row.utc).toLocaleTimeString():`+${Number(row.relative_s??0).toFixed(2)} s`}</span><b>{row.kind??'事件'}</b><span className="log-message">{message(row)}</span></div>)}</div>}
    </section>
  </div>;
}
