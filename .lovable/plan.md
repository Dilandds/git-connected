

# New Image Material Workflow for Presets

## Problem
Image-based presets like Lapis Lazuli currently use PBR material properties (roughness, metalness, emissive, env maps) that distort the image appearance. The Tile Density slider also fails after the first change due to UV caching bugs. The image should look as close to the source file as possible on the 3D surface.

## Approach
Create a dedicated image-material pipeline that prioritizes faithful image reproduction with a flat matte look. Gold, Silver, Glass, and Leather Brown remain unchanged.

## Changes

### 1. viewer_widget_pygfx.py -- New image preset pipeline

**In `_apply_material_preset_to_mesh`** (~line 3685-3795):
- Detect `albedo_map == "image_file"` early, before the metal/glass/fabric material branches
- For image presets, create a `MeshStandardMaterial` with:
  - `metalness=0.0`, `roughness=1.0` (fully matte, no reflections)
  - `color="#FFFFFF"` (white base so the texture map colors are unaltered)
  - No emissive, no env map (these tint/alter the image)
- Call `_apply_image_texture` (new method) instead of `_apply_pbr_texture_maps`
- Store `"image_file": True` in `_material_preset_data` so the slider knows it's an image preset
- Still emit `material_preset_applied` with `category: "fabric"` so the panel shows the right sliders

**New method `_apply_image_texture`**:
- Load the image via `_load_texture_image`
- Apply `_make_seamless` for edge blending
- Cache base UVs on geometry as `_base_texcoords` (same pattern as `_reset_and_scale_texcoords`)
- Scale UVs by `tile_repeat` (default 200)
- Set `material.map` with `wrap="repeat"`
- This method handles both single mesh and Group children

**In `update_texture_settings`** (~line 4077-4087):
- Change the tile density condition from `preset_data.get("image_file")` to check `_material_preset_data.get("image_file")` on the mesh object
- Use `_reset_and_scale_texcoords` which already caches base UVs -- but ensure it works by also storing `_base_texcoords` during initial application (in `_apply_image_texture`)
- After scaling, call `self._renderer.request_draw()` or `self._canvas.request_draw()`

**In `_apply_pbr_texture_maps`** (~line 3819-3835):
- Remove the `image_file` branch entirely since image presets now go through the new pipeline

### 2. ui/texture_panel.py -- Store image_file flag in preset data

**In `MATERIAL_PRESETS` Lapis Lazuli definition** (~line 92-108):
- Add `"tile_repeat": 200` explicitly (already used as default, but make it explicit)
- Add `"image_file": True` flag for easy detection

**In `MaterialPresetCard.mouseMoveEvent`** (~line 260-285):
- Ensure `image_file` and `tile_repeat` are included in the drag payload so the viewer receives them

### 3. viewer_widget_pygfx.py -- Fix _reset_and_scale_texcoords integration

The existing `_reset_and_scale_texcoords` method (line 3946) is correct in design but the tile density block (line 4082) checks `preset_data.get("image_file")` -- however `_material_preset_data` stored on the mesh doesn't include `image_file`. Fix by:
- Storing `"image_file": True` in `mesh_obj._material_preset_data` during image preset application
- Updating the condition to `preset_data.get("image_file", False)`

## Summary of the visual result
- Image presets will render with a pure white matte base, so the texture image colors appear exactly as in the source file
- No environment reflections or emissive tinting will alter the image
- The Tile Density slider will work repeatedly because base UVs are cached during initial application
- Gold, Silver, Glass, and Leather Brown presets are completely unaffected

**Files to edit**: `viewer_widget_pygfx.py`, `ui/texture_panel.py`

