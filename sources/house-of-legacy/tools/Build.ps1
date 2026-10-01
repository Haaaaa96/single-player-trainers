param(
    [string]$GameDir = $env:HOUSE_OF_LEGACY_GAME_DIR,
    [string]$FrameworkDir = $env:BEPINEX5_DIR,
    [string]$Dotnet = 'dotnet'
)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($GameDir)) { throw 'Pass -GameDir or set HOUSE_OF_LEGACY_GAME_DIR.' }
if ([string]::IsNullOrWhiteSpace($FrameworkDir)) { throw 'Pass -FrameworkDir or set BEPINEX5_DIR.' }
$Dotnet = (Get-Command -Name $Dotnet -CommandType Application -ErrorAction Stop).Source
$root = Split-Path $PSScriptRoot -Parent
$managed = Join-Path $GameDir 'House of Legacy_Data\Managed'
$sdk = (& $Dotnet --version).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot read compiler SDK version' }
$compiler = Join-Path (Split-Path $Dotnet -Parent) "sdk\$sdk\Roslyn\bincore\csc.dll"
if (!(Test-Path -LiteralPath $compiler)) { throw 'Compiler not found' }
$output = Join-Path $root 'bin'
New-Item -ItemType Directory -Path $output -Force | Out-Null
$refs = @('mscorlib.dll','netstandard.dll','System.dll','System.Core.dll','UnityEngine.dll',
    'UnityEngine.CoreModule.dll','UnityEngine.IMGUIModule.dll','UnityEngine.InputLegacyModule.dll',
    'UnityEngine.TextRenderingModule.dll','UnityEngine.UI.dll','UnityEngine.UIModule.dll',
    'Assembly-CSharp.dll') | ForEach-Object { Join-Path $managed $_ }
$refs += Join-Path $FrameworkDir 'BepInEx\core\BepInEx.dll'
$refs += Join-Path $FrameworkDir 'BepInEx\core\0Harmony.dll'
$refs += Join-Path $FrameworkDir 'BepInEx\core\Mono.Cecil.dll'
$argsFile = Join-Path $output 'compile.rsp'
$lines = @('/nostdlib+','/target:library','/langversion:latest','/optimize+',
    '/deterministic+','/utf8output', ('/out:"' + (Join-Path $output 'HouseOfLegacyTrainer.dll') + '"'))
foreach ($r in $refs) { if (!(Test-Path -LiteralPath $r)) { throw "Missing reference: $r" }; $lines += '/reference:"' + $r + '"' }
$sources = @(Get-ChildItem -LiteralPath (Join-Path $root 'src') -Filter '*.cs' -File | Sort-Object Name)
if ($sources.Count -eq 0) { throw 'No source files' }
$lines += $sources | ForEach-Object { '"' + $_.FullName + '"' }
$lines | Set-Content -LiteralPath $argsFile -Encoding utf8
& $Dotnet $compiler /noconfig "@$argsFile"
if ($LASTEXITCODE -ne 0) { throw "Compiler failed: $LASTEXITCODE" }
Get-FileHash -LiteralPath (Join-Path $output 'HouseOfLegacyTrainer.dll') -Algorithm SHA256
