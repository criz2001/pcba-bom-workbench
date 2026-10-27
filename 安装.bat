@echo off
setlocal
cd /d "%~dp0"

rem PCBA BOM Workbench - double-click installer
rem This file stays ASCII-only; all Chinese messages come from install.ps1.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
if errorlevel 1 (
  echo.
  echo [ERROR] Installation failed. See the messages above.
  pause
)
exit /b 0
