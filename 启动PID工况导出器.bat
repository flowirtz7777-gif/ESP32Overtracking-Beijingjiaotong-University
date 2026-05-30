@echo off
REM PID 工况仿真导出器 — 一键启动 (无需 npm)
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
    echo [Error] Electron not found in either:
    echo   %REPO_DIR%PID工况仿真导出器\node_modules\electron\dist\electron.exe
    echo   %REPO_DIR%trae\node_modules\electron\dist\electron.exe
    echo.
    echo You can also double-click pid工况仿真导出器.html in a browser.
    echo.
    pause
    exit /b 1
)

start "" "%ELECTRON_EXE%" "%REPO_DIR%."
exit /b 0