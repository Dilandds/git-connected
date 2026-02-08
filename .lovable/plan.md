

# Custom ECTOFORM File Format (.efm)

## Overview

This plan introduces a new **`.efm`** file format - a single, self-contained file that bundles the 3D model, annotations, and attached images. Only ECTOFORM can open this format, making it the perfect solution for sharing annotated 3D models.

## The Solution: `.efm` Format

The `.efm` format is essentially a **renamed ZIP archive** with a specific internal structure. This approach is:

- **Simple to implement** - Uses Python's built-in `zipfile` module
- **Self-contained** - One file contains everything
- **Reliable** - ZIP is a battle-tested format
- **Transparent to users** - They just see a single `.efm` file

```text
MyModel.efm (internally a ZIP archive)
├── manifest.json          # Metadata + format version
├── model.stl              # The 3D geometry (or .obj, etc.)
├── annotations.json       # Annotation data with reader_mode flag
└── images/                # Folder with attached photos
    ├── annotation_1_photo_1.jpg
    └── annotation_2_photo_1.png
```

## Workflow

```text
+---------------------------+     +---------------------------+
|  User A: Create & Export  |     |  User B: Open .efm File   |
+---------------------------+     +---------------------------+
           |                                   |
           v                                   v
  Load 3D file (any format)       Double-click or File > Open
           |                                   |
           v                                   v
  Add annotations + photos        ECTOFORM extracts to temp
           |                                   |
           v                                   v
  Click "Export as .efm"          Loads model + annotations
           |                                   |
           v                                   v
  Single MyModel.efm file         Auto-enables Reader Mode
  ready to share!                 (view-only annotations)
+---------------------------+     +---------------------------+
```

## What You'll Get

1. **Single file sharing** - No more ZIP + unzip workflow
2. **All data bundled** - Model, annotations, and photos in one file
3. **Auto Reader Mode** - Recipients see annotations but can't edit
4. **Native OS integration** - Can register `.efm` extension on Windows/macOS
5. **Any source format** - Works with STL, STEP, OBJ, IGES, 3DM inputs

## Technical Details

### 1. EFM Format Handler

File: `core/efm_format.py`:

```text
class EfmFormat:
    @staticmethod
    def export(mesh, annotations, output_path, source_format='stl'):
        """
        Create .efm bundle:
        1. Create temp directory
        2. Save mesh as model.{format}
        3. Create annotations.json with reader_mode=True
        4. Copy all attached images to images/
        5. Create manifest.json with metadata
        6. ZIP everything into output_path
        7. Cleanup temp directory
        """
    
    @staticmethod
    def import_efm(efm_path):
        """
        Open .efm bundle:
        1. Extract to temp directory
        2. Read manifest.json for format info
        3. Return (model_path, annotations, reader_mode)
        """
    
    @staticmethod
    def is_efm_file(file_path):
        """Check if file is a valid .efm format"""
```

### 2. Manifest Structure

```text
{
    "format_version": "1.0",
    "created_by": "ECTOFORM",
    "created_at": "2025-02-08T12:00:00Z",
    "model_file": "model.stl",
    "model_format": "stl",
    "reader_mode": true,
    "annotation_count": 5,
    "has_images": true
}
```

## Implementation Status: ✅ COMPLETE

| File | Status |
|------|--------|
| `core/efm_format.py` | ✅ Created |
| `stl_viewer.py` | ✅ Updated - .efm support in file dialogs and loading |
| `ui/sidebar_panel.py` | ✅ Updated - Export as .efm button |

## Advantages Over Alternatives

| Approach | Pros | Cons |
|----------|------|------|
| **ZIP bundle** | Standard format | Requires manual unzip |
| **glTF/GLB extras** | Industry standard | Complex, limited metadata |
| **Custom binary** | Compact | Hard to debug, version issues |
| **`.efm` (ZIP-based)** | Single file, easy to implement, debuggable | ECTOFORM-only (which is the goal!) |

