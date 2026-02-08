

# Custom ECTOFORM File Format (.ecto)

## Overview

This plan introduces a new **`.ecto`** file format - a single, self-contained file that bundles the 3D model, annotations, and attached images. Only ECTOFORM can open this format, making it the perfect solution for sharing annotated 3D models.

## The Solution: `.ecto` Format

The `.ecto` format is essentially a **renamed ZIP archive** with a specific internal structure. This approach is:

- **Simple to implement** - Uses Python's built-in `zipfile` module
- **Self-contained** - One file contains everything
- **Reliable** - ZIP is a battle-tested format
- **Transparent to users** - They just see a single `.ecto` file

```text
MyModel.ecto (internally a ZIP archive)
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
|  User A: Create & Export  |     |  User B: Open .ecto File  |
+---------------------------+     +---------------------------+
           |                                   |
           v                                   v
  Load 3D file (any format)       Double-click or File > Open
           |                                   |
           v                                   v
  Add annotations + photos        ECTOFORM extracts to temp
           |                                   |
           v                                   v
  Click "Export as .ecto"         Loads model + annotations
           |                                   |
           v                                   v
  Single MyModel.ecto file        Auto-enables Reader Mode
  ready to share!                 (view-only annotations)
+---------------------------+     +---------------------------+
```

## What You'll Get

1. **Single file sharing** - No more ZIP + unzip workflow
2. **All data bundled** - Model, annotations, and photos in one file
3. **Auto Reader Mode** - Recipients see annotations but can't edit
4. **Native OS integration** - Can register `.ecto` extension on Windows/macOS
5. **Any source format** - Works with STL, STEP, OBJ, IGES, 3DM inputs

## Technical Details

### 1. New ECTO Format Handler

Create `core/ecto_format.py`:

```text
class EctoFormat:
    @staticmethod
    def export(mesh, annotations, output_path, source_format='stl'):
        """
        Create .ecto bundle:
        1. Create temp directory
        2. Save mesh as model.{format}
        3. Create annotations.json with reader_mode=True
        4. Copy all attached images to images/
        5. Create manifest.json with metadata
        6. ZIP everything into output_path
        7. Cleanup temp directory
        """
    
    @staticmethod
    def import_ecto(ecto_path):
        """
        Open .ecto bundle:
        1. Extract to temp directory
        2. Read manifest.json for format info
        3. Return (model_path, annotations, reader_mode)
        """
    
    @staticmethod
    def is_ecto_file(file_path):
        """Check if file is a valid .ecto format"""
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

### 3. Update File Loading

Modify `stl_viewer.py` to:
- Accept `.ecto` in the file filter
- Detect `.ecto` extension and use `EctoFormat.import_ecto()`
- Extract to a temp directory, load the model, then load annotations

### 4. Update Sidebar Export

Modify `ui/sidebar_panel.py` to:
- Change "Export with Annotations" to export as `.ecto` format
- Show save dialog with `.ecto` filter
- Call `EctoFormat.export()` with current mesh and annotations

### 5. OS Integration (Optional Enhancement)

For Windows/macOS builds:
- Register `.ecto` file extension with ECTOFORM
- Users can double-click `.ecto` files to open directly

## Files to Create

| File | Purpose |
|------|---------|
| `core/ecto_format.py` | Handle .ecto bundle creation and extraction |

## Files to Modify

| File | Changes |
|------|---------|
| `stl_viewer.py` | Add .ecto to file filters, handle extraction on load |
| `ui/sidebar_panel.py` | Update export button to create .ecto files |
| `core/annotation_exporter.py` | Minor updates for internal bundling |

## Advantages Over Alternatives

| Approach | Pros | Cons |
|----------|------|------|
| **ZIP bundle** | Standard format | Requires manual unzip |
| **glTF/GLB extras** | Industry standard | Complex, limited metadata |
| **Custom binary** | Compact | Hard to debug, version issues |
| **`.ecto` (ZIP-based)** | Single file, easy to implement, debuggable | ECTOFORM-only (which is the goal!) |

## Implementation Notes

- Uses Python's `zipfile` module (no new dependencies)
- Temp extraction uses `tempfile.mkdtemp()` for safety
- Cleanup happens after loading or on app exit
- Format is future-proof with version field in manifest
- Internally uses existing `AnnotationExporter` logic

