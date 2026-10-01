$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Add-Type -Path @(
    (Join-Path $projectRoot 'src\GUI\SearchText.cs'),
    (Join-Path $PSScriptRoot 'SearchTextChecks.cs')
)
[SearchTextChecks]::Run()
