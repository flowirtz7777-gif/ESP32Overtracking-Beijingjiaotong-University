param([string]$ProjectRoot = 'E:\大创内轮差项目')
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath $ProjectRoot).ProviderPath.TrimEnd('\')
$source = [IO.Path]::GetFullPath((Join-Path $project '工具\转弯全过程盲区分析软件\自动化批量实验'))
$archive = [IO.Path]::GetFullPath((Join-Path $project '工具\转弯全过程盲区分析软件\实验封存\2026-10-14'))
foreach ($target in @($source, $archive)) {
    if (-not $target.StartsWith($project + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Archive path outside project: $target"
    }
}
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw 'Legacy source missing' }
$running = @(Get-CimInstance Win32_Process -Filter "name='node.exe'" | Where-Object {
    $_.CommandLine -like '*steering_experiment*'
})
if ($running.Count) { throw 'An old experimental process is still running; stop it before sealing' }

function Stream-Hash([IO.Stream]$Stream) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($Stream)).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function File-Hash([string]$File) {
    $stream = [IO.File]::OpenRead($File)
    try { return Stream-Hash $stream } finally { $stream.Dispose() }
}
function Write-Json([string]$File, $Value) {
    [IO.File]::WriteAllText($File, ($Value | ConvertTo-Json -Depth 16) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false))
}
$zipFile = Join-Path $archive '旧实验完整快照.zip'
$verifyFile = Join-Path $archive 'verification.json'
if (Test-Path -LiteralPath $zipFile) {
    if (Test-Path -LiteralPath $verifyFile) {
        $previous = Get-Content -LiteralPath $verifyFile -Raw | ConvertFrom-Json
        if ($previous.status -eq 'verified' -and (File-Hash $zipFile) -eq $previous.archive_sha256) {
            Write-Output 'Existing archive verified; no files changed'
            return
        }
    }
    throw 'Archive file already exists without a valid completed verification; do not overwrite'
}
New-Item -ItemType Directory -Path $archive -Force | Out-Null
$files = @(Get-ChildItem -LiteralPath $source -Recurse -File -Force | Sort-Object FullName)
$links = @(Get-ChildItem -LiteralPath $source -Recurse -Force -Attributes ReparsePoint)
if ($links.Count) { throw 'Reparse points require an explicit archive design' }
$bytes = [long](($files | Measure-Object Length -Sum).Sum)
if ((Get-PSDrive E).Free -lt ($bytes + 512MB)) { throw 'Insufficient space for a conservative complete snapshot' }
$records = [Collections.Generic.List[object]]::new()
$index = 0
foreach ($file in $files) {
    $relative = $file.FullName.Substring($source.Length + 1).Replace('\', '/')
    if ($relative.StartsWith('../') -or [IO.Path]::IsPathRooted($relative)) { throw 'Invalid archive entry' }
    $records.Add([ordered]@{ path = $relative; bytes = $file.Length; sha256 = (File-Hash $file.FullName);
        original_attributes = [int]$file.Attributes; last_write_utc = $file.LastWriteTimeUtc.ToString('o') })
    $index++
    if ($index % 1000 -eq 0) { Write-Output "HASH $index/$($files.Count)" }
}
$dependencies = [ordered]@{
    'index.html' = (Join-Path $project '工具\转弯全过程盲区分析软件\index.html')
    'steering_prediction.js' = (Join-Path $project '工具\转弯全过程盲区分析软件\steering_prediction.js')
    'target_sampling.js' = (Join-Path $project '工具\转弯全过程盲区分析软件\target_sampling.js')
    'default_cfg.json' = (Join-Path $project '工具\转弯全过程盲区分析软件\CFG配置\default_cfg.json')
    '预测模型与对照模型构建思路.md' = (Join-Path $project '项目文档\01_核心设计\预测模型与对照模型构建思路.md')
}
$dependencyDirectory = Join-Path $archive '外部依赖快照'
New-Item -ItemType Directory -Path $dependencyDirectory -Force | Out-Null
$dependencyRecords = [Collections.Generic.List[object]]::new()
foreach ($name in $dependencies.Keys) {
    $original = $dependencies[$name]
    $copy = Join-Path $dependencyDirectory $name
    Copy-Item -LiteralPath $original -Destination $copy
    $sha = File-Hash $original
    if ((File-Hash $copy) -ne $sha) { throw "Dependency copy mismatch: $name" }
    $dependencyRecords.Add([ordered]@{ original_path = $original; archive_relative_path = "外部依赖快照/$name";
        sha256 = $sha; role = 'current_dependency_snapshot_old_runs_use_their_own_source_fingerprints' })
}
$manifest = [ordered]@{ version = '2026-10-14-archive-v1'; source_path = $source;
    file_count = $files.Count; uncompressed_bytes = $bytes; files = $records;
    external_dependency_snapshots = $dependencyRecords; created_at_utc = [DateTime]::UtcNow.ToString('o') }
$manifestFile = Join-Path $archive 'archive_manifest.json'
Write-Json $manifestFile $manifest
Write-Json (Join-Path $archive 'restore_map.json') ([ordered]@{
    original_directory = $source; original_files_zip = $zipFile; original_attributes_in = 'archive_manifest.json';
    preserve_original_absolute_paths_for_replay = $true; extract_only_to_separate_writable_copy_by_default = $true;
    old_current_plan_is_historical = $true
})
Add-Type -AssemblyName System.IO.Compression.FileSystem
Write-Output "COMPRESS $($files.Count) files, $bytes bytes"
[IO.Compression.ZipFile]::CreateFromDirectory($source, $zipFile,
    [IO.Compression.CompressionLevel]::Optimal, $false, [Text.Encoding]::UTF8)
$expected = @{}
foreach ($record in $records) { $expected[$record.path] = $record }
$zip = [IO.Compression.ZipFile]::OpenRead($zipFile)
$checked = 0
try {
    $entries = @($zip.Entries | Where-Object { $_.Name -ne '' })
    if ($entries.Count -ne $files.Count) { throw 'ZIP file count mismatch' }
    foreach ($entry in $entries) {
        $name = $entry.FullName.Replace('\', '/')
        if (-not $expected.ContainsKey($name)) { throw "Unexpected ZIP entry: $name" }
        $record = $expected[$name]
        if ($entry.Length -ne $record.bytes) { throw "ZIP size mismatch: $name" }
        $stream = $entry.Open()
        try { $sha = Stream-Hash $stream } finally { $stream.Dispose() }
        if ($sha -ne $record.sha256) { throw "ZIP hash mismatch: $name" }
        $checked++
        if ($checked % 1000 -eq 0) { Write-Output "VERIFY ZIP $checked/$($files.Count)" }
    }
} finally { $zip.Dispose() }
Write-Output 'VERIFY ORIGINAL AND SET READONLY'
$sourceChecked = 0
foreach ($record in $records) {
    $original = Join-Path $source $record.path.Replace('/', '\')
    if ((File-Hash $original) -ne $record.sha256) { throw "Original changed during archive: $($record.path)" }
    (Get-Item -LiteralPath $original -Force).IsReadOnly = $true
    $sourceChecked++
}
$readonly = @($files | Where-Object { (Get-Item -LiteralPath $_.FullName -Force).IsReadOnly }).Count
if ($readonly -ne $files.Count) { throw 'Readonly verification incomplete' }
$archiveHash = File-Hash $zipFile
$verification = [ordered]@{ status = 'verified'; legacy_file_count = $files.Count; legacy_bytes = $bytes;
    zip_entry_hashes_verified = $checked; original_hashes_rechecked = $sourceChecked; readonly_file_count = $readonly;
    external_dependencies_verified = $dependencyRecords.Count; archive_path = $zipFile;
    archive_bytes = (Get-Item -LiteralPath $zipFile).Length; archive_sha256 = $archiveHash;
    manifest_sha256 = (File-Hash $manifestFile); completed_at_utc = [DateTime]::UtcNow.ToString('o');
    experiments_started = $false }
Write-Json $verifyFile $verification
$marker = Join-Path $source 'ARCHIVED.json'
Write-Json $marker ([ordered]@{ status = 'archived'; user_date = '2026-10-14'; archive_directory = $archive;
    verification_path = $verifyFile; archive_sha256 = $archiveHash; original_files_readonly = $true;
    no_legacy_resume = $true; new_plan = (Join-Path $project '工具\转弯全过程盲区分析软件\科研实验_2026-10-14\plan.json') })
(Get-Item -LiteralPath $marker).IsReadOnly = $true
Write-Output ($verification | ConvertTo-Json -Compress)
