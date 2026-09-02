# Build LYNS360 Lite edition for Windows
# Usage: powershell -ExecutionPolicy Bypass -File build_windows_lite.ps1

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  LYNS360 Lite - Windows Build" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# Ensure PyInstaller is installed
try {
    pyinstaller --version | Out-Null
} catch {
    Write-Host "Installing PyInstaller..."
    pip install "pyinstaller>=6.0.0"
}

# Icon generation (reuse commercial icons)
if ((Test-Path "assets/logo.png") -and (-not (Test-Path "assets/icon.ico"))) {
    Write-Host "Generating icons from logo..."
    python scripts/convert_logo_to_icons.py 2>&1 | Out-Null
}

# Download the Microsoft VC++ 2015-2022 x64 redistributable installer if we
# don't already have a cached copy. It gets bundled into the app as a
# silent, automatic self-repair fallback for rhino3dm's "DLL load failed"
# error on machines missing that runtime (see core/vcredist_repair.py).
if (-not (Test-Path "assets\vc_redist.x64.exe")) {
    Write-Host "Downloading vc_redist.x64.exe..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri "https://aka.ms/vs/17/release/vc_redist.x64.exe" -OutFile "assets\vc_redist.x64.exe"
}

# Clean
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

# Build
Write-Host "Building LYNS360 Lite EXE..."
pyinstaller stl_viewer_windows_lite.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build FAILED" -ForegroundColor Red
    exit 1
}

$exePath = "dist\LYNS360-Lite.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "ERROR: EXE not found at $exePath" -ForegroundColor Red
    exit 1
}

$fileInfo = Get-Item $exePath
$sizeMB = [math]::Round($fileInfo.Length / 1MB, 2)
Write-Host ("EXE created: {0} ({1} MB)" -f $exePath, $sizeMB) -ForegroundColor Green

# Read version and produce versioned filename
$Version = (python -c "from core.version import __version__; print(__version__)").Trim()
$VersionedExe = "dist\LYNS360-Lite-Setup-$Version.exe"
Copy-Item $exePath $VersionedExe -Force
Write-Host "Versioned EXE: $VersionedExe" -ForegroundColor Green

# Create ZIP
$zipPath = "LYNS360-Lite-Windows.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}
Compress-Archive -Path "dist\*" -DestinationPath $zipPath -Force
Write-Host ("ZIP created: {0}" -f $zipPath) -ForegroundColor Green

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Build complete - Lite edition" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
