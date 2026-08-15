"""
Top horizontal toolbar for 3D view controls.
"""
import logging
import os
import sys
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QSizePolicy, QFrame, QSpacerItem, QApplication, QMenu, QAction,
    QScrollArea, QWidgetAction, QSlider,
)
from PyQt5.QtCore import Qt, QRect, QEvent, pyqtSignal, QPropertyAnimation, QEasingCurve, QSettings, QTimer
from PyQt5.QtGui import QFont, QFontMetrics, QPixmap, QPainter, QColor, QImage, QBrush, QPen
from ui.styles import default_theme, make_font, TOOLTIP_STYLE, arrow_up_url as _arrow_up, arrow_down_url as _arrow_down
from i18n import t, on_language_changed

logger = logging.getLogger(__name__)


def _menu_diamond_px() -> int:
    """Match ◆/◇/◈ in QMenu items (font-size 11px)."""
    try:
        fm = QFontMetrics(make_font(size=11))
        try:
            w = fm.horizontalAdvance("◆")
        except AttributeError:
            logger.debug("horizontalAdvance not available, falling back to width()")
            w = fm.width("◆")
        h = fm.boundingRect("◆").height()
        result = max(10, min(12, int(round(max(w, h)))))
        logger.debug("_menu_diamond_px -> %d", result)
        return result
    except Exception:
        logger.warning("_menu_diamond_px failed, using fallback 11", exc_info=True)
        return 11


def _render_glyph_pixmap(text: str, box_px: int, font_px: int, color: str = None) -> QPixmap:
    """Render a single glyph/emoji into a box_px x box_px pixmap with its
    actual ink centered, rather than trusting the font's line metrics.

    QLabel's own Qt.AlignCenter centers text using the font's ascent/descent
    box. That's fine for Latin text, but color emoji fonts (Segoe UI Emoji
    on Windows especially) pad extra space above the glyph to match Latin
    line-height, so a tightly-sized label renders the icon low with a gap
    above it — exactly the "camera icon not centered" symptom. Measuring
    the glyph's tight ink bounds and centering *that* instead sidesteps the
    font's misleading line box.
    """
    dpr = 2
    if QApplication.instance():
        try:
            dpr = int(QApplication.instance().devicePixelRatio()) or 2
        except Exception:
            dpr = 2
    px = box_px * dpr
    font = QFont()
    font.setPixelSize(font_px * dpr)
    fm = QFontMetrics(font)
    ink = fm.tightBoundingRect(text)

    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setFont(font)
    if color:
        painter.setPen(QColor(color))
    if ink.isEmpty():
        # Some color-emoji glyphs don't report ink extents via
        # tightBoundingRect on every platform/Qt build — fall back to
        # plain line-metrics centering rather than mis-placing the glyph.
        painter.drawText(QRect(0, 0, px, px), Qt.AlignCenter, text)
    else:
        # tightBoundingRect is baseline-relative (top()/bottom() measured
        # from the baseline, negative = above it) — solve for the baseline
        # position that puts the ink rect's own center at the pixmap's
        # center.
        baseline_x = (px - (ink.left() + ink.right())) / 2
        baseline_y = (px - (ink.top() + ink.bottom())) / 2
        painter.drawText(int(round(baseline_x)), int(round(baseline_y)), text)
    painter.end()

    pm.setDevicePixelRatio(dpr)
    return pm


def _parts_menu_pixmap_fallback(size: int) -> QPixmap:
    """Draw a 2x2 grid of black squares — Windows-safe, integer-only."""
    try:
        if size <= 0:
            size = 10
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setPen(Qt.NoPen)
        cell = size // 2 - 1
        gap = 1
        white = QColor(255, 255, 255)
        for r in range(2):
            for c in range(2):
                x = gap + c * (cell + gap)
                y = gap + r * (cell + gap)
                p.fillRect(QRect(x, y, cell, cell), white)
        p.end()
        logger.debug("_parts_menu_pixmap_fallback v2: ok size=%d cell=%d", size, cell)
        return pm
    except Exception:
        logger.warning("_parts_menu_pixmap_fallback v2 failed", exc_info=True)
        pm = QPixmap(max(size, 10), max(size, 10))
        pm.fill(QColor(255, 255, 255))
        return pm


def _load_parts_menu_pixmap(path: str) -> QPixmap:
    """Scale parts icon to same visual size as diamond glyphs (not QIcon — avoids macOS tint)."""
    try:
        px = _menu_diamond_px()
        if not path or not os.path.isfile(path):
            logger.debug("_load_parts_menu_pixmap: no valid path (%s)", path)
            return QPixmap()
        pm = QPixmap(path)
        if pm.isNull():
            logger.warning("_load_parts_menu_pixmap: QPixmap('%s') is null", path)
            return QPixmap()
        logger.debug("_load_parts_menu_pixmap: loaded %dx%d, scaling to %d", pm.width(), pm.height(), px)
        pm = pm.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if pm.isNull() or pm.width() == 0 or pm.height() == 0:
            logger.warning("_load_parts_menu_pixmap: scaled pixmap is null/zero")
            return QPixmap()
        img = pm.toImage().convertToFormat(QImage.Format_ARGB32_Premultiplied)
        pm_alpha = QPixmap.fromImage(img)
        # Recolor to white: fill white then mask with original alpha channel
        result = QPixmap(pm_alpha.size())
        result.fill(Qt.transparent)
        p = QPainter(result)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(result.rect(), QColor(255, 255, 255))
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        p.drawPixmap(0, 0, pm_alpha)
        p.end()
        return result
    except Exception:
        logger.warning("_load_parts_menu_pixmap failed for '%s'", path, exc_info=True)
        return QPixmap()


class _PartsMenuRow(QWidget):
    """Parts row aligned like checkable ◆  Shaded rows; pixmap matches diamond size."""

    clicked = pyqtSignal()

    def __init__(self, pixmap_path: str, checked: bool, enabled: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("partsMenuRow")
        self.setAutoFillBackground(False)
        self._enabled = enabled
        menu_font = make_font(size=11)
        fm = QFontMetrics(menu_font)
        try:
            gap_two_spaces = fm.horizontalAdvance("  ")
        except AttributeError:
            gap_two_spaces = fm.width("  ")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 6, 16, 6)
        lay.setSpacing(0)

        chk = QLabel("✓" if checked else "")
        chk.setFixedWidth(18)
        chk.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        chk.setFont(menu_font)
        chk.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 11px;")

        pix_lbl = QLabel()
        pix_lbl.setAutoFillBackground(False)
        pix_lbl.setAttribute(Qt.WA_TranslucentBackground, True)
        pix_lbl.setAlignment(Qt.AlignCenter)
        pm = _load_parts_menu_pixmap(pixmap_path)
        if pm.isNull():
            pm = _parts_menu_pixmap_fallback(_menu_diamond_px())
        pix_lbl.setPixmap(pm)
        if not pm.isNull() and pm.width() > 0 and pm.height() > 0:
            pix_lbl.setFixedSize(pm.size())
        else:
            logger.warning("_PartsMenuRow: pixmap is null/zero after fallback, skipping setFixedSize")
            pix_lbl.setFixedSize(12, 12)
        pix_lbl.setStyleSheet("background: transparent; border: none;")

        txt = QLabel(t("toolbar.parts"))
        txt.setFont(menu_font)
        txt.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 11px;")

        lay.addWidget(chk)
        lay.addWidget(pix_lbl)
        lay.addSpacing(gap_two_spaces)
        lay.addWidget(txt)
        lay.addStretch()

        # Do not QWidget.setEnabled(False) or row opacity — Qt greys out QLabel pixmaps (looks like a flat gray tile).
        # Parts is inactive without a model, but the black icon should stay visually black like the ◆ glyphs.
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        if not enabled:
            chk.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 11px;")
            txt.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 11px;")
        hover = f"QWidget#partsMenuRow:hover {{ background-color: {default_theme.row_bg_hover}; }}"
        self.setStyleSheet(hover)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._enabled:
            self.clicked.emit()
        super().mousePressEvent(event)


# Toolbar chips: white background + dark labels
_TB_BG = "#ffffff"
_TB_FG = "#1e2530"
_TB_HOVER = "#e8f4f8"
_TB_HOVER_BORDER = "#2596BE"
_TB_ACTIVE = "#d0eaf4"
_TB_BORDER = "#d0d0d0"
_TB_ACTIVE_BORDER = "#2596BE"
_TB_SEP = "#2596BE"


def _toolbar_label_font(size=10):
    """Font for toolbar button text; Windows often renders small labels too thin — use bold there."""
    f = make_font(size=size)
    if sys.platform == 'win32':
        f.setBold(True)
    return f


def _toolbar_label_style(color: str, size: int = 10) -> str:
    """QLabel stylesheet for toolbar text; bold on Windows so QSS matches QFont."""
    w = 'font-weight: bold;' if sys.platform == 'win32' else ''
    return f'color: {color}; font-size: {size}px; background: transparent; {w}'


