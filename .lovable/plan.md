# Fix: Annotation mode still active after switching to Screenshot mode

## Root cause

In `ui/toolbar.py` (`_on_screenshot_clicked`, line ~1042), when the user turns Screenshot mode on while Annotation mode is already on, the toolbar silently clears its own `annotation_mode_enabled` flag and visually deactivates the button — **without emitting `toggle_annotation`**.

Then in `stl_viewer.py` `_toggle_screenshot_mode` (line 2084):

```python
if self.toolbar.annotation_mode_enabled:   # already False — skipped
    self._exit_annotation_mode()
```

So `_exit_annotation_mode()` → `vw.disable_annotation_mode()` never runs. The annotation event filter stays installed on the canvas, the `annotation_mode = True` flag on the viewer stays set, and every left-click on the mesh still drops an annotation pin — even though the screenshot overlay is up.

The same bug exists symmetrically in `_on_annotation_clicked` (line ~951): turning Annotation on while Screenshot is on clears the toolbar flag silently, so `_exit_screenshot_mode()` is never called.

## Fix

Make the handlers in `stl_viewer.py` rely on the **viewer's own state** (`vw.annotation_mode` / `vw.screenshot_mode`), not the toolbar flag — the toolbar flag is the thing that gets prematurely cleared.

### `stl_viewer.py` — `_toggle_screenshot_mode` (~line 2084)

Replace:
```python
if self.toolbar.annotation_mode_enabled:
    self._exit_annotation_mode()
```
with:
```python
if getattr(vw, 'annotation_mode', False):
    self._exit_annotation_mode()
```

### `stl_viewer.py` — `_toggle_annotation_mode` (~line 1731)

Replace the comment block + call so it triggers based on viewer state:
```python
if getattr(vw, 'screenshot_mode', False):
    self._exit_screenshot_mode()
```

## Why this fix

- Single source of truth becomes the viewer widget's actual mode flag, which only `disable_*_mode()` clears. The toolbar's premature flag clearing no longer hides the transition from us.
- No toolbar changes needed — the visual button state stays correct and the dependent handler still fires.
- Symmetrical: also fixes the reverse case (screenshot active → enabling annotation didn't tear down the screenshot overlay/event filter properly).

## What stays the same

Screenshot overlay, Space-to-capture input model, annotation pin pipeline, panel switching — all untouched. This is a two-line behavioral fix in the two toggle handlers.
