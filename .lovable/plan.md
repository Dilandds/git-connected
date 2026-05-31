## Root cause

`ArrowPanel.__init__` calls `self.setFixedWidth(240)`. But the panel is placed inside a `QSplitter` (in `stl_viewer.py`) whose right side is set to `320px` by default. The splitter expands its child widget to 320px, but because the panel itself is locked to 240px, the layout only fills the left 240px and leaves a ~80px empty band on the right — which is the "stretched / misaligned" look in your screenshot: header, cards, info text and bottom buttons all stop at 240px while the dark panel background continues to 320px.

## Fix

In `ui/arrow_panel.py`, replace the fixed width with a minimum width so the panel expands to fill whatever the splitter allocates:

```python
# before
self.setFixedWidth(240)
# after
self.setMinimumWidth(220)
```

That's the only change needed. All children already use `Expanding` size policies, so:
- Header row, info text, cards and bottom buttons will all stretch edge-to-edge
- Splitter still controls the panel's overall width (user can drag it)
- The 220px minimum keeps the panel from collapsing too narrow

## Files touched

- `ui/arrow_panel.py` — one-line change in `__init__`.

No other files change. No layout structure change.
