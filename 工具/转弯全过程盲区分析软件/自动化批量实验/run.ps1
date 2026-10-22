param([string]$Plan = '', [string]$Resume = '', [switch]$DryRun, [switch]$NoPause)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$bundle = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node'
$node = Join-Path $bundle 'bin\node.exe'
if (-not (Test-Path -LiteralPath $node)) {
    $command = Get-Command node -ErrorAction SilentlyContinue
    if (-not $command) { throw 'Node.js was not found.' }
    $node = $command.Source
}
$modules = Join-Path $bundle 'node_modules'
if (Test-Path -LiteralPath $modules) { $env:NODE_PATH = $modules }
$arguments = @((Join-Path $here 'batch_cfg.cjs'))
if ($Plan) { $arguments += @('--plan', $Plan) }
if ($Resume) { $arguments += @('--resume', $Resume) }
if ($DryRun) { $arguments += '--dry-run' }
$code = 1
try {
    & $node @arguments
    $code = $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    if (-not $NoPause) { Read-Host 'Press Enter to close' | Out-Null }
}
exit $code
