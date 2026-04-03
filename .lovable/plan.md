

# Texture Panel & Drag-to-Apply Textures

## Overview
Add a "Texture" mode to the right-hand panel (alongside Screenshot, Annotation, Arrow, Parts modes) where users can upload images, view them in a grid, and drag-drop them onto 3D model parts to apply as surface textures.

## Architecture

This is a **Python/PyQt5 desktop app** using **pygfx** for 3D rendering. The texture feature follows the same pattern as the existing Screenshot panel.

```text
┌──────────┬─────────────────────┬──────────────┐
│ Sidebar  │   3D Viewer (pygfx) │ Texture Panel│
│          │                     │ (right side) │
│          │   drag texture →    │ [img1] [img2]│
│          │   onto a part       │ [img3] [img4]│
│          │                     │ [UploadBtn] │
└──────────┴─────────────────────┴──────────────┘
```

## Implementation Steps

### 1. Create `ui/texture_panel.py`
- New panel modeled after `ui/screenshot_panel.py`
- Grid of `TextureCard` widgets showing uploaded image thumbnails
- "Upload Texture" button to add images (JPG, PNG, HEIC via existing `core/image_utils.py`)
- Delete button per card
- Each card supports **drag-start** (QDrag with image path as mime data)
- Signal: `exit_texture_mode`

### 2. Add Texture mode to `stl_viewer.py` (main window)
- Add `texture_mode_active` flag to `TabState`
- Create a `texture_stack` (QStackedWidget) and `TexturePanel` instance
- Register it in `right_panel_stack` (alongside annotation, screenshot, arrow, parts)
- Add toolbar button or render-mode menu entry to toggle texture mode
- Wire up enter/exit signals similar to screenshot mode

### 3. Add toolbar entry in `ui/toolbar.py`
- Add a "🎨 Textures" button or menu item under the render mode dropdown
- Emit `texture_mode_toggled` signal

### 4. Add texture application in `viewer_widget_pygfx.py`
- New method: `apply_texture_to_part(part_id, image_path)`
  - Load image as a pygfx `Texture` object
  - Generate UV coordinates for the part mesh (box projection or auto-UV from trimesh)
  - Create a `MeshPhongMaterial` (or `MeshStandardMaterial`) with the texture map
  - Replace the part's material
- New method: `remove_texture_from_part(part_id)` to revert to default material
- Accept drop events on the 3D canvas: detect which part is under the cursor via raycasting (same approach as parts-pick mode), then call `apply_texture_to_part`

### 5. UV coordinate generation
- Most STL/STEP files lack UV coordinates
- Use **trimesh** to auto-generate UVs via box/planar projection
- For each part's trimesh, compute UVs based on bounding box mapping
- Store UVs in the pygfx geometry buffer

## Technical Details

**Drag & Drop flow:**
1. User drags a `TextureCard` from the panel → QDrag with `text/uri-list` or custom mime type containing the image path
2. The pygfx viewer canvas accepts the drop → `dragEnterEvent` / `dropEvent`
3. On drop, raycast to find which part mesh is under the cursor
4. Generate UVs for that part (if not already present), load image as `gfx.Texture`, apply textured material

**pygfx texture application:**
```python
import pygfx as gfx
from PIL import Image
import numpy as np

img = Image.open(image_path).convert("RGB")
tex_data = np.array(img)
texture = gfx.Texture(tex_data, dim=2)
material = gfx.MeshPhongMaterial(map=texture)
part['mesh_obj'].material = material
```

**UV generation (box projection):**
```python
def generate_box_uvs(trimesh_obj):
    verts = trimesh_obj.vertices
    bounds = trimesh_obj.bounds
    size = bounds[1] - bounds[0]
    size[size == 0] = 1.0
    uvs = (verts[:, :2] - bounds[0, :2]) / size[:2]
    return uvs.astype(np.float32)
```

**Key files to modify:**
- `ui/texture_panel.py` — new file
- `ui/toolbar.py` — add texture mode toggle
- `stl_viewer.py` — wire up panel, mode switching, drop handling
- `viewer_widget_pygfx.py` — texture application, UV generation, drop acceptance

**Dependencies:** No new dependencies needed — pygfx, PIL, trimesh, and numpy are already available.

