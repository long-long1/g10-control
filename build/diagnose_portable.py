"""Run only explicit startup diagnostics from a relocated, isolated onedir copy.

This uses no business approval flags and exposes no business API to the hidden
React window. Outputs remain under output/ and are never release artifacts.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def move_when_released(source, target, session):
    """Windows can retain file handles briefly after the diagnostic EXE exits."""
    source.resolve().relative_to(session.resolve())
    target.resolve().relative_to(session.resolve())
    deadline = time.monotonic() + 10
    retries = 0
    while True:
        try:
            source.rename(target)
            return retries
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            if retries == 0:
                print('Waiting up to 10 seconds for Windows to release diagnostic directory handles.', flush=True)
            retries += 1
            time.sleep(.2)


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=root / 'dist/G10-Control')
    args = parser.parse_args()
    output = root / 'output'
    output.mkdir(exist_ok=True)
    session = Path(tempfile.mkdtemp(prefix='portable startup ', dir=output)).resolve()
    program = session / 'first location'
    program.mkdir()
    for name in ('G10-Control.exe', 'G10-AudioBridge.exe', 'portable.marker'):
        shutil.copy2(args.bundle / name, program / name)
    shutil.copytree(args.bundle / '_internal', program / '_internal')
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(('G10_', 'PYTHON', 'VIRTUAL_ENV', 'WEBVIEW2_'))}
    env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    env['LOCALAPPDATA'] = str(session / 'local app data')
    env['APPDATA'] = str(session / 'roaming app data')
    summary = []

    def run(name, component, webview=False):
        report_path = session / f'{name}.json'
        command = [str(program / f'G10-{component}.exe'), '--diagnose-startup', str(report_path)]
        if webview:
            command.append('--diagnose-webview')
        result = subprocess.run(command, cwd=session, env=env, timeout=45,
                                creationflags=subprocess.CREATE_NO_WINDOW,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.is_file() else {}
        item = {'name': name, 'exit_code': result.returncode, 'report': str(report_path),
                'ok': result.returncode == 0 and report.get('ok') is True}
        summary.append(item)
        print(json.dumps(item), flush=True)
        if not item['ok']:
            raise RuntimeError(f'Startup failed: {report_path}\n{report.get("error", "No report produced")}')
        return report

    try:
        run('bridge-portable', 'AudioBridge')
        run('control-portable-webview', 'Control', True)
        sentinel = program / 'data/move-check.txt'
        sentinel.write_text('preserved across relocation', encoding='utf-8')
        moved = session / 'moved 中文 location'
        # Verify both absolute paths before moving the diagnostic directory.
        program.resolve().relative_to(session)
        moved.resolve().relative_to(session)
        summary[-1]['relocation_retries'] = move_when_released(program, moved, session)
        program = moved
        report = run('control-moved-webview', 'Control', True)
        if Path(report['paths']['data_dir']) != program / 'data':
            raise RuntimeError('Relocated program selected the wrong data directory')
        if (program / 'data/move-check.txt').read_text(encoding='utf-8') != 'preserved across relocation':
            raise RuntimeError('Relocated program lost its data')
        run('bridge-moved', 'AudioBridge')

        # Force an actual creation failure without changing ACLs: a file blocks
        # the portable data directory. ACL-denied behavior is also unit tested.
        data = program / 'data'
        data.resolve().relative_to(session)
        saved = program / 'saved portable data'
        saved.resolve().relative_to(session)
        summary[-1]['data_move_retries'] = move_when_released(data, saved, session)
        data.write_text('intentionally blocks mkdir', encoding='utf-8')
        for component in ('Control', 'AudioBridge'):
            report = run(f'{component.lower()}-fallback', component, webview=component == 'Control')
            if report['portable'] or not report['fallback_reason']:
                raise RuntimeError('Expected portable write failure and a recorded fallback reason')
            if Path(report['paths']['data_dir']) != Path(env['LOCALAPPDATA']) / 'G10Control':
                raise RuntimeError('Fallback selected the wrong LocalAppData directory')
    finally:
        (session / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(f'Diagnostic artifacts: {session}', flush=True)


if __name__ == '__main__':
    main()
