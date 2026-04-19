"""
Top horizontal toolbar for 3D view controls.
"""
import logging
import os
import sys
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QSizePolicy, QFrame, QSpacerItem, QApplication, QMenu, QAction,
    QScrollArea, QWidgetAction,
)
from PyQt5.QtCore import Qt, QRect, QEvent, pyqtSignal, QPropertyAnimation, QEasingCurve, QSettings
from PyQt5.QtGui import QFont, QFontMetrics, QPixmap, QPainter, QColor, QImage
from ui.styles import default_theme, make_font
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
        black = QColor(0, 0, 0)
        for r in range(2):
            for c in range(2):
                x = gap + c * (cell + gap)
                y = gap + r * (cell + gap)
                p.fillRect(QRect(x, y, cell, cell), black)
        p.end()
        logger.debug("_parts_menu_pixmap_fallback v2: ok size=%d cell=%d", size, cell)
        return pm
    except Exception:
        logger.warning("_parts_menu_pixmap_fallback v2 failed", exc_info=True)
        pm = QPixmap(max(size, 10), max(size, 10))
        pm.fill(QColor(0, 0, 0))
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
        return QPixmap.fromImage(img)
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

        txt = QLabel("Parts")
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


# Toolbar chips: white background + black labels (selected tab uses dark style in styles.py)
_TB_BG = "#ffffff"
_TB_FG = "#000000"
_TB_HOVER = "#f0f0f0"
_TB_BORDER = "#d0d0d0"


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
                    background-color: {_TB_BG};
                    border: 1px solid {default_theme.border_highlight};
                    border-radius: 6px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {_TB_BG};
                    border: 1px solid transparent;
                    border-radius: 6px;
                }}
            """)
    
    def _apply_hover_style(self):
        """Apply the hover style."""
        if self._is_active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {_TB_HOVER};
                    border: 1px solid {default_theme.border_highlight};
                    border-radius: 6px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {_TB_HOVER};
                    border: 1px solid {_TB_BORDER};
                    border-radius: 6px;
                }}
            """)
    
    def _apply_disabled_style(self):
        """Apply disabled style."""
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: #ececec;
                border: 1px solid transparent;
                border-radius: 6px;
            }}
        """)
        _ifs = getattr(self, '_icon_label_font_px', 12)
        self.icon_label.setStyleSheet(f"color: #888888; font-size: {_ifs}px; background: transparent;")
        self.text_label.setStyleSheet(_toolbar_label_style('#888888', self._label_font_size))
    
    def set_active(self, active):
        """Set the active state of the button."""
        self._is_active = active
        self._apply_default_style()
    
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
    draw_color_changed = pyqtSignal(str)  # hex color
    draw_eraser_toggled = pyqtSignal(bool)
    draw_text_toggled = pyqtSignal(bool)  # True = text mode on
    draw_undo_requested = pyqtSignal()
    draw_clear_requested = pyqtSignal()
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
        self._draw_color = '#FF0000'
        self._draw_text_active = False
        self.stl_loaded = False
        
        # Load saved state
        self.settings = QSettings("ECTOFORM", "Toolbar")
        self.is_expanded = self.settings.value("toolbar_expanded", True, type=bool)
        
        self.init_ui()
        self._update_expanded_state(animate=False)
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
                border-bottom: 1px solid {default_theme.border_standard};
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
        content_layout.setSpacing(8)
        
        # === Display & Mode Controls ===
        self.grid_btn = ToolbarButton("⊞", "Grid", "")
        self.grid_btn.set_active(True)
        self.grid_btn.clicked.connect(self._on_grid_clicked)
        content_layout.addWidget(self.grid_btn)
        
        self.theme_btn = ToolbarButton("☀", "Light", "")
        self.theme_btn.clicked.connect(self._on_theme_clicked)
        content_layout.addWidget(self.theme_btn)
        
        self.render_mode_btn = ToolbarButton("◇", "Visual Style ▼", "")
        self.render_mode_btn.clicked.connect(self._show_render_mode_menu)
        content_layout.addWidget(self.render_mode_btn)
        
        # Spacer between groups
        content_layout.addSpacerItem(QSpacerItem(16, 0, QSizePolicy.Fixed, QSizePolicy.Minimum))
        
        # === View Orientation Controls ===
        self.reset_btn = ToolbarButton("↺", "Reset", "")
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        self.reset_btn.setEnabled(False)
        content_layout.addWidget(self.reset_btn)
        
        # 2D Views dropdown (six orthographic presets)
        self._current_view = "front"
        self.view_btn = ToolbarButton(
            "⬚", "2D Views ▼",
            "2D orthographic views: Front, Left, Right, Rear, Top, Bottom",
        )
        self.view_btn.clicked.connect(self._show_view_menu)
        self.view_btn.setEnabled(False)
        content_layout.addWidget(self.view_btn)
        
        # Spacer between groups
        content_layout.addSpacerItem(QSpacerItem(16, 0, QSizePolicy.Fixed, QSizePolicy.Minimum))
        
        # === Utility Actions ===
        _ruler_label_px = 12 if sys.platform == 'win32' else 10
        self.ruler_btn = ToolbarButton(
            "📏", "Ruler", "Measure distances on the model", label_font_size=_ruler_label_px
        )
        self.ruler_btn.clicked.connect(self._on_ruler_clicked)
        self.ruler_btn.setEnabled(False)  # Disabled until model is loaded
        content_layout.addWidget(self.ruler_btn)
        
        _anno_icon = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "assets", "annotation_icon.png"))
        self.annotation_btn = ToolbarButton(
            "📝", "Annotate ▼", "Add annotations or 3D arrows",
            icon_path=_anno_icon if os.path.exists(_anno_icon) else None
        )
        self.annotation_btn.clicked.connect(self._show_annotate_menu)
        self.annotation_btn.setEnabled(False)  # Disabled until model is loaded
        content_layout.addWidget(self.annotation_btn)
        
        self.screenshot_btn = ToolbarButton("📷", "Screenshot", "Capture a region of the 3D view")
        self.screenshot_btn.clicked.connect(self._on_screenshot_clicked)
        self.screenshot_btn.setEnabled(False)  # Disabled until model is loaded
        content_layout.addWidget(self.screenshot_btn)
        
        self.texture_btn = ToolbarButton("🎨", "Texture", "Upload and apply textures to model parts")
        self.texture_btn.clicked.connect(self._on_texture_clicked)
        self.texture_btn.setEnabled(False)  # Disabled until model is loaded
        content_layout.addWidget(self.texture_btn)
        
        self.draw_btn = ToolbarButton("🖊", "Draw ▼", "Freehand draw on model surface")
        self.draw_btn.clicked.connect(self._show_draw_menu)
        self.draw_btn.setEnabled(False)  # Disabled until model is loaded
        content_layout.addWidget(self.draw_btn)
        self._eraser_active = False
        
        # Parts button - hidden, state managed via Visual Style dropdown
        self.parts_btn = ToolbarButton("🧩", "Parts", "Toggle part visibility and selection")
        self.parts_btn.clicked.connect(self._on_parts_selected)
        self.parts_btn.setEnabled(False)
        self.parts_btn.setVisible(False)  # Not shown in toolbar; accessed via Visual Style menu
        
        # Spacer before utility group
        content_layout.addSpacerItem(QSpacerItem(16, 0, QSizePolicy.Fixed, QSizePolicy.Minimum))

        # Convert button - always enabled
        self.convert_btn = ToolbarButton("🔄", "Convert", "Convert between 3D file formats (3DM, STEP, STL)")
        self.convert_btn.clicked.connect(self._on_convert_clicked)
        content_layout.addWidget(self.convert_btn)

        self.fullscreen_btn = ToolbarButton("⛶", "Fullscreen", "")
        self.fullscreen_btn.clicked.connect(self._on_fullscreen_clicked)
        content_layout.addWidget(self.fullscreen_btn)
        
        # Load button - icon only with tooltip for filename
        self.load_btn = ToolbarButton("📂", "", "Load or replace 3D file (STL/STEP/3DM/OBJ/IGES)")
        self.load_btn.clicked.connect(self._on_load_clicked)
        self.load_btn.setFixedWidth(44)
        content_layout.addWidget(self.load_btn)
        
        # Reset button - icon only to clear current model
        self.reset_model_btn = ToolbarButton("↻", "", "Clear current model from view")
        self.reset_model_btn.clicked.connect(self._on_reset_model_clicked)
        self.reset_model_btn.setFixedWidth(44)
        self.reset_model_btn.setEnabled(False)  # Disabled until a model is loaded
        content_layout.addWidget(self.reset_model_btn)
        
        # Apply tooltip styling for black text
        self._apply_tooltip_style()
        
        # Collapse button (at the end) - outside scroll area
        self.collapse_btn = ToolbarButton("▲", "", "")
        self.collapse_btn.clicked.connect(self._toggle_expanded)
        self.collapse_btn.setFixedWidth(36)
        
        # Set toolbar_content into scroll area
        self.toolbar_scroll.setWidget(self.toolbar_content)
        
        # Build the expanded row: scroll area + collapse button
        expanded_row = QHBoxLayout()
        expanded_row.setContentsMargins(0, 0, 4, 0)
        expanded_row.setSpacing(0)
        expanded_row.addWidget(self.toolbar_scroll, 1)
        expanded_row.addWidget(self.collapse_btn)
        
        self.expanded_widget = QWidget()
        self.expanded_widget.setLayout(expanded_row)
        container_layout.addWidget(self.expanded_widget)
        
        # Collapsed strip (only shown when collapsed)
        self.collapsed_strip = QWidget()
        self.collapsed_strip.setObjectName("collapsedStrip")
        self.collapsed_strip.setFixedHeight(28)
        strip_layout = QHBoxLayout(self.collapsed_strip)
        strip_layout.setContentsMargins(12, 4, 12, 4)
        strip_layout.setSpacing(0)
        
        strip_layout.addStretch()
        
        self.expand_btn = ToolbarButton("▼", "", "")
        self.expand_btn.clicked.connect(self._toggle_expanded)
        self.expand_btn.setFixedWidth(36)
        self.expand_btn.setFixedHeight(22)
        strip_layout.addWidget(self.expand_btn)
        
        strip_layout.addStretch()
        
        container_layout.addWidget(self.collapsed_strip)
        
        main_layout.addWidget(self.container)
    
    def _toggle_expanded(self):
        """Toggle the expanded/collapsed state."""
        self.is_expanded = not self.is_expanded
        self.settings.setValue("toolbar_expanded", self.is_expanded)
        self._update_expanded_state(animate=True)
    
    def _update_expanded_state(self, animate=True):
        """Update the UI based on expanded/collapsed state."""
        if self.is_expanded:
            self.expanded_widget.setVisible(True)
            self.collapsed_strip.setVisible(False)
        else:
            self.expanded_widget.setVisible(False)
            self.collapsed_strip.setVisible(True)
    
    def set_stl_loaded(self, loaded):
        """Enable/disable view controls based on STL loaded state."""
        self.stl_loaded = loaded
        self.reset_btn.setEnabled(loaded)
        self.view_btn.setEnabled(loaded)
        self.ruler_btn.setEnabled(loaded)
        self.annotation_btn.setEnabled(loaded)
        self.screenshot_btn.setEnabled(loaded)
        self.texture_btn.setEnabled(loaded)
        self.draw_btn.setEnabled(loaded)
        self.parts_btn.setEnabled(loaded)
        self.reset_model_btn.setEnabled(loaded)
    
    def _on_grid_clicked(self):
        """Handle grid toggle."""
        self.grid_enabled = not self.grid_enabled
        self.grid_btn.set_active(self.grid_enabled)
        self.toggle_grid.emit()
    
    def _on_theme_clicked(self):
        """Handle theme toggle."""
        self.dark_theme = not self.dark_theme
        if self.dark_theme:
            self.theme_btn.set_label("Dark")
            self.theme_btn.set_icon("🌙")
        else:
            self.theme_btn.set_label("Light")
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
                ("shaded", "◆", "Shaded"),
                ("solid", "◇", "Solid"),
                ("wireframe", "◈", "Wireframe"),
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
            ("front", "⬚", "Front"),
            ("left", "⊏", "Left"),
            ("right", "⊐", "Right"),
            ("rear", "⬛", "Rear"),
            ("top", "⊤", "Top"),
            ("bottom", "⊥", "Bottom"),
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
        self.render_mode_btn.set_label("Visual Style ▼")
        self.render_mode_btn.set_active(mode != 'shaded')
        self.render_mode_changed.emit(mode)
    
    def _on_reset_clicked(self):
        """Handle reset rotation."""
        self.reset_rotation.emit()
    
    def _on_ruler_clicked(self):
        """Handle ruler toggle."""
        self.ruler_mode_enabled = not self.ruler_mode_enabled
        if self.ruler_mode_enabled:
            self.ruler_btn.set_label("Ruler")
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
                self.draw_btn.set_label("Draw ▼")
        else:
            self.ruler_btn.set_label("Ruler")
            self.ruler_btn.set_icon("📏")
        self.ruler_btn.set_active(self.ruler_mode_enabled)
        self.toggle_ruler.emit()
    
    def _show_annotate_menu(self):
        """Show dropdown menu with Annotate and 3D Arrow options."""
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

        annotate_action = menu.addAction("📝  Annotate")
        annotate_action.setCheckable(True)
        annotate_action.setChecked(self.annotation_mode_enabled)
        annotate_action.triggered.connect(self._on_annotation_selected)

        arrow_action = menu.addAction("➤  3D Arrow")
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
            self.annotation_btn.set_label("Annotate ▼")
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
                self.draw_btn.set_label("Draw ▼")
        else:
            self.annotation_btn.set_label("Annotate ▼")
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
            self.annotation_btn.set_label("Arrow ▼")
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
                self.draw_btn.set_label("Draw ▼")
        else:
            self.annotation_btn.set_label("Annotate ▼")
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
                self.draw_btn.set_label("Draw ▼")
        self.parts_btn.set_active(self.parts_mode_enabled)
        self.toggle_parts.emit()
    
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
                self.draw_btn.set_label("Draw ▼")
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
                self.draw_btn.set_label("Draw ▼")
        self.texture_btn.set_active(self.texture_mode_enabled)
        self.toggle_texture.emit()
    
    def _show_draw_menu(self):
        """Show dropdown menu with Draw, Eraser, Color, Undo, Clear options."""
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

        draw_action = menu.addAction("🖊  Draw")
        draw_action.setCheckable(True)
        draw_action.setChecked(self.draw_mode_enabled)
        draw_action.triggered.connect(self._on_draw_toggled)

        eraser_action = menu.addAction("🧹  Eraser")
        eraser_action.setCheckable(True)
        eraser_action.setChecked(self._eraser_active)
        eraser_action.setEnabled(self.draw_mode_enabled)
        eraser_action.triggered.connect(self._on_eraser_toggled)

        text_action = menu.addAction("T  Text")
        text_action.setCheckable(True)
        text_action.setChecked(self._draw_text_active)
        text_action.setEnabled(self.draw_mode_enabled)
        text_action.triggered.connect(self._on_text_toggled)

        menu.addSeparator()

        color_action = menu.addAction("🎨  Pen Color")
        color_action.triggered.connect(self.show_draw_color_picker)

        undo_action = menu.addAction("↩  Undo Stroke")
        undo_action.setEnabled(self.draw_mode_enabled)
        undo_action.triggered.connect(self.draw_undo_requested.emit)

        clear_action = menu.addAction("🗑  Clear All")
        clear_action.setEnabled(self.draw_mode_enabled)
        clear_action.triggered.connect(self.draw_clear_requested.emit)

        menu.exec_(self.draw_btn.mapToGlobal(
            self.draw_btn.rect().bottomLeft()
        ))

    def _on_draw_toggled(self):
        """Toggle draw mode on/off."""
        self.draw_mode_enabled = not self.draw_mode_enabled
        if self.draw_mode_enabled:
            self.draw_btn.set_label("Drawing ▼")
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
            self.draw_btn.set_label("Draw ▼")
            self._eraser_active = False
            self.draw_eraser_toggled.emit(False)
        self.draw_btn.set_active(self.draw_mode_enabled)
        self.toggle_draw.emit()

    def _on_eraser_toggled(self):
        """Toggle eraser mode."""
        self._eraser_active = not self._eraser_active
        self._draw_text_active = False
        self.draw_btn.set_label("Eraser ▼" if self._eraser_active else "Drawing ▼")
        self.draw_eraser_toggled.emit(self._eraser_active)
        self.draw_text_toggled.emit(False)

    def _on_text_toggled(self):
        """Toggle text placement mode."""
        self._draw_text_active = not self._draw_text_active
        if self._draw_text_active:
            self._eraser_active = False
            self.draw_eraser_toggled.emit(False)
        self.draw_btn.set_label("Text ▼" if self._draw_text_active else "Drawing ▼")
        self.draw_text_toggled.emit(self._draw_text_active)

    def reset_draw_state(self):
        """Reset draw button state (called when exiting draw mode externally)."""
        self.draw_mode_enabled = False
        self._eraser_active = False
        self._draw_text_active = False
        self.draw_btn.set_label("Draw ▼")
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
            self.fullscreen_btn.set_label("Exit")
            self.fullscreen_btn.set_icon("⛶")
        else:
            self.fullscreen_btn.set_label("Fullscreen")
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
        self.view_btn.set_label("2D Views ▼")

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
        self.fullscreen_btn.set_label("Fullscreen")
        self.fullscreen_btn.set_active(False)
    
    def reset_annotation_state(self):
        """Reset annotation button state (called when exiting annotation mode externally)."""
        self.annotation_mode_enabled = False
        self.arrow_mode_enabled = False
        self.annotation_btn.set_label("Annotate ▼")
        self.annotation_btn.set_icon("📝")
        self.annotation_btn.set_active(False)

    def reset_arrow_state(self):
        """Reset arrow button state (called when exiting arrow mode externally)."""
        self.arrow_mode_enabled = False
        if not self.annotation_mode_enabled:
            self.annotation_btn.set_label("Annotate ▼")
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
    
    def set_reader_mode(self, enabled: bool):
        """Enable or disable reader mode (disables annotation button)."""
        if enabled:
            self.annotation_btn.setEnabled(False)
            self.annotation_btn.setToolTip("Annotations are read-only for this file")
        else:
            # Re-enable only if model is loaded
            if self.stl_loaded:
                self.annotation_btn.setEnabled(True)
            self.annotation_btn.setToolTip("Add annotations to the model")
    
    def set_loaded_filename(self, filename):
        """Update the load button tooltip to show the loaded filename."""
        if filename:
            self.load_btn.setToolTip(filename)
        else:
            self.load_btn.setToolTip("Load or replace 3D file (STL/STEP/3DM/OBJ/IGES)")
    
    def _apply_tooltip_style(self):
        """Apply tooltip styling with black text."""
        app = QApplication.instance()
        if not app:
            return

        tooltip_style = """
            QToolTip {
                background-color: #2a2e34;
                color: #E0ECF4;
                border: 1px solid #3a3e48;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
        """
        existing = app.styleSheet() or ""
        if "QToolTip" not in existing:
            app.setStyleSheet(existing + "\n" + tooltip_style)

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
        self.screenshot_btn.set_label(t("toolbar.screenshot"))
        self.texture_btn.set_label(t("toolbar.texture"))
        if self.draw_mode_enabled:
            if self._eraser_active:
                self.draw_btn.set_label(t("toolbar.eraser") + " ▼")
            else:
                self.draw_btn.set_label(t("toolbar.draw").replace(" ▼", "ing ▼"))
        else:
            self.draw_btn.set_label(t("toolbar.draw"))
        self.convert_btn.set_label(t("toolbar.convert"))
        if self.is_fullscreen:
            self.fullscreen_btn.set_label("Exit")
        else:
            self.fullscreen_btn.set_label(t("toolbar.fullscreen"))
        self.ruler_btn.setToolTip(t("toolbar.measure_tooltip"))
        self.annotation_btn.setToolTip(t("toolbar.annotate_tooltip"))
        self.screenshot_btn.setToolTip(t("toolbar.screenshot_tooltip"))
        self.texture_btn.setToolTip(t("toolbar.texture_tooltip"))
        self.draw_btn.setToolTip(t("toolbar.draw_tooltip"))
        self.convert_btn.setToolTip(t("toolbar.convert_tooltip"))
        self.load_btn.setToolTip(t("toolbar.load_tooltip"))
        self.reset_model_btn.setToolTip(t("toolbar.clear_tooltip"))