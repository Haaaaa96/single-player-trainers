param([string]$Python = 'python',
      [string]$OutputDirectory = (Join-Path $PSScriptRoot 'release'))
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& $Python -c 'from release_info import read_feature_introduction; read_feature_introduction()'
if ($LASTEXITCODE -ne 0) { throw 'Every release must include matching feature notes.' }
$buildPython = Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) {
    & $Python -m venv (Join-Path $PSScriptRoot '.build-venv')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create isolated build environment.' }
}
& $buildPython -m pip install --disable-pip-version-check -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Failed to install pinned build dependencies.' }
& $buildPython -m PyInstaller --noconfirm --clean --distpath $OutputDirectory WorldApartTrainer.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
$builtExecutable = Join-Path $OutputDirectory 'WorldApartTrainer.exe'
& $buildPython verify_bundle.py $builtExecutable --output 'build\bundle-source-verification.json'
if ($LASTEXITCODE -ne 0) { throw 'Built EXE does not match the current source/resources.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'RELEASE_NOTES.md') -Destination (Join-Path $OutputDirectory 'README.md') -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'THIRD_PARTY_NOTICES.md') -Destination (Join-Path $OutputDirectory 'THIRD_PARTY_NOTICES.md') -Force
$releaseLicenses = Join-Path $OutputDirectory 'licenses'
New-Item -ItemType Directory -Path $releaseLicenses -Force | Out-Null
foreach ($licenseFile in Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'licenses') -File) {
    Copy-Item -LiteralPath $licenseFile.FullName -Destination (Join-Path $releaseLicenses $licenseFile.Name) -Force
}
Get-FileHash -Algorithm SHA256 -LiteralPath $builtExecutable
