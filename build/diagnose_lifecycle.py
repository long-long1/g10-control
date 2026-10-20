"""Normal visible UI/tray lifecycle in an isolated copy; all business APIs denied."""
import json
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from diagnose_portable import move_when_released


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=root / 'dist/G10-Control')
    args = parser.parse_args()
    session = Path(tempfile.mkdtemp(prefix='beta lifecycle ', dir=root / 'output')).resolve()
    program = session / 'first location'
    program.mkdir()
    bundle = args.bundle.resolve()
    for name in ('G10-Control.exe', 'G10-AudioBridge.exe', 'portable.marker'):
        shutil.copy2(bundle / name, program / name)
    shutil.copytree(bundle / '_internal', program / '_internal')
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(('G10_', 'PYTHON', 'VIRTUAL_ENV', 'WEBVIEW2_'))}
    env['LOCALAPPDATA'] = str(session / 'local')
    env['APPDATA'] = str(session / 'roaming')
    env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    summary = []
    for name in ('initial', 'moved'):
        report = session / f'{name}.json'
        result = subprocess.run([str(program / 'G10-Control.exe'), '--lifecycle-diagnostic', str(report)],
                                env=env, cwd=session, timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
        value = json.loads(report.read_text(encoding='utf-8'))
        if (result.returncode != 0 or not value['ok'] or value['service_running']
                or value['key_observer_available'] or not value['settings_roundtrip']):
            raise RuntimeError(f'Lifecycle failed: {report}: {value}')
        if name == 'moved' and (value['initial_gain_db'] != 6 or value['initial_setup_step'] != 2):
            raise RuntimeError('Moved program did not preserve settings/setup progress')
        summary.append({'case': name, 'report': str(report), 'result': value})
        print(json.dumps(summary[-1], ensure_ascii=False), flush=True)
        if name == 'initial':
            moved = session / '移动 中文 location'
            move_when_released(program, moved, session)
            program = moved
    (session / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Lifecycle artifacts: {session}', flush=True)


if __name__ == '__main__':
    main()
