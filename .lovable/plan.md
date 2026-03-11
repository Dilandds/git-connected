

# Fix: SyntaxError in `ui/toolbar.py`

## Problem
The `_on_draw_clicked()` method is missing its `else` branch and closing lines — they were accidentally merged into a new `reset_draw_state()` method. Also, line 621 (`self.screenshot_btn.set_active(False)`) lost its indentation under the `if self.screenshot_mode_enabled` block.

## Fix (lines 619-631 in `ui/toolbar.py`)

Replace the broken section with the correctly structured code:

```python
            if self.screenshot_mode_enabled:
                self.screenshot_mode_enabled = False
                self.screenshot_btn.set_active(False)
        else:
            self.draw_btn.set_label("Draw ▼")
        self.draw_btn.set_active(self.draw_mode_enabled)
        self.toggle_draw.emit()

    def reset_draw_state(self):
        """Reset draw button state (called when exiting draw mode externally)."""
        self.draw_mode_enabled = False
        self.draw_btn.set_label("Draw ▼")
        self.draw_btn.set_active(False)
```

This restores:
1. Proper indentation of `self.screenshot_btn.set_active(False)` inside the `if` block
2. The `else` branch back into `_on_draw_clicked()` (sets label back to "Draw ▼" when toggling off)
3. The emit and active-state lines as part of `_on_draw_clicked()`
4. A clean, separate `reset_draw_state()` method

### Files to modify
- `ui/toolbar.py` — fix lines 619-631

