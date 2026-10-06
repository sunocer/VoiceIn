param([switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

if (-not $SkipInstall) {
    python -m pip install -r .\voicein_windows\requirements-build.txt
}

python -m unittest voicein_windows.test_windows -v
if ($LASTEXITCODE -ne 0) { throw 'Windows tests failed' }

$assetDir = Join-Path $projectRoot 'voicein_windows\assets'
New-Item -ItemType Directory -Force -Path $assetDir | Out-Null
python -c "from voicein_windows.tray import make_icon; make_icon('idle').save(r'$assetDir\voicein.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(256,256)])"
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed' }

python -m PyInstaller --noconfirm --clean .\VoiceIn.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }

$exePath = Join-Path $projectRoot 'dist\VoiceIn-0.1.0-alpha-win-x64.exe'
$hash = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$exePath.sha256" -Encoding ASCII -Value "$hash  VoiceIn-0.1.0-alpha-win-x64.exe"

$stage = Join-Path $projectRoot 'build\release-source'
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null
Copy-Item -LiteralPath .\voicein_windows -Destination $stage -Recurse
Get-ChildItem -LiteralPath (Join-Path $stage 'voicein_windows') -Directory -Filter '__pycache__' -Recurse | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath (Join-Path $stage 'voicein_windows') -File -Filter '*.log' -Recurse | Remove-Item -Force
Copy-Item -LiteralPath @('.\README.md','.\.gitignore','.\VoiceIn.spec','.\build_windows.ps1') -Destination $stage
Get-ChildItem -Path . -File -Filter 'VoiceIn-Windows-MVP*.md' | Copy-Item -Destination $stage
Get-ChildItem -Path . -File -Filter '*VoiceIn-Windows.cmd' | Copy-Item -Destination $stage
Copy-Item -LiteralPath .\docs -Destination $stage -Recurse
Copy-Item -LiteralPath .\.github -Destination $stage -Recurse
$sourceZip = Join-Path $projectRoot 'dist\VoiceIn-0.1.0-alpha-source.zip'
if (Test-Path -LiteralPath $sourceZip) { Remove-Item -LiteralPath $sourceZip -Force }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $sourceZip -CompressionLevel Optimal

Get-Item -LiteralPath $exePath,$sourceZip | Select-Object FullName,Length,LastWriteTime
Write-Host "SHA256: $hash"
