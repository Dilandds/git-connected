## Problem

Switching from screenshot mode back to render mode feels laggy when the screenshot panel has captured images. The cause is in `ui/screenshot_panel.py` — each `ScreenshotCard` re-scales the **full-resolution** captured pixmap with `Qt.SmoothTransformation` every time the card receives a `resizeEvent`. When the right panel stack hides / switches widgets, every card resizes, so Qt does a high-quality downscale of every full-res screenshot synchronously on the UI thread. With several captures (each potentially multi-megapixel), this stalls the transition.

Lines involved:
- `ScreenshotCard._update_thumbnail` (l. 186–189) — rescales `self.pixmap` (the full-res capture) on every call.
- `ScreenshotCard.resizeEvent` (l. 191–193) — calls `_update_thumbnail` on every resize tick, with no debounce and no size check.

## Fix

Edit only `ui/screenshot_panel.py`:

1. **Cache a downscaled thumbnail** on the card. Pre-scale the full-res pixmap once to a reasonable max size (e.g. 512 px on the long edge) and store as `self._thumb_source`. Use that as the source for `_update_thumbnail` rescales — Qt's smooth scale on a 512 px source is effectively instant.
2. **Skip redundant rescales** in `_update_thumbnail`: only rescale when the target width actually changed since the last scale; cache the last-produced pixmap.
3. **Refresh the cached source** in `_on_pixmap_updated` (after the editor returns) so edits stay reflected.
4. Optional micro-fix: keep `Qt.SmoothTransformation` but apply it to the cached small source so it stays cheap.

No changes to `stl_viewer.py`, the viewer widget, or the overlay — the transition logic itself is already minimal (`_exit_screenshot_mode` already skips `reframe_for_viewport`). This is purely a UI rendering cost in the panel that gets hidden.

## Why this is the right fix

- The lag scales with number and resolution of captured screenshots — matches the user's "image assets" suspicion.
- `request_draw()` on the canvas is already cheap; the heavy work is Qt repainting/resizing the cards as the stacked widget swaps.
- Caching a small thumbnail source eliminates the per-resize full-res `scaled()` call without changing any visible behavior.

## Out of scope

- No changes to capture resolution (`SCREENSHOT_CAPTURE_SCALE`) — full-res is still kept on `self.pixmap` for save/edit.
- No changes to mode-switch flow in `stl_viewer.py`.
