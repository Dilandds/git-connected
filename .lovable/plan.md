

## Multi-Language Support (English/French) for ECTOFORM

### Overview
Add internationalization (i18n) to the entire ECTOFORM PyQt5 desktop application with a toggle button for English/French, placed left of the Help button in the mode bar.

### Approach: JSON-based i18n module
PyQt5 has a built-in `QTranslator` system, but it requires `.ts`/`.qm` compilation tooling. A simpler, more maintainable approach for two languages is a lightweight custom i18n module using JSON translation files — no extra dependencies needed.

### Files to create

1. **`i18n/__init__.py`** — Core translation engine
   - `_current_lang = "en"` state variable
   - `t(key: str) -> str` function that looks up a dotted key (e.g. `"sidebar.upload"`) in the current language dictionary
   - `set_language(lang: str)` to switch and notify listeners
   - `on_language_changed(callback)` to register UI refresh callbacks
   - Load translations from JSON files

2. **`i18n/en.json`** — English translations (all UI strings)

3. **`i18n/fr.json`** — French translations

### Structure of translation keys
Organized by UI module:
```text
mode_bar.3d_viewer, mode_bar.technical, mode_bar.drawing_scale, mode_bar.help
sidebar.upload_title, sidebar.dimensions, sidebar.surface_area, sidebar.weight, ...
toolbar.grid, toolbar.theme, toolbar.ruler, toolbar.annotate, ...
help.title, help.subtitle, help.q1, help.a1, ...
annotation.panel_title, annotation.clear_all, ...
screenshot.panel_title, screenshot.capture, screenshot.save, ...
texture.panel_title, texture.upload, ...
technical.title, technical.upload, technical.export, ...
scale.title, ...
common.save, common.cancel, common.delete, common.close, common.yes, common.no, ...
```

### Files to modify

4. **`stl_viewer.py`** — Mode bar changes:
   - Add a language toggle button (`🇬🇧`/`🇫🇷` or `EN`/`FR`) to the left of the Help button
   - On click, call `i18n.set_language()` to toggle between `"en"` and `"fr"`
   - Register a `_retranslate_ui()` callback that updates all mode bar button texts
   - Pass i18n refresh down to child widgets

5. **`ui/sidebar_panel.py`** — Replace all hardcoded English strings with `t()` calls; add `retranslate()` method

6. **`ui/toolbar.py`** — Replace button labels/tooltips with `t()` calls; add `retranslate()` method

7. **`ui/help_panel.py`** — Replace `HELP_TOPICS` with language-aware lookup; rebuild cards on language change

8. **`ui/annotation_panel.py`** — Replace labels with `t()` calls

9. **`ui/arrow_panel.py`** — Replace labels with `t()` calls

10. **`ui/parts_panel.py`** — Replace labels with `t()` calls

11. **`ui/screenshot_panel.py`** / **`ui/screenshot_editor.py`** — Replace labels with `t()` calls

12. **`ui/texture_panel.py`** — Replace labels with `t()` calls

13. **`ui/technical_sidebar.py`** / **`ui/technical_overview.py`** — Replace labels with `t()` calls

14. **`ui/scale_sidebar.py`** / **`ui/scale_canvas.py`** — Replace labels with `t()` calls

15. **`ui/converter_dialog.py`** — Replace labels with `t()` calls

16. **`ui/components.py`** — Replace labels in confirmation dialogs, row labels

17. **`ui/ruler_toolbar.py`** — Replace labels with `t()` calls

18. **`ui/license_dialog.py`** / **`ui/passcode_dialog.py`** — Replace labels with `t()` calls

### How the toggle works
- A `QPushButton` labeled `"EN"` or `"FR"` in the mode bar, left of the Help button
- Clicking toggles the language and updates the button text
- Language preference is saved in `QSettings` and restored on startup
- All widgets register a `retranslate()` method via `i18n.on_language_changed(self.retranslate)`

### Implementation order
1. Create `i18n/` module with `en.json`, `fr.json`, and translation engine
2. Add toggle button to mode bar in `stl_viewer.py`
3. Migrate strings in each UI file one-by-one, starting with the mode bar and sidebar, then toolbar, help panel, and remaining panels
4. Each file gets a `retranslate()` method that re-sets all visible text from `t()` calls

