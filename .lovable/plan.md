

# Drawing Scale Calibration Mode

## Overview
Add a third workspace mode tab ("Drawing Scale") alongside "3D Viewer" and "Technical Overview". This mode lets users load 2D technical drawings (PDF/JPG/PNG), display them on a canvas surrounded by a graduated ruler frame (cm/mm/inches), and proportionally resize the drawing until a known reference dimension matches the frame graduations. Once calibrated, a measurement ruler allows accurate real-world measurements on the drawing.

## Architecture

```text
┌─────────────────────────────────────────────────────┐
│  [🔲 3D Viewer] [📋 Technical Overview] [📐 Drawing Scale]  │  ← mode bar
├──────────┬──────────────────────────────────────────┤
│          │  ╔══ graduated ruler (cm/mm/in) ══════╗  │
│ Sidebar  │  ║  ┌─────────────────────────┐       ║  │
│          │  ║  │                         │       ║  │
│ - Upload │  ║  │   Drawing (PDF/IMG)     │       ║  │
│ - Scale  │  ║  │   + 1cm reference line  │       ║  │
│   1:1    │  ║  │                         │       ║  │
│   1:2    │  ║  └─────────────────────────┘       ║  │
│ - Unit   │  ╚════════════════════════════════════╝  │
│ - Ruler  │                                          │
│   tool   │                                          │
└──────────┴──────────────────────────────────────────┘
```

## Implementation Steps

### 1. Create `ui/scale_canvas.py` — Graduated frame canvas
- New `QWidget` subclass with a zoomable/pannable image canvas (similar to `ImageCanvas` in technical_overview.py)
- Draws a graduated ruler border around the workspace edges (tick marks every mm, labeled every cm)
- Supports unit switching: cm, mm, inches
- Scale ratio support (1:1, 1:2, etc.) — in 1:2 mode, graduation spacing is halved
- Draws a "1 cm reference line" overlay on the drawing
- Mouse wheel zoom resizes the drawing proportionally (homothetic scaling) relative to the fixed graduated frame
- Accepts PDF/JPG/PNG files via upload or drag-drop
- PDF rendering via `fitz` (PyMuPDF) for first page, same as technical_overview

### 2. Create `ui/scale_ruler_tool.py` — Measurement ruler
- Two-click point-to-point measurement tool on the calibrated drawing
- Calculates real-world distance based on current scale calibration
- Draws a line between two points with distance label in selected units
- Multiple measurements can coexist on canvas
- Clear/undo support

### 3. Create `ui/scale_sidebar.py` — Left sidebar controls
- Upload button (PDF/JPG/PNG)
- Unit selector dropdown (cm / mm / inches)
- Scale ratio selector (1:1, 1:2, 1:5, 1:10, custom)
- "Ruler" toggle button to enable measurement mode
- Reset button to clear drawing and measurements
- Instructions/help text explaining the calibration workflow

### 4. Integrate into `stl_viewer.py` — Third workspace mode
- Add `_mode_scale_btn` ("📐 Drawing Scale") to mode bar alongside existing 3D and Technical buttons
- Add `scale_workspace` as index 2 in `_workspace_stack`
- Wire `_switch_mode("scale")` to show the scale workspace
- Instantiate `ScaleCanvas`, `ScaleSidebar`, connect signals

### 5. Calibration workflow (core logic in scale_canvas)
- User uploads a drawing that contains a known reference dimension
- A 1 cm reference line is displayed on the drawing as a guide
- User drags/scrolls to proportionally resize the drawing until the reference line aligns with the graduated frame markings
- Once aligned, the canvas stores the pixels-per-unit ratio
- The ruler tool then uses this ratio to convert pixel distances to real-world measurements

## Technical Details

**Graduated frame rendering:**
- Use `QPainter` in `paintEvent` to draw tick marks along all 4 edges
- Small ticks every mm, medium ticks every 5mm, large ticks + label every cm
- Scale ratio affects tick spacing: at 1:2, each "1cm" mark represents 2cm real-world
- Screen DPI from `QApplication.primaryScreen().logicalDotsPerInch()` to map physical cm to pixels

**Homothetic (proportional) scaling:**
- Mouse wheel adjusts a `scale_factor` that uniformly scales the drawing
- Drawing always scales from its center point
- The graduated frame stays fixed — only the drawing moves/scales

**Key files:**
- `ui/scale_canvas.py` — new (canvas with graduated frame + drawing display)
- `ui/scale_ruler_tool.py` — new (measurement tool logic)
- `ui/scale_sidebar.py` — new (sidebar controls)
- `stl_viewer.py` — modified (add third mode tab + workspace wiring)

**Dependencies:** No new dependencies — uses PyQt5 QPainter, fitz (already used), and screen DPI APIs.

