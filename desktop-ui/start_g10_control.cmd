@echo off
setlocal
set "G10_ROOT=%~dp0.."
set "G10_UI=%~dp0web"
if not exist "%G10_ROOT%\.venv\Scripts\pythonw.exe" (
  echo Python virtual environment not found: %G10_ROOT%\.venv
  pause
  exit /b 1
)
if not exist "%G10_UI%\dist\index.html" (
  if not exist "%G10_UI%\node_modules\.bin\vite.cmd" (
    echo Frontend dependencies are missing. Run npm install in desktop-ui\web first.
    pause
    exit /b 1
  )
  pushd "%G10_UI%"
  call npm run build
  if errorlevel 1 (popd & pause & exit /b 1)
  popd
)
start "" "%G10_ROOT%\.venv\Scripts\pythonw.exe" "%~dp0app.py"
endlocal
