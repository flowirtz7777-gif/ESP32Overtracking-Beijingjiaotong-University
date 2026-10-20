$ErrorActionPreference = 'Stop'
$appDir = $PSScriptRoot
$electronExe = Join-Path $appDir 'node_modules\electron\dist\electron.exe'
if (-not (Test-Path -LiteralPath $electronExe)) {
    $electronExe = Join-Path (Split-Path -Parent $appDir) 'PID工况仿真导出器\node_modules\electron\dist\electron.exe'
}
if (Test-Path -LiteralPath $electronExe) {
    Start-Process -FilePath $electronExe -ArgumentList ('"' + $appDir + '"') -WorkingDirectory $appDir
} else {
    Start-Process -FilePath (Join-Path $appDir '人工驾驶仿真软件.html')
}
