

# Immersive Jewelry Gold — Ultra-Realistic Overhaul

## Problem
Current gold is too bright/yellow with greenish shadows. The reference images show dark, high-contrast polished gold: a deep bronze base with white-hot specular bands and chocolate-brown shadows — not "golden yellow."

## What Changes

### 1. Gold Preset Values (`ui/texture_panel.py`)

Replace current Gold preset with the user's specified palette:

| Property | Current | New | Why |
|----------|---------|-----|-----|
| color | `#BF9B30` | `#705421` | Deep bronze base — real gold is actually dark |
| specular | `#FFD700` | `#FFF9E5` | Near-white cream highlights for sharp bands |
| shininess | 400 | 95 | Tight but not mirror-flat — creates the "banded" look |
| emissive | `#8B6914` | `#1A0F00` | Very dark brown — crevices glow warm, not green |
| emissive_intensity | 0.45 | 0.15 | Subtle warmth, not flooding |
| metalness | 1.0 | 1.0 | Keep |
| roughness | 0.12 | 0.10 | Slightly tighter reflections |
| highlight (swatch) | `#FEDD2B` | `#FFF9E5` | Match the new specular |

### 2. Lighting Rig (`viewer_widget_pygfx.py`)

The "immersive" look needs **high-contrast** lighting — few intense lights with low ambient, not 8 warm floods. Replace current 8-light rig with:

- **Key light**: bright white-warm `#FFFAF0`, intensity **3.0**, position `(5, 5, 5)` — creates the dominant highlight band
- **Rim light**: opposing `#FFF5E0`, intensity **2.5**, position `(-5, -2, 5)` — second highlight band
- **Top accent**: `#FFE8D0`, intensity **1.5**, position `(0, 6, -2)` — top reflection
- **Ambient**: `#120A00` (very dark brown), intensity **0.15** — keeps shadows chocolate, not black or green

This high-intensity / low-ambient combo creates the dark-base-with-bright-bands look from the references.

### 3. PBR Material Application (`viewer_widget_pygfx.py`)

Update `_apply_material_preset_to_mesh()` for Gold to also pass `specular` and `shininess` hints. Since we use `MeshStandardMaterial` for metallic presets, the key knobs are `metalness=1.0`, `roughness=0.10`, plus the dark emissive. The high-intensity directional lights do the heavy lifting for the "banded reflection" effect.

### 4. Swatch (`ui/texture_panel.py`)

Update Gold swatch gradient: base `#705421`, highlight `#FFF9E5` — previews the dark-gold-with-bright-band look on the card.

## Technical Details

**Files modified:**
- `ui/texture_panel.py` — Gold preset colors + swatch
- `viewer_widget_pygfx.py` — replace 8-light flood with 3-light high-contrast rig + dark ambient

**Key insight**: The "immersive" look comes from contrast (dark base + intense highlights), not from warm ambient flooding.

