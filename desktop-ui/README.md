# G10 Control (development build)

G10 Control is a Windows 11 GUI for the existing G10 BLE/ATVV voice bridge. It uses the established Python audio service as a separately supervised process; the React interface does not own or duplicate the codec or BLE session.

## Start

Run `start_g10_control.cmd` from Explorer. It opens the local WebView2 app and does **not** connect the G10 automatically. Use **连接 G10** when ready. The first stage does not change Windows default audio devices, install a driver, add an auto-start entry, or automatically invoke Doubao.

The development environment currently relies on the project `.venv` and the installed npm dependencies. To rebuild the web interface:

```powershell
cd desktop-ui\web
npm install
npm run build
cd ..
..\.venv\Scripts\python.exe -m unittest test_runtime -v
```

## Current scope

The home page reports the known G10 identity and supervised BLE/ATVV state. Voice settings retain the confirmed CABLE Output route and allow G10 decoder gain adjustment. Doubao auto wake is off by default. Changing the toggle while connected safely restarts the bridge so the selection takes effect. Both synthetic Right Alt and status-bar window messages have failed local testing, including a temporary elevated comparison. The UI now identifies auto wake as a diagnostic feature that has not passed hardware testing and displays its actual error on the voice page. The verified manual audio bridge remains available.

Offline analysis of this installed Doubao build found an explicit injected-key bypass in its voice keyboard hook. See `../output/doubao-integration-analysis/static-entry-findings.md`. The separate `doubao_ui_probe.py --activate --interactive --trigger mouse` experiment is staged but must not be run until the user separately approves temporary pointer movement and input. It is not integrated into normal G10 Control operation.

The key page is observation-only. Windows Raw Input cannot suppress the G10 event; therefore action mapping, key blocking, and global injection are not enabled. Known but unmeasured buttons remain marked as waiting for detection. Close-to-tray and safe exit are supported. Auto reconnect remains disabled until the later recovery stage.

## Layout

- `app.py`: WebView2 host, single-instance mutex, tray lifecycle and desktop API.
- `app_runtime.py`: persistent configuration, status projection, and bridge process supervision.
- `web/src`: React pages and styles.
- `../g10_audio_bridge.py`: existing BLE, ATVV, decoder, and VB-CABLE audio service.
- `test_runtime.py`: local configuration and validation tests.

See [`../G10-Control架构与实施计划.md`](../G10-Control架构与实施计划.md) for architecture decisions and the staged roadmap. Third-party notices are in [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).
