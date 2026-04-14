
Goal: fix the Windows bundled texture presets properly, based on how assets are resolved elsewhere in the app, so preset textures load reliably in both Commercial and Education builds.

What I found
- The warning is real and the current fix is incomplete.
- `viewer_widget_pygfx.py` resolves bundled assets correctly using `sys._MEIPASS`, so the loader logic itself is basically fine.
- The actual mismatch is in `ui/texture_panel.py`:
  - `Lapis Lazuli` points to `assets/textures/lapis_lazuli.png`
  - but most other presets still point to top-level paths like `assets/leather_orange.png`
- The PyInstaller specs currently bundle:
  - some selected top-level files in `assets/`
  - the whole `assets/textures/` folder
- Result: anything still referencing `assets/<file>` can fail in the Windows EXE unless that exact top-level file was also individually included.

Implementation plan
1. Normalize preset texture paths
- Update all image-based material presets in `ui/texture_panel.py` so built-in preset files consistently use one bundled location.
- Best path: move all built-in preset references to `assets/textures/<filename>` in code.
- This includes both:
  - `albedo_map_path`
  - `swatch_image`

2. Make swatch/runtime asset resolution use a shared convention
- Add or reuse a small helper for “resolve asset path in dev + PyInstaller”.
- Use that helper in:
  - `_generate_image_swatch()` in `ui/texture_panel.py`
  - `_load_texture_image()` in `viewer_widget_pygfx.py`
- This avoids one-off path joining logic and makes asset behavior match other working helpers like `ui/styles.py` and `ui/annotation_icon.py`.

3. Align bundling with runtime expectations
- Keep the specs bundling `assets/textures` for:
  - `stl_viewer_windows.spec`
  - `stl_viewer_windows_education.spec`
  - `stl_viewer_mac.spec`
  - `stl_viewer_mac_education.spec`
- If the actual image files still live at top-level `assets/` in the repo, add a clean follow-up strategy:
  - either also bundle those top-level preset files explicitly, or
  - preferably move/copy the actual files into `assets/textures/` and keep code/specs consistent.
- Preferred final state: all built-in material images live under `assets/textures/`.

4. Audit every built-in image preset
- Verify every preset in `MATERIAL_PRESETS` points to a file that exists.
- Specifically check the known texture/image set:
  - leathers
  - woods
  - stone
  - brushed metal
  - color presets
  - astro grain
  - pink onyx
  - lapis lazuli
- Also check case sensitivity issues like `Leather_light_blue.png` so macOS/Linux builds stay safe.

5. Verify education restrictions still behave correctly
- Ensure the Education upload restriction remains unchanged:
  - upload button disabled
  - notice shown
- Only built-in preset loading should be fixed.

Technical details
```text
Current mismatch:
code expects:  assets/leather_orange.png
bundle has:    assets/textures/lapis_lazuli.png (+ some selected assets/*)

Safer target state:
code expects:  assets/textures/leather_orange.png
bundle has:    assets/textures/*
resolver uses: shared helper -> base/assets/textures/file
```

Files likely to change
- `ui/texture_panel.py`
- `viewer_widget_pygfx.py`
- Possibly all 4 PyInstaller spec files if we tighten bundling consistency
- Possibly asset file locations under `assets/textures/` if we choose the cleaner consolidation route

Why this is the right fix
- It addresses the root cause: inconsistent asset paths between presets and bundle layout.
- It follows the project’s existing PyInstaller-safe asset pattern instead of relying on fragile one-off additions.
- It should fix both swatch previews and actual texture application, not just one side.

Validation I would do after approval
- Static audit that every preset path resolves to a real bundled file
- Re-check both Windows spec files against the final asset layout
- Confirm no preset still references `assets/<file>` when the bundle only guarantees `assets/textures/*`
- End-to-end test the preset flow in both Commercial and Education builds

<lov-actions>
<lov-suggestion message="Test the preset texture flow end-to-end in both Commercial and Education builds to make sure every built-in material loads correctly">Verify that it works</lov-suggestion>
<lov-suggestion message="Implement the asset-path normalization so all built-in texture presets use a single bundled assets/textures location with shared PyInstaller-safe resolution helpers">Fix preset asset paths</lov-suggestion>
<lov-suggestion message="Audit all material preset image files and clean up any missing files or filename case mismatches so Mac and Windows builds stay consistent">Audit all texture files</lov-suggestion>
<lov-suggestion message="Consolidate all built-in material images into assets/textures and simplify the PyInstaller specs so bundling matches runtime expectations exactly">Consolidate texture assets</lov-suggestion>
<lov-suggestion message="Add a lightweight startup diagnostic log that reports missing built-in material assets by preset name to catch packaging mistakes earlier">Add texture diagnostics</lov-suggestion>
</lov-actions>