class _RecButton(QPushButton):
    """Broadcast-style REC button drawn entirely via QPainter."""

    _W, _H = 76, 30
    _DOT_R  = 6      # dot radius
    _DOT_X  = 12     # dot left edge
    _GAP    = 8      # gap between dot and text

    def __init__(self, tooltip: str = '', parent=None):
        super().__init__(parent)
        self._active   = False
        self._blink_on = True
        self._hover    = False

        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self._W, self._H)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # Suppress default QPushButton paint
        self.setStyleSheet(
            'QPushButton { background: transparent; border: none; }' + TOOLTIP_STYLE
        )

        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink)

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Background
        bg = QColor('#1a1a1a') if self._hover else QColor('#000000')
        p.setBrush(QBrush(bg))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, self._W, self._H, 7, 7)

        # Red border
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor('#e63946'), 2))
        p.drawRoundedRect(1, 1, self._W - 2, self._H - 2, 6, 6)

        # Red dot
        dot_color = QColor('#e63946' if (self._blink_on or not self._active) else '#4a0a0a')
        p.setBrush(QBrush(dot_color))
        p.setPen(Qt.NoPen)
        cy = self._H // 2
        p.drawEllipse(self._DOT_X, cy - self._DOT_R, self._DOT_R * 2, self._DOT_R * 2)

        # REC text
        p.setPen(QColor('#ffffff'))
        font = QFont()
        font.setPixelSize(13)
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        p.setFont(font)
        tx = self._DOT_X + self._DOT_R * 2 + self._GAP
        p.drawText(tx, 0, self._W - tx - 6, self._H,
                   Qt.AlignVCenter | Qt.AlignLeft, 'REC')
        p.end()

    # ── hover tracking ────────────────────────────────────────────────────────

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    # ── blink ─────────────────────────────────────────────────────────────────

    def _blink(self):
        self._blink_on = not self._blink_on
        self.update()

    # ── public API ────────────────────────────────────────────────────────────

    def set_active(self, active: bool):
        self._active = active
        if active:
            self._blink_on = True
            self._blink_timer.start(500)
        else:
            self._blink_timer.stop()
            self._blink_on = True
        self.update()

    def set_label(self, _text: str = ''):
        pass  # label is always "REC"


