

# Fix Gold Realism: Environment Map + Corrected Color

## The Core Problem

The gold looks like copper/dark bronze because **PBR metals without an environment map have nothing to reflect**. The pygfx docs explicitly state: "for best results you should always specify an environment map when using this material." Without it, `metalness=1.0` just makes the surface dark — it's reflecting black void.

The current approach of adding more lights is a dead end. Real metallic appearance = **reflections**, not more direct lighting.

## Solution

Two changes that will transform the gold from "dark copper" to "bright polished jewelry gold":

### 1. Generate a Procedural Studio Environment Map

Instead of requiring an external HDRI file, create a programmatic warm studio environment texture directly in code. This simulates a jewelry photography light box — bright warm panels with soft gradients.

In `viewer_widget_pygfx.py`, add a method `_create_studio_env_map()` that:
- Creates a 6-face cube texture (256x256 per face) using numpy
- Fills each face with a warm white/cream gradient (simulating studio softboxes)
- Top face: bright white, Bottom face: warm gold-tinted reflection floor
- Side faces: gradient from warm white center to soft gray edges
- Returns a `gfx.Texture(dim=2, size=(256, 256, 6))`

### 2. Apply Environment Map to Metallic Materials

In `_apply_material_preset_to_mesh()`, after creating the `MeshStandardMaterial`:
- Call `_create_studio_env_map()` (cached after first call)
- Set `material.env_map = self._studio_env_tex`
- Set `material.env_map_intensity = 1.0` (full reflection strength)

### 3. Fix Gold Base Color

Change from `#FFC356` (too orange) to `#FFD700` (pure gold) — this is the actual gold hex color. With proper env map reflections, this will read as gold, not copper.

Update in `MATERIAL_PRESETS`:
- Gold color: `#FFD700`
- Roughness: `0.05` (more mirror-like for jewelry)
- Emissive: `#4A3500` (slightly warmer shadow fill)

### 4. Simplify Lighting

Reduce the 10-light rig back to a cleaner 4-light setup. The environment map now handles reflections, so fewer direct lights are needed:
- Key light: intensity 2.0
- Fill light: intensity 1.0
- Rim light: intensity 1.5
- Bottom bounce: intensity 0.5 (warm tint)

Too many direct lights wash out the env map reflections.

## Why This Works

The uploaded reference image shows gold with:
- Bright specular bands (= environment reflections on curved surfaces)
- Deep shadows between tubes (= controlled ambient, not washed out)
- Warm golden tone throughout (= correct base color + warm env map)

Current setup: 10% color + 0% reflections + 90% direct lights = copper
New setup: 10% color + 80% reflections + 10% direct lights = real gold

## Technical Details

**Files modified:**
- `ui/texture_panel.py` — update Gold color to `#FFD700`, roughness to `0.05`
- `viewer_widget_pygfx.py` — add `_create_studio_env_map()`, apply env map in preset method, simplify accent lights to 4

**No new dependencies.** Uses numpy (already imported) for procedural texture generation and pygfx's built-in `env_map` support.

