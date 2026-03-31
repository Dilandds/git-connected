

## Plan: Replace Fragile QPainter Fallback with Simple fillRect

### Problem
`drawRoundedRect` has strict overload resolution on Windows PyQt5 that causes crashes regardless of int/float casting. The rounded corners on a 5px cell are invisible anyway.

### Fix — `ui/toolbar.py`, `_parts_menu_pixmap_fallback()`

Replace the entire function body with a simpler approach that avoids `drawRoundedRect` completely:

```python
from PyQt5.QtCore import QRect

def _parts_menu_pixmap_fallback(size: int) -> QPixmap:
    try:
        if size <= 0:
            size = 10
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0))
        cell = size // 2 - 1          # integer math only
        gap = 1
        for r in range(2):
            for c in range(2):
                x = gap + c * (cell + gap)
                y = gap + r * (cell + gap)
                p.fillRect(QRect(x, y, cell, cell), QColor(0, 0, 0))
        p.end()
        return pm
    except Exception:
        logger.warning("_parts_menu_pixmap_fallback failed", exc_info=True)
        pm = QPixmap(max(size, 10), max(size, 10))
        pm.fill(QColor(0, 0, 0))
        return pm
```

Key changes:
- **All integer arithmetic** — no floats anywhere
- **`fillRect(QRect, QColor)`** instead of `drawRoundedRect` — this overload exists in all PyQt5 versions and has no type ambiguity
- **`QRect` constructed from ints** — guaranteed compatible
- **Ultimate fallback**: if even `fillRect` fails, return a solid black square (still better than crashing)

This produces the same 2×2 grid of black squares visible in the user's screenshot. The 1px rounded corners from `drawRoundedRect` were imperceptible at this size anyway.

### Files changed
- `ui/toolbar.py` — only `_parts_menu_pixmap_fallback()` function (lines 37-59)

