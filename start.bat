@echo off
setlocal
cd /d "%~dp0"

rem ===========================================================
rem  PCBA BOM Workbench - double-click launcher
rem  NOTE: keep this file ASCII-only. cmd.exe mis-parses batch
rem  files that mix UTF-8 text with a code page switch, so all
rem  Chinese messages are printed by app\desktop.py instead.
rem ===========================================================

rem ---------- 1. locate Python ----------
set "PYCMD="
where py >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD (
  where python >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD (
  echo [ERROR] Python not found. Install Python 3.10 or newer and enable "Add to PATH".
  pause
  exit /b 1
)

for /f "delims=" %%i in ('%PYCMD% -c "import sys;print(sys.executable)"') do set "SYS_PY=%%i"
set "SYS_PYW=%SYS_PY:python.exe=pythonw.exe%"
if not exist "%SYS_PYW%" set "SYS_PYW=%SYS_PY%"

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
set "VENV_PYW=%CD%\.venv\Scripts\pythonw.exe"

rem ---------- 2. first run: prepare an isolated environment ----------
if not exist "%VENV_PY%" goto build

rem Existing environment must actually work (it breaks if the folder was moved)
"%VENV_PY%" -c "import flask, openpyxl, olefile" >nul 2>nul
if not errorlevel 1 goto ensure_gui

echo Existing environment is unusable; rebuilding it ...
rmdir /s /q .venv

:build
echo Preparing environment (first run only) ...
%PYCMD% -m venv .venv
if errorlevel 1 goto fallback

echo Installing dependencies: flask openpyxl olefile ...
"%VENV_PY%" -m pip install -q --upgrade pip
"%VENV_PY%" -m pip install -q -r requirements.txt
if errorlevel 1 goto fallback

:ensure_gui
rem Desktop window needs pywebview; if it cannot be installed the app
rem automatically falls back to opening the default browser.
"%VENV_PY%" -c "import webview" >nul 2>nul
if errorlevel 1 (
  echo Installing desktop window component: pywebview ...
  "%VENV_PY%" -m pip install -q -r requirements-desktop.txt
)

echo Starting PCBA BOM Workbench ...
if exist "logs\desktop.ready" del "logs\desktop.ready" >nul 2>nul
start "" "%VENV_PYW%" app\desktop.py

rem Wait for the window to report itself ready, so a silent failure is visible.
rem ping is used instead of timeout: timeout needs an interactive stdin.
set /a TRIES=0
:wait
ping -n 3 127.0.0.1 >nul 2>nul
if exist "logs\desktop.ready" goto end
set /a TRIES+=1
if %TRIES% lss 12 goto wait

echo.
echo [ERROR] The desktop window did not start. See logs\desktop.log for details.
echo.
pause
goto end

rem ---------- 3. fallback to system Python ----------
:fallback
echo.
echo [WARN] Environment setup failed (usually network). Using system Python instead.
echo.
"%SYS_PYW%" app\desktop.py
goto end

:end
exit /b 0
