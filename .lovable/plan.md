

# Add Texture-Mapped Leather with Reference Images

## Summary

Replace the current solid-color Leather Brown preset with a texture-mapped approach using bundled leather texture images (albedo, normal map, roughness map). This will give leather a realistic grain, pores, and wear patterns instead of a flat color.

## What Changes

### 1. Bundle Leather Texture Images

Add three texture images to an `assets/textures/leather/` directory:
- `leather_albedo.jpg` — base color with patchy tan/brown variations
- `leather_normal.jpg` — purple/blue normal map encoding surface grain and wrinkles
- `leather_roughness.jpg` — grayscale map (dark = shiny pore peaks, light = matte valleys)

These can be generated procedurally with numpy/PIL if we want zero external dependencies, or sourced from a CC0 texture library like ambientCG.

### 2. Update Material Application in `viewer_widget_pygfx.py`

In `_apply_material_preset_to_mesh`, add a texture-mapped path for presets that include texture file references:

```python
# When preset has texture maps (e.g. Leather)
if preset_data.get("albedo_map"):
    from PIL import Image
    albedo = np.array(Image.open(albedo_path).convert("RGB"), dtype=np.uint8)
    material.map = gfx.Texture(albedo, dim=2)
    
    # Generate UVs via box projection (reuse existing _generate_box_uvs)
    geom = mesh_obj.geometry
    uvs = self._generate_box_uvs(positions)
    geom.texcoords = gfx.Buffer(uvs)

if preset_data.get("normal_map"):
    normal = np.array(Image.open(normal_path).convert("RGB"), dtype=np.uint8)
    material.normal_map = gfx.Texture(normal, dim=2)
    material.normal_scale = (1.0, 1.0)

if preset_data.get("roughness_map"):
    rough = np.array(Image.open(rough_path), dtype=np.uint8)
    material.roughness_map = gfx.Texture(rough, dim=2)
```

### 3. Update Leather Preset in `ui/texture_panel.py`

Add texture map paths to the Leather Brown preset definition:

```python
{
    "name": "Leather Brown",
    "color": "#8B4513",
    "metalness": 0.0,
    "roughness": 1.0,        # base roughness multiplied by map
    "emissive": "#1A0A02",
    "env_tone": "warm",
    "albedo_map": "leather/leather_albedo.jpg",
    "normal_map": "leather/leather_normal.jpg",
    "roughness_map": "leather/leather_roughness.jpg",
}
```

### 4. Include Texture Map Paths in Drag Payload

Update `MaterialPresetCard` drag payload in `texture_panel.py` to include the `*_map` keys so the viewer receives them during drop.

### 5. Generate Procedural Leather Textures (fallback)

Add a helper in `viewer_widget_pygfx.py` that generates leather-like textures procedurally using numpy/Perlin noise if the image files aren't found. This ensures it works in PyInstaller bundles without external files.

## Technical Details

- **Files modified**: `viewer_widget_pygfx.py`, `ui/texture_panel.py`
- **Files added**: `assets/textures/leather/` (3 images, or procedural generation)
- **PyInstaller**: Update `.spec` files to bundle `assets/textures/` directory
- **No new dependencies** — uses PIL (already imported) and numpy for procedural fallback
- **Existing UV generation** (`_generate_box_uvs`) is reused for texture coordinate mapping

## Open Question

Do you want to use bundled CC0 texture images from a library like ambientCG, or should we generate all leather textures procedurally with numpy so there are zero external image files to manage?

