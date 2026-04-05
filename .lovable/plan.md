

# Add Material Presets + Keep Upload Textures

## Overview
Add 3 predefined material preset cards (Gold, Silver, Leather Brown) to the texture panel in a "Materials" section, while keeping the existing "Upload Texture" functionality intact below it. Material presets are draggable onto model parts just like uploaded textures, but apply a colored phong material with shininess instead of an image texture.

## What Changes

### 1. Texture Panel — Materials Section (`ui/texture_panel.py`)

Add a **"Materials"** label and a 2-column grid of 3 preset cards between the banner and the "Upload Texture" button. Each card shows a programmatically generated sphere swatch (QPainter + QRadialGradient) with a label underneath.

**Presets:**
- **Gold** — base `#D4AF37`, highlight `#FFF8DC`, shininess 250, specular `#FFD700`
- **Silver** — base `#C0C0C0`, highlight `#FFFFFF`, shininess 300, specular `#FFFFFF`
- **Leather Brown** — base `#8B4513`, highlight `#C4956A`, shininess 10, specular `#3D2B1F`

New class `MaterialPresetCard(QFrame)` — similar styling to `TextureCard` but:
- No delete button (presets are permanent)
- Drag MIME type: `application/x-ectoform-material-preset` with JSON payload `{"color": "#D4AF37", "specular": "#FFD700", "shininess": 250}`
- Generated sphere swatch as thumbnail (no external images needed)

Panel layout order becomes: Banner → "Materials" label + preset grid → "Upload Texture" button → uploaded textures grid → Clear All button.

### 2. Swatch Generation (`ui/texture_panel.py`)

Helper function `_generate_material_swatch(base_color, highlight_color, size=80)`:
- Creates a `QPixmap` with dark `#2a2a2a` background
- Draws a sphere using `QRadialGradient` with highlight at top-left, base color at middle, darkened base at edges
- Returns the `QPixmap` for use in the card thumbnail

### 3. Viewer Handles Material Presets (`viewer_widget_pygfx.py`)

**New method: `apply_material_preset_to_part(part_id, color, specular, shininess)`**
- Creates `MeshPhongMaterial` with the given `color`, `specular`, and `shininess`
- Stores original material for revert (same pattern as `apply_texture_to_part`)
- Requests canvas redraw

**Update `dropEvent`**: Check for `application/x-ectoform-material-preset` MIME type first. If present, parse JSON and call `apply_material_preset_to_part`. Otherwise fall through to existing image texture logic.

### 4. Wiring (`stl_viewer.py`)

No new wiring needed — drag-and-drop already goes directly from card to viewer widget via Qt drag/drop. The viewer's `dropEvent` just needs to handle the new MIME type.

## Technical Details

**Files modified:**
- `ui/texture_panel.py` — add `MaterialPresetCard`, `_generate_material_swatch()`, preset grid in `_init_ui`
- `viewer_widget_pygfx.py` — add `apply_material_preset_to_part()`, update `dropEvent` to check for material preset MIME

**No new dependencies.** Uses existing PyQt5 QPainter for swatches and pygfx `MeshPhongMaterial` for rendering.

