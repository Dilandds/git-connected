

# Annotation Export with Reader Mode

## Overview

This plan implements a comprehensive annotation sharing system that allows ECTOFORM users to export 3D files with annotations, and automatically opens annotated files in **Reader Mode** (view-only). New 3D objects without annotations will have full **Annotation Mode** available.

## Workflow

```text
+---------------------------+     +---------------------------+
|  User A: Create Model     |     |  User B: Receive File     |
+---------------------------+     +---------------------------+
           |                                   |
           v                                   v
  Load new 3D file              Open file with annotations
           |                                   |
           v                                   v
  Enable Annotation Mode        Auto-detect Reader Mode
  (Gray dots -> Black)                         |
           |                                   v
           v                     Display annotations (view-only)
  Export with Annotations        - See all markers (black dots)
  (.annotations.json +           - Hover for tooltips
   images folder)                - Click to view comments/photos
           |                     - Annotation button disabled
           v                                   |
  Share file bundle              Cannot add/edit/delete
  (model + annotations + images)   annotations
+---------------------------+     +---------------------------+
```

## What You'll Get

1. **Enhanced Export**: Export any 3D format (STL, STEP, OBJ, 3DM, IGES) with annotations
2. **Bundled Images**: Photos attached to annotations are copied to a dedicated folder
3. **Automatic Reader Mode**: When opening a file with annotations, ECTOFORM enters read-only mode
4. **Visual Indicators**: Clear UI feedback showing "Reader Mode" status
5. **View-Only Popup**: Clicking annotation dots opens a simplified view (no edit/delete options)

## Technical Details

### 1. Enhanced Annotation Exporter

Update `core/annotation_exporter.py` to:
- Copy attached images to a `{model_name}_annotations/` folder alongside the model
- Store relative paths to images in the JSON sidecar file
- Add a `reader_mode: true` flag to mark files as read-only when shared
- Support all input formats (the sidecar JSON works with any format)

### 2. Reader Mode Detection in Main Window

Modify `stl_viewer.py` to:
- Check for existing annotations when loading a file
- If annotations exist, set a `reader_mode` flag
- Disable the Annotation toolbar button when in Reader Mode
- Show a banner or indicator: "📖 Reader Mode - View Only"

### 3. New Reader-Only Popup

Create `ui/annotation_viewer_popup.py`:
- Simplified popup that shows comment text and photos
- No "Delete" or text editing functionality
- Only a "Close" button
- Used when clicking annotations in Reader Mode

### 4. Annotation Panel Updates

Modify `ui/annotation_panel.py`:
- Add `set_reader_mode(enabled: bool)` method
- In reader mode:
  - Hide "Clear All" button
  - Cards show view-only styling
  - Clicking cards opens the viewer popup (not editor)

### 5. Toolbar Updates

Modify `ui/toolbar.py`:
- Disable "Annotate" button when Reader Mode is active
- Show tooltip: "Annotations are read-only for imported files"

### 6. Export Menu Enhancement

Add an export option in the sidebar that:
- Prompts user to choose output format (STL, OBJ, etc.)
- Bundles model + annotation JSON + images folder
- Shows confirmation with file list

### File Structure for Shared Annotations

When exporting `MyModel.stl` with annotations:

```text
MyModel.stl                       # The 3D model
MyModel.annotations.json          # Annotation data with reader_mode flag
MyModel_annotations/              # Folder for attached images
  ├── annotation_1_photo_1.jpg
  ├── annotation_1_photo_2.png
  └── annotation_3_photo_1.jpg
```

### Reader Mode Flag in JSON

```text
{
  "version": "1.0",
  "reader_mode": true,
  "model_file": "MyModel.stl",
  "annotations": [
    {
      "id": 1,
      "point": [10.5, 20.3, 5.0],
      "text": "Check this edge",
      "is_validated": true,
      "image_paths": ["MyModel_annotations/annotation_1_photo_1.jpg"]
    }
  ]
}
```

## Files to Create

| File | Purpose |
|------|---------|
| `ui/annotation_viewer_popup.py` | Read-only popup for viewing annotations |

## Files to Modify

| File | Changes |
|------|---------|
| `core/annotation_exporter.py` | Add image bundling, reader_mode flag, export all formats |
| `stl_viewer.py` | Detect reader mode on file load, show indicator |
| `ui/annotation_panel.py` | Add reader mode support, disable editing when active |
| `ui/annotation_popup.py` | Minor updates for reader mode compatibility |
| `ui/toolbar.py` | Disable Annotate button in reader mode |
| `ui/sidebar_panel.py` | Add "Export with Annotations" button (optional) |

## Implementation Notes

- The `.annotations.json` sidecar approach already works with all file formats
- Images are copied (not moved) to preserve originals
- Reader Mode is determined by the presence of existing annotations on file load
- Users can still use all other tools (ruler, views, etc.) in Reader Mode

