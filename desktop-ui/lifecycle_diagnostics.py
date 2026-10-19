"""Exercise production window/tray/mutex methods without OS input injection."""
import ctypes
import json
from pathlib import Path
import subprocess
import sys
import time


def wait_until(predicate, message, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.05)
    raise RuntimeError(message)


def exercise_lifecycle(app, report_path):
    window = app._window
    wait_until(lambda: window.evaluate_js("Boolean(document.querySelector('[data-testid=setup-wizard]'))"), 'Wizard did not render')
    handle = int(window.native.Handle.ToInt64())
    visible = lambda: bool(ctypes.windll.user32.IsWindowVisible(ctypes.c_void_p(handle)))
    wait_until(visible, 'Normal window did not become visible')
    wait_until(lambda: app._tray.visible and bool(getattr(app._tray, '_hwnd', None)), 'Tray did not become ready')
    initial_gain = app._store.load()['voice']['gain_db']
    initial_step = app._supervisor.wizard.snapshot()['step']
    settings = app._store.load()
    settings['voice']['gain_db'] = 6
    app._store.save(settings)
    app.set_setup_step(2)
    blocked = []
    operations = [app.start_service, app.scan_ble_devices, lambda: app.select_ble_device('invalid'),
                  lambda: app.check_ble_compatibility(True), app.detect_audio_route,
                  lambda: app.verify_audio_route('invalid', True), app.start_key_detection,
                  lambda: app.set_autostart(True, True)]
    for operation in operations:
        try:
            operation()
        except RuntimeError as exc:
            if '隔离诊断' not in str(exc):
                raise
            blocked.append(True)
        else:
            raise RuntimeError('Nonbusiness mode failed to block an operation')
    if app.on_window_closing() is not False:
        raise RuntimeError('Close-to-tray did not cancel close')
    wait_until(lambda: not visible(), 'Window did not hide to tray')
    app._tray.menu.items[0](app._tray)  # Actual restore menu callback, no mouse input.
    wait_until(visible, 'Tray restore did not show window')
    secondary = report_path.with_name(report_path.stem + '-secondary.json')
    command = [str(Path(sys.executable)), '--lifecycle-diagnostic', str(secondary)]
    if not getattr(sys, 'frozen', False):
        command.insert(1, str(Path(__file__).with_name('control_entry.py')))
    result = subprocess.run(command, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    second = json.loads(secondary.read_text(encoding='utf-8'))
    if result.returncode != 0 or not second.get('already_running'):
        raise RuntimeError('Single-instance mutex did not reject the second process')
    return {'ok': True, 'normal_ui_visible': True, 'tray_ready': True, 'close_to_tray': True,
            'tray_restore': True, 'single_instance': True, 'blocked_operations': len(blocked),
            'service_running': app._supervisor.snapshot()['service']['running'],
            'initial_gain_db': initial_gain, 'initial_setup_step': initial_step,
            'settings_roundtrip': app._store.load()['voice']['gain_db'] == 6,
            'key_observer_available': app.get_status()['shell']['key_observer_available']}
