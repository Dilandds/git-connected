

# Screenshot Mode for ECTOFORM

## Overview
Add a "Screenshot" toolbar button that enters a mode where users draw a rectangular frame on the 3D view, then validate to capture that region. Captured screenshots appear in a panel on the right (similar to the annotation panel), each with Delete and Save actions.

## Architecture

```text
Toolbar: [...existing buttons...] [📷 Screenshot] [...]

Screenshot mode active:
+------------------------------------------+-----------------+
|  3D Viewer                               | Screenshot      |
|  (draw rectangle with mouse)             | Panel           |
|  ┌─────────────┐                         |                 |
|  │  selection   │  ← rubber-band overlay | [Screenshot 1]  |
|  └─────────────┘                         |   Delete | Save |
|                                          | [Screenshot 2]  |
|                                          |   Delete | Save |
+------------------------------------------+-----------------+
```

## Files to Create

### 1. `ui/screenshot_panel.py` — New file
A sidebar panel (similar to `AnnotationPanel`) that:
- Shows a scrollable list of `ScreenshotCard` widgets
- Each card displays a thumbnail of the captured image
- Clicking a card shows two buttons: **Delete** and **Save**
  - **Delete**: confirmation dialog "Are you sure to delete the photo?" → removes card
  - **Save**: `QFileDialog.getSaveFileName` to choose location and filename, saves the image
- Header with "Screenshots" title and instruction text
- Clear-all button
- `exit_screenshot_mode` signal

### 2. `ui/screenshot_overlay.py` — New file
A transparent overlay widget placed over the 3D viewer canvas:
- Captures mouse press → drag → release to define a rectangle
- Draws the rubber-band rectangle with a semi-transparent blue border and fill
- On mouse release, emits `region_selected(QRect)` signal with the selected region
- Supports canceling with Escape key

## Files to Modify

### 3. `ui/toolbar.py`
- Add `toggle_screenshot = pyqtSignal()`
- Add `screenshot_mode_enabled` state flag
- Add `📷 Screenshot` button between Annotate and Fullscreen
- `_on_screenshot_clicked()`: toggles mode, disables ruler/annotation if active, emits signal
- Add `reset_screenshot_state()` method

### 4. `stl_viewer.py`
- Add `screenshot_mode_active` flag to `TabState`
- Add `screenshot_panel` to `TabState` (or use a shared panel)
- Create `screenshot_stack` (QStackedWidget) alongside `annotation_stack` in the right layout
- Connect `toolbar.toggle_screenshot` → `_toggle_screenshot_mode()`
- `_toggle_screenshot_mode()`:
  - Shows/hides the screenshot panel and overlay
  - Disables ruler/annotation if active
- `_on_screenshot_captured(pixmap)`:
  - Grabs the viewer widget's framebuffer within the selected rect using `QWidget.grab(rect)`
  - Passes the `QPixmap` to the screenshot panel
- Handle tab switching: save/restore screenshot mode state
- Wire screenshot panel signals (delete, save)

### 5. `viewer_widget_pygfx.py`
- Add `enable_screenshot_mode()` / `disable_screenshot_mode()` methods
- Install the screenshot overlay widget on top of the canvas
- When overlay emits `region_selected(QRect)`, grab that region from the canvas using `self._canvas.grab(rect)` and emit a `screenshot_taken(QPixmap)` signal

## Implementation Details

**Rubber-band selection**: The overlay widget is a transparent `QWidget` placed over the viewer. It uses `paintEvent` to draw the selection rectangle during mouse drag. On release, it computes the rect relative to the canvas and triggers the capture.

**Capture method**: `QWidget.grab(QRect)` on the pygfx canvas widget captures exactly what's visible in the selected region.

**Screenshot storage**: Screenshots are stored as `QPixmap` objects in a list on the screenshot panel. They are not persisted to disk unless the user explicitly saves them.

**Panel behavior**: The screenshot panel appears on the right side (same position as annotation panel) when screenshot mode is active. Only one mode panel is visible at a time.

**Delete flow**: Click Delete → `QMessageBox.question("Are you sure to delete the photo?")` → Yes removes the card.

**Save flow**: Click Save → `QFileDialog.getSaveFileName(filter="PNG (*.png);;JPEG (*.jpg)")` → `pixmap.save(path)`.

