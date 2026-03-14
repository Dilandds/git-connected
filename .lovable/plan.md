

# Plan: 3D Object Part Selection and Hide/Show

## Overview

Add the ability to select individual parts of a loaded 3D model and hide/show them, allowing users to isolate interior components by hiding exterior parts. This requires preserving sub-meshes as separate pygfx objects instead of merging them into one.

## Current Problem

The viewer currently concatenates all sub-meshes (from STEP scenes, OBJ files, etc.) into a single `trimesh.Trimesh` at line 477 of `viewer_widget_pygfx.py`. This destroys part boundaries. We need to keep them separate.

## Architecture

```text
Scene
 └── _mesh_group (gfx.Group)    ← replaces single _mesh_obj
      ├── Part 0: gfx.Mesh  (visible=True)
      ├── Part 1: gfx.Mesh  (visible=False)  ← hidden by user
      └── Part 2: gfx.Mesh  (visible=True)
```

For single-body files (STL, PLY), there will be just one part in the group.

## Implementation

### 1. Modify mesh loading in `viewer_widget_pygfx.py`

- Instead of concatenating `trimesh.Scene` geometry into one mesh, keep each sub-mesh as a separate `gfx.Mesh` inside a `gfx.Group`.
- Store a list `self._mesh_parts` with metadata: `[{id, name, mesh_obj, trimesh, visible}, ...]`.
- For single-mesh files, create one part named after the filename.
- `self._mesh_obj` becomes `self._mesh_group` (a `gfx.Group`) for backward compatibility with scene add/remove.
- The combined `pv_mesh` and `_annotation_trimesh` are still built from all parts for MeshCalculator and raycasting.

### 2. Add part picking via click

- In a new "select mode" or always-on: when user clicks on the model, use raycasting to determine which sub-mesh was hit.
- Highlight the selected part with a different color or outline.

### 3. Create `ui/parts_panel.py` — Parts List Panel

A right-side panel (similar to `ArrowPanel` / `AnnotationPanel`) containing:

- **Parts list**: Scrollable list showing each part name with:
  - Eye icon toggle button (visible/hidden)
  - Color indicator
  - Click to select/highlight in viewer
- **Bulk actions**: "Show All" / "Hide All" / "Invert Visibility" buttons
- **Selected part info**: Name and face count

### 4. Add toolbar access

- Add a "Parts" option inside the existing Annotate dropdown menu, or add a dedicated "Parts" button if space allows. Given the dropdown pattern already established, adding it to a new "Object" dropdown or the existing Annotate dropdown makes sense.

### 5. Wire into `stl_viewer.py`

- Add `parts_panel` to `TabState`.
- Show/hide the parts panel when toggled.
- Wire visibility toggle signals from the panel to `viewer.set_part_visible(part_id, bool)`.

## Files

| Action | File | Description |
|--------|------|-------------|
| Create | `ui/parts_panel.py` | Parts list panel with visibility toggles |
| Modify | `viewer_widget_pygfx.py` | Preserve sub-meshes as separate parts in a Group; add `set_part_visible()`, `select_part()`, `get_parts_list()` |
| Modify | `stl_viewer.py` | Wire parts panel into tab system |
| Modify | `ui/toolbar.py` | Add "Parts" menu option to access parts mode |

## Key Considerations

- **Single-body files** (most STLs): Will show one part in the list. Still useful for completeness.
- **STEP/OBJ with multiple bodies**: Each body becomes a separate selectable/hideable part.
- **Performance**: Each part is a separate draw call. For models with hundreds of parts this is fine on desktop GPUs.
- **Render mode**: `set_render_mode()` must iterate all parts to update materials.
- **MeshCalculator**: Still uses the combined PyVista mesh for dimensions/volume — unaffected by visibility toggles.

