## Problem

The OK / Cancel buttons in the Arrow Color picker (`QColorDialog`) have no visible hover state on Windows. On macOS the native color panel is used and looks fine; on Windows Qt renders its own dialog which inherits the app's dark stylesheet but doesn't define a `:hover` rule for those buttons, so they look flat/dead.

## Fix

Force Qt's own (non-native) color dialog and inject a small stylesheet so OK / Cancel get a proper hover background that matches the rest of the app.

In `ui/arrow_panel.py`, inside `_pick_color()`:

1. Build the dialog explicitly instead of using `QColorDialog.getColor(...)`:
   ```python
   dlg = QColorDialog(QColor(self._arrow_color), self)
   dlg.setWindowTitle(t("arrow.color_title"))   # existing i18n
   dlg.setOption(QColorDialog.DontUseNativeDialog, True)   # consistent across OS
   dlg.setStyleSheet(<dark theme QSS, see below>)
   if dlg.exec_() == QColorDialog.Accepted:
       color = dlg.currentColor()
       ...
   ```

2. The stylesheet only targets `QPushButton` (the OK / Cancel buttons inside the dialog) so the rest of the picker keeps Qt's default look:
   ```css
   QDialog { background-color: <card_background>; color: <text_primary>; }
   QPushButton {
       background-color: <row_bg_standard>;
       color: <text_primary>;
       border: 1px solid <border_standard>;
       border-radius: 6px;
       padding: 6px 16px;
       min-width: 72px;
   }
   QPushButton:hover {
       background-color: <row_bg_hover>;
       border-color: <button_primary>;
   }
   QPushButton:pressed {
       background-color: <button_primary>;
       color: white;
   }
   ```
   Values pulled from `ui/styles.default_theme` so it matches the rest of the app.

## Why this works on Windows

- `DontUseNativeDialog=True` makes Qt render the dialog itself on every OS, so our QSS reliably applies to its child `QPushButton`s (the native Windows dialog ignores stylesheets).
- macOS already uses Qt's dialog (the native macOS color panel is only used in specific cases); the same QSS gives it consistent hover styling too.
- We only override button styling — swatches, hue/sat picker, and spinboxes keep Qt's default rendering.

## Files touched

- `ui/arrow_panel.py` — replace the single `QColorDialog.getColor(...)` call with the explicit dialog + stylesheet block (≈15 lines).

No other files change. No behavior change beyond styling.
