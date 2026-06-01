$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidDir = Get-ChildItem -LiteralPath $repoDir -Directory |
    Where-Object { $_.Name -like "PID*" } |
    Select-Object -First 1

if ($null -eq $pidDir) {
    [Console]::Error.WriteLine("PID launcher error: PID app folder was not found.")
    exit 1
}

$electronExe = Join-Path $pidDir.FullName "node_modules\electron\dist\electron.exe"
if (-not (Test-Path -LiteralPath $electronExe -PathType Leaf)) {
    [Console]::Error.WriteLine("PID launcher error: electron.exe was not found.")
    [Console]::Error.WriteLine($electronExe)
    exit 1
}

$rootHtml = Get-ChildItem -LiteralPath $repoDir -File -Filter "pid*.html" | Select-Object -First 1
$folderHtml = Get-ChildItem -LiteralPath $pidDir.FullName -File -Filter "pid*.html" | Select-Object -First 1

if ((Test-Path -LiteralPath (Join-Path $repoDir "desktop-main.js") -PathType Leaf) -and
    (Test-Path -LiteralPath (Join-Path $repoDir "package.json") -PathType Leaf) -and
    ($null -ne $rootHtml)) {
    $appDir = $repoDir
} elseif ((Test-Path -LiteralPath (Join-Path $pidDir.FullName "desktop-main.js") -PathType Leaf) -and
          (Test-Path -LiteralPath (Join-Path $pidDir.FullName "package.json") -PathType Leaf) -and
          ($null -ne $folderHtml)) {
    $appDir = $pidDir.FullName
} else {
    [Console]::Error.WriteLine("PID launcher error: Electron app entry was not found.")
    [Console]::Error.WriteLine($repoDir)
    [Console]::Error.WriteLine($pidDir.FullName)
    exit 1
}

Start-Process -FilePath $electronExe -ArgumentList @($appDir) -WorkingDirectory $appDir
