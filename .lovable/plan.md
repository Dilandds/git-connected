

# Plan: Add DXF File Format Support

## Overview

Add DXF (Drawing Exchange Format) file loading to the 3D viewer. DXF files are commonly used in CAD and can contain 3D geometry. We'll use the `ezdxf` library to parse DXF files and convert 3D entities (meshes, 3D faces, polylines) into trimesh/PyVista meshes.

## Changes

### 1. New file: `core/dxf_loader.py`

A `DxfLoader` class following the same pattern as `IgesLoader`/`StepLoader`:
- `load_dxf(file_path)` → returns `pyvista.PolyData` or raises `ValueError`
- Uses `ezdxf` to read the DXF file
- Extracts 3D geometry from entities: `3DFACE`, `MESH`, `POLYFACE`, `3DSOLID`, `POLYLINE` (3D)
- Converts collected triangles into a PyVista mesh
- Falls back to trimesh if ezdxf fails

### 2. Modify: `viewer_widget_pygfx.py`

- Add `.dxf` to the `supported` tuple (line 370)
- Add a DXF loading branch (after IGES, before OBJ) that calls `DxfLoader.load_dxf()`

### 3. Modify: `viewer_widget.py` and `viewer_widget_offscreen.py`

- Add `.dxf` to supported extensions and DXF loading branch using `DxfLoader`

### 4. Modify: `ui/drop_zone_overlay.py`

- Add `.dxf` to the accepted extensions in `dragEnterEvent` and `dropEvent`
- Update helper label text to include "DXF"

### 5. Modify: `stl_viewer.py`

- Add `*.dxf` to the file dialog filter in `upload_stl_file()`

### 6. Modify: `requirements.txt`

- Add `ezdxf>=0.18.0`

### Files to create
- `core/dxf_loader.py`

### Files to modify
- `viewer_widget_pygfx.py` — add DXF to supported formats and loading branch
- `viewer_widget.py` — add DXF loading branch
- `viewer_widget_offscreen.py` — add DXF loading branch
- `ui/drop_zone_overlay.py` — add .dxf to drag/drop and label
- `stl_viewer.py` — add *.dxf to file dialog filter
- `requirements.txt` — add ezdxf

