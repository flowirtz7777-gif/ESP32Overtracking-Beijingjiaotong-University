$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $appDir "..")
$htmlPath = Join-Path $appDir "index.html"

$electron = Get-ChildItem -Path $repoRoot -Filter "electron.exe" -Recurse -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -like "*\node_modules\electron\dist\electron.exe" } |
  Select-Object -First 1

if ($electron) {
  Start-Process -FilePath $electron.FullName -ArgumentList "`"$appDir`"" -WorkingDirectory $appDir
} else {
  Start-Process -FilePath $htmlPath
}
