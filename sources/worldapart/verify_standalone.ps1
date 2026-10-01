param([string]$Executable = (Join-Path $PSScriptRoot 'release\WorldApartTrainer.exe'))
$ErrorActionPreference = 'Stop'
$Executable = (Resolve-Path -LiteralPath $Executable).Path
$checkRoot = Join-Path $PSScriptRoot ('build\standalone-check-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$programRoot = Join-Path $checkRoot 'isolated-program'
$profileRoot = Join-Path $checkRoot 'isolated-localappdata'
New-Item -ItemType Directory -Path $programRoot, $profileRoot -Force | Out-Null
$copiedExe = Join-Path $programRoot 'WorldApartTrainer.exe'
Copy-Item -LiteralPath $Executable -Destination $copiedExe
$output = Join-Path $checkRoot 'self-test.json'
$start = [Diagnostics.ProcessStartInfo]::new()
$start.FileName = $copiedExe
$start.ArgumentList.Add('--self-test')
$start.ArgumentList.Add($output)
$start.WorkingDirectory = $programRoot
$start.UseShellExecute = $false
$start.CreateNoWindow = $true
$start.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
# Do not uninstall or rename the user's Python. The frozen process must prove
# that all interpreter/module/Tcl/Frida paths point inside its own bundle.
$start.Environment['PATH'] = Join-Path $env:SystemRoot 'System32'
$start.Environment['PYTHONHOME'] = Join-Path $checkRoot 'no-python-home'
$start.Environment['PYTHONPATH'] = Join-Path $checkRoot 'no-python-modules'
$start.Environment['PYTHONNOUSERSITE'] = '1'
$start.Environment['LOCALAPPDATA'] = $profileRoot
$start.Environment.Remove('VIRTUAL_ENV') | Out-Null
$started = Get-Date
$process = [Diagnostics.Process]::Start($start)
if (-not $process.WaitForExit(60000)) {
    throw "Self-test still running after 60 seconds. Inspect process $($process.Id), do not blindly restart it."
}
if (-not (Test-Path -LiteralPath $output)) {
    throw "Self-test produced no report. Exit code: $($process.ExitCode)"
}
$report = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
if ($process.ExitCode -ne 0 -or -not $report.passed) {
    throw "Standalone verification failed: $($report.error)"
}
if ((Get-ChildItem -LiteralPath $programRoot -File).Count -ne 1) {
    throw 'Isolated program folder contains external support files.'
}
[pscustomobject]@{
    Passed = $report.passed
    Executable = $Executable
    SHA256 = (Get-FileHash -LiteralPath $Executable -Algorithm SHA256).Hash
    Bytes = (Get-Item -LiteralPath $Executable).Length
    ElapsedSeconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 2)
    Report = $output
    Tabs = ($report.tabs -join ', ')
} | ConvertTo-Json
