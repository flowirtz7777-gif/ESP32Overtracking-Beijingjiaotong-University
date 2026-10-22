# Midterm temporary training launcher (pre-correction scores; not a frozen research asset).
# Opens one visible PowerShell window per step: P0 first, then M1/M2a/M2b/M3/M4 in parallel, then SUM.
param(
    [string[]]$Only = @()
)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Py = "C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

function Open-Window([string]$Step) {
    $status = Join-Path $Logs "$Step.status.json"
    if (Test-Path $status) { Remove-Item $status -Force }
    $cmd = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " +
           "`$Host.UI.RawUI.WindowTitle='Midterm temp training - $Step'; " +
           "try { `$Host.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size(160, 3000) } catch {}; " +
           "Set-Location -LiteralPath '$Root'; " +
           "& '$Py' -X utf8 -B -u run_step.py $Step; " +
           "Write-Host ''; Write-Host ('[' + '$Step' + '] exit code ' + `$LASTEXITCODE + ' - window kept open, you may close it.')"
    Start-Process powershell -ArgumentList @("-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $cmd) | Out-Null
    Write-Host "opened window: $Step"
}

function Wait-Steps([string[]]$Steps) {
    while ($true) {
        $states = @{}
        foreach ($s in $Steps) {
            $p = Join-Path $Logs "$s.status.json"
            $states[$s] = if (Test-Path $p) { (Get-Content $p -Raw -Encoding UTF8 | ConvertFrom-Json).state } else { "starting" }
        }
        $line = ($Steps | ForEach-Object { "$_=$($states[$_])" }) -join "  "
        Write-Host ("{0}  {1}" -f (Get-Date -Format "HH:mm:ss"), $line)
        if (($states.Values | Where-Object { $_ -in @("done", "failed") }).Count -eq $Steps.Count) { return $states }
        Start-Sleep -Seconds 20
    }
}

$train = @("M1", "M2a", "M2b", "M3", "M4")
if ($Only.Count -gt 0) { $train = $Only }

if ($Only.Count -eq 0) {
    Open-Window "P0"
    $s = Wait-Steps @("P0")
    if ($s["P0"] -ne "done") { Write-Host "P0 failed, stop."; exit 1 }
}
foreach ($t in $train) { Open-Window $t; Start-Sleep -Seconds 2 }
$s = Wait-Steps $train
Open-Window "SUM"
$s2 = Wait-Steps @("SUM")
Write-Host "ALL DONE"
$s.GetEnumerator() | ForEach-Object { Write-Host ("  {0}: {1}" -f $_.Key, $_.Value) }
Write-Host ("  SUM: {0}" -f $s2["SUM"])
