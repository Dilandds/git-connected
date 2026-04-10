

# Realistic Jewelry-Grade Gold Using PBR Material

## Problem
The current gold uses `MeshPhongMaterial` which produces a flat, plasticky yellow. Real gold (like image-11) has tight mirror-like reflections, warm depth in shadows, and visible environment reflections on curved surfaces. Phong shading cannot achieve this — it lacks the physically-based metalness/roughness model needed for metals.

## Solution
Switch from `MeshPhongMaterial` to **`MeshStandardMaterial`** (pygfx's PBR material) for metallic presets. This material has `metalness` and `roughness` properties that simulate real-world metal behavior:
- `metalness=1.0` makes the surface reflect like a metal (tints reflections with the base color, just like real gold)
- `roughness=0.15` gives tight, mirror-like specular highlights with soft falloff

## What Changes

### 1. Update Gold & Silver Presets (`ui/texture_panel.py`)

Add `metalness` and `roughness` fields to preset definitions. Change Gold base color to a warmer, jewelry-accurate tone:

| Preset | color | metalness | roughness | emissive |
|--------|-------|-----------|-----------|----------|
| Gold | `#CFB53B` (old gold) | 1.0 | 0.15 | `#3D2B00` |
| Silver | `#C0C0C0` | 1.0 | 0.1 | `#1A1A1A` |
| Leather | `#8B4513` | 0.0 | 0.8 | (none) |

The `MaterialPresetCard` drag payload will include `metalness` and `roughness` when present.

### 2. Switch to PBR Material in Viewer (`viewer_widget_pygfx.py`)

Update `_apply_material_preset_to_mesh()`:
- When preset has `metalness` field, use `gfx.MeshStandardMaterial` instead of `MeshPhongMaterial`
- Pass `metalness`, `roughness`, `emissive`, `emissive_intensity`
- For non-metallic presets (Leather), fall back to `MeshPhongMaterial`

```python
# For metallic presets (Gold, Silver):
material = gfx.MeshStandardMaterial(
    color="#CFB53B",
    metalness=1.0,
    roughness=0.15,
    emissive="#3D2B00",
    emissive_intensity=0.2,
)
```

### 3. Enhance Accent Lighting (`viewer_widget_pygfx.py`)

Increase accent light count from 2 to 4 and boost intensities for PBR materials (PBR responds differently to light than Phong). Add warm-tinted key light to simulate gold-toned environment reflections:

- Light 3: top-back, intensity 0.5
- Light 4: side accent, intensity 0.4
- Light 5: bottom fill (warm `#FFF5E0`), intensity 0.3
- Light 6: front-high, intensity 0.3

### 4. Update Swatch Generation (`ui/texture_panel.py`)

Adjust the Gold swatch thumbnail gradient to match the new warmer `#CFB53B` base so the card preview looks correct.

## Technical Details

**Files modified:**
- `ui/texture_panel.py` — update preset values, include `metalness`/`roughness` in drag payload
- `viewer_widget_pygfx.py` — use `MeshStandardMaterial` for metallic presets, enhance accent lights

**No new dependencies.** `MeshStandardMaterial` is already part of pygfx.

