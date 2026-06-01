$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here

$electron = $null
$directCandidates = @(
  (Join-Path $repo "trae\node_modules\.bin\electron.cmd"),
  (Join-Path $repo "node_modules\.bin\electron.cmd"),
  (Join-Path $here "node_modules\.bin\electron.cmd")
)
$electron = $directCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $electron) {
  $electron = Get-ChildItem -Path $repo -Recurse -Filter "electron.cmd" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -like "*node_modules*\.bin*electron.cmd" } |
    Select-Object -First 1 -ExpandProperty FullName
}
if (-not $electron) {
  Write-Host "Electron was not found."
  Write-Host "Install dependencies first, or open index.html directly in a browser."
  pause
  exit 1
}

try {
  Push-Location $here
  & $electron .
} catch {
  Write-Host "Failed to launch CFG Builder:"
  Write-Host $_.Exception.Message
  pause
  exit 1
} finally {
  Pop-Location
}
