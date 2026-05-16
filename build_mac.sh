#!/bin/bash
# Build script for macOS DMG distribution
# Creates .app bundle and DMG installer

set -e  # Exit on error

echo "Building ECTOFORM for macOS..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo -e "${YELLOW}PyInstaller not found. Installing...${NC}"
    pip install pyinstaller>=6.0.0
fi

# Generate icon files from logo.png if they don't exist
echo "Generating icon files from logo.png..."
if [ -f "assets/logo.png" ]; then
    if [ ! -f "assets/icon.icns" ] || [ ! -f "assets/icon.ico" ]; then
        python3 scripts/convert_logo_to_icons.py
    else
        echo "Icon files already exist, skipping generation."
    fi
else
    echo -e "${YELLOW}Warning: assets/logo.png not found. Icon files may not be available.${NC}"
fi

# Read version from single source of truth
VERSION=$(python3 -c "from core.version import __version__; print(__version__)")
# Detect CPU arch (arm64 on Apple Silicon, x64 on Intel)
RAW_ARCH=$(uname -m)
if [ "$RAW_ARCH" = "arm64" ]; then ARCH="arm64"; else ARCH="x64"; fi
echo "Version: $VERSION  Arch: $ARCH"

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf build dist *.dmg

# Build with PyInstaller
echo "Running PyInstaller..."
pyinstaller stl_viewer_mac.spec --clean --noconfirm

# Check if .app was created
APP_PATH="dist/ECTOFORM.app"
if [ ! -d "$APP_PATH" ]; then
    echo "Error: .app bundle not found at $APP_PATH"
    exit 1
fi

echo -e "${GREEN}✓ .app bundle created successfully${NC}"

# Check if create-dmg is installed
if ! command -v create-dmg &> /dev/null; then
    echo -e "${YELLOW}create-dmg not found. Installing via Homebrew...${NC}"
    if command -v brew &> /dev/null; then
        brew install create-dmg
    else
        echo "Error: Homebrew not found. Please install create-dmg manually:"
        echo "  brew install create-dmg"
        echo ""
        echo "Or create DMG manually using hdiutil"
        exit 1
    fi
fi

# Create DMG
echo "Creating DMG installer..."
DMG_NAME="ECTOFORM-${VERSION}-macOS-${ARCH}.dmg"

# Create a temporary folder for DMG contents
DMG_TEMP="dist/dmg_temp"
rm -rf "$DMG_TEMP"
mkdir -p "$DMG_TEMP"

# Copy .app to temp folder
if [ ! -d "$APP_PATH" ]; then
    echo "Error: Cannot find .app bundle at $APP_PATH"
    exit 1
fi

cp -R "$APP_PATH" "$DMG_TEMP/"

# Verify the app was copied
if [ ! -d "$DMG_TEMP/ECTOFORM.app" ]; then
    echo "Error: Failed to copy .app bundle to temp folder"
    exit 1
fi

# Build create-dmg command with proper syntax
# create-dmg format: create-dmg [options] <output.dmg> <source_folder>
# Use absolute paths for create-dmg (required by create-dmg)
ABS_DMG_TEMP="$(cd "$DMG_TEMP" && pwd)"
ABS_DMG_NAME="$(pwd)/$DMG_NAME"

# Check if icon exists and build command accordingly
ICON_FILE="$APP_PATH/Contents/Resources/icon.icns"

# Build create-dmg command
# Try with window customization first, fall back to basic if AppleScript times out
DMG_ERROR=0
DMG_SCRIPT_ERROR=""

# First attempt: with full customization
if [ -f "$ICON_FILE" ]; then
    create-dmg \
        --volname "ECTOFORM" \
        --volicon "$ICON_FILE" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "ECTOFORM.app" 175 190 \
        --hide-extension "ECTOFORM.app" \
        --app-drop-link 425 190 \
        --hdiutil-quiet \
        "$ABS_DMG_NAME" \
        "$ABS_DMG_TEMP" 2>&1 | tee /tmp/create-dmg-output.log || DMG_ERROR=$?
else
    create-dmg \
        --volname "ECTOFORM" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "ECTOFORM.app" 175 190 \
        --hide-extension "ECTOFORM.app" \
        --app-drop-link 425 190 \
        --hdiutil-quiet \
        "$ABS_DMG_NAME" \
        "$ABS_DMG_TEMP" 2>&1 | tee /tmp/create-dmg-output.log || DMG_ERROR=$?
fi

# Check if AppleScript failed (non-critical - DMG may still be created)
if [ -f /tmp/create-dmg-output.log ] && grep -q "AppleEvent timed out\|Failed running AppleScript" /tmp/create-dmg-output.log; then
    DMG_SCRIPT_ERROR="AppleScript timeout (non-critical)"
fi

# Check if any DMG was created (final or temp)
TEMP_DMG_EXISTS=$(ls -t rw.*.dmg 2>/dev/null | head -1)

# If create-dmg failed and no DMG exists at all, try simpler version without window customization
if [ "$DMG_ERROR" -ne 0 ] && [ ! -f "$ABS_DMG_NAME" ] && [ -z "$TEMP_DMG_EXISTS" ]; then
    echo -e "${YELLOW}Retrying with simpler DMG creation (without window customization)...${NC}"
    if [ -f "$ICON_FILE" ]; then
        create-dmg \
            --volname "ECTOFORM" \
            --volicon "$ICON_FILE" \
            --hdiutil-quiet \
            "$ABS_DMG_NAME" \
            "$ABS_DMG_TEMP" 2>&1 || DMG_ERROR=$?
    else
        create-dmg \
            --volname "ECTOFORM" \
            --hdiutil-quiet \
            "$ABS_DMG_NAME" \
            "$ABS_DMG_TEMP" 2>&1 || DMG_ERROR=$?
    fi
fi

# Clean up log file
rm -f /tmp/create-dmg-output.log

# Clean up temp folder
rm -rf "$DMG_TEMP"

# Check if DMG was created (may have temp name if AppleScript failed)
DMG_CREATED=""
if [ -f "$DMG_NAME" ]; then
    DMG_CREATED="$DMG_NAME"
elif [ -f "$ABS_DMG_NAME" ]; then
    DMG_CREATED="$ABS_DMG_NAME"
else
    # Check for temporary DMG files (create-dmg sometimes creates temp files with pattern rw.PID.*.dmg)
    TEMP_DMG=$(ls -t rw.*.dmg 2>/dev/null | head -1)
    if [ -n "$TEMP_DMG" ] && [ -f "$TEMP_DMG" ]; then
        echo -e "${YELLOW}Found temporary DMG file, renaming to final name...${NC}"
        mv "$TEMP_DMG" "$DMG_NAME"
        DMG_CREATED="$DMG_NAME"
    fi
fi

if [ -n "$DMG_CREATED" ] && [ -f "$DMG_CREATED" ]; then
    echo -e "${GREEN}✓ DMG created successfully: $DMG_CREATED${NC}"
    if [ -n "$DMG_SCRIPT_ERROR" ]; then
        echo -e "${YELLOW}Note: $DMG_SCRIPT_ERROR - DMG is functional but window customization may be missing${NC}"
    elif [ "$DMG_ERROR" -ne 0 ]; then
        echo -e "${YELLOW}Note: DMG was created but some customization may have failed (non-critical)${NC}"
    fi
    echo ""
    echo "Build complete! Files:"
    echo "  - .app bundle: $APP_PATH"
    echo "  - DMG installer: $DMG_CREATED"
else
    echo "Error: DMG creation failed"
    exit 1
fi
