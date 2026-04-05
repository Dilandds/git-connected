

# Fix Gold Material + Add Texture Adjustment Sliders

## Overview
Two changes: (1) Make Gold look like real polished gold instead of flat yellow by using richer colors and emissive warmth. (2) Add adjustment sliders (Scale, Rotation, Roughness, Metalness, Opacity) to the texture panel so users can tweak how textures/materials appear on the model.

## What Changes

### 1. Fix Gold & Silver Presets (`ui/texture_panel.py`)

Update `MATERIAL_PRESETS` with richer values and add `emissive` field:

- **Gold**: color `#B8860B` (DarkGoldenrod), highlight `#FFE066`, specular `#FFD700`, shininess 350, emissive `#3D2B00`
- **Silver**: color `#C0C0C0`, shininess 400, emissive `#1A1A1A`
- **Leather Brown**: unchanged

The `MaterialPresetCard` drag payload will include `emissive` when present.

### 2. Add Texture Settings Sliders (`ui/texture_panel.py`)

Add a "Texture Settings" section after the Clear All button with 5 labeled `QSlider` controls:

| Slider | Range | Default | Purpose |
|--------|-------|---------|---------|
| Scale | 0.1x–10.0x | 1.0 | UV tiling repeat |
| Rotation | 0–360° | 0 | UV rotation |
| Roughness | 0–100% | 50 | Surface roughness |
| Metalness | 0–100% | 0 | Metallic look |
| Opacity | 0–100% | 100 | Transparency |

Each slider has a value label showing the current value. When any slider changes, emit a new `texture_settings_changed = pyqtSignal(dict)` signal with all current slider values.

A small helper `_create_slider_row(label, min_val, max_val, default, suffix)` keeps the code DRY.

### 3. Emissive + Accent Lights in Viewer (`viewer_widget_pygfx.py`)

**Update `_apply_material_preset_to_mesh()`:**
- Pass `emissive` and `emissive_intensity=0.15` to `MeshPhongMaterial` when preset includes `emissive` — this adds warm ambient glow to Gold in shadow areas.

**Add accent lights on preset application:**
- When a material preset is applied, add 2 extra directional lights to the scene (stored as `self._preset_accent_lights`) to create multiple specular highlight bands on curved surfaces.
- Remove these lights when preset is cleared via `remove_texture_from_part`.

**New method `update_texture_settings(settings_dict)`:**
- For UV scale/rotation: re-transform UVs on the currently textured mesh using 2D matrix math.
- For roughness/metalness/opacity: update the active material properties directly.
- Request canvas redraw.

### 4. Wiring (`stl_viewer.py`)

Connect `TexturePanel.texture_settings_changed` → viewer's `update_texture_settings()`.

## Technical Details

**Files modified:**
- `ui/texture_panel.py` — update presets, add sliders section + signal
- `viewer_widget_pygfx.py` — emissive support, accent lights, `update_texture_settings()`
- `stl_viewer.py` — wire `texture_settings_changed` signal

**No new dependencies.**

