@echo off
REM ============================================================
REM PID 工况仿真导出器 - 一键启动 (无需 npm)
REM 直接调用 trae/node_modules/electron/dist/electron.exe
REM 加载本目录下的 desktop-main.js
REM ============================================================
chcp 65001 >nul
set "REPO_DIR=%~dp0"
set "ELECTRON_EXE=%REPO_DIR%trae\node_modules\electron\dist\electron.exe"

if not exist "%ELECTRON_EXE%" (
    echo.
    echo [错误] 找不到 Electron: %ELECTRON_EXE%
    echo 请确认 trae/node_modules 完整。如已删除，请先在 trae 沙箱里跑 npm install
    echo.
    pause
    exit /b 1
)

start "" "%ELECTRON_EXE%" "%REPO_DIR%."
exit /b 0
