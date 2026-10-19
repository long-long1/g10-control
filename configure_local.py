"""Read local audio inventory and save selected identities; no BLE writes or setting changes."""
import argparse
import json
from local_config import CONFIG, require_address


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address',required=True,help='Your verified G10 Bluetooth address')
    args=parser.parse_args()
    address=require_address(args.address)
    from virtual_audio_probe import catalog, select_devices
    info=catalog()
    capture,_=select_devices(info,'vbcable')
    matches=[d for d in info['core_audio_endpoints'] if d['name']==capture['name'] and d['flow']==1 and d['state']==1]
    if len(matches)!=1:raise RuntimeError('CABLE Output 不唯一，未保存配置。')
    data={'bluetooth_address':address,'cable_capture_id':matches[0]['id']}
    temporary=CONFIG.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(CONFIG)
    print('本地配置已保存；未连接蓝牙、未修改 Windows 默认设备。此文件禁止提交。')


if __name__=='__main__':main()
