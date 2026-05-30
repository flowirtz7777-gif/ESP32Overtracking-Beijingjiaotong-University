@echo off
REM TTC 预警复盘软件 — 一键启动
setlocal
cd /d "%~dp0"
set "ELECTRON_EXE="

if exist "..\PID工况仿真导出器\node_modules\electron\dist\electron.exe" (
  set "ELECTRON_EXE=..\PID工况仿真导出器\node_modules\electron\dist\electron.exe"
) else if exist "..\trae\node_modules\electron\dist\electron.exe" (
  set "ELECTRON_EXE=..\trae\node_modules\electron\dist\electron.exe"
)

if defined ELECTRON_EXE (
  "%ELECTRON_EXE%" .
) else (
  echo Electron runtime not found in either:
  echo   ..\PID工况仿真导出器\node_modules\electron\dist\electron.exe
  echo   ..\trae\node_modules\electron\dist\electron.exe
  echo You can also open index.html directly in a browser.
  pause
)