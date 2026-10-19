@echo off
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" "g10_audio_bridge.py" --business-approval --allow-cccd --monitor-output --local-input-test --observe-ime
