

## Goal
Fix unreadable rulers at scale ratios 1:5 and 1:10 (and prevent the same issue at any future high ratio) by making the tick/label spacing **adaptive to actual pixel density** instead of fixed to the unit.

## Root Cause
In `ui/scale_canvas.py → _draw_ruler_frame()`:
- `pixels_per_unit (ppu)` shrinks linearly with the scale ratio.
- At 1:1 (cm): ~38 px/cm → readable.
- At 1:5 (cm): ~7.5 px/cm → minor mm ticks clamp to 2 px, major labels every ~7.5 px.
- At 1:10 (cm): ~3.78 px/cm → major labels drawn ~4 px apart → black smear.

The label-emission logic assumes fixed `1 cm`, `1 mm`, `1 inch`, `10 cm` major intervals regardless of how visually close that is.

## Fix Strategy

Introduce an **adaptive labeling step** so labels are emitted only when their real-world spacing produces enough on-screen pixels (target: ≥ 40 px between labels).

### Algorithm (per unit)
Compute `label_step_units` from a "nice number" sequence so that `label_step_units * ppu_per_base_unit ≥ MIN_LABEL_PX (40)`:

- **cm**: candidates `[1, 2, 5, 10, 20, 50, 100, 200, 500]` cm
- **mm**: candidates `[1, 2, 5, 10, 20, 50, 100, 200] mm` (label text = value mm or convert to cm if ≥ 100)
- **inches**: candidates `[1, 2, 5, 10, 20, 50] in`
- **m**: candidates `[10, 20, 50, 100, 200, 500] cm` (label text in cm or m if ≥ 100 cm)

Tick hierarchy (3 levels, all derived from chosen `label_step`):
- **Major** (long tick + label) every `label_step`.
- **Medium** (mid tick, no label) every `label_step / 2`.
- **Minor** (short tick) every `label_step / 10` — but only drawn if `≥ 3 px` apart, otherwise skipped.

This guarantees labels never overlap and the ruler stays clean at every ratio (1:1 → 1:10 → 1:100).

### Implementation Changes (single file: `ui/scale_canvas.py`)

1. **Add helper** `_compute_label_step(ppu_per_base_unit) → (step_value, base_unit_name)` that picks the smallest "nice" step so `step * ppu ≥ 40 px`.

2. **Refactor `_draw_ruler_frame()`** to compute:
   - `label_step_px` (pixel spacing between labels)
   - `medium_step_px = label_step_px / 2`
   - `minor_step_px = label_step_px / 10` (skip if `< 3 px`)
   - Pass these + a `format_label(major_idx) → str` callback into the tick drawers.

3. **Refactor `_draw_ruler_ticks_horizontal/vertical()`** to use the new step values and the formatter callback (replaces the hard-coded `"mm"/"m"/"inches"/"cm"` branches inside).

4. **Bonus polish**: use a slightly larger font (`Segoe UI 8`) for major labels at higher steps to keep them legible.

### Files Changed
- `ui/scale_canvas.py` — only file that needs editing.

### Validation
- Switch unit/ratio in the Drawing Scale workspace and verify:
  - 1:1 cm → labels every 1 cm.
  - 1:5 cm → labels auto-promote to every 5 cm.
  - 1:10 cm → labels auto-promote to every 10 cm.
  - 1:1 mm → labels every 10 mm.
  - 1:10 m → labels every 100 cm or 1 m.
- Confirm no overlapping numbers on top, bottom, left and right rulers at any ratio.

