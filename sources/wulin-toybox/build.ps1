param([string]$GameDir = $env:WULIN_GAME_DIR)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($GameDir)) { throw 'Pass -GameDir or set WULIN_GAME_DIR.' }
$root = $PSScriptRoot
Add-Type -Path (Join-Path $PSHOME 'Microsoft.CodeAnalysis.dll')
Add-Type -Path (Join-Path $PSHOME 'Microsoft.CodeAnalysis.CSharp.dll')
$refs = [System.Collections.Generic.List[Microsoft.CodeAnalysis.MetadataReference]]::new()
$files = @(Get-ChildItem "$GameDir\dotnet\*.dll") + @(Get-ChildItem "$GameDir\BepInEx\core\*.dll") + @(Get-ChildItem "$GameDir\BepInEx\interop\*.dll") + @(Get-Item "$GameDir\BepInEx\plugins\HaxxToyBox\UniverseLib.IL2CPP.dll")
foreach ($f in $files) {
    try { $null = [System.Reflection.AssemblyName]::GetAssemblyName($f.FullName) } catch { continue }
    $refs.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile($f.FullName))
}
$trees = [System.Collections.Generic.List[Microsoft.CodeAnalysis.SyntaxTree]]::new()
foreach ($f in Get-ChildItem "$root\src" -Recurse -Filter '*.cs') {
    $trees.Add([Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText([System.IO.File]::ReadAllText($f.FullName), [Microsoft.CodeAnalysis.CSharp.CSharpParseOptions]::Default.WithLanguageVersion([Microsoft.CodeAnalysis.CSharp.LanguageVersion]::Latest), $f.FullName))
}
$options = [Microsoft.CodeAnalysis.CSharp.CSharpCompilationOptions]::new([Microsoft.CodeAnalysis.OutputKind]::DynamicallyLinkedLibrary).WithAllowUnsafe($true).WithOptimizationLevel([Microsoft.CodeAnalysis.OptimizationLevel]::Release).WithDeterministic($true)
$compilation = [Microsoft.CodeAnalysis.CSharp.CSharpCompilation]::Create('HaxxToyBox', $trees, $refs, $options)
$assetPath = Join-Path $root 'src\Assets\toybox'
$provider = [System.Func[System.IO.Stream]]{ [System.IO.File]::OpenRead($assetPath) }.GetNewClosure()
$resources = [Microsoft.CodeAnalysis.ResourceDescription[]]@([Microsoft.CodeAnalysis.ResourceDescription]::new('HaxxToyBox.Assets.toybox', $provider, $true))
New-Item -ItemType Directory -Path "$root\build" -Force | Out-Null
$stream = [System.IO.File]::Create("$root\build\HaxxToyBox.dll")
$win32Resources = $compilation.CreateDefaultWin32Resources($true, $false, $null, $null)
try { $result = $compilation.Emit($stream, $null, $null, $win32Resources, $resources) } finally { $stream.Dispose(); $win32Resources.Dispose() }
$result.Diagnostics | Where-Object { $_.Severity -eq 'Error' } | ForEach-Object { $_.ToString() }
if (-not $result.Success) { throw 'Compilation failed; see diagnostics above.' }
Get-FileHash "$root\build\HaxxToyBox.dll"
