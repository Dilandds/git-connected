# Build script for Windows EXE distribution
# Creates standalone .exe file using PyInstaller

$ErrorActionPreference = "Stop"

Write-Host "Building LYNS360 for Windows..." -ForegroundColor Cyan

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Check if PyInstaller is installed
$pyinstallerCmd = Get-Command pyinstaller -ErrorAction SilentlyContinue
if ($null -eq $pyinstallerCmd) {
    Write-Host "PyInstaller not found. Installing..." -ForegroundColor Yellow
    pip install pyinstaller>=6.0.0
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to install PyInstaller" -ForegroundColor Red
        exit 1
    }
}
else {
    Write-Host "PyInstaller found" -ForegroundColor Green
}

# Generate icon files from logo.png if they don't exist
Write-Host "Generating icon files from logo.png..." -ForegroundColor Cyan
if (Test-Path "assets\logo.png") {
    if (-not (Test-Path "assets\icon.ico") -or -not (Test-Path "assets\icon.icns")) {
        python scripts\convert_logo_to_icons.py
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Warning: Icon generation failed, but continuing build..." -ForegroundColor Yellow
        }
    }
    else {
        Write-Host "Icon files already exist, skipping generation." -ForegroundColor Green
    }
}
else {
    Write-Host "Warning: assets\logo.png not found. Icon files may not be available." -ForegroundColor Yellow
}

# Clean previous builds
Write-Host "Cleaning previous builds..." -ForegroundColor Yellow
if (Test-Path "build") {
    Remove-Item -Recurse -Force "build"
}
if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
}

# Build with PyInstaller
Write-Host "Running PyInstaller..." -ForegroundColor Cyan
pyinstaller stl_viewer_windows.spec --clean --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: PyInstaller build failed" -ForegroundColor Red
    exit 1
}

# Check if EXE was created
$ExePath = "dist\LYNS360.exe"
if (-not (Test-Path $ExePath)) {
    Write-Host "Error: EXE not found at $ExePath" -ForegroundColor Red
    exit 1
}

Write-Host "EXE created successfully: $ExePath" -ForegroundColor Green

# Read version from single source of truth and rename to versioned filename
$Version = (python -c "from core.version import __version__; print(__version__)").Trim()
$VersionedExe = "dist\LYNS360-Setup-$Version.exe"
Copy-Item $ExePath $VersionedExe -Force
Write-Host "Versioned EXE: $VersionedExe" -ForegroundColor Green

# Get file size
$FileInfo = Get-Item $ExePath
$SizeMB = [math]::Round($FileInfo.Length / 1MB, 2)
Write-Host "Size: $SizeMB MB" -ForegroundColor Cyan

Write-Host ""
Write-Host "Build complete! File:" -ForegroundColor Green
Write-Host "  - EXE: $ExePath" -ForegroundColor White
Write-Host "  - Versioned: $VersionedExe" -ForegroundColor White
