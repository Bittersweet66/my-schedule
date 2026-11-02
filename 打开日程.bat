@echo off
rem ============================================================
rem  MySchedule launcher
rem  1) start the background service (no window)
rem  2) open the UI in Google Chrome
rem  This mirrors the verified-working manual test.
rem ============================================================
setlocal
cd /d "%~dp0"

set "PY=%CD%\runtime\pythonw.exe"
if not exist "%PY%" set "PY=pythonw.exe"
set "APP=%CD%\backend\app.py"

start "" "%PY%" "%APP%" --no-window
timeout /t 2 /nobreak >nul

set "URL=http://127.0.0.1:47823/"
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" (
  start "" "%CHROME%" "%URL%"
) else (
  start "" "%URL%"
)

exit /b 0
