$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$electronExe = Join-Path $appDir "node_modules\electron\dist\electron.exe"
if (-not (Test-Path -LiteralPath $electronExe -PathType Leaf)) {
    [Console]::Error.WriteLine("PID launcher error: electron.exe was not found.")
    [Console]::Error.WriteLine($electronExe)
    exit 1
}

if (-not (Test-Path -LiteralPath (Join-Path $appDir "desktop-main.js") -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $appDir "package.json") -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $appDir "pid工况仿真导出器.html") -PathType Leaf)) {
    [Console]::Error.WriteLine("PID launcher error: Electron app entry was not found.")
    [Console]::Error.WriteLine($appDir)
    exit 1
}

Start-Process -FilePath $electronExe -ArgumentList @($appDir) -WorkingDirectory $appDir
