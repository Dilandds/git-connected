

# Group Materials with Context-Specific Controls

## Summary

Split the flat "Materials" grid into two labeled groups — **Metals** (Gold, Silver) and **Fabrics** (Leather Brown) — and dynamically swap the "Texture Settings" sliders based on which group the last-applied preset belongs to.

## What Changes

### 1. Group presets in the UI (`ui/texture_panel.py`)

Replace the single "Materials" grid with two sub-sections:

```text
┌─────────────────────────┐
│  Metals                 │
│  ┌──────┐  ┌──────┐    │
│  │ Gold │  │Silver│    │
│  └──────┘  └──────┘    │
│                         │
│  Fabrics                │
│  ┌──────────┐           │
│  │ Leather  │           │
│  └──────────┘           │
└─────────────────────────┘
```

Add a `"group"` key to each preset definition: `"metals"` or `"fabrics"`.

### 2. Metal-specific sliders (shown when Gold/Silver is active)

- **Shine** (0–100) — maps to roughness (existing)
- **Shadow** (0–100) — maps to emissive intensity (existing)
- **Brightness** (0–100) — maps to env_map intensity (existing)

These are the current 3 sliders — no change in behavior.

### 3. Fabric-specific sliders (shown when Leather is active)

- **Shine** (0–100) — roughness multiplier for the roughness_map (fixed to scale, not override)
- **Shadow** (0–100) — emissive intensity (same)
- **Brightness** (0–100) — env_map intensity (same)
- **Grain Depth** (0–100, default 50) — controls `normal_scale` (0→flat, 50→1.5, 100→3.0)
- **Texture Scale** (1–10, default 3) — controls UV tiling multiplier

### 4. Dynamic slider visibility (`ui/texture_panel.py`)

- Wrap the Grain Depth and Texture Scale rows in a container widget (e.g. `_fabric_controls`).
- On preset application, `sync_material_controls` checks `preset_data.get("group")`:
  - `"metals"` → hide `_fabric_controls`
  - `"fabrics"` → show `_fabric_controls`, reset Grain Depth to 50, Texture Scale to 3
- Store the active group so `_emit_settings` includes `grain_depth` and `texture_scale` only for fabrics.

### 5. Apply controls in viewer (`viewer_widget_pygfx.py`)

In `update_texture_settings`:
- If mesh has a `roughness_map`, treat Shine as a multiplier on `mat.roughness` instead of flat override.
- Read `grain_depth` → set `mat.normal_scale = (val * 0.03, val * 0.03)`.
- Read `texture_scale` → regenerate UVs: `geom.texcoords = gfx.Buffer(base_uvs * scale)`.

## Technical Details

- **Files modified**: `ui/texture_panel.py`, `viewer_widget_pygfx.py`
- **No new files or dependencies**
- Group labels use existing `make_font(size=11, bold=True)` styling
- Slider creation reuses existing `_create_slider_row` helper
- `_emit_settings` extended with optional `grain_depth` and `texture_scale` keys

