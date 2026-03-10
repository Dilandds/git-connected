

# Plan: Freehand Drawing on 3D Object Surface

## Overview

Add a **Draw Mode** to the 3D viewer that lets users draw freehand lines directly on the surface of a 3D model using the mouse. A color picker lets users choose the pen color before or during drawing. Strokes are projected onto the mesh surface via raycasting as the mouse moves.

## Architecture

```text
Toolbar: [...existing buttons...] [🖊 Draw ▼]
                                      ↓ (color picker popup)
                                   [Color swatches + custom]

Draw Mode active:
  - Mouse down on mesh → start new stroke
  - Mouse drag → raycast each move, collect surface points → draw polyline
  - Mouse up → finalize stroke
  - Strokes rendered as pygfx.Line objects on the scene
```

## Implementation

### 1. Add Draw button + color picker to toolbar (`ui/toolbar.py`)

- Add a new `ToolbarButton` "Draw" with a `🖊` icon and a `toggle_draw` signal.
- Add mutual exclusivity with ruler, annotation, and screenshot modes.
- On long-press or dropdown arrow, show a small color picker popup (grid of preset color swatches + a QColorDialog "Custom" option). Store selected color, default `#FF0000` (red).
- Emit `draw_color_changed(str)` signal when color changes.

### 2. Add draw mode to viewer widget (`viewer_widget_pygfx.py`)

- New state: `self.draw_mode = False`, `self._draw_color = '#FF0000'`, `self._draw_strokes = []` (list of pygfx.Line objects), `self._current_stroke_points = []`.
- `enable_draw_mode()` / `disable_draw_mode()`: toggle mode, install/remove event filter (same pattern as annotation mode), disable rotation during draw, show gizmo overlay for camera control.
- `set_draw_color(color: str)`: update pen color.
- Event filter logic:
  - **MouseButtonPress** (left): raycast to mesh surface; if hit, start stroke (`_current_stroke_points = [hit_point]`).
  - **MouseMove** (while button held): raycast each move; if hit, append point to `_current_stroke_points`, update live polyline in scene.
  - **MouseButtonRelease**: finalize stroke, store in `_draw_strokes`.
- Rendering: Use `pygfx.Line` with `pygfx.LineSegmentMaterial` or `pygfx.LineMaterial` (thick line, ~2-3px) with chosen color. Offset points slightly along surface normal to prevent z-fighting.
- `clear_drawings()`: remove all stroke Line objects from scene.
- `undo_last_stroke()`: remove the most recent stroke.

### 3. Wire draw mode in main window (`stl_viewer.py`)

- Connect toolbar `toggle_draw` signal to `_on_toggle_draw()`.
- Connect `draw_color_changed` to `viewer_widget.set_draw_color()`.
- Disable draw mode when switching to ruler/annotation/screenshot.

### 4. Add color picker popup (`ui/draw_color_picker.py` — new file)

- Small `QWidget` popup with a grid of ~12 preset colors (red, blue, green, yellow, orange, purple, white, black, cyan, magenta, pink, brown).
- A "Custom..." button that opens `QColorDialog`.
- Emits `color_selected(str)` signal.
- Styled to match the dark ECTOFORM theme.

## Technical Details

- Raycasting reuses the existing `_screen_to_ray()` and trimesh intersection logic from annotation mode.
- Surface normal offset (~0.1% of model bounding box diagonal) prevents drawn lines from clipping into the mesh.
- Each stroke is a separate `pygfx.Line` object added to the scene, making undo straightforward (remove last Line from scene and list).
- Drawing state is per-viewer (per-tab ready).

### Files to create:
- `ui/draw_color_picker.py`

### Files to modify:
- `ui/toolbar.py` — add Draw button, color picker trigger, signals
- `viewer_widget_pygfx.py` — draw mode logic, stroke rendering, event handling
- `stl_viewer.py` — wire toolbar signals to viewer methods