class ToolbarButton(QPushButton):
    """A styled toolbar button with icon and text."""
    
    def __init__(self, icon_text, label_text, tooltip, parent=None, icon_path=None, label_font_size=None):
        super().__init__(parent)
        self.icon_text = icon_text
        self.icon_path = icon_path
        self._preferred_icon_path = icon_path  # Kept when set_icon is called with emoji
        self.label_text = label_text
        self._is_active = False
        if label_font_size is None:
            label_font_size = 12 if sys.platform == 'win32' else 10
        self._label_font_size = label_font_size
        # Larger label (e.g. Ruler on Windows): taller chip + more left room so emoji is not clipped
        _win_large = sys.platform == 'win32' and label_font_size >= 12
        
        # Create layout for icon + text
        self._layout = QHBoxLayout(self)
        if _win_large:
            self._layout.setContentsMargins(8, 5, 10, 5)
        else:
            self._layout.setContentsMargins(6, 4, 8, 4)
        self._layout.setSpacing(4)
        
        # Icon (image or emoji)
        self.icon_label = QLabel()
        if icon_path:
            self._icon_size = 24
            _ih = 24
            _icon_fs = 12
        elif _win_large:
            self._icon_size = 18
            _ih = 18
            _icon_fs = 14
        else:
            self._icon_size = 14
            _ih = 14
            _icon_fs = 12
        self._icon_label_font_px = _icon_fs
        self.icon_label.setStyleSheet(f"color: {_TB_FG}; font-size: {_icon_fs}px; background: transparent;")
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setFixedWidth(self._icon_size)
        self.icon_label.setFixedHeight(_ih)
        if icon_path:
            self._set_icon_pixmap(icon_path)
        else:
            self.icon_label.setText(icon_text)
        self._layout.addWidget(self.icon_label)
        
        # Text label
        self.text_label = QLabel(label_text)
        self.text_label.setStyleSheet(_toolbar_label_style(_TB_FG, label_font_size))
        self.text_label.setFont(_toolbar_label_font(label_font_size))
        self.text_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self._layout.addWidget(self.text_label)
        
        # Configure button
        self.setToolTip(tooltip or "")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        _btn_h = 32 if _win_large else 28
        self.setMinimumHeight(_btn_h)
        self.setMaximumHeight(_btn_h)
        
        self._apply_default_style()
        self._update_min_width()
        self.installEventFilter(self)

    def _set_icon_pixmap(self, path):
        """Set icon from image file (crisp scaling for high-DPI)."""
        from ui.annotation_icon import get_annotation_icon_pixmap
        pixmap = get_annotation_icon_pixmap(self._icon_size, path)
        if not pixmap.isNull():
            self.icon_label.setPixmap(pixmap)
            self.icon_label.setText("")
        else:
            self.icon_label.setText(self.icon_text or "?")

    def _update_min_width(self):
        """Ensure the button is wide enough to show its full label."""
        if not hasattr(self, "_layout"):
            return

        m = self._layout.contentsMargins()
        left = m.left()
        right = m.right()

        icon_w = self._icon_size if getattr(self, '_preferred_icon_path', None) or getattr(self, 'icon_path', None) else 14
        text = (self.text_label.text() or "").strip()

        if text:
            # Use QFontMetrics with the actual font for reliable measurement
            fm = QFontMetrics(self.text_label.font())
            label_w = fm.horizontalAdvance(text)
            # Windows font metrics can underestimate; add buffer to prevent clipping
            if sys.platform == 'win32':
                label_w += 10
            spacing = self._layout.spacing()
        else:
            label_w = 0
            spacing = 0

        # Minimal padding
        min_width = left + right + icon_w + spacing + label_w + 6
        self.setFixedWidth(min_width)
        self.text_label.setMinimumWidth(label_w)
    
    def _apply_default_style(self):
        """Apply the default button style."""
        if self._is_active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {_TB_ACTIVE};
                    border: 1px solid {_TB_ACTIVE_BORDER};
                    border-radius: 6px;
                }}
                QPushButton:pressed {{
                    background-color: {_TB_ACTIVE};
                    border: 1px solid {_TB_ACTIVE_BORDER};
                    border-radius: 6px;
                }}
            """ + TOOLTIP_STYLE)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {_TB_BG};
                    border: 1px solid transparent;
                    border-radius: 6px;
                }}
                QPushButton:pressed {{
                    background-color: {_TB_ACTIVE};
                    border: 1px solid {_TB_BORDER};
                    border-radius: 6px;
                }}
            """ + TOOLTIP_STYLE)

    def _apply_hover_style(self):
        """Apply the hover style."""
        if self._is_active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {_TB_ACTIVE};
                    border: 1px solid {_TB_ACTIVE_BORDER};
                    border-radius: 6px;
                }}
                QPushButton:pressed {{
                    background-color: {_TB_ACTIVE};
                    border: 1px solid {_TB_ACTIVE_BORDER};
                    border-radius: 6px;
                }}
            """ + TOOLTIP_STYLE)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {_TB_HOVER};
                    border: 1px solid {_TB_HOVER_BORDER};
                    border-radius: 6px;
                }}
                QPushButton:pressed {{
                    background-color: {_TB_ACTIVE};
                    border: 1px solid {_TB_HOVER_BORDER};
                    border-radius: 6px;
                }}
            """ + TOOLTIP_STYLE)

    def _apply_disabled_style(self):
        """Apply disabled style."""
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: #ececec;
                border: 1px solid transparent;
                border-radius: 6px;
            }}
        """ + TOOLTIP_STYLE)
        _ifs = getattr(self, '_icon_label_font_px', 12)
        self.icon_label.setStyleSheet(f"color: #888888; font-size: {_ifs}px; background: transparent;")
        self.text_label.setStyleSheet(_toolbar_label_style('#888888', self._label_font_size))
    
    def set_active(self, active):
        """Set the active state of the button. Must respect the current
        enabled/disabled look — _apply_default_style() ignores isEnabled(),
        so calling this on a disabled button (e.g. render_mode_btn's icon
        updating while read-only, from a saved project restoring its
        render mode) used to silently restyle it back to looking clickable
        even though clicks were still blocked."""
        self._is_active = active
        if self.isEnabled():
            self._apply_default_style()
        else:
            self._apply_disabled_style()
    
    def set_label(self, text):
        """Update the button label text."""
        self.label_text = text
        self.text_label.setText(text)
        self._update_min_width()
    
    def set_icon(self, icon_text_or_path):
        """Update the button icon (emoji text or path to image)."""
        import os
        # If we have a preferred image icon and caller passes emoji, keep the image
        if (self._preferred_icon_path and isinstance(icon_text_or_path, str) and
                not os.path.isfile(icon_text_or_path) and icon_text_or_path in ("📝", "✏️")):
            self._set_icon_pixmap(self._preferred_icon_path)
            self.icon_text = icon_text_or_path
            return
        self.icon_text = icon_text_or_path
        if isinstance(icon_text_or_path, str) and os.path.isfile(icon_text_or_path):
            self.icon_path = icon_text_or_path
            self._set_icon_pixmap(icon_text_or_path)
        else:
            self.icon_path = None
            self.icon_label.setPixmap(QPixmap())
            self.icon_label.setText(icon_text_or_path or "")
    
    def eventFilter(self, obj, event):
        """Handle hover events."""
        if obj == self:
            if not self.isEnabled():
                return super().eventFilter(obj, event)
            if event.type() == QEvent.Enter:
                self._apply_hover_style()
            elif event.type() == QEvent.Leave:
                self._apply_default_style()
        return super().eventFilter(obj, event)
    
    def setEnabled(self, enabled):
        """Override setEnabled to update styling."""
        super().setEnabled(enabled)
        if enabled:
            self._apply_default_style()
            _ifs = getattr(self, '_icon_label_font_px', 12)
            self.icon_label.setStyleSheet(f"color: {_TB_FG}; font-size: {_ifs}px; background: transparent;")
            self.text_label.setStyleSheet(_toolbar_label_style(_TB_FG, self._label_font_size))
            self.text_label.setFont(_toolbar_label_font(self._label_font_size))
        else:
            self._apply_disabled_style()


class ViewControlsToolbar(QWidget):
    """Collapsible horizontal toolbar for 3D view controls."""
    
    # Signals for viewer controls
    toggle_grid = pyqtSignal()
    toggle_theme = pyqtSignal()
    render_mode_changed = pyqtSignal(str)  # 'solid', 'wireframe', 'shaded'
    reset_rotation = pyqtSignal()
    view_front = pyqtSignal()
    view_rear = pyqtSignal()
    view_left = pyqtSignal()
    view_right = pyqtSignal()
    view_top = pyqtSignal()
    view_bottom = pyqtSignal()
    toggle_fullscreen = pyqtSignal()
    toggle_ruler = pyqtSignal()
    toggle_annotation = pyqtSignal()
    toggle_arrow = pyqtSignal()
    toggle_parts = pyqtSignal()
    toggle_screenshot = pyqtSignal()
    toggle_texture = pyqtSignal()
    toggle_draw = pyqtSignal()
    toggle_rotate = pyqtSignal()
    rotate_speed_changed = pyqtSignal(float)
    rotate_axis_changed = pyqtSignal(str)   # 'h' or 'v'
    toggle_record = pyqtSignal()
    draw_color_changed = pyqtSignal(str)  # hex color
    draw_eraser_toggled = pyqtSignal(bool)
    draw_text_toggled = pyqtSignal(bool)  # True = text mode on
    draw_font_size_changed = pyqtSignal(float)  # multiplier relative to auto size
    draw_undo_requested = pyqtSignal()
    draw_undo_text_requested = pyqtSignal()
    draw_clear_requested = pyqtSignal()
    draw_color_picker_requested = pyqtSignal()  # show color picker (pen/text only, not eraser)
    load_file = pyqtSignal()
    clear_model = pyqtSignal()
    open_converter = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # State tracking
        self.grid_enabled = True
        self.dark_theme = False
        self.render_mode = 'shaded'  # 'shaded', 'solid', 'wireframe'
        self.is_fullscreen = False
        self.ruler_mode_enabled = False
        self.annotation_mode_enabled = False
        self.arrow_mode_enabled = False
        self.parts_mode_enabled = False
        self.screenshot_mode_enabled = False
        self.texture_mode_enabled = False
        self.draw_mode_enabled = False
        self.rotate_mode_enabled = False
        self.record_mode_enabled = False
        self._read_only = False
        self._draw_color = '#FF0000'
        self._draw_text_active = False
        self._draw_font_size_multiplier = 1.0
        self.stl_loaded = False
        
        self.settings = QSettings("LYNS360", "Toolbar")
        self.init_ui()
        on_language_changed(self.retranslate)
    
    def init_ui(self):
        """Initialize the toolbar UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Container frame for styling
        self.container = QFrame()
        self.container.setObjectName("toolbarContainer")
        self.container.setStyleSheet(f"""
            QFrame#toolbarContainer {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {default_theme.gradient_start},
                    stop:0.5 {default_theme.gradient_mid},
                    stop:1 {default_theme.gradient_end});
                border-bottom: 2px solid {_TB_SEP};
            }}
        """)
        
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Scroll area for horizontal scrolling when toolbar overflows
        self.toolbar_scroll = QScrollArea()
        self.toolbar_scroll.setObjectName("toolbarScroll")
        self.toolbar_scroll.setWidgetResizable(True)
        self.toolbar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.toolbar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Room for toolbar row (~32px) + visible horizontal scrollbar (~10px) + margin
        self.toolbar_scroll.setFixedHeight(48)
        self.toolbar_scroll.setStyleSheet(f"""
            QScrollArea#toolbarScroll {{
                border: none;
                background: transparent;
            }}
            QScrollArea#toolbarScroll QScrollBar:horizontal {{
                height: 10px;
                background: rgba(0, 0, 0, 0.35);
                border: none;
                border-radius: 4px;
                margin: 2px 6px 4px 6px;
            }}
            QScrollArea#toolbarScroll QScrollBar::handle:horizontal {{
                background: {default_theme.scrollbar_handle_hover};
                border-radius: 4px;
                min-width: 40px;
                margin: 1px;
            }}
            QScrollArea#toolbarScroll QScrollBar::handle:horizontal:hover {{
                background: #5a5e68;
            }}
            QScrollArea#toolbarScroll QScrollBar::add-line:horizontal,
            QScrollArea#toolbarScroll QScrollBar::sub-line:horizontal {{
                width: 0px;
                height: 0px;
            }}
            QScrollArea#toolbarScroll QScrollBar::add-page:horizontal,
            QScrollArea#toolbarScroll QScrollBar::sub-page:horizontal {{
                background: transparent;
            }}
        """)

        # Expanded toolbar content
        self.toolbar_content = QWidget()
        self.toolbar_content.setObjectName("toolbarContent")
        content_layout = QHBoxLayout(self.toolbar_content)
        content_layout.setContentsMargins(10, 6, 10, 6)
        content_layout.setSpacing(6)

        def _sep():
            """Vertical divider between toolbar groups."""
            line = QFrame()
            line.setFrameShape(QFrame.VLine)
            line.setFixedWidth(6)
            line.setFixedHeight(30)
            line.setStyleSheet(
                f'background-color: {_TB_SEP}; border: none; border-radius: 2px;'
            )
            return line

        # ── Group 1: Scene display ────────────────────────────────────────────
        self.grid_btn = ToolbarButton("⊞", t("toolbar.grid"), "")
        self.grid_btn.set_active(True)
        self.grid_btn.clicked.connect(self._on_grid_clicked)
        content_layout.addWidget(self.grid_btn)

        self.theme_btn = ToolbarButton("☀", t("toolbar.light"), "")
        self.theme_btn.clicked.connect(self._on_theme_clicked)
        content_layout.addWidget(self.theme_btn)

        self.render_mode_btn = ToolbarButton("◇", t("toolbar.visual_style"), "")
        self.render_mode_btn.clicked.connect(self._show_render_mode_menu)
        content_layout.addWidget(self.render_mode_btn)

        content_layout.addWidget(_sep())

        # ── Group 2: Camera / navigation ─────────────────────────────────────
        self.reset_btn = ToolbarButton("↺", t("toolbar.reset"), "")
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        self.reset_btn.setEnabled(False)
        content_layout.addWidget(self.reset_btn)

        self._current_view = "front"
        self.view_btn = ToolbarButton(
            "⬚", t("toolbar.2d_views"),
            t("toolbar.2d_views_tooltip"),
        )
        self.view_btn.clicked.connect(self._show_view_menu)
        self.view_btn.setEnabled(False)
        content_layout.addWidget(self.view_btn)

        content_layout.addWidget(_sep())

        # ── Group 3: Markup / measurement ────────────────────────────────────
        _ruler_label_px = 12 if sys.platform == 'win32' else 10
        self.ruler_btn = ToolbarButton(
            "📏", t("toolbar.ruler"), t("toolbar.measure_tooltip"), label_font_size=_ruler_label_px
        )
        self.ruler_btn.clicked.connect(self._on_ruler_clicked)
        self.ruler_btn.setEnabled(False)
        content_layout.addWidget(self.ruler_btn)

        _anno_icon = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "assets", "annotation_icon.png"))
        self.annotation_btn = ToolbarButton(
            "📝", t("toolbar.annotate"), t("toolbar.annotate_tooltip"),
            icon_path=_anno_icon if os.path.exists(_anno_icon) else None
        )
        self.annotation_btn.clicked.connect(self._show_annotate_menu)
        self.annotation_btn.setEnabled(False)
        content_layout.addWidget(self.annotation_btn)

        self.draw_btn = ToolbarButton("🖊", t("toolbar.draw"), t("toolbar.draw_tooltip"))
        self.draw_btn.clicked.connect(self._show_draw_menu)
        self.draw_btn.setEnabled(False)
        content_layout.addWidget(self.draw_btn)
        self._eraser_active = False

        content_layout.addWidget(_sep())

        # ── Group 4: Capture / output ─────────────────────────────────────────
        self.screenshot_btn = ToolbarButton("📷", "", t("toolbar.screenshot_tooltip"))
        self.screenshot_btn.text_label.hide()
        # Pull the hidden label out of the layout entirely (not just hide())
        # and center the remaining icon with zero margins — leaving the old
        # asymmetric (8, 2, 8, 2) margins let leftover label spacing nudge
        # the camera icon off-center, most visibly on Windows where the
        # taller 32px button made the offset more noticeable.
        self.screenshot_btn._layout.removeWidget(self.screenshot_btn.text_label)
        self.screenshot_btn.icon_label.setFixedSize(24, 24)
        self.screenshot_btn.icon_label.setStyleSheet("background: transparent;")
        # Render the camera glyph to a pixmap with its ink centered instead
        # of letting the QLabel center it by font line metrics — Segoe UI
        # Emoji's ascent padding on Windows made setText()-based centering
        # render the icon low with a visible gap above it.
        self.screenshot_btn.icon_label.setPixmap(
            _render_glyph_pixmap("📷", 24, 22, _TB_FG)
        )
        self.screenshot_btn._icon_label_font_px = 22
        self.screenshot_btn._icon_size = 24
        self.screenshot_btn._layout.setContentsMargins(0, 0, 0, 0)
        self.screenshot_btn._layout.setAlignment(Qt.AlignCenter)
        _scr_h = 32 if sys.platform == 'win32' else 28
        self.screenshot_btn.setFixedSize(44, _scr_h)
        self.screenshot_btn.clicked.connect(self._on_screenshot_clicked)
        self.screenshot_btn.setEnabled(False)
        content_layout.addWidget(self.screenshot_btn)

        self.rotate_btn = ToolbarButton("↻", "360°", t("toolbar.rotate_tooltip"))
        self.rotate_btn.clicked.connect(self._on_rotate_clicked)
        self.rotate_btn.setEnabled(False)
        content_layout.addWidget(self.rotate_btn)

        # ── Rotate speed control (shown only while rotating) ─────────────────
        self._rotate_speed_widget = QWidget()
        self._rotate_speed_widget.setStyleSheet("background: transparent;")
        self._rotate_speed_widget.hide()
        _rs_lay = QHBoxLayout(self._rotate_speed_widget)
        _rs_lay.setContentsMargins(4, 0, 4, 0)
        _rs_lay.setSpacing(4)

        _rs_icon = QLabel("⚡")
        _rs_icon.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 11px; background: transparent;")
        _rs_lay.addWidget(_rs_icon)

        self._rotate_speed_slider = QSlider(Qt.Horizontal)
        self._rotate_speed_slider.setMinimum(2)
        self._rotate_speed_slider.setMaximum(90)
        self._rotate_speed_slider.setValue(15)
        self._rotate_speed_slider.setFixedWidth(80)
        self._rotate_speed_slider.setFixedHeight(18)
        self._rotate_speed_slider.setToolTip("Rotation speed (°/sec)")
        self._rotate_speed_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 4px;
                background: {default_theme.border_standard};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 12px; height: 12px;
                background: {default_theme.button_primary};
                border-radius: 6px;
                margin: -4px 0;
            }}
            QSlider::sub-page:horizontal {{
                background: {default_theme.button_primary};
                border-radius: 2px;
            }}
        """ + TOOLTIP_STYLE)
        self._rotate_speed_slider.valueChanged.connect(self._on_rotate_speed_slider_changed)
        _rs_lay.addWidget(self._rotate_speed_slider)

        self._rotate_speed_label = QLabel("15°/s")
        self._rotate_speed_label.setStyleSheet(
            f"color: {default_theme.text_primary}; font-size: 10px; font-weight: bold; background: transparent; min-width: 30px;"
        )
        _rs_lay.addWidget(self._rotate_speed_label)

        # Divider before axis toggle
        _axis_div = QFrame()
        _axis_div.setFrameShape(QFrame.VLine)
        _axis_div.setFixedWidth(1)
        _axis_div.setFixedHeight(20)
        _axis_div.setStyleSheet(f"background: {default_theme.border_standard}; border: none;")
        _rs_lay.addWidget(_axis_div)

        # H / V axis toggle buttons
        _btn_active_ss = f"""
            QPushButton {{
                background: {default_theme.button_primary};
                color: #ffffff; border: none;
                border-radius: 4px;
                font-size: 11px; font-weight: bold;
                padding: 2px 7px;
            }}
        """
        _btn_inactive_ss = f"""
            QPushButton {{
                background: {default_theme.border_standard};
                color: {default_theme.text_primary}; border: none;
                border-radius: 4px;
                font-size: 11px; font-weight: bold;
                padding: 2px 7px;
            }}
            QPushButton:hover {{ background: {default_theme.row_bg_hover}; }}
        """
        self._rotate_axis_h_btn = QPushButton("H")
        self._rotate_axis_h_btn.setFixedHeight(20)
        self._rotate_axis_h_btn.setToolTip("Horizontal rotation (turntable)")
        self._rotate_axis_h_btn.setStyleSheet(_btn_active_ss)
        self._rotate_axis_h_btn.setCursor(Qt.PointingHandCursor)
        self._rotate_axis_h_btn.clicked.connect(lambda: self._on_rotate_axis_clicked('h'))
        _rs_lay.addWidget(self._rotate_axis_h_btn)

        self._rotate_axis_v_btn = QPushButton("V")
        self._rotate_axis_v_btn.setFixedHeight(20)
        self._rotate_axis_v_btn.setToolTip("Vertical rotation (wheel)")
        self._rotate_axis_v_btn.setStyleSheet(_btn_inactive_ss)
        self._rotate_axis_v_btn.setCursor(Qt.PointingHandCursor)
        self._rotate_axis_v_btn.clicked.connect(lambda: self._on_rotate_axis_clicked('v'))
        _rs_lay.addWidget(self._rotate_axis_v_btn)

        self._rotate_axis_active_ss   = _btn_active_ss
        self._rotate_axis_inactive_ss = _btn_inactive_ss

        content_layout.addWidget(self._rotate_speed_widget)

        self.record_btn = _RecButton(t("toolbar.record_tooltip"))
        self.record_btn.clicked.connect(self._on_record_clicked)
        self.record_btn.setEnabled(False)
        content_layout.addWidget(self.record_btn)

        content_layout.addWidget(_sep())

        # ── Group 5: Appearance ───────────────────────────────────────────────
        self.texture_btn = ToolbarButton("🎨", t("toolbar.texture"), t("toolbar.texture_tooltip"))
        self.texture_btn.clicked.connect(self._on_texture_clicked)
        self.texture_btn.setEnabled(False)
        content_layout.addWidget(self.texture_btn)

        # Parts button — hidden, accessed via Visual Style dropdown
        self.parts_btn = ToolbarButton("🧩", t("toolbar.parts"), "")
        self.parts_btn.clicked.connect(self._on_parts_selected)
        self.parts_btn.setEnabled(False)
        self.parts_btn.setVisible(False)

        content_layout.addWidget(_sep())

        # ── Group 6: File / window ────────────────────────────────────────────
        self.convert_btn = ToolbarButton("🔄", t("toolbar.convert"), t("toolbar.convert_tooltip"))
        self.convert_btn.clicked.connect(self._on_convert_clicked)
        content_layout.addWidget(self.convert_btn)

        self.fullscreen_btn = ToolbarButton("⛶", t("toolbar.fullscreen"), "")
        self.fullscreen_btn.clicked.connect(self._on_fullscreen_clicked)
        content_layout.addWidget(self.fullscreen_btn)

        # Folder/load icon removed from the visible toolbar — loading a 3D
        # file is already available from the sidebar's Upload button, and
        # this was redundant clutter. The button object is kept (but never
        # added to the layout) so set_loaded_filename() and other internal
        # bookkeeping below don't need special-casing.
        self.load_btn = ToolbarButton("📂", "", "Load or replace 3D file (STL/STEP/3DM/OBJ/IGES)")
        self.load_btn.clicked.connect(self._on_load_clicked)
        self.load_btn.setFixedWidth(44)
        self.load_btn.hide()

        self.reset_model_btn = ToolbarButton("↻", "", "Clear current model from view")
        self.reset_model_btn.clicked.connect(self._on_reset_model_clicked)
        self.reset_model_btn.setFixedWidth(44)
        self.reset_model_btn.setEnabled(False)
        content_layout.addWidget(self.reset_model_btn)
        
        # Apply tooltip styling for black text
        self._apply_tooltip_style()

        # Set toolbar_content into scroll area
        self.toolbar_scroll.setWidget(self.toolbar_content)

        container_layout.addWidget(self.toolbar_scroll)

        main_layout.addWidget(self.container)
    
    def set_stl_loaded(self, loaded):
        """Enable/disable view controls based on STL loaded state."""
        self.stl_loaded = loaded
        self.reset_btn.setEnabled(loaded)
        self.view_btn.setEnabled(loaded)
        self.ruler_btn.setEnabled(loaded)
        self.annotation_btn.setEnabled(loaded)
        self.screenshot_btn.setEnabled(loaded)
        self.rotate_btn.setEnabled(loaded)
        self.record_btn.setEnabled(loaded)
        self.texture_btn.setEnabled(loaded)
        self.draw_btn.setEnabled(loaded)
        self.parts_btn.setEnabled(loaded)
        self.reset_model_btn.setEnabled(loaded)

    def set_read_only(self, read_only: bool):
        """Grey out the controls that change what gets saved (annotate,
        draw, render style, screenshot — screenshots are persisted into the
        project file too, see ui/screenshot_panel.py) while the project is
        open read-only — leaves pure-viewing controls (rotate/reset/2D
        views/ruler) untouched. Re-applying set_stl_loaded's own gating on
        the way back out rather than blindly re-enabling, so a tool that's
        disabled because no model is loaded doesn't light up just because
        read-only was lifted."""
        self._read_only = read_only
        self.render_mode_btn.setEnabled(not read_only)
        self.annotation_btn.setEnabled(self.stl_loaded and not read_only)
        self.draw_btn.setEnabled(self.stl_loaded and not read_only)
        self.screenshot_btn.setEnabled(self.stl_loaded and not read_only)

    def _on_grid_clicked(self):
        """Handle grid toggle."""
        self.grid_enabled = not self.grid_enabled
        self.grid_btn.set_active(self.grid_enabled)
        self.toggle_grid.emit()
    
    def _on_theme_clicked(self):
        """Handle theme toggle."""
        self.dark_theme = not self.dark_theme
        if self.dark_theme:
            self.theme_btn.set_label(t("toolbar.dark"))
            self.theme_btn.set_icon("🌙")
        else:
            self.theme_btn.set_label(t("toolbar.light"))
            self.theme_btn.set_icon("☀")
        self.theme_btn.set_active(self.dark_theme)
        self.toggle_theme.emit()
    
    def _get_parts_icon_path(self):
        """Return path to the black parts icon (dev + PyInstaller)."""
        from ui.styles import _get_assets_dir
        return str(_get_assets_dir() / "parts_icon_black.png")

    def _show_render_mode_menu(self):
        """Show dropdown menu for render mode and parts selection."""
        try:
            logger.debug("_show_render_mode_menu: opening menu")
            menu = QMenu(self)
            menu.setStyleSheet(f"""
                QMenu {{
                    background-color: {default_theme.card_background};
                    border: 1px solid {default_theme.border_standard};
                    border-radius: 6px;
                    padding: 4px 0;
                }}
                QMenu::item {{
                    padding: 6px 16px;
                    color: {default_theme.text_primary};
                    font-size: 11px;
                }}
                QMenu::item:selected {{
                    background-color: {default_theme.row_bg_hover};
                }}
                QMenu::item:checked {{
                    font-weight: bold;
                }}
                QMenu::separator {{
                    height: 1px;
                    background: {default_theme.border_standard};
                    margin: 4px 8px;
                }}
            """)

            modes = [
                ("shaded",    "◆", t("toolbar.shaded")),
                ("solid",     "◇", t("toolbar.solid")),
                ("wireframe", "◈", t("toolbar.wireframe")),
            ]
            for mode_id, icon, label in modes:
                action = menu.addAction(f"{icon}  {label}")
                action.setCheckable(True)
                action.setChecked(self.render_mode == mode_id)
                action.triggered.connect(lambda checked, m=mode_id: self._set_render_mode(m))

            # Separator + Parts (QPixmap in QLabel — QAction+QIcon is tinted gray / oversized on macOS)
            menu.addSeparator()
            parts_icon_path = self._get_parts_icon_path()
            logger.debug("_show_render_mode_menu: parts_icon_path=%s", parts_icon_path)
            if not (parts_icon_path and os.path.isfile(parts_icon_path)):
                parts_icon_path = ""
            row = _PartsMenuRow(parts_icon_path, self.parts_mode_enabled, self.stl_loaded, menu)
            wa = QWidgetAction(menu)
            wa.setDefaultWidget(row)
            menu.addAction(wa)

            def _parts_row_activate():
                self._on_parts_selected()
                menu.close()

            row.clicked.connect(_parts_row_activate)

            # Show below the button
            menu.exec_(self.render_mode_btn.mapToGlobal(
                self.render_mode_btn.rect().bottomLeft()
            ))
            logger.debug("_show_render_mode_menu: menu closed")
        except Exception:
            logger.error("_show_render_mode_menu CRASHED", exc_info=True)

    def _show_view_menu(self):
        """Show 2D Views menu: Front, Left, Right, Rear, Top, Bottom."""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {default_theme.card_background};
                border: 1px solid {default_theme.border_standard};
                border-radius: 6px;
                padding: 4px 0;
            }}
            QMenu::item {{
                padding: 6px 16px;
                color: {default_theme.text_primary};
                font-size: 11px;
            }}
            QMenu::item:selected {{
                background-color: {default_theme.row_bg_hover};
            }}
            QMenu::item:checked {{
                font-weight: bold;
            }}
        """)
        views_2d = [
            ("front",  "⬚", t("toolbar.front")),
            ("left",   "⊏", t("toolbar.left")),
            ("right",  "⊐", t("toolbar.right")),
            ("rear",   "⬛", t("toolbar.rear")),
            ("top",    "⊤", t("toolbar.top")),
            ("bottom", "⊥", t("toolbar.bottom")),
        ]
        for view_id, icon, label in views_2d:
            action = menu.addAction(f"{icon}  {label}")
            action.setCheckable(True)
            action.setChecked(self._current_view == view_id)
            action.triggered.connect(lambda checked, v=view_id: self._set_view(v))
        menu.exec_(self.view_btn.mapToGlobal(self.view_btn.rect().bottomLeft()))

    def _set_view(self, view_id):
        """Set view preset and emit signal."""
        if self.parts_mode_enabled:
            self.parts_mode_enabled = False
            self.parts_btn.set_active(False)
            self.toggle_parts.emit()
        self._current_view = view_id
        self._sync_2d_views_button()
        if view_id == "front":
            self.view_front.emit()
        elif view_id == "rear":
            self.view_rear.emit()
        elif view_id == "left":
            self.view_left.emit()
        elif view_id == "right":
            self.view_right.emit()
        elif view_id == "top":
            self.view_top.emit()
        elif view_id == "bottom":
            self.view_bottom.emit()

    def _set_render_mode(self, mode):
        """Set the render mode and update button appearance."""
        self.render_mode = mode
        icons = {'solid': '◇', 'wireframe': '◈', 'shaded': '◆'}
        self.render_mode_btn.set_icon(icons[mode])
        self.render_mode_btn.set_label(t("toolbar.visual_style"))
        self.render_mode_btn.set_active(mode != 'shaded')
        self.render_mode_changed.emit(mode)
    
    def _on_reset_clicked(self):
        """Handle reset rotation."""
        self.reset_rotation.emit()
    
    def _on_ruler_clicked(self):
        """Handle ruler toggle."""
        self.ruler_mode_enabled = not self.ruler_mode_enabled
        if self.ruler_mode_enabled:
            self.ruler_btn.set_label(t("toolbar.ruler"))
            self.ruler_btn.set_icon("📐")
            if self.parts_mode_enabled:
                self.parts_mode_enabled = False
                self.parts_btn.set_active(False)
                self.toggle_parts.emit()
            if self.annotation_mode_enabled:
                self.annotation_mode_enabled = False
                self.annotation_btn.set_active(False)
                self.annotation_btn.set_icon("📝")
            if self.draw_mode_enabled:
                self.draw_mode_enabled = False
                self._eraser_active = False
                self.draw_btn.set_active(False)
                self.draw_btn.set_label(t("toolbar.draw"))
                self._hide_draw_extras()
        else:
            self.ruler_btn.set_label(t("toolbar.ruler"))
            self.ruler_btn.set_icon("📏")
        self.ruler_btn.set_active(self.ruler_mode_enabled)
        self.toggle_ruler.emit()
    
    def _show_annotate_menu(self):
        """Show dropdown menu with Annotation and 3D Arrow options."""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {default_theme.card_background};
                border: 1px solid {default_theme.border_standard};
                border-radius: 6px;
                padding: 4px 0;
            }}
            QMenu::item {{
                padding: 6px 16px;
                color: {default_theme.text_primary};
                font-size: 11px;
            }}
            QMenu::item:selected {{
                background-color: {default_theme.row_bg_hover};
            }}
            QMenu::item:checked {{
                font-weight: bold;
            }}
        """)

        annotate_action = menu.addAction(f"📝  {t('toolbar.annotate_item')}")
        annotate_action.setCheckable(True)
        annotate_action.setChecked(self.annotation_mode_enabled)
        annotate_action.triggered.connect(self._on_annotation_selected)

        arrow_action = menu.addAction(f"➤  {t('toolbar.arrow_3d_item')}")
        arrow_action.setCheckable(True)
        arrow_action.setChecked(self.arrow_mode_enabled)
        arrow_action.triggered.connect(self._on_arrow_selected)

        menu.exec_(self.annotation_btn.mapToGlobal(
            self.annotation_btn.rect().bottomLeft()
        ))

    def _on_annotation_selected(self):
        """Handle annotation mode selection from dropdown."""
        # If arrow mode is active, exit it first
        if self.arrow_mode_enabled:
            self.arrow_mode_enabled = False
            self.toggle_arrow.emit()

        self.annotation_mode_enabled = not self.annotation_mode_enabled
        if self.annotation_mode_enabled:
            self.annotation_btn.set_label(t("toolbar.annotate"))
            self.annotation_btn.set_icon("✏️")
            if self.parts_mode_enabled:
                self.parts_mode_enabled = False
                self.parts_btn.set_active(False)
                self.toggle_parts.emit()
            if self.ruler_mode_enabled:
                self.ruler_mode_enabled = False
                self.ruler_btn.set_active(False)
                self.ruler_btn.set_icon("📏")
            if self.screenshot_mode_enabled:
                self.screenshot_mode_enabled = False
                self.screenshot_btn.set_active(False)
            if self.draw_mode_enabled:
                self.draw_mode_enabled = False
                self._eraser_active = False
                self.draw_btn.set_active(False)
                self.draw_btn.set_label(t("toolbar.draw"))
                self._hide_draw_extras()
        else:
            self.annotation_btn.set_label(t("toolbar.annotate"))
            self.annotation_btn.set_icon("📝")
        self.annotation_btn.set_active(self.annotation_mode_enabled)
        self.toggle_annotation.emit()

    def _on_arrow_selected(self):
        """Handle 3D arrow mode selection from dropdown."""
        # If annotation mode is active, exit it first
        if self.annotation_mode_enabled:
            self.annotation_mode_enabled = False
            self.annotation_btn.set_active(False)
            self.toggle_annotation.emit()

        self.arrow_mode_enabled = not self.arrow_mode_enabled
        if self.arrow_mode_enabled:
            self.annotation_btn.set_label(t("toolbar.arrow"))
            self.annotation_btn.set_icon("➤")
            if self.parts_mode_enabled:
                self.parts_mode_enabled = False
                self.parts_btn.set_active(False)
                self.toggle_parts.emit()
            if self.ruler_mode_enabled:
                self.ruler_mode_enabled = False
                self.ruler_btn.set_active(False)
                self.ruler_btn.set_icon("📏")
            # Screenshot: do NOT clear flags here — main window must run _exit_screenshot_mode()
            # to hide the rubber-band overlay. Clearing only the toolbar flag prevents that and
            # leaves the overlay intercepting clicks so arrows can't be placed.
            if self.draw_mode_enabled:
                self.draw_mode_enabled = False
                self._eraser_active = False
                self.draw_btn.set_active(False)
                self.draw_btn.set_label(t("toolbar.draw"))
                self._hide_draw_extras()
        else:
            self.annotation_btn.set_label(t("toolbar.annotate"))
            self.annotation_btn.set_icon("📝")
        self.annotation_btn.set_active(self.arrow_mode_enabled)
        self.toggle_arrow.emit()

    def _on_parts_selected(self):
        """Handle parts mode selection from dropdown."""
        # Exit other modes
        if self.annotation_mode_enabled:
            self.annotation_mode_enabled = False
            self.annotation_btn.set_active(False)
            self.annotation_btn.set_icon("📝")
            self.toggle_annotation.emit()
        if self.arrow_mode_enabled:
            self.arrow_mode_enabled = False
            self.annotation_btn.set_active(False)
            self.annotation_btn.set_icon("📝")
            self.toggle_arrow.emit()

        self.parts_mode_enabled = not self.parts_mode_enabled
        if self.parts_mode_enabled:
            if self.ruler_mode_enabled:
                self.ruler_mode_enabled = False
                self.ruler_btn.set_active(False)
                self.ruler_btn.set_icon("📏")
            if self.screenshot_mode_enabled:
                self.screenshot_mode_enabled = False
                self.screenshot_btn.set_active(False)
            if self.draw_mode_enabled:
                self.draw_mode_enabled = False
                self._eraser_active = False
                self.draw_btn.set_active(False)
                self.draw_btn.set_label(t("toolbar.draw"))
                self._hide_draw_extras()
        self.parts_btn.set_active(self.parts_mode_enabled)
        self.toggle_parts.emit()
    
    def _on_rotate_clicked(self):
        """Handle rotate mode toggle (no mode conflicts — rotate works alongside any other mode)."""
        self.rotate_mode_enabled = not self.rotate_mode_enabled
        self.rotate_btn.set_active(self.rotate_mode_enabled)
        self.rotate_btn.set_label("360°")
        self._rotate_speed_widget.setVisible(self.rotate_mode_enabled)
        if not self.rotate_mode_enabled:
            self._on_rotate_axis_clicked('h')
        self.toggle_rotate.emit()

    def _on_rotate_speed_slider_changed(self, value: int):
        self._rotate_speed_label.setText(f"{value}°/s")
        self.rotate_speed_changed.emit(float(value))

    def _on_rotate_axis_clicked(self, axis: str):
        self._rotate_axis_h_btn.setStyleSheet(
            self._rotate_axis_active_ss if axis == 'h' else self._rotate_axis_inactive_ss
        )
        self._rotate_axis_v_btn.setStyleSheet(
            self._rotate_axis_active_ss if axis == 'v' else self._rotate_axis_inactive_ss
        )
        self.rotate_axis_changed.emit(axis)

    def _on_record_clicked(self):
        """Handle record mode toggle — exits conflicting exclusive modes first."""
        self.record_mode_enabled = not self.record_mode_enabled
        if self.record_mode_enabled:
            # Exit modes that conflict with a clean viewport recording
            if self.ruler_mode_enabled:
                self.ruler_mode_enabled = False
                self.ruler_btn.set_active(False)
                self.ruler_btn.set_icon("📏")
            if self.annotation_mode_enabled:
                self.annotation_mode_enabled = False
                self.annotation_btn.set_active(False)
                self.annotation_btn.set_icon("📝")
            if self.screenshot_mode_enabled:
                self.screenshot_mode_enabled = False
                self.screenshot_btn.set_active(False)
                self.toggle_screenshot.emit()
            if self.texture_mode_enabled:
                self.texture_mode_enabled = False
                self.texture_btn.set_active(False)
                self.toggle_texture.emit()
            if self.draw_mode_enabled:
                self.draw_mode_enabled = False
                self._eraser_active = False
                self.draw_btn.set_active(False)
                self.draw_btn.set_label(t("toolbar.draw"))
                self._hide_draw_extras()
        self.record_btn.set_active(self.record_mode_enabled)
        self.record_btn.set_label(t("toolbar.rec") if self.record_mode_enabled else t("toolbar.record"))
        self.toggle_record.emit()

    def _on_screenshot_clicked(self):
        """Handle screenshot mode toggle."""
        self.screenshot_mode_enabled = not self.screenshot_mode_enabled
        if self.screenshot_mode_enabled:
            if self.parts_mode_enabled:
                self.parts_mode_enabled = False
                self.parts_btn.set_active(False)
                self.toggle_parts.emit()
            if self.ruler_mode_enabled:
                self.ruler_mode_enabled = False
                self.ruler_btn.set_active(False)
                self.ruler_btn.set_icon("📏")
            if self.annotation_mode_enabled:
                self.annotation_mode_enabled = False
                self.annotation_btn.set_active(False)
                self.annotation_btn.set_icon("📝")
            if self.texture_mode_enabled:
                self.texture_mode_enabled = False
                self.texture_btn.set_active(False)
                self.toggle_texture.emit()
            if self.draw_mode_enabled:
                self.draw_mode_enabled = False
                self._eraser_active = False
                self.draw_btn.set_active(False)
                self.draw_btn.set_label(t("toolbar.draw"))
                self._hide_draw_extras()
        self.screenshot_btn.set_active(self.screenshot_mode_enabled)
        self.toggle_screenshot.emit()

    def _on_texture_clicked(self):
        """Handle texture mode toggle."""
        self.texture_mode_enabled = not self.texture_mode_enabled
        if self.texture_mode_enabled:
            if self.parts_mode_enabled:
                self.parts_mode_enabled = False
                self.parts_btn.set_active(False)
                self.toggle_parts.emit()
            if self.ruler_mode_enabled:
                self.ruler_mode_enabled = False
                self.ruler_btn.set_active(False)
                self.ruler_btn.set_icon("📏")
            if self.annotation_mode_enabled:
                self.annotation_mode_enabled = False
                self.annotation_btn.set_active(False)
                self.annotation_btn.set_icon("📝")
            if self.screenshot_mode_enabled:
                self.screenshot_mode_enabled = False
                self.screenshot_btn.set_active(False)
            if self.draw_mode_enabled:
                self.draw_mode_enabled = False
                self._eraser_active = False
                self.draw_btn.set_active(False)
                self.draw_btn.set_label(t("toolbar.draw"))
                self._hide_draw_extras()
        self.texture_btn.set_active(self.texture_mode_enabled)
        self.toggle_texture.emit()
    
    def _show_draw_menu(self):
        """Show dropdown menu with Draw, Eraser, Color, Undo, Clear options.
        Always shows the menu so tools and font size remain accessible while draw mode is on.
        """
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {default_theme.card_background};
                border: 1px solid {default_theme.border_standard};
                border-radius: 6px;
                padding: 4px 0;
            }}
            QMenu::item {{
                padding: 6px 16px;
                color: {default_theme.text_primary};
                font-size: 11px;
            }}
            QMenu::item:selected {{
                background-color: {default_theme.row_bg_hover};
            }}
            QMenu::item:checked {{
                font-weight: bold;
            }}
        """)

        from PyQt5.QtWidgets import QActionGroup

        # Exit draw mode — only shown when already active
        if self.draw_mode_enabled:
            def _exit_draw():
                self.draw_mode_enabled = False
                self.draw_btn.set_active(False)
                self.draw_btn.set_label(t("toolbar.draw"))
                self._hide_draw_extras()
                self.toggle_draw.emit()
            exit_action = menu.addAction(f"✕  {t('toolbar.exit_draw')}")
            exit_action.triggered.connect(_exit_draw)
            menu.addSeparator()

        # Mutually exclusive tool selection — clicking any tool auto-enables draw mode
        tool_group = QActionGroup(menu)
        tool_group.setExclusive(True)

        pen_active = self.draw_mode_enabled and not self._eraser_active and not self._draw_text_active
        pen_action = menu.addAction(f"✏  {t('toolbar.pen')}")
        pen_action.setCheckable(True)
        pen_action.setChecked(pen_active)
        pen_action.triggered.connect(self._on_pen_tool_selected)
        tool_group.addAction(pen_action)

        eraser_action = menu.addAction(f"🧹  {t('toolbar.eraser')}")
        eraser_action.setCheckable(True)
        eraser_action.setChecked(self.draw_mode_enabled and self._eraser_active)
        eraser_action.triggered.connect(self._on_eraser_tool_selected)
        tool_group.addAction(eraser_action)

        text_action = menu.addAction(f"T  {t('toolbar.text_tool')}")
        text_action.setCheckable(True)
        text_action.setChecked(self.draw_mode_enabled and self._draw_text_active)
        text_action.triggered.connect(self._on_text_tool_selected)
        tool_group.addAction(text_action)

        # Font size — directly below Text (no separator), always visible
        from PyQt5.QtWidgets import QDoubleSpinBox, QHBoxLayout, QWidget, QLabel
        _fs_widget = QWidget()
        _fs_widget.setStyleSheet("background: transparent;")
        _fs_lay = QHBoxLayout(_fs_widget)
        _fs_lay.setContentsMargins(32, 3, 16, 3)
        _fs_lay.setSpacing(8)
        _fs_lbl = QLabel(t("toolbar.font_size"))
        _fs_lbl.setStyleSheet(
            f"color: {default_theme.text_primary}; font-size: 11px; background: transparent;"
        )
        _fs_spin = QDoubleSpinBox()
        _fs_spin.setRange(0.5, 5.0)
        _fs_spin.setSingleStep(0.5)
        _fs_spin.setDecimals(1)
        _fs_spin.setValue(self._draw_font_size_multiplier)
        _fs_spin.setSuffix("×")
        _fs_spin.setFixedWidth(80)
        _fs_spin.setFixedHeight(26)
        _fs_spin.setStyleSheet(f"""
            QDoubleSpinBox {{
                background: {default_theme.card_background}; color: {default_theme.text_primary};
                border: 1px solid {default_theme.border_standard}; border-radius: 4px;
                padding: 2px 4px; font-size: 11px;
            }}
            QDoubleSpinBox:focus {{ border-color: {default_theme.button_primary}; }}
            QDoubleSpinBox::up-button {{
                subcontrol-origin: border; subcontrol-position: top right;
                width: 16px; border-left: 1px solid {default_theme.border_standard};
                border-top-right-radius: 4px; background: {default_theme.row_bg_standard};
            }}
            QDoubleSpinBox::up-button:hover {{ background: {default_theme.button_primary}; }}
            QDoubleSpinBox::up-arrow {{ image: url({_arrow_up()}); width: 8px; height: 8px; }}
            QDoubleSpinBox::down-button {{
                subcontrol-origin: border; subcontrol-position: bottom right;
                width: 16px; border-left: 1px solid {default_theme.border_standard};
                border-bottom-right-radius: 4px; background: {default_theme.row_bg_standard};
            }}
            QDoubleSpinBox::down-button:hover {{ background: {default_theme.button_primary}; }}
            QDoubleSpinBox::down-arrow {{ image: url({_arrow_down()}); width: 8px; height: 8px; }}
        """)
        _fs_spin.valueChanged.connect(lambda v: (
            setattr(self, '_draw_font_size_multiplier', v),
            self.draw_font_size_changed.emit(v)
        ))
        _fs_lay.addWidget(_fs_lbl)
        _fs_lay.addWidget(_fs_spin)
        _fs_action = QWidgetAction(menu)
        _fs_action.setDefaultWidget(_fs_widget)
        menu.addAction(_fs_action)

        menu.addSeparator()

        color_action = menu.addAction(f"🎨  {t('toolbar.draw_color')}")
        color_action.triggered.connect(self.show_draw_color_picker)

        undo_action = menu.addAction(f"↩  {t('toolbar.undo_stroke')}")
        undo_action.setEnabled(self.draw_mode_enabled)
        undo_action.triggered.connect(self.draw_undo_requested.emit)

        undo_text_action = menu.addAction(f"↩  {t('toolbar.undo_word')}")
        undo_text_action.setEnabled(self.draw_mode_enabled)
        undo_text_action.triggered.connect(self.draw_undo_text_requested.emit)

        clear_action = menu.addAction(f"🗑  {t('toolbar.clear_all')}")
        clear_action.setEnabled(self.draw_mode_enabled)
        clear_action.triggered.connect(self.draw_clear_requested.emit)

        menu.exec_(self.draw_btn.mapToGlobal(
            self.draw_btn.rect().bottomLeft()
        ))

    def _ensure_draw_mode_on(self):
        """Enable draw mode if it isn't already (called by tool selectors)."""
        if not self.draw_mode_enabled:
            self.draw_mode_enabled = True
            self.draw_btn.set_active(True)
            if self.parts_mode_enabled:
                self.parts_mode_enabled = False
                self.parts_btn.set_active(False)
                self.toggle_parts.emit()
            if self.ruler_mode_enabled:
                self.ruler_mode_enabled = False
                self.ruler_btn.set_active(False)
                self.ruler_btn.set_icon("📏")
            if self.annotation_mode_enabled:
                self.annotation_mode_enabled = False
                self.annotation_btn.set_active(False)
                self.annotation_btn.set_icon("📝")
            self.toggle_draw.emit()

    def _on_pen_tool_selected(self):
        """Switch to pen tool — enables draw mode automatically if needed."""
        was_off = not self.draw_mode_enabled
        self._ensure_draw_mode_on()
        self._eraser_active = False
        self._draw_text_active = False
        self.draw_btn.set_label(t("toolbar.drawing"))
        self.draw_eraser_toggled.emit(False)
        self.draw_text_toggled.emit(False)
        if was_off:
            self.draw_color_picker_requested.emit()

    def _on_eraser_tool_selected(self):
        """Switch to eraser tool — enables draw mode automatically, no color picker."""
        self._ensure_draw_mode_on()
        self._eraser_active = True
        self._draw_text_active = False
        self.draw_btn.set_label(f"{t('toolbar.eraser')} ▼")
        self.draw_text_toggled.emit(False)
        self.draw_eraser_toggled.emit(True)

    def _on_text_tool_selected(self):
        """Switch to text tool — enables draw mode automatically if needed."""
        was_off = not self.draw_mode_enabled
        self._ensure_draw_mode_on()
        self._eraser_active = False
        self._draw_text_active = True
        self.draw_btn.set_label(f"{t('toolbar.text_tool')} ▼")
        self.draw_eraser_toggled.emit(False)
        self.draw_text_toggled.emit(True)
        if was_off:
            self.draw_color_picker_requested.emit()

    def _on_draw_toggled(self):
        """Toggle draw mode on/off."""
        self.draw_mode_enabled = not self.draw_mode_enabled
        if self.draw_mode_enabled:
            self.draw_btn.set_label(t("toolbar.drawing"))
            if self.parts_mode_enabled:
                self.parts_mode_enabled = False
                self.parts_btn.set_active(False)
                self.toggle_parts.emit()
            if self.ruler_mode_enabled:
                self.ruler_mode_enabled = False
                self.ruler_btn.set_active(False)
                self.ruler_btn.set_icon("📏")
            if self.annotation_mode_enabled:
                self.annotation_mode_enabled = False
                self.annotation_btn.set_active(False)
                self.annotation_btn.set_icon("📝")
            # Screenshot: do not clear flags here — main window must run _exit_screenshot_mode()
            # (overlay + panel). Clearing only the toolbar flag prevented that from running.
        else:
            self.draw_btn.set_label(t("toolbar.draw"))
            self._eraser_active = False
            self.draw_eraser_toggled.emit(False)
            self._hide_draw_extras()
        self.draw_btn.set_active(self.draw_mode_enabled)
        self.toggle_draw.emit()

    def _on_eraser_toggled(self):
        """Toggle eraser mode."""
        self._eraser_active = not self._eraser_active
        self._draw_text_active = False
        self.draw_btn.set_label(f"{t('toolbar.eraser')} ▼" if self._eraser_active else t("toolbar.drawing"))
        self.draw_eraser_toggled.emit(self._eraser_active)
        self.draw_text_toggled.emit(False)

    def _on_text_toggled(self):
        """Toggle text placement mode."""
        self._draw_text_active = not self._draw_text_active
        if self._draw_text_active:
            self._eraser_active = False
            self.draw_eraser_toggled.emit(False)
        self.draw_btn.set_label(f"{t('toolbar.text_tool')} ▼" if self._draw_text_active else t("toolbar.drawing"))
        self.draw_text_toggled.emit(self._draw_text_active)

    def _hide_draw_extras(self):
        """Clear text-mode flag when exiting draw mode."""
        self._draw_text_active = False

    def reset_draw_state(self):
        """Reset draw button state (called when exiting draw mode externally)."""
        self.draw_mode_enabled = False
        self._eraser_active = False
        self._draw_text_active = False
        self.draw_btn.set_label(t("toolbar.draw"))
        self.draw_btn.set_active(False)
    
    def show_draw_color_picker(self):
        """Show the color picker popup below the draw button."""
        from ui.draw_color_picker import DrawColorPicker
        picker = DrawColorPicker(self)
        picker.color_selected.connect(self._on_draw_color_selected)
        pos = self.draw_btn.mapToGlobal(self.draw_btn.rect().bottomLeft())
        picker.move(pos)
        picker.show()
    
    def _on_draw_color_selected(self, color: str):
        """Handle color selected from draw color picker."""
        self._draw_color = color
        self.draw_color_changed.emit(color)
    
    def _on_fullscreen_clicked(self):
        """Handle fullscreen toggle."""
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.fullscreen_btn.set_label(t("toolbar.fullscreen_exit"))
            self.fullscreen_btn.set_icon("⛶")
        else:
            self.fullscreen_btn.set_label(t("toolbar.fullscreen"))
            self.fullscreen_btn.set_icon("⛶")
        self.fullscreen_btn.set_active(self.is_fullscreen)
        self.toggle_fullscreen.emit()

    def _on_convert_clicked(self):
        """Handle convert button click."""
        self.open_converter.emit()

    def _sync_2d_views_button(self):
        """Keep label '2D Views ▼'; icon reflects current orthographic view."""
        icons = {"front": "⬚", "rear": "⬛", "left": "⊏", "right": "⊐", "top": "⊤", "bottom": "⊥"}
        self.view_btn.set_icon(icons.get(self._current_view, "⬚"))
        self.view_btn.set_label(t("toolbar.2d_views"))

    def _restore_view_btn(self):
        """Restore 2D Views button icon after exiting Parts mode."""
        self._sync_2d_views_button()

    def reset_parts_state(self):
        """Reset parts button state (called when exiting parts mode externally)."""
        self.parts_mode_enabled = False
        self.parts_btn.set_active(False)
    
    def _on_load_clicked(self):
        """Handle load file."""
        self.load_file.emit()
    

    def _on_reset_model_clicked(self):
        """Handle reset model (clear current model from view)."""
        self.clear_model.emit()

    def reset_fullscreen_state(self):
        """Reset fullscreen button state (called when exiting fullscreen externally)."""
        self.is_fullscreen = False
        self.fullscreen_btn.set_label(t("toolbar.fullscreen"))
        self.fullscreen_btn.set_active(False)
    
    def reset_annotation_state(self):
        """Reset annotation button state (called when exiting annotation mode externally)."""
        self.annotation_mode_enabled = False
        self.arrow_mode_enabled = False
        self.annotation_btn.set_label(t("toolbar.annotate"))
        self.annotation_btn.set_icon("📝")
        self.annotation_btn.set_active(False)

    def reset_arrow_state(self):
        """Reset arrow button state (called when exiting arrow mode externally)."""
        self.arrow_mode_enabled = False
        if not self.annotation_mode_enabled:
            self.annotation_btn.set_label(t("toolbar.annotate"))
            self.annotation_btn.set_icon("📝")
            self.annotation_btn.set_active(False)
    
    def reset_screenshot_state(self):
        """Reset screenshot button state (called when exiting screenshot mode externally)."""
        self.screenshot_mode_enabled = False
        self.screenshot_btn.set_active(False)

    def reset_texture_state(self):
        """Reset texture button state (called when exiting texture mode externally)."""
        self.texture_mode_enabled = False
        self.texture_btn.set_active(False)

    def reset_rotate_state(self):
        """Reset rotate button state (called when stopping rotation externally)."""
        self.rotate_mode_enabled = False
        self.rotate_btn.set_active(False)
        self.rotate_btn.set_label("360°")
        self._rotate_speed_widget.hide()

    def reset_record_state(self):
        """Reset record button state (called when stopping recording externally)."""
        self.record_mode_enabled = False
        self.record_btn.set_active(False)
        self.record_btn.set_label(t("toolbar.record"))

    def set_reader_mode(self, enabled: bool):
        """Enable or disable reader mode (disables annotation button)."""
        if enabled:
            self.annotation_btn.setEnabled(False)
            self.annotation_btn.setToolTip(t("toolbar.reader_mode_tooltip"))
        else:
            # Re-enable only if model is loaded
            if self.stl_loaded:
                self.annotation_btn.setEnabled(True)
            self.annotation_btn.setToolTip(t("toolbar.annotations_tooltip"))
    
    def set_loaded_filename(self, filename):
        """Update the load button tooltip to show the loaded filename."""
        if filename:
            self.load_btn.setToolTip(filename)
        else:
            self.load_btn.setToolTip(t("toolbar.load_tooltip"))
    
    def _apply_tooltip_style(self):
        """Tooltip style is defined centrally in get_global_stylesheet — nothing to do here."""
        pass

    def retranslate(self):
        """Update all toolbar button labels for the current language."""
        self.grid_btn.set_label(t("toolbar.grid"))
        if self.dark_theme:
            self.theme_btn.set_label(t("toolbar.dark"))
        else:
            self.theme_btn.set_label(t("toolbar.light"))
        self.render_mode_btn.set_label(t("toolbar.visual_style"))
        self.reset_btn.set_label(t("toolbar.reset"))
        self.view_btn.set_label(t("toolbar.2d_views"))
        self.ruler_btn.set_label(t("toolbar.ruler"))
        if self.arrow_mode_enabled:
            self.annotation_btn.set_label(t("toolbar.arrow"))
        elif self.annotation_mode_enabled:
            self.annotation_btn.set_label(t("toolbar.annotate"))
        else:
            self.annotation_btn.set_label(t("toolbar.annotate"))
        self.screenshot_btn.set_label("")
        self.texture_btn.set_label(t("toolbar.texture"))
        if self.draw_mode_enabled:
            if self._eraser_active:
                self.draw_btn.set_label(f"{t('toolbar.eraser')} ▼")
            elif self._draw_text_active:
                self.draw_btn.set_label(f"{t('toolbar.text_tool')} ▼")
            else:
                self.draw_btn.set_label(t("toolbar.drawing"))
        else:
            self.draw_btn.set_label(t("toolbar.draw"))
        self.convert_btn.set_label(t("toolbar.convert"))
        self.rotate_btn.set_label("360°")
        self.record_btn.set_label(t("toolbar.rec") if self.record_mode_enabled else t("toolbar.record"))
        if self.is_fullscreen:
            self.fullscreen_btn.set_label(t("toolbar.fullscreen_exit"))
        else:
            self.fullscreen_btn.set_label(t("toolbar.fullscreen"))
        self.ruler_btn.setToolTip(t("toolbar.measure_tooltip"))
        self.annotation_btn.setToolTip(t("toolbar.annotate_tooltip"))
        self.screenshot_btn.setToolTip(t("toolbar.screenshot_tooltip"))
        self.texture_btn.setToolTip(t("toolbar.texture_tooltip"))
        self.draw_btn.setToolTip(t("toolbar.draw_tooltip"))
        self.convert_btn.setToolTip(t("toolbar.convert_tooltip"))
        self.rotate_btn.setToolTip(t("toolbar.rotate_tooltip"))
        self.record_btn.setToolTip(t("toolbar.record_tooltip"))
        self.view_btn.setToolTip(t("toolbar.2d_views_tooltip"))
        self.load_btn.setToolTip(t("toolbar.load_tooltip"))
        self.reset_model_btn.setToolTip(t("toolbar.clear_tooltip"))