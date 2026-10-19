@echo off
setlocal
cd /d "%~dp0"
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0g10_audio_bridge.py" --business-approval --allow-cccd
exit /b
