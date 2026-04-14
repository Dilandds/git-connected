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
        "ECTOFORM-Education-1.0.0-macOS.dmg" \
        "dist/dmg_temp/" || echo "Warning: DMG creation had issues"

    rm -rf dist/dmg_temp
    [ -f "ECTOFORM-Education-1.0.0-macOS.dmg" ] && echo "✓ DMG created" || echo "Warning: DMG not found"
else
    echo "Skipping DMG (install create-dmg via: brew install create-dmg)"
fi

echo ""
echo "=========================================="
echo "  Build complete — Education edition"
echo "=========================================="
