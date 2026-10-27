@echo off
setlocal
cd /d "%~dp0"

rem ===========================================================
rem  PCBA BOM Workbench - double-click launcher
rem  Keep this file ASCII-only: cmd.exe mis-parses batch files
rem  that mix UTF-8 text with a code page switch. All Chinese
rem  messages are shown by app\startup_error.ps1 instead.
rem ===========================================================

if not exist "logs" mkdir "logs" >nul 2>nul
set "STARTLOG=%CD%\logs\start.log"
>>"%STARTLOG%" echo.
>>"%STARTLOG%" echo ===== %DATE% %TIME% =====
>>"%STARTLOG%" echo launched from %CD%

rem ---------- 1. locate Python ----------
set "PYCMD="
where py >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD (
  where python >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD (
  where python3 >nul 2>nul && set "PYCMD=python3"
)
if not defined PYCMD goto no_python

set "SYS_PY="
for /f "delims=" %%i in ('%PYCMD% -c "import sys;print(sys.executable)" 2^>nul') do set "SYS_PY=%%i"
if not defined SYS_PY goto no_python
if not exist "%SYS_PY%" goto no_python

"%SYS_PY%" -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if errorlevel 1 goto python_old

>>"%STARTLOG%" echo python: %SYS_PY%
"%SYS_PY%" --version >>"%STARTLOG%" 2>&1

set "SYS_PYW=%SYS_PY:python.exe=pythonw.exe%"
if not exist "%SYS_PYW%" set "SYS_PYW=%SYS_PY%"

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
set "VENV_PYW=%CD%\.venv\Scripts\pythonw.exe"
set "LAUNCH_PY=%VENV_PYW%"

rem ---------- 2. first run: prepare an isolated environment ----------
if not exist "%VENV_PY%" goto build

"%VENV_PY%" -c "import flask, openpyxl, olefile" >nul 2>nul
if not errorlevel 1 goto ensure_gui

echo Existing environment is unusable; rebuilding it ...
>>"%STARTLOG%" echo existing .venv unusable; rebuilding
rmdir /s /q ".venv" >nul 2>nul

:build
echo Preparing environment (first run only) ...
>>"%STARTLOG%" echo creating .venv
%PYCMD% -m venv ".venv" >>"%STARTLOG%" 2>&1
if errorlevel 1 goto env_failed
if not exist "%VENV_PY%" goto env_failed

>>"%STARTLOG%" echo installing dependencies
"%VENV_PY%" -m pip install -q --upgrade pip >>"%STARTLOG%" 2>&1
"%VENV_PY%" -m pip install -q -r requirements.txt >>"%STARTLOG%" 2>&1
if errorlevel 1 goto env_failed
"%VENV_PY%" -c "import flask, openpyxl, olefile" >nul 2>nul
if errorlevel 1 goto env_failed

:ensure_gui
"%VENV_PY%" -c "import webview" >nul 2>nul
if errorlevel 1 (
  echo Installing desktop window component: pywebview ...
  >>"%STARTLOG%" echo installing pywebview
  "%VENV_PY%" -m pip install -q -r requirements-desktop.txt >>"%STARTLOG%" 2>&1
)

:launch
echo Starting PCBA BOM Workbench ...
if exist "logs\desktop.ready" del "logs\desktop.ready" >nul 2>nul
>>"%STARTLOG%" echo starting: %LAUNCH_PY% app\desktop.py
start "" "%LAUNCH_PY%" app\desktop.py

rem Wait for the window to report itself ready, so a silent failure is visible.
rem ping is used instead of timeout: timeout needs an interactive stdin.
set /a TRIES=0
:wait
ping -n 3 127.0.0.1 >nul 2>nul
if exist "logs\desktop.ready" goto end
set /a TRIES+=1
if %TRIES% lss 30 goto wait
goto start_timeout

:no_python
>>"%STARTLOG%" echo ERROR: Python not found
call :show_error no_python
exit /b 1

:python_old
>>"%STARTLOG%" echo ERROR: Python too old: %SYS_PY%
call :show_error python_old
exit /b 1

:env_failed
>>"%STARTLOG%" echo ERROR: environment setup failed
rem Fall back to system Python only when it already has the core dependencies.
"%SYS_PY%" -c "import flask, openpyxl, olefile" >nul 2>nul
if errorlevel 1 (
  call :show_error env_failed
  exit /b 1
)
>>"%STARTLOG%" echo fallback to system Python: %SYS_PY%
set "LAUNCH_PY=%SYS_PYW%"
goto launch

:start_timeout
>>"%STARTLOG%" echo ERROR: desktop window did not report ready in time
call :show_error start_timeout
exit /b 1

:show_error
where powershell >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Startup failed: %~1
  echo See logs\start.log and logs\desktop.log for details.
  exit /b 0
)
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "app\startup_error.ps1" -Key "%~1" -LogFile "%STARTLOG%"
exit /b 0

:end
exit /b 0
