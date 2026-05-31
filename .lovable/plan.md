## Efficiency improvements

Targeted fixes across the four areas you picked, ordered by impact. The biggest win — and the one that fixes your "moving is slow with many annotations" report — is #1.

---

### 1. Render loop: stop raycasting every annotation, every frame  (HIGH impact)

**Problem**: `animate()` in `viewer_widget_pygfx.py` (l. 341–346) runs on every redraw and calls `_update_annotation_label_visibility()`, which loops over every annotation and runs a separate CPU trimesh raycast (`_is_dot_visible`, l. 1956–1980). With N annotations and 60 fps rotation, that's 60 × N raycasts/second on the UI thread — the exact reason rotating slows down as annotations accumulate.

**Fix** (`viewer_widget_pygfx.py`):
- **Batch raycasts**: `trimesh.ray.intersects_location` accepts arrays. Rewrite `_update_annotation_label_visibility` to build one `ray_origins` (camera position repeated) and one `ray_directions` array (one normalized vector per annotation), and call it once instead of N times.
- **Skip during camera motion**: hide labels (or freeze last visibility state) while the trackball controller is actively dragging/zooming, and recompute once on release. Detect motion by hooking the controller's input events or by comparing camera matrix between frames; only run the visibility pass when the camera changed AND no motion happened in the last ~150 ms (QTimer single-shot debounce).
- **Throttle redundant work**: skip the visibility pass entirely when `len(self.annotations) == 0` (already short-circuited) and when the camera matrix hasn't changed since the last pass.

### 2. Mode switching responsiveness  (MEDIUM impact)

- **Lazy-build heavy panels**. Today `_init_ui` creates every right-side panel (annotation, screenshot, texture, parts, arrow…) up front. Convert them to lazy properties so each panel is constructed on first use, then cached. Cuts first-paint cost and switching overhead.
- **Defer `reframe_for_viewport` calls** that are still wired into other mode transitions (annotation/ruler/arrow). They recenter the camera and force a full redraw; only call them when the *viewport size* truly changed, not just when overlay widgets toggle. (We already fixed this for screenshot mode.)
- **Decouple toolbar state from teardown**. Standardize all mode-exit checks on `getattr(vw, '<mode>', False)` (the viewer's truth) instead of `self.toolbar.*_enabled`, which is cleared before the toggle signal — same root cause as the recent draw/annotation bugs. Audit the remaining mode transitions for this pattern.

### 3. 3D viewer rendering  (MEDIUM impact)

- **Single `request_draw`**. ~25 call sites issue `self._canvas.request_draw()`. Add a tiny coalescer: a flag + 0 ms QTimer that fires once per event loop tick, so rapid sequential calls collapse into one draw.
- **Lower idle GPU**. Confirm pygfx isn't re-rendering when nothing changes (auto_update + request_draw should already gate this — verify by logging frame count when idle).
- **Texture compression in preview**. Cap material texture upload size in `texture_panel`/material loader (e.g. max 2K for preview, full-res only during export). Big PBR maps cost both VRAM and upload time.
- **Annotation marker LOD**. When annotation count > ~30, use a single `gfx.Points` cloud for markers instead of one mesh per dot. Labels can be hidden past a distance threshold.

### 4. Memory & image handling  (MEDIUM impact)

- **Generalize the thumbnail cache** we just added in `screenshot_panel.py`: apply the same "pre-scale once, cache, skip if width unchanged" pattern to `annotation_panel`, `arrow_panel`, `parts_panel`, `texture_panel` (any QLabel that does `pixmap.scaled(...)` in `resizeEvent`).
- **Free heavy buffers on tab close**. When a viewer tab is closed, explicitly null out `_annotation_trimesh`, `_mesh_data`, captured screenshot QPixmaps, and call `gc.collect()`.
- **Limit captured screenshot resolution per device**. Keep the current `_SCREENSHOT_MAX_PIXELS` cap but also store an explicit *display* copy (1024 px long edge) separate from the *export* copy; UI always uses display copy.

### 5. Startup & file loading  (LOW–MEDIUM impact)

- **Lazy-import heavy modules**. In `stl_viewer.py` / `main.py`, defer imports of `pygfx`, `trimesh`, format loaders (`step_loader`, `iges_loader`, `rhino3dm_loader`, `dxf_loader`, `obj_loader`, `pdf3d_exporter`, `technical_pdf_exporter`) until the user actually opens a file of that type. Cuts cold-start measurably (pygfx alone pulls wgpu).
- **Splash earlier**. Show the `QSplashScreen` *before* importing `stl_viewer` so it appears within ~200 ms of launch.
- **Cache parsed meshes**. For `.ecto` reopen, keep a small LRU of parsed `trimesh.Trimesh` keyed by file path + mtime; skip re-tessellation when the file is unchanged. (Respects PyInstaller paths via `sys._MEIPASS` rule.)

---

## Suggested implementation order

1. **Annotation render-loop fix** (#1) — biggest perceived win, isolated to `viewer_widget_pygfx.py`.
2. **Coalesced `request_draw` + audit mode-exit checks** (#2, #3 first bullet).
3. **Lazy panels + lazy heavy imports** (#2, #5).
4. **Thumbnail cache generalization + memory cleanup on tab close** (#4).
5. **Texture/material caps + marker LOD** (#3 tail).

Pick which slice you want me to implement first — I'd recommend (1) since it directly addresses the slowdown you actually feel, and we can iterate from there.
