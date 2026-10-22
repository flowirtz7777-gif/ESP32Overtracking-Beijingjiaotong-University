$ErrorActionPreference = 'Stop'

function Wait-And-Exit {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    Write-Host ''
    [void](Read-Host '按 Enter 键关闭此窗口')
    exit $ExitCode
}

$repoDir = $PSScriptRoot
Set-Location -LiteralPath $repoDir

$nodeCommand = Get-Command 'node.exe' -ErrorAction SilentlyContinue
$npmCommand = Get-Command 'npm.cmd' -ErrorAction SilentlyContinue

if (-not $nodeCommand -or -not $npmCommand) {
    Write-Host '错误：未检测到 Node.js 或 npm.cmd。' -ForegroundColor Red
    Write-Host '请先安装 Node.js，并确认 node.exe 与 npm.cmd 已加入 PATH。'
    Wait-And-Exit -ExitCode 1
}

$nodeModulesDir = Join-Path $repoDir 'node_modules'
if (-not (Test-Path -LiteralPath $nodeModulesDir -PathType Container)) {
    Write-Host '错误：项目尚未安装 npm 依赖，未找到 node_modules。' -ForegroundColor Red
    Write-Host '请在项目根目录先运行：npm.cmd install'
    Wait-And-Exit -ExitCode 1
}

Write-Host '正在启动人工驾驶仿真软件……' -ForegroundColor Cyan
Write-Host ('项目目录：{0}' -f $repoDir)
Write-Host ''

& $npmCommand.Source run human:dev
$launchExitCode = $LASTEXITCODE

if ($launchExitCode -ne 0) {
    Write-Host ''
    Write-Host ('人工驾驶仿真软件启动失败，退出码：{0}' -f $launchExitCode) -ForegroundColor Red
    Write-Host '请根据上方 npm / Electron 错误信息排查。'
    Wait-And-Exit -ExitCode $launchExitCode
}

exit 0

