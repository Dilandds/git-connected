

## Plan: Move File Converter from Sidebar to Top Toolbar

### Overview
Move the "Convert File" feature from the left sidebar panel to the top toolbar as a new button that opens a dialog window for file conversion.

### Changes

**1. Create a converter dialog (`ui/converter_dialog.py`)**
- New `QDialog` class containing all the converter UI (source file selector, format dropdown, convert button)
- Move the conversion logic (file selection, format detection, running conversion) from `sidebar_panel.py` into this dialog
- Style it to match the app's dark theme with gradient background
- Emit `conversion_complete` signal when done

**2. Add "Convert" button to toolbar (`ui/toolbar.py`)**
- Add a new `ToolbarButton` (e.g. "🔄", "Convert") in the utility actions section, after the existing buttons
- Add a new signal `open_converter = pyqtSignal()`
- Wire the button click to emit that signal
- This button should always be enabled (converter works independently of loaded model)

**3. Remove converter section from sidebar (`ui/sidebar_panel.py`)**
- Remove `create_converter_section()` and all related methods (`set_conversion_blocked`, `reset_converter`, `set_converter_source_from_file`, `_select_converter_source`, `_run_selected_conversion`, `_run_conversion`)
- Remove the `conversion_complete` signal from SidebarPanel
- Remove the converter card from `init_ui`

**4. Update main window wiring (`stl_viewer.py`)**
- Connect toolbar's `open_converter` signal to open the new `ConverterDialog`
- Connect `ConverterDialog.conversion_complete` to `_load_converted_file`
- Remove all sidebar converter calls (`set_converter_source_from_file`, `set_conversion_blocked`, `reset_converter`)

### Technical Details
- The dialog will be a modal `QDialog` with the same widgets currently in the sidebar card
- Conversion map and `FileConverter` usage stays identical
- The dialog can optionally pre-populate with the current file path if it's a convertible format (3DM/STEP)

