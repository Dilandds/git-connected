#!/usr/bin/env python3
"""
Pre-build texture compression script.

Converts large PNG textures in assets/textures/ to JPEG (quality 85) to reduce
the Windows build size. Also patches hardcoded .png → .jpg paths in
ui/texture_panel.py so the app still finds the files.

Usage (run from repo root before build_windows.ps1):
    python scripts/compress_textures.py

To revert: git checkout assets/textures/ ui/texture_panel.py
"""

import sys
import re
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required: pip install Pillow")

REPO_ROOT = Path(__file__).resolve().parent.parent
TEXTURES_DIR = REPO_ROOT / "assets" / "textures"
TEXTURE_PANEL = REPO_ROOT / "ui" / "texture_panel.py"

MIN_SIZE_BYTES = 500_000   # only compress PNGs larger than 500 KB
JPEG_QUALITY = 85


def compress_textures():
    if not TEXTURES_DIR.exists():
        sys.exit(f"Textures directory not found: {TEXTURES_DIR}")

    png_files = sorted(TEXTURES_DIR.glob("*.png"))
    converted = []

    for png_path in png_files:
        size = png_path.stat().st_size
        if size < MIN_SIZE_BYTES:
            print(f"  skip  {png_path.name} ({size // 1024} KB — below threshold)")
            continue

        jpg_path = png_path.with_suffix(".jpg")
        try:
            img = Image.open(png_path).convert("RGB")
            img.save(jpg_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
            old_kb = size // 1024
            new_kb = jpg_path.stat().st_size // 1024
            saving_kb = old_kb - new_kb
            print(f"  OK    {png_path.name} → {jpg_path.name}  ({old_kb} KB → {new_kb} KB, saved {saving_kb} KB)")
            converted.append((png_path, jpg_path))
        except Exception as exc:
            print(f"  FAIL  {png_path.name}: {exc}")

    return converted


def patch_texture_panel(converted):
    if not converted:
        return

    if not TEXTURE_PANEL.exists():
        print(f"Warning: {TEXTURE_PANEL} not found — skipping reference patch")
        return

    src = TEXTURE_PANEL.read_text(encoding="utf-8")
    patched = src

    for png_path, jpg_path in converted:
        # Replace both forward-slash and backslash forms of the filename
        png_name = png_path.name       # e.g. leather_red.png
        jpg_name = jpg_path.name       # e.g. leather_red.jpg
        patched = patched.replace(png_name, jpg_name)

    if patched != src:
        TEXTURE_PANEL.write_text(patched, encoding="utf-8")
        print(f"\n  Patched {TEXTURE_PANEL.relative_to(REPO_ROOT)}")
    else:
        print(f"\n  {TEXTURE_PANEL.relative_to(REPO_ROOT)} — no changes needed")


def delete_original_pngs(converted):
    total_freed = 0
    for png_path, _ in converted:
        freed = png_path.stat().st_size
        png_path.unlink()
        total_freed += freed
    print(f"\n  Deleted {len(converted)} PNG source files, freed {total_freed // (1024*1024)} MB")


def main():
    print(f"Compressing textures in {TEXTURES_DIR.relative_to(REPO_ROOT)} ...\n")
    converted = compress_textures()

    if not converted:
        print("\nNothing to compress.")
        return

    total_before = sum(p.stat().st_size for p, _ in [(p, j) for p, j in converted])
    # sizes before deletion
    before_mb = sum(p.stat().st_size for p, _ in converted) // (1024 * 1024)
    after_mb  = sum(j.stat().st_size for _, j in converted) // (1024 * 1024)

    patch_texture_panel(converted)

    print(f"\nReplacing original PNGs with JPEGs ...")
    delete_original_pngs(converted)

    print(f"\nDone. Converted {len(converted)} file(s): ~{before_mb} MB → ~{after_mb} MB")
    print("To revert:  git checkout assets/textures/ ui/texture_panel.py")


if __name__ == "__main__":
    main()
