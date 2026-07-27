# Build LYNS360 Education edition for Windows
# Usage: powershell -ExecutionPolicy Bypass -File build_windows_education.ps1

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  LYNS360 Education - Windows Build" -ForegroundColor Cyan
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

# Clean
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

# Build
Write-Host "Building LYNS360 Education EXE..."
pyinstaller stl_viewer_windows_education.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build FAILED" -ForegroundColor Red
    exit 1
}

$exePath = "dist\LYNS360-Education.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "ERROR: EXE not found at $exePath" -ForegroundColor Red
    exit 1
}

$fileInfo = Get-Item $exePath
$sizeMB = [math]::Round($fileInfo.Length / 1MB, 2)
Write-Host ("EXE created: {0} ({1} MB)" -f $exePath, $sizeMB) -ForegroundColor Green

# Read version and produce versioned filename
$Version = (python -c "from core.version import __version__; print(__version__)").Trim()
$VersionedExe = "dist\LYNS360-Education-Setup-$Version.exe"
Copy-Item $exePath $VersionedExe -Force
Write-Host "Versioned EXE: $VersionedExe" -ForegroundColor Green

# Create ZIP
$zipPath = "LYNS360-Education-Windows.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}
Compress-Archive -Path "dist\*" -DestinationPath $zipPath -Force
Write-Host ("ZIP created: {0}" -f $zipPath) -ForegroundColor Green

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Build complete - Education edition" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
