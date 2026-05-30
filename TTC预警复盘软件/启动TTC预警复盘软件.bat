@echo off
setlocal
cd /d "%~dp0"
if exist "..\trae\node_modules\electron\dist\electron.exe" (
  "..\trae\node_modules\electron\dist\electron.exe" .
) else (
  echo Electron runtime not found: ..\trae\node_modules\electron\dist\electron.exe
  echo You can also open index.html directly in a browser.
  pause
)
