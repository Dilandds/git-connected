#!/bin/bash
# Build ECTOFORM Education edition for macOS
# Usage: ./build_mac_education.sh

set -e

echo "=========================================="
echo "  ECTOFORM Education — macOS Build"
echo "=========================================="

# Ensure pyinstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "Installing PyInstaller..."
    pip install pyinstaller>=6.0.0
fi

# Icon generation (reuse commercial icons)
if [ -f "assets/logo.png" ]; then
    if [ ! -f "assets/icon.icns" ] || [ ! -f "assets/icon.ico" ]; then
        echo "Generating icons from logo..."
        python3 scripts/convert_logo_to_icons.py || echo "Warning: Icon generation failed"
    fi
fi

# Read version from single source of truth
VERSION=$(python3 -c "from core.version import __version__; print(__version__)")
RAW_ARCH=$(uname -m)
if [ "$RAW_ARCH" = "arm64" ]; then ARCH="arm64"; else ARCH="x64"; fi
echo "Version: $VERSION  Arch: $ARCH"

# Clean previous education build
rm -rf build dist ECTOFORM-Education-*.dmg

# Build
echo "Building ECTOFORM Education .app..."
pyinstaller stl_viewer_mac_education.spec --clean --noconfirm

if [ ! -d "dist/ECTOFORM-Education.app" ]; then
    echo "ERROR: .app bundle not found!"
    exit 1
fi

echo "✓ ECTOFORM Education .app created successfully"

DMG_NAME="ECTOFORM-Education-${VERSION}-macOS-${ARCH}.dmg"

# Create DMG (optional)
if command -v create-dmg &> /dev/null; then
    echo "Creating DMG..."
    mkdir -p dist/dmg_temp
    cp -R "dist/ECTOFORM-Education.app" dist/dmg_temp/

    create-dmg \
        --volname "ECTOFORM Education" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --app-drop-link 425 175 \
        --icon "ECTOFORM-Education.app" 175 175 \
        "${DMG_NAME}" \
        "dist/dmg_temp/" || echo "Warning: DMG creation had issues"

    rm -rf dist/dmg_temp
    [ -f "${DMG_NAME}" ] && echo "✓ DMG created: ${DMG_NAME}" || echo "Warning: DMG not found"
else
    echo "Skipping DMG (install create-dmg via: brew install create-dmg)"
fi

echo ""
echo "=========================================="
echo "  Build complete — Education edition"
echo "=========================================="
