
# Multi-Tab Support for ECTOFORM

## Overview
Add a tab bar to the main window so users can open multiple 3D files simultaneously, each in its own tab with independent viewer, sidebar data, and annotations.

## Architecture

```text
+----------------------------------------------------------+
| ECTOFORM - Tab Bar                                        |
| [Model1.stl  x] [Model2.step  x] [+]                    |
+----------------------------------------------------------+
| Sidebar  |  Toolbar                                       |
|          |  Ruler Toolbar (if active)                     |
|          +-----------------------------------------------+
|          |  3D Viewer + Annotation Panel                  |
|          |  (per-tab content)                             |
+----------------------------------------------------------+
```

## Implementation Plan

### 1. Create a Tab Data class to hold per-tab state
- Create a dataclass or simple class (`TabState`) that stores:
  - `file_path` -- the loaded file
  - `viewer_widget` -- its own `STLViewerWidget` instance
  - `annotation_panel` -- its own `AnnotationPanel` instance
  - `sidebar_data` -- cached mesh data / dimensions for restoring sidebar
  - `annotations` -- list of annotations
  - `ruler_active` / `annotation_mode_active` -- mode flags
  - `mesh` reference

### 2. Add QTabBar to the right container
- Insert a `QTabBar` above the toolbar in the right panel layout
- Style it to match the dark ECTOFORM theme
- Each tab shows the filename with a close button
- A "+" button at the end to open a new file
- When no files are loaded, show a single "Untitled" tab with the drop zone

### 3. Refactor STLViewerWindow to manage multiple tabs
- Replace the single `self.viewer_widget` with a `QStackedWidget` that holds one viewer per tab
- Maintain a list of `TabState` objects (`self.tabs`)
- Track `self.current_tab_index`
- When switching tabs:
  - Save current tab's mode states (ruler, annotation)
  - Hide current viewer, show new tab's viewer
  - Update sidebar panel with the new tab's mesh data
  - Update toolbar state (loaded filename, enabled controls)
  - Restore ruler/annotation mode if it was active on that tab

### 4. Modify file loading to create new tabs
- `upload_stl_file()` and `_load_dropped_file()`: instead of replacing the current model, create a new tab with a fresh `STLViewerWidget` and load the file into it
- If the current tab is empty (no file loaded), reuse it instead of creating a new tab
- Connect all signals (drag-drop, click-to-upload, etc.) for each new viewer widget

### 5. Add tab close functionality
- Close button on each tab removes the tab, destroys its viewer widget, and cleans up state
- If the last tab is closed, create a new empty tab with the drop zone
- Prompt to save unsaved annotations before closing a tab

### 6. Update sidebar to reflect active tab
- When switching tabs, call `self.sidebar_panel.update_dimensions()` with the active tab's cached mesh data
- Clear sidebar if switching to an empty tab

## Technical Details

### Files to modify:
- **`stl_viewer.py`** -- Major refactor: add `QTabBar`, `QStackedWidget`, `TabState` management, modify all file-loading and mode-toggling methods to be tab-aware
- **`ui/styles.py`** -- Add tab bar styling to match the ECTOFORM theme

### Key considerations:
- Each tab gets its own `STLViewerWidget` instance (pygfx context), which may use significant GPU memory -- this is acceptable for a desktop app but worth noting
- Annotation state is per-tab, so switching tabs must save/restore annotations
- Ruler mode measurements are per-tab
- The sidebar panel is shared but updates its content based on the active tab
- Window title updates to show the active tab's filename
