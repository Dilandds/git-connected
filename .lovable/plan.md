# Screenshot mode: keyboard-driven capture, native 3D nav

## New input model

| Action | Input |
|---|---|
| Rotate view | Left-mouse drag (native pygfx) |
| Zoom | Mouse wheel (native pygfx) |
| Draw capture square | **Hold Space + drag mouse** |
| Cancel current draw / exit | Esc |
| On-screen 3D Control gizmo | Hidden in screenshot mode |

## Changes

### 1. `ui/screenshot_overlay.py`
- Add `_space_held` state flag; default cursor = `ArrowCursor`.
- `setFocusPolicy(Qt.StrongFocus)`; call `grabKeyboard()` on `showEvent`, `releaseKeyboard()` on `hideEvent`. This guarantees Space reaches the overlay regardless of focus and prevents Space from triggering focused buttons elsewhere.
- **Mouse forwarding fix:** set `WA_TransparentForMouseEvents = True` by default so left-drag / wheel pass straight to the `QRenderWidget` (pygfx canvas) underneath → native rotate + zoom work unchanged. Flip the attribute to `False` only while `_space_held` is True so rubber-band can be captured.
- `keyPressEvent`:
  - `Space` (ignore auto-repeat): `_space_held = True`, set `WA_TransparentForMouseEvents = False`, set `CrossCursor`.
  - `Esc`: cancel current rubber-band, reset state.
- `keyReleaseEvent`:
  - `Space`: if mid-draw, finalize and emit `region_selected` when size > threshold. Then `_space_held = False`, restore `WA_TransparentForMouseEvents = True`, restore `ArrowCursor`.
- Mouse handlers: only engage rubber-band when `_space_held` is True (otherwise the attribute makes them unreachable anyway — defense in depth).
- Drop the `rotate_callback`/`zoom_callback` plumbing; both now go natively to the canvas.

### 2. `viewer_widget_pygfx.py` → `enable_screenshot_mode()` / `disable_screenshot_mode()`
- Do **not** show `_object_control_overlay` (3D Control gizmo) when entering screenshot mode.
- Do **not** show `_zoom_controls_overlay` either (wheel zoom replaces it).
- Remove the `zoom_callback` / `rotate_callback` arguments passed to `ScreenshotOverlay`.
- Keep `screenshot_mode = True/False` and the existing capture flow intact.
- On `disable_screenshot_mode`, ensure `releaseKeyboard()` is called via overlay's `hideEvent` (already covered).

### 3. UI text — `ui/screenshot_panel.py` + `i18n/en.json` + `i18n/fr.json`
Update `screenshot.instruction`:
- EN: `"Drag to rotate, scroll to zoom. Hold Space and drag to capture a square."`
- FR: `"Glissez pour pivoter, molette pour zoomer. Maintenez Espace et glissez pour capturer un carré."`

## What stays the same
- `region_selected` signal → `_on_screenshot_region_selected` → save pipeline: unchanged.
- Camera math, sensitivity, pygfx TrackballController: unchanged (left-drag now reaches it natively).
- Annotation mode's 3D Control gizmo: untouched.
- Screenshot panel cards, editor, save flow: untouched.

## Risks addressed
- **Event forwarding:** `WA_TransparentForMouseEvents` (not `event.ignore()`) — Qt-guaranteed pass-through to the canvas.
- **Focus fragility:** `grabKeyboard()` while screenshot mode is active.
- **Space collisions:** `grabKeyboard()` intercepts Space globally only while the overlay is visible, and releases on exit — no leakage to focused buttons/toolbar.
