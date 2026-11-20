[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $BuilderRoot,
    [Parameter(Mandatory)] [string] $Game,
    [Parameter(Mandatory)] [string] $Stage,
    [ValidateRange(1, 256)] [int] $Jobs = [Math]::Max(1, [Math]::Min(8, [Environment]::ProcessorCount))
)

# Run in a dedicated copy of the v2.3.1 Builder toolkit. This step patches
# that copy and performs the full upstream build with its native toolchain.
$ErrorActionPreference = 'Stop'
$builderPath = (Resolve-Path -LiteralPath $BuilderRoot).ProviderPath
$gamePath = (Resolve-Path -LiteralPath $Game).ProviderPath
$stagePath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Stage)
$tools = Join-Path $builderPath 'versions/v2.3.1/HookshotBuilder/tools'
$work = Join-Path $builderPath 'work-v2.3.1'
$python = Join-Path $tools 'python/python.exe'

foreach ($inputPath in @($builderPath, $gamePath, $PSScriptRoot)) {
    $relative = [IO.Path]::GetRelativePath($inputPath, $stagePath)
    if ($relative -ne '..' -and !$relative.StartsWith("..$([IO.Path]::DirectorySeparatorChar)") -and
        ![IO.Path]::IsPathRooted($relative)) {
        throw 'Stage must be a new directory outside the source, game and Builder trees.'
    }
}
if ((Test-Path -LiteralPath $stagePath) -or (Test-Path -LiteralPath $work)) {
    throw 'Choose an unused stage and a dedicated v2.3.1 Builder copy with no work-v2.3.1 directory.'
}
if ((Get-Content -LiteralPath (Join-Path $tools 'version.txt') -Raw).Trim() -ne 'v2.3.1') {
    throw 'A complete v2.3.1 Windows Builder toolkit is required.'
}
$exeFsPath = Join-Path $gamePath '.hookshot_exefs'
$romFsPath = Join-Path $gamePath 'romfs'
$mainHash = (Get-FileHash -LiteralPath (Join-Path $exeFsPath 'main')).Hash
if ($mainHash -ne '2591fb99008d0814f8056c3f36b36790048ed857ff0ae2bb3a4c1e37b960a4de' -or
    !(Test-Path -LiteralPath $romFsPath -PathType Container)) {
    throw 'The reference game revision and its extracted RomFS are required.'
}

New-Item -ItemType Directory -Path $stagePath | Out-Null
& $python -B -X utf8 (Join-Path $PSScriptRoot 'trainer/shader_size_fix.py') --tools $tools --record (Join-Path $stagePath 'shader-patch')
if ($LASTEXITCODE -ne 0) { throw 'The shader patch failed. See the message above.' }

# Process-scoped environment, so the invoking PowerShell session retains its settings.
$job = [Diagnostics.ProcessStartInfo]::new()
$job.FileName = $python
$job.WorkingDirectory = $tools
$job.UseShellExecute = $false
foreach ($name in @('RX_MARCH', 'RX_VK_ONLY', 'RX_PGO', 'RX_VK_PGO')) {
    $null = $job.Environment.Remove($name)
}
foreach ($pair in @{
    HOOKSHOT_KEEP_BUILD_FILES = '1'
    HOOKSHOT_MINGW = (Join-Path $tools 'llvm-mingw')
    RX_CPM = (Join-Path $tools 'cpm')
    WGPU_NATIVE = (Join-Path $tools 'wgpu-native')
    EMSDK = (Join-Path $tools 'emsdk')
}.GetEnumerator()) {
    $job.Environment[$pair.Key] = $pair.Value
}
if (!$job.Environment['HOOKSHOT_NGX_SDK'] -and (Test-Path -LiteralPath (Join-Path $tools 'ngx-sdk/lib/nvsdk_ngx_s.lib'))) {
    $job.Environment['HOOKSHOT_NGX_SDK'] = Join-Path $tools 'ngx-sdk'
}
foreach ($argument in @('-I','-B','-u','-X','utf8','nx2/make_game.py','--romfs',$romFsPath,
        '--exefs',$exeFsPath,'--out',(Join-Path $stagePath 'base'),'--work',$work,'--jobs',
        $Jobs.ToString(),'--no-prepare-shaders','--log',(Join-Path $stagePath 'builder.log'))) {
    $job.ArgumentList.Add($argument)
}
$compiler = [Diagnostics.Process]::Start($job)
try {
    $compiler.WaitForExit()
    if ($compiler.ExitCode -ne 0) { throw "The upstream build failed with exit code $($compiler.ExitCode)." }
} finally {
    $compiler.Dispose()
}
Write-Output "Retained build is ready in $work"
