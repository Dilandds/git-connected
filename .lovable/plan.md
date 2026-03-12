

# Plan: Add File Format Converter Module to Sidebar

## Overview

Add a new "Convert File" card section to the left sidebar panel that provides three conversion options:
- **3DM → STEP**
- **3DM → STL**
- **STEP → STL**

Each option lets the user pick an input file, convert it, and save the output.

## Implementation

### 1. New file: `core/file_converter.py`

A `FileConverter` class with three static methods:

- `convert_3dm_to_step(input_path, output_path)` — loads 3DM via `rhino3dm`, converts geometry to STEP using `cadquery`/OCP's `STEPControl_Writer`
- `convert_3dm_to_stl(input_path, output_path)` — loads 3DM via `Rhino3dmLoader` (already returns PyVista mesh), saves as STL via `mesh.save(output_path)`
- `convert_step_to_stl(input_path, output_path)` — loads STEP via `StepLoader` (already returns PyVista mesh), saves as STL via `mesh.save(output_path)`

Each method returns `True` on success or raises an exception with details.

### 2. Modify: `ui/sidebar_panel.py`

Add a new section method `create_converter_section()` that builds a card with:
- Title: "Convert File" with a 🔄 icon
- Three buttons styled consistently with existing cards:
  - "3DM → STEP"
  - "3DM → STL"  
  - "STEP → STL"
- Each button opens a `QFileDialog` to select the input file (filtered by source format), then a save dialog for the output file, then runs the conversion with a progress indicator and success/error message box.

Insert this section in `init_ui()` between the export annotations section and the stretch (around line 168), so it appears near the bottom of the sidebar.

No dependency on having a model loaded — this is a standalone utility.

### Files to create
- `core/file_converter.py`

### Files to modify
- `ui/sidebar_panel.py` — add `create_converter_section()` method and wire it into `init_ui()`

