export type Settings = {
  schema_version: number;
  voice: { auto_wake_doubao: boolean; virtual_microphone_id: string; gain_db: number };
  behavior: { close_to_tray: boolean; auto_reconnect: boolean };
  key_detection: { target_address: string };
};
export type EventRow = Record<string, unknown> & { kind?: string; relative_s?: number; utc?: string; hex?: string };
export type RouteEndpoint = {id:string;name:string;flow:number;samplerate:number;mix_format:{nChannels:number}};
export type AudioRouteStatus = {state:string;message:string;validated:boolean;pair:{capture:RouteEndpoint;render:RouteEndpoint}|null;verified_at:string|null;proof_path:string;confirmation_token:string|null};
export type BleCandidate = {id:string;address:string;name:string;advertised_services:string[];paired?:boolean;connected?:boolean|null;present?:boolean|null;winrt_device_id?:string;name_source?:string};
export type DeviceSetupStatus = {state:string;message:string;selected:BleCandidate|null;compatible:boolean;candidates:BleCandidate[];busy:boolean};
export type SetupStatus = {step:number;completed:boolean;ready:boolean;statuses:string[];environment:{name:string;passed:boolean;detail:string}[];data_directory:string;portable:boolean;fallback_reason:string|null};
export type Snapshot = {
  settings_warning?: string|null;
  application: { name: string; version: string; single_instance: boolean };
  service: { running:boolean; connection:'stopped'|'starting'|'connected'|'unknown'; detail:string; started_at:string|null; audio_active:boolean; processed_audio_seconds:number; input_level_dbfs:number; cable_level_dbfs:number; cable_peak:number; error_count:number; error:string|null };
  device: { name:string; address:string; transport:string; vid:string|null; pid:string|null; battery:number|null };
  device_setup: DeviceSetupStatus;
  setup: SetupStatus;
  shell:{key_observer_available:boolean;key_observer_reason:string;nonbusiness:boolean};
  startup:{enabled:boolean;repair_needed:boolean;error?:string};
  microphone: { name:string; id:string; validated:boolean; is_active:boolean };
  audio_route: AudioRouteStatus;
  settings: Settings;
  runtime: { log_directory:string; service_log_directory:string|null };
};
export type KeySnapshot = { running:boolean; device_filter:string; events:EventRow[] };
export type DesktopAPI = {
  get_status():Promise<Snapshot>; start_service():Promise<{started:boolean;already_running?:boolean}>; stop_service():Promise<{stopped:boolean;exit_code?:number}>;
  save_settings(value:Settings):Promise<Settings>; reset_settings():Promise<Settings>; export_settings():Promise<string>; import_settings(contents:string):Promise<Settings>;
  get_audio_devices():Promise<{name:string;id:string;channels:number;validated:boolean}[]>; get_logs():Promise<EventRow[]>;
  detect_audio_route():Promise<AudioRouteStatus>; verify_audio_route(token:string,confirmed:boolean):Promise<AudioRouteStatus>;
  scan_ble_devices():Promise<DeviceSetupStatus>; select_ble_device(identity:string):Promise<DeviceSetupStatus>; check_ble_compatibility(confirmed:boolean):Promise<DeviceSetupStatus>;
  detect_environment():Promise<SetupStatus>; set_setup_step(step:number):Promise<SetupStatus>; complete_setup():Promise<SetupStatus>;
  get_diagnostics():Promise<Record<string,unknown>>; save_diagnostics(contents:string):Promise<{saved:boolean;path?:string}>;
  start_key_detection():Promise<{running:boolean}>; stop_key_detection():Promise<{stopped:boolean}>; get_key_events():Promise<KeySnapshot>;
  set_autostart(enabled:boolean,confirmed?:boolean):Promise<boolean>; get_autostart():Promise<boolean>; request_exit():Promise<{exiting:boolean}>;
  set_close_to_tray(enabled:boolean):Promise<boolean>;
};
declare global { interface Window { pywebview?:{api:DesktopAPI}; g10SetExitError?:(message:string)=>void } }
export function nativeAPI():DesktopAPI|null{
  const api=window.pywebview?.api;
  return api&&typeof api.get_status==='function'?api:null;
}
