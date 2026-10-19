"""Explicit one-shot local validation; metadata preflight by default. No BLE."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from audio_route import AudioRoute, _probe
from audio_idle import inspect_idle
from portable_paths import resolve_paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--program-directory', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--execute-when-idle', action='store_true')
    args = parser.parse_args()
    paths = resolve_paths(executable=args.program_directory / 'G10-Control.exe', frozen=True,
                          bundle_dir=args.program_directory / '_internal')
    report = {'stream_attempted': False, 'passed': False, 'data_directory': str(paths.data_dir)}
    route = AudioRoute(paths)
    try:
        detected = route.detect()
        report['detected'] = detected
        if not detected['pair']:
            raise RuntimeError(detected['message'])
        report['idle_checks'] = [inspect_idle(detected['pair'])]
        time.sleep(.3)
        report['idle_checks'].append(inspect_idle(detected['pair']))
        if not all(check['idle'] for check in report['idle_checks']):
            raise RuntimeError('无法确认虚拟通道空闲，请用户关闭相关程序并确认后再操作。')
        if args.execute_when_idle:
            def guarded_probe(info, directory):
                check = inspect_idle(detected['pair'])
                report['idle_checks'].append(check)
                if not check['idle']:
                    raise RuntimeError('打开流前虚拟通道不再空闲，未执行音频测试。')
                report['stream_attempted'] = True
                return _probe(info, directory)
            route._probe = guarded_probe
            report['validation'] = route.verify(detected['confirmation_token'], True)
            route.require_verified()
            report['passed'] = True
        else:
            report['preflight_only'] = True
    except Exception as exc:
        report['error'] = str(exc)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('stream_attempted', 'passed', 'data_directory', 'error') if key in report}, ensure_ascii=False))
    return 1 if 'error' in report else 0


if __name__ == '__main__':
    sys.exit(main())
