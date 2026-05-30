@echo off
REM ============================================================
REM PID 工况仿真导出器 — 一键启动 (无需 npm)
REM 直接调用 Electron 启动根目录下的 desktop-main.js + HTML
REM 沙箱目录（含 node_modules）可能叫 PID工况仿真导出器/ 或 trae/
REM ============================================================
chcp 65001 >nul
setlocal
set "REPO_DIR=%~dp0"
set "ELECTRON_EXE="

if exist "%REPO_DIR%PID工况仿真导出器\node_modules\electron\dist\electron.exe" (
  set "ELECTRON_EXE=%REPO_DIR%PID工况仿真导出器\node_modules\electron\dist\electron.exe"
) else if exist "%REPO_DIR%trae\node_modules\electron\dist\electron.exe" (
  set "ELECTRON_EXE=%REPO_DIR%trae\node_modules\electron\dist\electron.exe"
)

if not defined ELECTRON_EXE (
    echo.
    echo [错误] 未找到 Electron 可执行文件
    echo   1) %REPO_DIR%PID工况仿真导出器\node_modules\electron\dist\electron.exe
    echo   2) %REPO_DIR%trae\node_modules\electron\dist\electron.exe
    echo 任意一个沙箱目录里完整 npm install 后再试。
    echo 也可以直接双击 pid工况仿真导出器.html 在浏览器中使用。
    echo.
    pause
    exit /b 1
)

start "" "%ELECTRON_EXE%" "%REPO_DIR%."
exit /b 0
