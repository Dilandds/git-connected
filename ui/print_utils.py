"""
Print / PDF-export utility for The Project sections.
Custom in-app print preview with a formatted document renderer for Brief.
"""
import math
from datetime import date
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QScrollArea, QDialog, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QFrame, QFileDialog,
    QMessageBox,
)
from PyQt5.QtCore import QRectF, QRect, Qt
from PyQt5.QtGui import QPainter, QPixmap, QColor, QPen, QFont, QFontMetrics

from ui.styles import default_theme, TOOLTIP_STYLE


# ── Brief document renderer ───────────────────────────────────────────────────

class _BriefRenderer:
    """Paints a formatted, multi-page Brief document into a QPixmap."""

    PW = 1240        # A4 width  @ 150 dpi
    PH = 1754        # A4 height @ 150 dpi
    MX = 76          # horizontal margin
    CW = PW - 2 * MX  # content width = 1088

    _BLUE   = QColor('#2596BE')
    _TEXT   = QColor('#1e2430')
    _MUTED  = QColor('#8899a8')
    _BORDER = QColor('#dce4ec')
    _CELL   = QColor('#f0f7fb')
    _THEAD  = QColor('#2596BE')
    _LIGHT  = QColor('#f8fafc')

    MAX_PAGES = 8   # safety ceiling for canvas allocation

    def __init__(self, data: dict, info: dict):
        self._d = data
        self._i = info
        self._page = 1
        self._pm = QPixmap(self.PW, self.PH * self.MAX_PAGES)
        self._pm.fill(Qt.white)
        self._p = QPainter(self._pm)
        self._p.setRenderHint(QPainter.Antialiasing)
        self._p.setRenderHint(QPainter.SmoothPixmapTransform)
        self._p.setRenderHint(QPainter.TextAntialiasing)
        self._y = 0

    # ── Public ────────────────────────────────────────────────────────────────

    def render(self) -> QPixmap:
        self._start_page()          # page 1 top margin + header
        self._header()
        self._section1_overview()
        self._section2_techniques()
        self._section34_targets_dates()
        self._section5_inspiration()
        self._section6_components()
        self._section7_notes()
        self._footer()

        self._p.end()
        used_pages = max(1, math.ceil(self._y / self.PH))
        return self._pm.copy(0, 0, self.PW, used_pages * self.PH)

    # ── Layout helpers ────────────────────────────────────────────────────────

    def _start_page(self):
        """Jump to the top content margin of the current page."""
        self._y = (self._page - 1) * self.PH + 64

    def _page_break(self):
        """Advance to the next page."""
        self._page += 1
        self._start_page()

    def _ensure_space(self, needed: int):
        """If fewer than `needed` pixels remain on this page, break to next."""
        page_bottom = self._page * self.PH - 72   # leave 72px footer margin
        if self._y + needed > page_bottom:
            self._page_break()

    def _f(self, size: int, bold=False, italic=False) -> QFont:
        f = QFont('', size)
        f.setBold(bold)
        f.setItalic(italic)
        return f

    def _hline(self, color: QColor = None, thickness: float = 1, indent=0):
        c = color or self._BORDER
        self._p.setPen(QPen(c, thickness))
        self._p.drawLine(self.MX + indent, self._y,
                         self.MX + self.CW, self._y)

    def _rect_fill(self, x, y, w, h, color: QColor):
        self._p.fillRect(int(x), int(y), int(w), int(h), color)

    def _rect_border(self, x, y, w, h, color: QColor, thickness=1):
        self._p.setPen(QPen(color, thickness))
        self._p.setBrush(Qt.NoBrush)
        self._p.drawRect(int(x), int(y), int(w), int(h))

    def _draw_text(self, x, y, w, h, text: str, color: QColor,
                   font: QFont, flags=None):
        self._p.setPen(color)
        self._p.setFont(font)
        fl = flags if flags is not None else (Qt.AlignLeft | Qt.AlignVCenter)
        self._p.drawText(QRect(int(x), int(y), int(w), int(h)), fl, str(text))

    def _measure_h(self, text: str, font: QFont, width: int) -> int:
        """Height needed to render text wrapped to width."""
        fm = QFontMetrics(font)
        br = fm.boundingRect(QRect(0, 0, width, 10000),
                             Qt.TextWordWrap, text)
        return max(16, br.height())

    def _section_header(self, num: int, label: str):
        """Draw section title bar, advance _y. Breaks to next page if near bottom."""
        self._ensure_space(100)   # need at least 100px for header + first content line
        self._y += 16
        self._rect_fill(self.MX, self._y, 5, 22, self._BLUE)
        self._draw_text(self.MX + 12, self._y, self.CW - 12, 22,
                        f'{num}.  {label.upper()}',
                        self._BLUE, self._f(11, bold=True),
                        Qt.AlignLeft | Qt.AlignVCenter)
        self._y += 26
        self._hline(self._BLUE, 1.5)
        self._y += 12

    def _label_value(self, label: str, value: str,
                     x: int, w: int) -> int:
        """Draw label + wrapped value at current _y (advancing it), return height used."""
        if not value:
            return 0
        y0 = self._y
        self._draw_text(x, self._y, w, 14, label.upper(),
                        self._MUTED, self._f(9),
                        Qt.AlignLeft | Qt.AlignVCenter)
        self._y += 15
        h = self._measure_h(value, self._f(11), w)
        self._draw_text(x, self._y, w, h + 4, value,
                        self._TEXT, self._f(11),
                        Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap)
        self._y += h + 10
        return self._y - y0

    def _load_px(self, b64: str, max_w: int, max_h: int) -> Optional[QPixmap]:
        from core.image_utils import b64_to_pixmap
        pm = b64_to_pixmap(b64)
        return None if pm is None else pm.scaled(
            max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    # ── Header ────────────────────────────────────────────────────────────────

    def _header(self):
        # Blue top accent bar
        self._rect_fill(0, self._y - 14, self.PW, 7, self._BLUE)

        company = self._i.get('company', '') or 'Project Brief'
        title   = self._i.get('title', '')
        ref     = self._i.get('reference', '')
        manager = self._i.get('project_manager', '')
        start   = self._i.get('start_date', '')
        due     = self._i.get('due_date', '')

        # Company name
        self._draw_text(self.MX, self._y, self.CW, 34, company,
                        self._BLUE, self._f(22, bold=True),
                        Qt.AlignLeft | Qt.AlignVCenter)
        self._y += 38

        if title:
            self._draw_text(self.MX, self._y, self.CW, 26, title,
                            self._TEXT, self._f(14),
                            Qt.AlignLeft | Qt.AlignVCenter)
            self._y += 30

        # Metadata row
        parts = []
        if ref:     parts.append(f'Ref: {ref}')
        if manager: parts.append(f'Manager: {manager}')
        if start:   parts.append(f'Start: {start}')
        if due:     parts.append(f'Due: {due}')
        if parts:
            self._draw_text(self.MX, self._y, self.CW, 18,
                            '   ·   '.join(parts),
                            self._MUTED, self._f(10),
                            Qt.AlignLeft | Qt.AlignVCenter)
            self._y += 22

        self._hline(self._BLUE, 2)
        self._y += 26

    # ── Section 1: Product Overview ───────────────────────────────────────────

    def _section1_overview(self):
        self._section_header(1, 'Product Overview')

        img_w   = 360
        img_h   = 340
        gap     = 36
        txt_x   = self.MX + img_w + gap
        txt_w   = self.CW - img_w - gap
        start_y = self._y

        # Left: product image
        pm = self._load_px(self._d.get('image_b64', ''), img_w, img_h)
        if pm:
            ox = (img_w - pm.width()) // 2
            oy = (img_h - pm.height()) // 2
            self._rect_fill(self.MX, start_y, img_w, img_h, self._LIGHT)
            self._p.drawPixmap(self.MX + ox, start_y + oy, pm)
        else:
            self._rect_fill(self.MX, start_y, img_w, img_h, self._LIGHT)
            self._rect_border(self.MX, start_y, img_w, img_h, self._BORDER)
            self._draw_text(self.MX, start_y, img_w, img_h, '+ Add Image',
                            self._MUTED, self._f(11), Qt.AlignCenter)

        # Right: fields
        self._y = start_y
        for lbl, key in [
            ('Product Name',        'product_name'),
            ('Reference / Version', 'reference'),
            ('Short Description',   'description'),
            ('Intended Use',        'intended_use'),
            ('Image / Visual Links','visual_links'),
        ]:
            self._label_value(lbl, self._d.get(key, '') or '', txt_x, txt_w)

        self._y = max(self._y, start_y + img_h + 12)
        self._y += 20

    # ── Section 2: Techniques / Watch Points ──────────────────────────────────

    def _section2_techniques(self):
        self._section_header(2, 'Planned Techniques / Watch Points')

        col_w   = (self.CW - 24) // 2
        col2_x  = self.MX + col_w + 24

        techniques  = [t for t in (self._d.get('techniques', []) or []) if t and t != '...']
        watchpoints = [t for t in (self._d.get('watchpoints', []) or []) if t and t != '...']

        # Column headers
        self._draw_text(self.MX,    self._y, col_w, 18, 'Techniques Considered',
                        self._BLUE, self._f(10, bold=True), Qt.AlignLeft | Qt.AlignVCenter)
        self._draw_text(col2_x, self._y, col_w, 18, 'Watch Points',
                        self._BLUE, self._f(10, bold=True), Qt.AlignLeft | Qt.AlignVCenter)
        self._y += 20
        self._p.setPen(QPen(self._BORDER, 1))
        self._p.drawLine(self.MX, self._y, self.MX + col_w, self._y)
        self._p.drawLine(col2_x,  self._y, col2_x + col_w,  self._y)
        self._y += 10

        base_y = self._y
        ly = base_y
        ry = base_y
        bullet_f = self._f(11)
        item_w   = col_w - 20

        for text in techniques:
            self._draw_text(self.MX, ly, 16, 16, '●', self._BLUE, self._f(9),
                            Qt.AlignCenter)
            h = self._measure_h(text, bullet_f, item_w)
            self._draw_text(self.MX + 18, ly, item_w, h + 4, text,
                            self._TEXT, bullet_f,
                            Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap)
            ly += h + 10

        for text in watchpoints:
            self._draw_text(col2_x, ry, 16, 16, '●', self._BLUE, self._f(9),
                            Qt.AlignCenter)
            h = self._measure_h(text, bullet_f, item_w)
            self._draw_text(col2_x + 18, ry, item_w, h + 4, text,
                            self._TEXT, bullet_f,
                            Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap)
            ry += h + 10

        self._y = max(ly, ry) + 20

    # ── Sections 3 & 4: Target Points + Target Dates (side by side) ──────────

    def _section34_targets_dates(self):
        self._ensure_space(140)   # need room for both side-by-side headers + first row
        col_w  = (self.CW - 24) // 2
        col2_x = self.MX + col_w + 24

        # Headers
        self._rect_fill(self.MX,    self._y, 5, 22, self._BLUE)
        self._rect_fill(col2_x, self._y, 5, 22, self._BLUE)
        self._draw_text(self.MX + 12,    self._y, col_w - 12, 22,
                        '3.  TARGET POINTS', self._BLUE, self._f(11, bold=True),
                        Qt.AlignLeft | Qt.AlignVCenter)
        self._draw_text(col2_x + 12, self._y, col_w - 12, 22,
                        '4.  TARGET DATES',  self._BLUE, self._f(11, bold=True),
                        Qt.AlignLeft | Qt.AlignVCenter)
        self._y += 26
        self._p.setPen(QPen(self._BLUE, 1.5))
        self._p.drawLine(self.MX,    self._y, self.MX + col_w,      self._y)
        self._p.drawLine(col2_x, self._y, col2_x + col_w, self._y)
        self._y += 14

        base_y = self._y
        ly = base_y
        ry = base_y

        # ── Left: Target Points ───────────────────────────────────────────────
        for lbl, key in [
            ('Dimensions',       'dimensions'),
            ('Target Weight',    'weight'),
            ('Target Total Cost','cost'),
            ('Other Constraints','constraints'),
        ]:
            val = self._d.get(key, '') or ''
            if not val:
                continue
            self._draw_text(self.MX, ly, col_w, 14, lbl.upper(),
                            self._MUTED, self._f(9), Qt.AlignLeft | Qt.AlignVCenter)
            ly += 15
            h = self._measure_h(val, self._f(12), col_w)
            self._draw_text(self.MX, ly, col_w, h + 4, val,
                            self._TEXT, self._f(12),
                            Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap)
            ly += h + 16

        # ── Right: Target Dates ───────────────────────────────────────────────
        for lbl, key in [
            ('Expected Delivery Date',          'delivery_date'),
            ('Expected Mockup / Prototype',     'prototype_date'),
            ('Expected Production Start',       'production_date'),
        ]:
            val = self._d.get(key, '') or '—'
            self._draw_text(col2_x, ry, col_w, 14, lbl.upper(),
                            self._MUTED, self._f(9), Qt.AlignLeft | Qt.AlignVCenter)
            ry += 15
            # Date in a tinted pill
            date_h = 30
            self._rect_fill(col2_x, ry, col_w, date_h, self._CELL)
            self._rect_border(col2_x, ry, col_w, date_h, self._BORDER)
            self._draw_text(col2_x + 12, ry, col_w - 24, date_h, val,
                            self._BLUE, self._f(12, bold=True),
                            Qt.AlignLeft | Qt.AlignVCenter)
            ry += date_h + 14

        # Comments
        notes = self._d.get('date_notes', '') or ''
        if notes:
            self._draw_text(col2_x, ry, col_w, 14, 'COMMENTS',
                            self._MUTED, self._f(9), Qt.AlignLeft | Qt.AlignVCenter)
            ry += 15
            h = self._measure_h(notes, self._f(11), col_w)
            self._draw_text(col2_x, ry, col_w, h + 4, notes,
                            self._TEXT, self._f(11),
                            Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap)
            ry += h + 8

        self._y = max(ly, ry) + 32

    # ── Section 5: Inspiration ────────────────────────────────────────────────

    def _section5_inspiration(self):
        self._section_header(5, 'Inspiration / Idea / Direction')

        text = self._d.get('inspiration', '') or ''
        if text:
            h = self._measure_h(text, self._f(11, italic=True), self.CW - 32)
            self._rect_fill(self.MX, self._y, self.CW, h + 28, self._CELL)
            self._rect_border(self.MX, self._y, self.CW, h + 28, self._BORDER)
            self._draw_text(self.MX + 16, self._y + 14, self.CW - 32, h + 4,
                            text, self._TEXT, self._f(11, italic=True),
                            Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap)
            self._y += h + 36

        # Photos
        photos = [b for b in (self._d.get('photo_b64s', []) or []) if b]
        if photos:
            self._draw_text(self.MX, self._y, self.CW, 14,
                            'REFERENCE IMAGES', self._MUTED, self._f(9),
                            Qt.AlignLeft | Qt.AlignVCenter)
            self._y += 18
            n    = len(photos)
            gap  = 14
            pw   = (self.CW - gap * (n - 1)) // n
            ph   = int(pw * 0.72)
            for i, b64 in enumerate(photos):
                px = self.MX + i * (pw + gap)
                pm = self._load_px(b64, pw, ph)
                self._rect_fill(px, self._y, pw, ph, self._LIGHT)
                self._rect_border(px, self._y, pw, ph, self._BORDER)
                if pm:
                    ox = (pw - pm.width()) // 2
                    oy = (ph - pm.height()) // 2
                    self._p.drawPixmap(px + ox, self._y + oy, pm)
            self._y += ph + 20

    # ── Section 6: Components ─────────────────────────────────────────────────

    def _section6_components(self):
        self._section_header(6, 'Components, Materials & Colours')

        components = self._d.get('components', []) or []
        components = [r for r in components
                      if any(str(c).strip() for c in (r if isinstance(r, (list, tuple)) else []))]

        if not components:
            self._draw_text(self.MX, self._y, self.CW, 24,
                            'No components defined.',
                            self._MUTED, self._f(11, italic=True),
                            Qt.AlignLeft | Qt.AlignVCenter)
            self._y += 30
            return

        # Column widths: #(44) | Component(380) | Material(332) | Colour(332)
        col_labels = ['#', 'Component', 'Material', 'Colour']
        col_widths = [44, 380, 332, 332]
        row_h = 34

        # Table header
        self._rect_fill(self.MX, self._y, self.CW, row_h, self._THEAD)
        self._p.setPen(Qt.white)
        self._p.setFont(self._f(10, bold=True))
        cx = self.MX
        for lbl, cw in zip(col_labels, col_widths):
            self._p.drawText(QRect(cx + 10, self._y, cw - 10, row_h),
                             Qt.AlignLeft | Qt.AlignVCenter, lbl)
            cx += cw
        self._y += row_h

        # Data rows
        for idx, row in enumerate(components):
            vals = list(row) if isinstance(row, (list, tuple)) else []
            while len(vals) < 3:
                vals.append('')

            # Measure row height (for multiline cells)
            row_content_h = max(row_h, max(
                (self._measure_h(str(v), self._f(11), col_widths[i + 1] - 20)
                 for i, v in enumerate(vals)), default=row_h
            ) + 14)

            self._ensure_space(row_content_h + 4)
            bg = self._CELL if idx % 2 == 0 else Qt.white
            self._rect_fill(self.MX, self._y, self.CW, row_content_h, bg)
            self._hline(self._BORDER)

            cx = self.MX
            # Row number
            self._draw_text(cx + 10, self._y, col_widths[0] - 10, row_content_h,
                            str(idx + 1), self._MUTED, self._f(10),
                            Qt.AlignLeft | Qt.AlignVCenter)
            cx += col_widths[0]
            # Component, Material, Colour
            for v, cw in zip(vals, col_widths[1:]):
                self._draw_text(cx + 10, self._y, cw - 20, row_content_h,
                                str(v or ''), self._TEXT, self._f(11),
                                Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap)
                cx += cw
            self._y += row_content_h

        # Bottom border
        self._hline(self._BORDER)
        self._y += 28

    # ── Section 7: Notes ──────────────────────────────────────────────────────

    def _section7_notes(self):
        self._section_header(7, 'Notes')

        notes = self._d.get('notes', '') or ''
        if not notes:
            self._draw_text(self.MX, self._y, self.CW, 24,
                            'No additional notes.',
                            self._MUTED, self._f(11, italic=True),
                            Qt.AlignLeft | Qt.AlignVCenter)
            self._y += 30
            return

        h = self._measure_h(notes, self._f(11), self.CW - 32)
        self._rect_fill(self.MX, self._y, self.CW, h + 32, self._LIGHT)
        self._rect_border(self.MX, self._y, self.CW, h + 32, self._BORDER)
        self._draw_text(self.MX + 16, self._y + 16, self.CW - 32, h + 4,
                        notes, self._TEXT, self._f(11),
                        Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap)
        self._y += h + 48

    # ── Footer ────────────────────────────────────────────────────────────────

    def _footer(self):
        # Place footer at bottom of the current (last) page
        foot_y  = self._page * self.PH - 52
        today   = date.today().strftime('%d %B %Y')

        self._p.setPen(QPen(self._BORDER, 1))
        self._p.drawLine(self.MX, foot_y, self.MX + self.CW, foot_y)

        self._draw_text(self.MX, foot_y + 10, self.CW // 2, 20,
                        f'Document generated on {today}',
                        self._MUTED, self._f(9), Qt.AlignLeft | Qt.AlignVCenter)
        self._draw_text(self.MX + self.CW // 2, foot_y + 10, self.CW // 2, 20,
                        'LYNS360 v1.2.0',
                        self._MUTED, self._f(9), Qt.AlignRight | Qt.AlignVCenter)


def _build_brief_pixmap(widget: QWidget, project_info: dict) -> QPixmap:
    """Render the Brief section as a formatted, print-ready QPixmap."""
    data = widget.get_data() if hasattr(widget, 'get_data') else {}
    renderer = _BriefRenderer(data, project_info)
    return renderer.render()


# ── Generic pixmap extraction (fallback for other sections) ──────────────────

def _get_printable_pixmap(section_key: str, widget: QWidget) -> QPixmap:
    """Return a full-content pixmap for the given section (screenshot-based)."""
    if section_key == 'timeline':
        canvas = getattr(widget, '_canvas', None)
        if canvas is not None:
            return canvas.grab()

    for sa in widget.findChildren(QScrollArea):
        inner = sa.widget()
        if inner is not None and inner.height() > 150:
            return inner.grab()

    return widget.grab()


# ── Page preview widget ───────────────────────────────────────────────────────

class _PagePreview(QWidget):
    """Renders a pixmap spread across A4 pages for on-screen preview."""

    _PX_PER_MM = 3.0
    _PAGE_W_MM = 210.0
    _PAGE_H_MM = 297.0
    _MARGIN_MM = 12.0
    _GAP_PX    = 20

    def __init__(self, pixmap: QPixmap, landscape: bool = False, parent=None):
        super().__init__(parent)
        self._pixmap   = pixmap
        self._landscape = landscape
        self.setStyleSheet('background: #888888;')
        self._refresh_size()

    def set_landscape(self, landscape: bool):
        self._landscape = landscape
        self._refresh_size()
        self.update()

    def _page_dims(self):
        p = self._PX_PER_MM
        if self._landscape:
            return self._PAGE_H_MM * p, self._PAGE_W_MM * p
        return self._PAGE_W_MM * p, self._PAGE_H_MM * p

    def _page_count(self) -> int:
        if self._pixmap.isNull():
            return 1
        pw, ph = self._page_dims()
        margin = self._MARGIN_MM * self._PX_PER_MM
        cw = pw - 2 * margin
        ch = ph - 2 * margin
        scale = cw / self._pixmap.width()
        return max(1, math.ceil(self._pixmap.height() * scale / ch))

    def _refresh_size(self):
        pw, ph = self._page_dims()
        n = self._page_count()
        self.setFixedSize(int(pw + 2 * self._GAP_PX),
                          int(n * (ph + self._GAP_PX) + self._GAP_PX))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        pw, ph = self._page_dims()
        margin = self._MARGIN_MM * self._PX_PER_MM
        gap    = self._GAP_PX
        n      = self._page_count()

        for i in range(n):
            px = gap
            py = gap + i * (ph + gap)

            p.fillRect(int(px + 4), int(py + 4), int(pw), int(ph),
                       QColor(0, 0, 0, 55))
            p.fillRect(int(px), int(py), int(pw), int(ph), QColor(255, 255, 255))
            p.setPen(QPen(QColor('#bbbbbb'), 1))
            p.drawRect(int(px), int(py), int(pw), int(ph))

            if not self._pixmap.isNull():
                cw     = pw - 2 * margin
                ch     = ph - 2 * margin
                scale  = cw / self._pixmap.width()
                y_src  = (i * ch) / scale
                h_src  = min(ch / scale, self._pixmap.height() - y_src)
                if h_src <= 0:
                    continue
                src = QRectF(0, y_src, float(self._pixmap.width()), h_src)
                dst = QRectF(px + margin, py + margin, cw, h_src * scale)
                p.drawPixmap(dst, self._pixmap, src)

        p.end()


# ── Custom print-preview dialog ───────────────────────────────────────────────

class PrintPreviewDialog(QDialog):
    """In-app print preview — no native OS dialog."""

    _BG     = '#1e2430'
    _CARD   = '#252b38'
    _BORDER = '#3a4050'
    _TEXT   = '#e0e8f0'
    _MUTED  = '#8899aa'
    _ACCENT = default_theme.button_primary
    _ACCENT_H = default_theme.button_primary_hover

    def __init__(self, pixmap: QPixmap, title: str,
                 landscape: bool = False, parent=None):
        super().__init__(parent)
        self._pixmap    = pixmap
        self._title     = title
        self._landscape = landscape
        self._printer_infos: list = []
        self.setWindowTitle(f'Print Preview — {title}')
        self.setModal(True)
        self.resize(1120, 820)
        self.setStyleSheet(f'background: {self._BG}; color: {self._TEXT};')
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        scroll.setStyleSheet('background: #777777; border: none;')
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._preview = _PagePreview(self._pixmap, self._landscape)
        scroll.setWidget(self._preview)
        root.addWidget(scroll, 1)

    def _build_sidebar(self) -> QWidget:
        sb = QWidget()
        sb.setFixedWidth(230)
        sb.setStyleSheet(
            f'background: {self._CARD}; border-right: 1px solid {self._BORDER};')
        lay = QVBoxLayout(sb)
        lay.setContentsMargins(18, 22, 18, 18)
        lay.setSpacing(12)

        hdr = QLabel('🖨  Print Preview')
        hdr.setStyleSheet(
            f'color: {self._TEXT}; font-size: 14px; font-weight: bold; background: transparent;')
        lay.addWidget(hdr)
        lay.addWidget(self._hsep())

        lay.addWidget(self._lbl('PRINTER'))
        self._printer_combo = QComboBox()
        self._printer_combo.setStyleSheet(self._combo_qss())
        self._populate_printers()
        lay.addWidget(self._printer_combo)
        lay.addWidget(self._hsep())

        lay.addWidget(self._lbl('ORIENTATION'))
        orient = QHBoxLayout(); orient.setSpacing(6)
        self._portrait_btn  = QPushButton('Portrait')
        self._landscape_btn = QPushButton('Landscape')
        for btn in (self._portrait_btn, self._landscape_btn):
            btn.setCheckable(True); btn.setFixedHeight(30)
            btn.setStyleSheet(self._toggle_qss())
            btn.setCursor(Qt.PointingHandCursor)
        self._portrait_btn.setChecked(not self._landscape)
        self._landscape_btn.setChecked(self._landscape)
        self._portrait_btn.clicked.connect(lambda: self._set_orientation(False))
        self._landscape_btn.clicked.connect(lambda: self._set_orientation(True))
        orient.addWidget(self._portrait_btn)
        orient.addWidget(self._landscape_btn)
        lay.addLayout(orient)
        lay.addWidget(self._hsep())

        lay.addWidget(self._lbl('COPIES'))
        self._copies_spin = QSpinBox()
        self._copies_spin.setMinimum(1); self._copies_spin.setMaximum(99)
        self._copies_spin.setValue(1); self._copies_spin.setFixedHeight(32)
        self._copies_spin.setStyleSheet(self._spin_qss())
        lay.addWidget(self._copies_spin)
        lay.addStretch()
        lay.addWidget(self._hsep())

        print_btn = QPushButton('🖨   Print')
        print_btn.setFixedHeight(38); print_btn.setCursor(Qt.PointingHandCursor)
        print_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self._ACCENT}; color: white;
                border: none; border-radius: 7px;
                font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {self._ACCENT_H}; }}
        """ + TOOLTIP_STYLE)
        print_btn.clicked.connect(self._do_print)
        lay.addWidget(print_btn)

        pdf_btn = QPushButton('📄   Save as PDF')
        pdf_btn.setFixedHeight(32); pdf_btn.setCursor(Qt.PointingHandCursor)
        pdf_btn.setStyleSheet(f"""
            QPushButton {{
                background: #2d3748; color: {self._TEXT};
                border: 1px solid {self._BORDER}; border-radius: 6px; font-size: 12px;
            }}
            QPushButton:hover {{ background: #3a4558; border-color: {self._ACCENT}; }}
        """ + TOOLTIP_STYLE)
        pdf_btn.clicked.connect(self._save_pdf)
        lay.addWidget(pdf_btn)

        cancel_btn = QPushButton('Cancel')
        cancel_btn.setFixedHeight(26); cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {self._MUTED};
                           border: none; font-size: 12px; }}
            QPushButton:hover {{ color: {self._TEXT}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        lay.addWidget(cancel_btn)
        return sb

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _lbl(self, text):
        l = QLabel(text)
        l.setStyleSheet(
            f'color: {self._MUTED}; font-size: 10px; font-weight: bold;'
            f'background: transparent; letter-spacing: 1px;')
        return l

    def _hsep(self):
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setFixedHeight(1)
        f.setStyleSheet(f'background: {self._BORDER}; border: none;')
        return f

    def _combo_qss(self):
        return f"""
            QComboBox {{ background: #2d3748; color: {self._TEXT};
                border: 1px solid {self._BORDER}; border-radius: 5px;
                padding: 5px 8px; font-size: 12px; }}
            QComboBox:hover {{ border-color: {self._ACCENT}; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: #2d3748; color: {self._TEXT};
                border: 1px solid {self._BORDER};
                selection-background-color: {self._ACCENT}; }}
        """

    def _spin_qss(self):
        return f"""
            QSpinBox {{ background: #2d3748; color: {self._TEXT};
                border: 1px solid {self._BORDER}; border-radius: 5px;
                padding: 4px 8px; font-size: 13px; }}
            QSpinBox:hover {{ border-color: {self._ACCENT}; }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background: #3a4558; border: none; width: 18px; }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: {self._ACCENT}; }}
        """

    def _toggle_qss(self):
        return f"""
            QPushButton {{ background: #2d3748; color: {self._MUTED};
                border: 1px solid {self._BORDER}; border-radius: 5px; font-size: 11px; }}
            QPushButton:checked {{ background: {self._ACCENT}; color: white;
                border-color: {self._ACCENT}; }}
            QPushButton:hover:!checked {{ border-color: {self._ACCENT}; color: {self._TEXT}; }}
        """

    # ── Logic ─────────────────────────────────────────────────────────────────

    def _populate_printers(self):
        try:
            from PyQt5.QtPrintSupport import QPrinterInfo
            self._printer_infos = QPrinterInfo.availablePrinters()
            default_name = QPrinterInfo.defaultPrinter().printerName()
            for info in self._printer_infos:
                self._printer_combo.addItem(info.printerName())
            idx = self._printer_combo.findText(default_name)
            if idx >= 0:
                self._printer_combo.setCurrentIndex(idx)
        except Exception:
            self._printer_combo.addItem('Default printer')

    def _set_orientation(self, landscape: bool):
        self._landscape = landscape
        self._portrait_btn.setChecked(not landscape)
        self._landscape_btn.setChecked(landscape)
        self._preview.set_landscape(landscape)

    def _build_printer(self):
        from PyQt5.QtPrintSupport import QPrinter
        from PyQt5.QtGui import QPageLayout
        printer = QPrinter(QPrinter.HighResolution)
        idx = self._printer_combo.currentIndex()
        if 0 <= idx < len(self._printer_infos):
            printer.setPrinterName(self._printer_infos[idx].printerName())
        printer.setCopyCount(self._copies_spin.value())
        printer.setPageOrientation(
            QPageLayout.Landscape if self._landscape else QPageLayout.Portrait)
        return printer

    def _render(self, printer):
        if self._pixmap.isNull():
            return
        painter = QPainter(printer)
        page    = QRectF(printer.pageRect())
        mx = page.width()  * 0.04
        my = page.height() * 0.04
        cw = page.width()  - 2 * mx
        ch = page.height() - 2 * my
        sw = float(self._pixmap.width())
        sh = float(self._pixmap.height())
        scale  = cw / sw
        pages  = max(1, math.ceil(sh * scale / ch))
        for i in range(pages):
            if i > 0:
                printer.newPage()
            y_src = (i * ch) / scale
            h_src = min(ch / scale, sh - y_src)
            if h_src <= 0:
                break
            painter.drawPixmap(
                QRectF(mx, my, cw, h_src * scale),
                self._pixmap,
                QRectF(0, y_src, sw, h_src),
            )
        painter.end()

    def _do_print(self):
        try:
            self._render(self._build_printer())
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, 'Print error', str(exc))

    def _save_pdf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save as PDF', f'{self._title}.pdf', 'PDF Files (*.pdf)')
        if not path:
            return
        try:
            from PyQt5.QtPrintSupport import QPrinter
            from PyQt5.QtGui import QPageLayout
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(path)
            printer.setPageOrientation(
                QPageLayout.Landscape if self._landscape else QPageLayout.Portrait)
            self._render(printer)
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, 'PDF error', str(exc))


# ── Public entry point ────────────────────────────────────────────────────────

def print_section(section_key: str, widget: QWidget,
                  title: str, parent: QWidget,
                  landscape: bool = False,
                  project_info: Optional[dict] = None) -> None:
    """Open the custom in-app print preview for the given project section."""
    try:
        from PyQt5.QtPrintSupport import QPrinter  # noqa: F401
    except ImportError:
        QMessageBox.warning(
            parent, 'Print unavailable',
            'PyQt5 print support is not installed.\n'
            'Run: pip install PyQt5 --upgrade')
        return

    # Brief gets a formatted document; everything else gets a screenshot
    if section_key == 'brief' and project_info is not None:
        pixmap = _build_brief_pixmap(widget, project_info)
        landscape = False  # Brief is always portrait
    else:
        pixmap = _get_printable_pixmap(section_key, widget)

    dlg = PrintPreviewDialog(pixmap, title, landscape=landscape, parent=parent)
    dlg.exec_()
