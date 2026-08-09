"""
Sidebar panel widget for the ECTOFORM application.
"""
import logging
import os
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QComboBox, QSizePolicy, QGraphicsDropShadowEffect,
    QLineEdit, QFileDialog, QMessageBox, QApplication, QStyleFactory,
)
from PyQt5.QtCore import Qt, QEvent, pyqtSignal, QSettings, QTimer
from PyQt5.QtGui import QFont, QColor, QDoubleValidator, QPalette, QPainter, QPen, QBrush
from ui.components import (
    DimensionRow, SurfaceAreaRow, WeightRow, WeightDensityInputRow,
    Separator, ScaleResultRow, ReportCheckbox, confirm_dialog,
)
from ui.styles import get_button_style, default_theme, make_font, sidebar_section_card_stylesheet, _dropdown_arrow_url
from i18n import t, on_language_changed
from core.edition import is_education

logger = logging.getLogger(__name__)

_ICON_COLOR = QColor("#8b5cf6")


class _DimIcon(QWidget):
    """Custom-painted dimension icon (x / y / z / vol)."""

    def __init__(self, kind: str, size: int = 38, parent=None):
        super().__init__(parent)
        self._kind = kind
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(_ICON_COLOR, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        w, h = self.width(), self.height()
        getattr(self, f"_draw_{self._kind}")(p, w, h)
        p.end()

    def _draw_x(self, p, w, h):
        my, m, a, bh = h // 2, 5, 5, 10
        p.drawLine(m, my, w - m, my)
        p.drawLine(m, my, m + a, my - a); p.drawLine(m, my, m + a, my + a)
        p.drawLine(w - m, my, w - m - a, my - a); p.drawLine(w - m, my, w - m - a, my + a)
        p.drawLine(m, my - bh // 2, m, my + bh // 2)
        p.drawLine(w - m, my - bh // 2, w - m, my + bh // 2)

    def _draw_y(self, p, w, h):
        m, o, a = 7, 7, 5
        p.drawRect(m + o, m + o, w - 2 * m - o, h - 2 * m - o)
        p.drawLine(w - m, m, w - m - a, m); p.drawLine(w - m, m, w - m, m + a)
        p.drawLine(m, h - m, m + a, h - m); p.drawLine(m, h - m, m, h - m - a)

    def _draw_z(self, p, w, h):
        mx, m, a, bw = w // 2, 5, 5, 10
        p.drawLine(mx, m, mx, h - m)
        p.drawLine(mx, m, mx - a, m + a); p.drawLine(mx, m, mx + a, m + a)
        p.drawLine(mx, h - m, mx - a, h - m - a); p.drawLine(mx, h - m, mx + a, h - m - a)
        p.drawLine(mx - bw // 2, m, mx + bw // 2, m)
        p.drawLine(mx - bw // 2, h - m, mx + bw // 2, h - m)

    def _draw_vol(self, p, w, h):
        m, o = 7, 7
        fw, fh = w - 2 * m - o, h - 2 * m - o
        p.drawRect(m + o, m + o, fw, fh)
        p.drawLine(m + o, m + o, m, m)
        p.drawLine(m + o + fw, m + o, m + fw, m)
        p.drawLine(m, m, m + fw, m)
        p.drawLine(m + fw, m, m + fw, m + fh)
        p.drawLine(m + o + fw, m + o + fh, m + fw, m + fh)


class _DimColumn(QWidget):
    """Single dimension column: icon + label + value."""

    def __init__(self, kind: str, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        icon = _DimIcon(kind, 36)
        lay.addWidget(icon, alignment=Qt.AlignHCenter)

        self._label_lbl = QLabel(label)
        self._label_lbl.setAlignment(Qt.AlignCenter)
        self._label_lbl.setWordWrap(True)
        self._label_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.55); font-size: 13px; background: transparent; border: none;"
        )
        lay.addWidget(self._label_lbl)

        self._value_lbl = QLabel("--")
        self._value_lbl.setAlignment(Qt.AlignCenter)
        font = QFont(); font.setPointSize(13); font.setBold(True)
        self._value_lbl.setFont(font)
        self._value_lbl.setStyleSheet(
            "color: #ffffff; font-size: 13px; font-weight: bold; background: transparent; border: none;"
        )
        lay.addWidget(self._value_lbl)

    def set_value(self, text: str):
        self._value_lbl.setText(text)

    def set_label(self, text: str):
        self._label_lbl.setText(text)


class _SurfaceCol(QWidget):
    """Half of the two-column surface area card."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)

        self._label_lbl = QLabel(label)
        self._label_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.5); font-size: 13px; background: transparent; border: none;"
        )
        lay.addWidget(self._label_lbl)

        self._value_lbl = QLabel("--")
        f = QFont(); f.setPointSize(14); f.setBold(True)
        self._value_lbl.setFont(f)
        self._value_lbl.setStyleSheet(
            "color: #ffffff; font-size: 14px; font-weight: bold; background: transparent; border: none;"
        )
        lay.addWidget(self._value_lbl)

    def set_value(self, text: str):
        self._value_lbl.setText(text)

    def set_label(self, text: str):
        self._label_lbl.setText(text)


class _MaterialCombo(QComboBox):
    """QComboBox that emits popupClosed when its dropdown is dismissed (any reason)."""
    popupClosed = pyqtSignal()

    def hidePopup(self):
        super().hidePopup()
        QTimer.singleShot(0, self.popupClosed.emit)


class _WeightInfoRow(QWidget):
    """A single row inside the weight inner card: label left, value right, optional > arrow."""

    def __init__(self, label: str, show_arrow: bool = False, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(8)

        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(
            "color: rgba(255,255,255,0.55); font-size: 15px; background: transparent; border: none;"
        )
        lay.addWidget(self._lbl)
        lay.addStretch()

        self._val = QLabel("--")
        self._val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._val.setStyleSheet(
            "color: rgba(255,255,255,0.9); font-size: 15px; background: transparent; border: none;"
        )
        lay.addWidget(self._val)

        if show_arrow:
            arr = QLabel("›")
            arr.setStyleSheet(
                "color: rgba(255,255,255,0.35); font-size: 14px; background: transparent; border: none;"
            )
            lay.addWidget(arr)

    def set_value(self, text: str):
        self._val.setText(text)

    def set_label(self, text: str):
        self._lbl.setText(text)



class _WeightResultRow(QFrame):
    """Gold-highlighted estimated weight result row."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background: rgba(234,179,8,0.10);
                border: 1px solid rgba(234,179,8,0.25);
                border-radius: 10px;
            }
        """)
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)

        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(
            "color: rgba(234,179,8,0.85); font-size: 12px; font-weight: bold; background: transparent; border: none;"
        )
        lay.addWidget(self._lbl)
        lay.addStretch()

        self._val = QLabel("--")
        f = QFont(); f.setPointSize(16); f.setBold(True)
        self._val.setFont(f)
        self._val.setStyleSheet(
            "color: #eab308; font-weight: bold; background: transparent; border: none;"
        )
        self._val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self._val)

    def set_value(self, text: str):
        self._val.setText(text)

    def set_label(self, text: str):
        self._lbl.setText(text)


class SidebarPanel(QWidget):
    """Left sidebar panel with upload controls and information sections."""
    
    # Signal emitted when export is requested (file_path, scale_factor)
    export_scaled_stl = pyqtSignal(str, float)
    
    # Signal emitted when annotations are exported as .ecto
    annotations_exported = pyqtSignal()
    
    
    # Material density data (g/cm³) — first element is an i18n key
    # (sidebar.mat_<key>), not a display string; use _material_label() to
    # get the translated name for the current language.
    MATERIALS = [
        ("gold_24k", 19.32),
        ("gold_22k", 17.7),
        ("gold_18k_yellow", 15.5),
        ("gold_18k_rose", 15.0),
        ("gold_18k_white_pd", 15.0),
        ("gold_18k_white_ag", 14.7),
        ("gold_14k_yellow", 13.58),
        ("gold_14k_rose", 13.2),
        ("gold_14k_white", 13.0),
        ("gold_10k", 11.6),
        ("gold_9k", 10.8),
        ("platinum_pure", 21.45),
        ("platinum_950", 20.64),
        ("platinum_900", 20.0),
        ("palladium_pure", 12.02),
        ("palladium_950", 11.5),
        ("silver_pure", 10.49),
        ("silver_sterling", 10.36),
        ("copper", 8.96),
        ("brass", 8.5),
        ("bronze", 8.8),
        ("steel_316l", 8.0),
        ("titanium_g2", 4.51),
        ("aluminium", 2.7),
        ("resin", 1.2),
        ("diamond", 3.52),
        ("sapphire_ruby", 4.0),
        ("emerald", 2.75),
        ("quartz", 2.65),
        ("lapis_lazuli", 2.75),
        ("crystal_glass", 3.0),
        ("aventurine_glass", 2.65),
    ]

    @staticmethod
    def _material_label(key: str) -> str:
        return t(f"sidebar.mat_{key}")
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings("LYNS360", "Sidebar")
        self._surface_area_expanded = self._settings.value("surface_area_expanded", True, type=bool)
        self._adjust_weight_expanded = self._settings.value("adjust_weight_expanded", True, type=bool)
        self.current_volume_mm3 = 0.0
        self.current_weight_grams = 0.0
        self.current_dimensions = {'width': 0.0, 'height': 0.0, 'depth': 0.0}
        self._dim_unit = "mm"   # active dimension unit
        self.calculated_scale_factor = 1.0
        self.current_surface_area_cm2 = 0.0
        self._annotation_count = 0
        self.current_stl_filename = ""
        self.has_stl_loaded = False
        self.has_scaled_data = False
        self.init_ui()
        on_language_changed(self.retranslate)
    
    def _add_card_shadow(self, widget, blur_radius=26, y_offset=8, alpha=110):
        """Add a black drop shadow to a sidebar card, button, or other widget."""
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(blur_radius)
        shadow.setXOffset(0)
        shadow.setYOffset(y_offset)
        shadow.setColor(QColor(0, 0, 0, alpha))
        widget.setGraphicsEffect(shadow)

    def set_2d_mode(self, is_2d: bool):
        """Handle UI state when a 2D model is loaded or switched from.
        
        In 2D mode, disable/grey out Visual style and 2D/3D view controls.
        Keep enabled: Ruler, Annotation, Draw.
        """
        # This is a placeholder that can be expanded based on the actual UI structure
        # when the specific visual style and 2D/3D view controls are identified
        pass

    def _style_section_card(self, card: QFrame):
        """Gradient + border on this card, styled background + drop shadow.

        Per-widget stylesheet + WA_StyledBackground is required on macOS / with
        QGraphicsDropShadowEffect so qlineargradient paints; relying on the app-wide
        sheet alone often shows a flat background.
        """
        name = card.objectName()
        if not name:
            return
        frag = sidebar_section_card_stylesheet(default_theme)
        card.setStyleSheet(f"QFrame#{name} {{ {frag} }}")
        card.setAttribute(Qt.WA_StyledBackground, True)
        self._add_card_shadow(card)

    def init_ui(self):
        """Initialize the sidebar UI."""
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setObjectName("sidebarScrollArea")
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setMinimumWidth(420)
        
        # Style scroll area
        scroll_area.setStyleSheet(f"""
            QScrollArea#sidebarScrollArea {{
                background-color: {default_theme.background};
                border: none;
            }}
            QScrollArea#sidebarScrollArea > QWidget > QWidget {{
                background-color: {default_theme.background};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #5b6470;
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #7a8594;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        scroll_area.viewport().setStyleSheet(f"background-color: {default_theme.background};")
        
        # Create content widget
        content_widget = QWidget()
        content_widget.setObjectName("sidebarContent")
        content_widget.setStyleSheet(f"background-color: {default_theme.background};")
        content_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        layout = QVBoxLayout(content_widget)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)
        # Extra top/bottom so upload card drop shadow is not clipped by the scroll area
        layout.setContentsMargins(10, 14, 20, 18)
        
        # Upload card — gradient + shadow via global stylesheet (QFrame#uploadCard)
        upload_card = QFrame()
        upload_card.setObjectName("uploadCard")
        self._style_section_card(upload_card)
        upload_card_layout = QVBoxLayout(upload_card)
        upload_card_layout.setContentsMargins(16, 18, 16, 18)
        upload_card_layout.setSpacing(10)
        
        # Title label
        self._title_label = QLabel(t("sidebar.title"))
        self._title_label.setObjectName("titleLabel")
        title_font = make_font(size=16, bold=True)
        self._title_label.setFont(title_font)
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setStyleSheet(f"background: transparent; border: none; color: {default_theme.text_title};")
        upload_card_layout.addWidget(self._title_label)
        
        # Upload button
        self.upload_btn = QPushButton(t("sidebar.upload_btn"))
        self.upload_btn.setMinimumHeight(50)
        self.upload_btn.setObjectName("uploadBtn")
        self.upload_btn.setCursor(Qt.PointingHandCursor)
        self.upload_btn.setStyleSheet(get_button_style("uploadBtn"))
        self.upload_btn.setAttribute(Qt.WA_StyledBackground, True)
        # Strong black drop shadow (visible below the pill; layout margin reserves space in stylesheet)
        self._add_card_shadow(self.upload_btn, blur_radius=34, y_offset=9, alpha=210)
        upload_card_layout.addWidget(self.upload_btn)
        
        # Info label
        self._info_label = QLabel(t("sidebar.upload_info"))
        self._info_label.setObjectName("infoLabel")
        self._info_label.setAlignment(Qt.AlignCenter)
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet(f"background: transparent; border: none; color: {default_theme.text_white};")
        upload_card_layout.addWidget(self._info_label)
        
        layout.addWidget(upload_card)
        
        # Create sections
        self.dimensions_group = self.create_dimensions_section()
        layout.addWidget(self.dimensions_group)
        
        self.weight_group = self.create_weight_section()
        layout.addWidget(self.weight_group)

        # Surface area moved under weight per UX request
        self.surface_area_group = self.create_surface_area_section()
        layout.addWidget(self.surface_area_group)
        
        # Create Adjust to Target Weight section
        self.adjust_weight_group = self.create_adjust_weight_section()
        layout.addWidget(self.adjust_weight_group)
        
        # Create PDF Report section (commented out for now - uncomment to re-enable 3D PDF export)
        # self.pdf_report_group = self.create_pdf_report_section()
        # layout.addWidget(self.pdf_report_group)
        
        # Create Export with Annotations section
        self.export_annotations_group = self.create_export_annotations_section()
        layout.addWidget(self.export_annotations_group)

        # Export as .lyns.review — disabled until LYNS Lite ships
        # self.export_review_group = self.create_export_review_section()
        # layout.addWidget(self.export_review_group)

        # Add stretch
        layout.addStretch()
        
        # Set content widget to scroll area
        scroll_area.setWidget(content_widget)
        
        # Store scroll area as main widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll_area)
    
    def create_dimensions_section(self):
        """Create the dimensions display section — horizontal 4-column grid."""
        card = QFrame()
        card.setObjectName("dimensionsCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(6)

        # ── Header: icon + DIMENSIONS + mm selector ──
        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        ruler = QLabel("📐")
        ruler.setStyleSheet("background: transparent; border: none; font-size: 14px;")
        ruler.setFixedSize(20, 20)
        ruler.setAlignment(Qt.AlignCenter)

        self._dim_title = QLabel(t("sidebar.dimensions").upper())
        self._dim_title.setFont(make_font(size=14, bold=True))
        self._dim_title.setStyleSheet(
            f"color: {default_theme.text_title}; background: transparent; border: none; letter-spacing: 1px;"
        )

        self._unit_btn = QPushButton("mm  ▾")
        self._unit_btn.setFixedHeight(24)
        self._unit_btn.setCursor(Qt.PointingHandCursor)
        self._unit_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08);
                color: rgba(255,255,255,0.75);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 12px;
                padding: 0 10px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.15);
                color: white;
            }
        """)

        self._unit_btn.clicked.connect(self._show_unit_menu)
        hdr.addWidget(ruler)
        hdr.addWidget(self._dim_title)
        hdr.addStretch()
        hdr.addWidget(self._unit_btn)
        card_layout.addLayout(hdr)

        # ── 4-column grid ──
        grid = QHBoxLayout()
        grid.setContentsMargins(0, 2, 0, 2)
        grid.setSpacing(0)

        specs = [
            ("x",   t("sidebar.length_x")),
            ("y",   t("sidebar.width_y")),
            ("z",   t("sidebar.height_z")),
            ("vol", t("sidebar.volume")),
        ]
        dim_widgets = []
        for i, (kind, label) in enumerate(specs):
            col = _DimColumn(kind, label)
            grid.addWidget(col, 1)
            dim_widgets.append(col)
            if i < len(specs) - 1:
                div = QFrame()
                div.setFrameShape(QFrame.VLine)
                div.setStyleSheet(
                    "color: rgba(255,255,255,0.1); background: rgba(255,255,255,0.1); "
                    "max-width: 1px; border: none;"
                )
                grid.addWidget(div)

        card_layout.addLayout(grid)

        # Keep existing names so update_dimensions() still works unchanged
        self.width_row  = dim_widgets[0]
        self.height_row = dim_widgets[1]
        self.depth_row  = dim_widgets[2]
        self.volume_row = dim_widgets[3]

        self._style_section_card(card)
        return card
    
    def create_surface_area_section(self):
        """Create the surface area section — two-column card matching Technical Overview style."""
        card = QFrame()
        card.setObjectName("surfaceAreaCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(8)

        # ── Header: wave icon + title + help badge ──
        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        wave_icon = QLabel("∿")
        wave_icon.setStyleSheet(
            f"color: {default_theme.text_title}; font-size: 16px; background: transparent; border: none;"
        )
        wave_icon.setFixedSize(20, 20)
        wave_icon.setAlignment(Qt.AlignCenter)

        self.surface_title_label = QLabel(t("sidebar.total_surface_area").upper())
        self.surface_title_label.setFont(make_font(size=14, bold=True))
        self.surface_title_label.setStyleSheet(
            f"color: {default_theme.text_title}; background: transparent; border: none; letter-spacing: 1px;"
        )

        hdr.addWidget(wave_icon)
        hdr.addWidget(self.surface_title_label)
        hdr.addStretch()
        card_layout.addLayout(hdr)

        # ── Two-column inner card ──
        inner = QFrame()
        inner.setStyleSheet("""
            QFrame {
                background: rgba(0,0,0,0.20);
                border-radius: 10px;
                border: 1px solid rgba(255,255,255,0.06);
            }
        """)
        inner.setAttribute(Qt.WA_StyledBackground, True)
        inner_lay = QHBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.setSpacing(0)

        self.surface_total_row = _SurfaceCol(t("sidebar.total_area"))
        inner_lay.addWidget(self.surface_total_row, 1)

        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setStyleSheet(
            "color: rgba(255,255,255,0.1); background: rgba(255,255,255,0.1); max-width: 1px; border: none;"
        )
        inner_lay.addWidget(div)

        self.surface_cm_row = _SurfaceCol(t("sidebar.area_cm2"))
        inner_lay.addWidget(self.surface_cm_row, 1)

        card_layout.addWidget(inner)

        # Keep collapse references alive (used in eventFilter) — point to card-level dummies
        self._surface_header  = card
        self._surface_content = inner
        self._surface_collapse_lbl = QLabel()   # unused but avoids AttributeError

        self._style_section_card(card)
        return card
    
    def create_weight_section(self):
        """Create the estimated weight calculator section."""
        card = QFrame()
        card.setObjectName("weightCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(8)

        # ── Header: bag icon + ESTIMATED WEIGHT + crown icon ──
        hdr = QHBoxLayout(); hdr.setSpacing(6)

        bag = QLabel("⚖")
        bag.setStyleSheet(
            "color: #eab308; font-size: 15px; background: transparent; border: none;"
        )
        bag.setFixedSize(20, 20); bag.setAlignment(Qt.AlignCenter)

        self.weight_title_label = QLabel(t("sidebar.estimated_weight").upper())
        self.weight_title_label.setFont(make_font(size=14, bold=True))
        self.weight_title_label.setStyleSheet(
            f"color: {default_theme.text_title}; background: transparent; border: none; letter-spacing: 1px;"
        )

        crown = QLabel("♛")
        crown.setStyleSheet(
            "color: #eab308; font-size: 14px; background: transparent; border: none;"
        )
        crown.setAlignment(Qt.AlignCenter)

        hdr.addWidget(bag)
        hdr.addWidget(self.weight_title_label)
        hdr.addStretch()
        hdr.addWidget(crown)
        card_layout.addLayout(hdr)

        # ── Hidden combo — keeps all data logic intact ──
        self.material_combo = _MaterialCombo()
        self.material_combo.setObjectName("materialCombo")
        self.material_combo.setAttribute(Qt.WA_StyledBackground, True)
        _fusion = QStyleFactory.create("Fusion")
        if _fusion:
            self.material_combo.setStyle(_fusion)
        _arrow = _dropdown_arrow_url()
        _wp = default_theme.weight_panel_bg
        _wph = default_theme.weight_panel_hover
        _bd = default_theme.border_medium
        self.material_combo.setStyleSheet(f"""
            QComboBox#materialCombo {{
                background-color: {_wp}; border: 1px solid {_bd}; border-radius: 8px;
                padding: 8px 12px; color: {default_theme.text_white};
            }}
            QComboBox#materialCombo::drop-down {{ width: 32px; border: none; border-left: 1px solid {_bd};
                border-top-right-radius: 8px; border-bottom-right-radius: 8px; background: {_wp}; }}
            QComboBox#materialCombo::down-arrow {{ image: url({_arrow}); width: 14px; height: 14px; }}
            QComboBox#materialCombo QAbstractItemView {{
                background-color: {_wp}; color: {default_theme.text_white};
                border: 1px solid {_bd}; selection-background-color: {_wph};
                selection-color: {default_theme.text_white}; padding: 4px;
            }}
        """)
        for material_key, density in self.MATERIALS:
            self.material_combo.addItem(f"{self._material_label(material_key)} ({density} g/cm³)", density)
        self.material_combo.currentIndexChanged.connect(self._on_material_changed_new)
        self.material_combo.popupClosed.connect(lambda: self.material_combo.setVisible(False))
        self.material_combo.setVisible(False)   # hidden — triggered by material row click
        card_layout.addWidget(self.material_combo)

        # ── Inner dark info card ──
        inner = QFrame()
        inner.setStyleSheet("""
            QFrame {
                background: rgba(0,0,0,0.20);
                border-radius: 10px;
                border: 1px solid rgba(255,255,255,0.06);
            }
        """)
        inner.setAttribute(Qt.WA_StyledBackground, True)
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 2, 0, 2)
        inner_lay.setSpacing(0)

        def _hsep():
            f = QFrame(); f.setFrameShape(QFrame.HLine)
            f.setStyleSheet("color: rgba(255,255,255,0.07); background: rgba(255,255,255,0.07); max-height: 1px; border: none;")
            return f

        # Material row (clickable — opens hidden combo popup)
        self._material_display_row = _WeightInfoRow(t("sidebar.material"), show_arrow=True)
        self._material_display_row.setCursor(Qt.PointingHandCursor)
        self._material_display_row.mousePressEvent = lambda _: self._open_material_picker()
        inner_lay.addWidget(self._material_display_row)
        inner_lay.addWidget(_hsep())

        # Volume display row
        self.weight_volume_row = _WeightInfoRow(t("sidebar.volume"))
        inner_lay.addWidget(self.weight_volume_row)
        inner_lay.addWidget(_hsep())

        # Density editable row
        self.weight_density_row = WeightDensityInputRow()
        self.weight_density_row.densityChanged.connect(self.calculate_weight)
        inner_lay.addWidget(self.weight_density_row)

        card_layout.addWidget(inner)

        # ── Result row (gold) ──
        self.weight_result_row = _WeightResultRow(t("sidebar.estimated_weight_result"))
        card_layout.addWidget(self.weight_result_row)

        # Initialise display
        if self.MATERIALS:
            _, d0 = self.MATERIALS[0]
            self.weight_density_row.set_density_silent(d0)
            self._update_material_display(0)

        self._style_section_card(card)
        return card

    def _open_material_picker(self):
        """Show the hidden combo's popup at the material row position."""
        self.material_combo.setVisible(True)
        self.material_combo.showPopup()
        # combo hides itself via popupClosed signal when the popup closes

    def _on_material_changed_new(self, index):
        """Wraps on_material_changed and also refreshes the display row."""
        self.on_material_changed(index)
        self._update_material_display(index)

    def _update_material_display(self, index: int):
        if 0 <= index < len(self.MATERIALS):
            key, density = self.MATERIALS[index]
            self._material_display_row.set_value(f"{self._material_label(key)} ({density} g/cm³)")
    
    def create_adjust_weight_section(self):
        """Create the adjust to target weight section (collapsible)."""
        card = QFrame()
        card.setObjectName("adjustWeightCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)
        self._adjust_weight_card_layout = card_layout
        
        # Header row: use QWidget (not QPushButton) so macOS does not paint an opaque
        # button plate behind the row; nested QPushButtons also confuse native styling.
        self._adjust_weight_header = QWidget()
        self._adjust_weight_header.setObjectName("adjustWeightHeader")
        self._adjust_weight_header.setCursor(Qt.PointingHandCursor)
        self._adjust_weight_header.setStyleSheet("""
            QWidget#adjustWeightHeader {
                background-color: transparent;
                border: none;
            }
        """)
        self._adjust_weight_header.installEventFilter(self)
        header_layout = QHBoxLayout(self._adjust_weight_header)
        header_layout.setContentsMargins(0, 8, 0, 8)
        header_layout.setSpacing(8)
        self._adjust_weight_header_layout = header_layout
        
        # QLabel instead of QPushButton — macOS still draws an opaque button plate on tiny flat buttons.
        self._adjust_weight_collapse_lbl = QLabel("▼" if self._adjust_weight_expanded else "▶")
        self._adjust_weight_collapse_lbl.setObjectName("adjustWeightCollapseArrow")
        self._adjust_weight_collapse_lbl.setFixedSize(24, 24)
        self._adjust_weight_collapse_lbl.setCursor(Qt.PointingHandCursor)
        self._adjust_weight_collapse_lbl.setAlignment(Qt.AlignCenter)
        self._adjust_weight_collapse_lbl.setStyleSheet(f"""
            QLabel#adjustWeightCollapseArrow {{
                color: {default_theme.text_secondary};
                background-color: transparent;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
                font-size: 12px;
            }}
        """)
        self._adjust_weight_collapse_lbl.installEventFilter(self)
        
        self.adjust_weight_title_label = QLabel(t("sidebar.adjust_target_weight"))
        title_font = make_font(size=14, bold=True)
        self.adjust_weight_title_label.setFont(title_font)
        self.adjust_weight_title_label.setStyleSheet(
            f"color: {default_theme.text_title}; padding: 2px 0; background-color: transparent; background: transparent; border: none;"
        )
        self.adjust_weight_title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # Ensure full title is visible (avoids truncation on narrow sidebars)
        fm = self.adjust_weight_title_label.fontMetrics()
        self.adjust_weight_title_label.setMinimumWidth(fm.horizontalAdvance(self.adjust_weight_title_label.text()) + 8)
        
        icon_label = QLabel("⚙")
        icon_label.setStyleSheet(
            f"color: {default_theme.icon_blue}; font-size: 16px; background-color: transparent; background: transparent; border: none; padding: 0px;"
        )
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        
        header_layout.addWidget(self._adjust_weight_collapse_lbl)
        header_layout.addWidget(self.adjust_weight_title_label)
        header_layout.addStretch()
        header_layout.addWidget(icon_label)
        card_layout.addWidget(self._adjust_weight_header)
        
        # Content widget (collapsible) — transparent so parent card gradient shows behind rows/fields
        self._adjust_weight_content = QWidget()
        self._adjust_weight_content.setStyleSheet("background-color: transparent;")
        content_layout = QVBoxLayout(self._adjust_weight_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        
        # Target weight input
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)
        
        self.target_weight_input = QLineEdit()
        self.target_weight_input.setObjectName("targetWeightInput")
        self.target_weight_input.setPlaceholderText("Enter target weight")
        self.target_weight_input.setMinimumHeight(40)
        _le_fusion = QStyleFactory.create("Fusion")
        if _le_fusion is not None:
            self.target_weight_input.setStyle(_le_fusion)
        _ib = default_theme.input_bg
        _ibd = default_theme.input_border
        self.target_weight_input.setStyleSheet(f"""
            QLineEdit#targetWeightInput {{
                background-color: {_ib};
                background: {_ib};
                border: 1px solid {_ibd};
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 13px;
                color: {default_theme.text_primary};
            }}
            QLineEdit#targetWeightInput:hover {{
                background-color: {_ib};
                border: 1px solid {default_theme.input_border_hover};
            }}
            QLineEdit#targetWeightInput:focus {{
                background-color: {_ib};
                border: 2px solid {default_theme.button_primary};
            }}
        """)
        self.target_weight_input.setAttribute(Qt.WA_StyledBackground, True)
        try:
            _pal = self.target_weight_input.palette()
            _pal.setColor(QPalette.PlaceholderText, QColor("#888888"))
            self.target_weight_input.setPalette(_pal)
        except Exception:
            pass
        
        # Set validator for numeric input
        validator = QDoubleValidator(0.0, 999999.0, 4)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.target_weight_input.setValidator(validator)
        self.target_weight_input.returnPressed.connect(self.calculate_scale)
        
        unit_label = QLabel("g")
        unit_label.setStyleSheet(
            f"color: {default_theme.text_primary}; font-weight: bold; background-color: transparent; border: none;"
        )
        unit_label.setFixedWidth(20)
        
        input_layout.addWidget(self.target_weight_input)
        input_layout.addWidget(unit_label)
        content_layout.addLayout(input_layout)
        
        # Calculate button
        self.calculate_scale_btn = QPushButton("Calculate Scale")
        self.calculate_scale_btn.setObjectName("calculateScaleBtn")
        self.calculate_scale_btn.setMinimumHeight(40)
        self.calculate_scale_btn.setEnabled(False)
        self.calculate_scale_btn.setStyleSheet(f"""
            QPushButton#calculateScaleBtn {{
                background-color: {default_theme.button_primary};
                color: {default_theme.text_white};
                border: none;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#calculateScaleBtn:hover {{
                background-color: {default_theme.button_primary_hover};
            }}
            QPushButton#calculateScaleBtn:pressed {{
                background-color: {default_theme.button_primary_pressed};
            }}
            QPushButton#calculateScaleBtn:disabled {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_secondary};
                border: 1px solid {default_theme.border_standard};
                border-radius: 8px;
            }}
        """)
        self.calculate_scale_btn.clicked.connect(self.calculate_scale)
        content_layout.addWidget(self.calculate_scale_btn)
        
        # Separator
        separator = Separator(self)
        content_layout.addWidget(separator)
        
        # Results section title
        self.results_label = QLabel(t("sidebar.scaled_results"))
        results_font = make_font(size=14, bold=True)
        self.results_label.setFont(results_font)
        self.results_label.setStyleSheet(
            f"color: {default_theme.text_secondary}; margin-top: 4px; background-color: transparent; border: none;"
        )
        content_layout.addWidget(self.results_label)
        
        # Scale factor row
        self.scale_factor_row = ScaleResultRow("Scale factor", "--", "highlight", self)
        content_layout.addWidget(self.scale_factor_row)
        
        # New dimensions rows
        self.new_x_row = ScaleResultRow("New X (Length)", "--", "standard", self)
        self.new_y_row = ScaleResultRow("New Y (Width)", "--", "standard", self)
        self.new_z_row = ScaleResultRow("New Z (Height)", "--", "standard", self)
        content_layout.addWidget(self.new_x_row)
        content_layout.addWidget(self.new_y_row)
        content_layout.addWidget(self.new_z_row)
        
        # New volume row (with subtle border to differentiate from dimensions)
        self.new_volume_row = ScaleResultRow("New Volume", "--", "volume", self)
        content_layout.addWidget(self.new_volume_row)
        
        # Weight comparison separator
        separator2 = Separator(self)
        content_layout.addWidget(separator2)
        
        # Weight comparison title
        self.weight_comparison_label = QLabel(t("sidebar.weight_comparison"))
        self.weight_comparison_label.setFont(results_font)
        self.weight_comparison_label.setStyleSheet(
            f"color: {default_theme.text_secondary}; margin-top: 4px; background-color: transparent; border: none;"
        )
        content_layout.addWidget(self.weight_comparison_label)
        
        # Weight comparison rows
        self.original_weight_row = ScaleResultRow("Original weight", "--", "comparison", self)
        self.target_weight_row = ScaleResultRow("Target weight", "--", "highlight", self)
        content_layout.addWidget(self.original_weight_row)
        content_layout.addWidget(self.target_weight_row)
        
        # Export button
        self.export_scaled_btn = QPushButton("Export Scaled STL")
        self.export_scaled_btn.setObjectName("exportScaledBtn")
        self.export_scaled_btn.setMinimumHeight(44)
        self.export_scaled_btn.setEnabled(False)
        self.export_scaled_btn.setStyleSheet(f"""
            QPushButton#exportScaledBtn {{
                background-color: #10B981;
                color: {default_theme.text_white};
                border: none;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#exportScaledBtn:hover {{
                background-color: #059669;
            }}
            QPushButton#exportScaledBtn:pressed {{
                background-color: #047857;
            }}
            QPushButton#exportScaledBtn:disabled {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_secondary};
                border: 1px solid {default_theme.border_standard};
                border-radius: 8px;
            }}
        """)
        self.export_scaled_btn.clicked.connect(self.export_scaled_stl_file)
        content_layout.addWidget(self.export_scaled_btn)
        
        card_layout.addWidget(self._adjust_weight_content)
        self._adjust_weight_content.setVisible(self._adjust_weight_expanded)

        if not self._adjust_weight_expanded:
            card_layout.setContentsMargins(16, 4, 16, 4)
            header_layout.setContentsMargins(0, 2, 0, 2)

        self._style_section_card(card)

        return card
    
    def _toggle_adjust_weight(self):
        """Toggle the adjust to target weight section."""
        self._adjust_weight_expanded = not self._adjust_weight_expanded
        self._settings.setValue("adjust_weight_expanded", self._adjust_weight_expanded)
        self._adjust_weight_content.setVisible(self._adjust_weight_expanded)
        self._adjust_weight_collapse_lbl.setText("▼" if self._adjust_weight_expanded else "▶")
        if self._adjust_weight_expanded:
            self._adjust_weight_card_layout.setContentsMargins(16, 16, 16, 16)
            self._adjust_weight_header_layout.setContentsMargins(0, 8, 0, 8)
        else:
            self._adjust_weight_card_layout.setContentsMargins(16, 4, 16, 4)
            self._adjust_weight_header_layout.setContentsMargins(0, 2, 0, 2)

    def _toggle_surface_area(self):
        """Toggle the surface area collapsible section."""
        self._surface_area_expanded = not self._surface_area_expanded
        self._settings.setValue("surface_area_expanded", self._surface_area_expanded)
        self._surface_content.setVisible(self._surface_area_expanded)
        self._surface_collapse_lbl.setText("▼" if self._surface_area_expanded else "▶")
    
    def create_pdf_report_section(self):
        """Create the 3D PDF export section. (UI currently commented out - uncomment in init to show)"""
        card = QFrame()
        card.setObjectName("pdfReportCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)
        
        # Header row with title and icon
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        title_label = QLabel("Export 3D PDF")
        title_font = make_font(size=14, bold=True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(
            f"color: {default_theme.text_title}; margin-bottom: 4px; background: transparent; border: none;"
        )
        
        icon_label = QLabel("📐")
        icon_label.setStyleSheet(f"color: {default_theme.icon_blue}; font-size: 16px;")
        icon_label.setAlignment(Qt.AlignCenter)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(icon_label)
        card_layout.addLayout(header_layout)
        
        # Description
        desc_label = QLabel("Export interactive 3D PDF for Adobe Acrobat Reader.\nRotate, pan, and zoom the model inside the PDF.")
        desc_font = make_font(size=11)
        desc_label.setFont(desc_font)
        desc_label.setStyleSheet(f"color: {default_theme.text_secondary};")
        desc_label.setWordWrap(True)
        card_layout.addWidget(desc_label)
        
        # Export button
        self.export_pdf_btn = QPushButton("Export 3D PDF")
        self.export_pdf_btn.setObjectName("exportPdfBtn")
        self.export_pdf_btn.setMinimumHeight(44)
        self.export_pdf_btn.setEnabled(False)
        self.export_pdf_btn.setStyleSheet(f"""
            QPushButton#exportPdfBtn {{
                background-color: {default_theme.button_primary};
                color: {default_theme.text_white};
                border: none;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#exportPdfBtn:hover {{
                background-color: {default_theme.button_primary_hover};
            }}
            QPushButton#exportPdfBtn:pressed {{
                background-color: {default_theme.button_primary_pressed};
            }}
            QPushButton#exportPdfBtn:disabled {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_primary};
            }}
        """)
        self.export_pdf_btn.clicked.connect(self.export_pdf_report)
        if is_education():
            self.export_pdf_btn.hide()
        card_layout.addWidget(self.export_pdf_btn)
        
        # Information footer
        footer_frame = QFrame()
        footer_frame.setObjectName("pdfReportFooter")
        footer_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        footer_frame.setMinimumHeight(36)
        footer_frame.setStyleSheet(f"""
            QFrame#pdfReportFooter {{
                background-color: {default_theme.background};
                border: 1px solid {default_theme.border_standard};
                border-radius: 6px;
            }}
        """)
        
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(10, 6, 10, 6)
        footer_layout.setSpacing(8)
        
        info_icon = QLabel("ℹ️")
        info_icon.setStyleSheet(f"color: {default_theme.icon_info_gray}; font-size: 11px;")
        info_icon.setFixedWidth(18)
        info_icon.setAlignment(Qt.AlignTop)
        
        disclaimer = QLabel("Requires Adobe Acrobat Reader for interactive 3D. Ensure VTK provides vtkU3DExporter (usually via 'pip install -U vtk').")
        disclaimer_font = make_font(size=9)
        disclaimer.setFont(disclaimer_font)
        disclaimer.setStyleSheet(f"color: {default_theme.icon_info_gray};")
        disclaimer.setWordWrap(True)
        
        footer_layout.addWidget(info_icon)
        footer_layout.addWidget(disclaimer)
        footer_layout.addStretch()
        
        card_layout.addWidget(footer_frame)
        
        self._style_section_card(card)
        
        return card
    
    def eventFilter(self, obj, event):
        """Handle hover events for rows and clickable section headers."""
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            collapse = getattr(self, "_adjust_weight_collapse_lbl", None)
            if collapse is not None and obj is collapse:
                self._toggle_adjust_weight()
                return True
            header = getattr(self, "_adjust_weight_header", None)
            if header is not None and obj is header:
                self._toggle_adjust_weight()
                return True
            # Surface area collapse handling
            s_collapse = getattr(self, "_surface_collapse_lbl", None)
            if s_collapse is not None and obj is s_collapse:
                self._toggle_surface_area()
                return True
            s_header = getattr(self, "_surface_header", None)
            if s_header is not None and obj is s_header:
                self._toggle_surface_area()
                return True
        return super().eventFilter(obj, event)
    
    def on_material_changed(self, index):
        """Handle material selection change."""
        if index < 0 or index >= len(self.MATERIALS):
            return
        
        material_name, density = self.MATERIALS[index]
        self.weight_density_row.set_density_silent(density)
        self.calculate_weight()
    
    def _effective_density_g_per_cm3(self):
        """Density from the manual field if valid; otherwise from the material preset."""
        text = self.weight_density_row.density_input.text().strip().replace(",", ".")
        if text:
            try:
                v = float(text)
                if v > 0:
                    return v
            except ValueError:
                pass
        index = self.material_combo.currentIndex()
        if 0 <= index < len(self.MATERIALS):
            return self.MATERIALS[index][1]
        return None
    
    def calculate_weight(self, volume_mm3=None, density_g_per_cm3=None):
        """Calculate and update the estimated weight."""
        from core.mesh_calculator import MeshCalculator
        
        if volume_mm3 is None:
            volume_mm3 = self.current_volume_mm3
        
        if density_g_per_cm3 is None:
            density_g_per_cm3 = self._effective_density_g_per_cm3()
            if density_g_per_cm3 is None:
                self.weight_result_row.set_value("--")
                self.current_weight_grams = 0.0
                self.calculate_scale_btn.setEnabled(False)
                self.reset_scale_results()
                return
        
        result = MeshCalculator.estimate_weight(volume_mm3, density_g_per_cm3)
        self.weight_result_row.set_value(result['display'])
        
        # Store current weight for scaling calculations
        self.current_weight_grams = result['grams']
        
        # Enable/disable calculate button based on whether we have valid data
        has_valid_weight = self.current_weight_grams > 0
        self.calculate_scale_btn.setEnabled(has_valid_weight)
        
        # Reset scale results if weight changed
        self.reset_scale_results()
    
    def calculate_scale(self):
        """Calculate the scale factor for target weight."""
        from core.mesh_calculator import MeshCalculator
        
        # Get target weight from input
        target_text = self.target_weight_input.text().strip()
        if not target_text:
            return
        
        try:
            target_weight = float(target_text)
        except ValueError:
            return
        
        if target_weight <= 0 or self.current_weight_grams <= 0:
            return
        
        # Calculate scale factor
        scale_result = MeshCalculator.calculate_scale_for_target_weight(
            self.current_weight_grams, target_weight
        )
        
        if not scale_result['valid']:
            return
        
        scale_factor = scale_result['scale_factor']
        self.calculated_scale_factor = scale_factor
        
        # Update scale factor display
        self.scale_factor_row.set_value(f"{scale_factor:.6f}")
        
        # Calculate new dimensions
        new_dims = MeshCalculator.apply_scale_to_dimensions(
            self.current_dimensions['width'],
            self.current_dimensions['height'],
            self.current_dimensions['depth'],
            scale_factor
        )
        
        self.new_x_row.set_value(f"{new_dims['width']:.2f} mm")
        self.new_y_row.set_value(f"{new_dims['height']:.2f} mm")
        self.new_z_row.set_value(f"{new_dims['depth']:.2f} mm")
        
        # Calculate new volume
        new_volume = MeshCalculator.apply_scale_to_volume(self.current_volume_mm3, scale_factor)
        self.new_volume_row.set_value(f"{new_volume['volume_cm3']:.4f} cm³")
        
        # Update weight comparison
        if self.current_weight_grams >= 1000:
            original_display = f"{self.current_weight_grams / 1000:.3f} kg"
        else:
            original_display = f"{self.current_weight_grams:.2f} g"
        
        if target_weight >= 1000:
            target_display = f"{target_weight / 1000:.3f} kg"
        else:
            target_display = f"{target_weight:.2f} g"
        
        self.original_weight_row.set_value(original_display)
        self.target_weight_row.set_value(target_display)
        
        # Enable export button
        self.export_scaled_btn.setEnabled(True)
        
        # Update state - scaled data now available
        self.has_scaled_data = True
        self.update_pdf_button_state()
    
    def reset_scale_results(self):
        """Reset all scale result displays."""
        self.scale_factor_row.set_value("--")
        self.new_x_row.set_value("--")
        self.new_y_row.set_value("--")
        self.new_z_row.set_value("--")
        self.new_volume_row.set_value("--")
        self.original_weight_row.set_value("--")
        self.target_weight_row.set_value("--")
        self.export_scaled_btn.setEnabled(False)
        self.calculated_scale_factor = 1.0
        
        # Update state - scaled data no longer available
        self.has_scaled_data = False
        self.update_pdf_button_state()
    
    def export_scaled_stl_file(self):
        """Handle export of scaled STL file."""
        if self.calculated_scale_factor == 1.0:
            return
        
        # Open save dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Scaled STL File",
            "",
            "STL Files (*.stl);;All Files (*)"
        )
        
        if file_path:
            # Ensure .stl extension
            if not file_path.lower().endswith('.stl'):
                file_path += '.stl'
            
            # Emit signal with file path and scale factor
            self.export_scaled_stl.emit(file_path, self.calculated_scale_factor)
    
    # ── Unit conversion ──────────────────────────────────────────────────────

    _UNITS = ["mm", "cm", "in"]
    _UNIT_LABELS = {"mm": "mm  ▾", "cm": "cm  ▾", "in": "in  ▾"}
    _LEN_FACTORS  = {"mm": 1.0,        "cm": 0.1,      "in": 1/25.4}
    _VOL_FACTORS  = {"mm": 1.0,        "cm": 0.001,    "in": 1/16387.064}
    _LEN_SUFFIXES = {"mm": "mm",       "cm": "cm",     "in": "in"}
    _VOL_SUFFIXES = {"mm": "mm³",      "cm": "cm³",    "in": "in³"}

    def _show_unit_menu(self):
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: #1c2029; color: #e2e8f0;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 8px; padding: 4px;
                font-size: 15px; font-weight: bold;
            }}
            QMenu::item {{ padding: 7px 20px; border-radius: 5px; }}
            QMenu::item:selected {{ background: {default_theme.button_primary}; color: white; }}
            QMenu::item[checked="true"] {{ color: {default_theme.button_primary}; }}
        """)
        for unit in self._UNITS:
            action = menu.addAction(("✓  " if unit == self._dim_unit else "    ") + unit)
            action.triggered.connect(lambda _, u=unit: self._set_dim_unit(u))
        menu.exec_(self._unit_btn.mapToGlobal(self._unit_btn.rect().bottomLeft()))

    def _set_dim_unit(self, unit: str):
        if unit == self._dim_unit:
            return
        self._dim_unit = unit
        self._unit_btn.setText(self._UNIT_LABELS[unit])
        self._refresh_dim_display()

    def _refresh_dim_display(self):
        """Reformat displayed dimension values using the current unit."""
        dims = self.current_dimensions
        vol  = self.current_volume_mm3
        lf   = self._LEN_FACTORS[self._dim_unit]
        vf   = self._VOL_FACTORS[self._dim_unit]
        ls   = self._LEN_SUFFIXES[self._dim_unit]
        vs   = self._VOL_SUFFIXES[self._dim_unit]

        if dims['width'] == 0.0 and dims['height'] == 0.0 and dims['depth'] == 0.0:
            self.width_row.set_value("--")
            self.height_row.set_value("--")
            self.depth_row.set_value("--")
            self.volume_row.set_value("--")
            return

        dp = 4 if self._dim_unit == "in" else 2
        self.width_row.set_value(f"{dims['width']  * lf:.{dp}f} {ls}")
        self.height_row.set_value(f"{dims['height'] * lf:.{dp}f} {ls}")
        self.depth_row.set_value(f"{dims['depth']  * lf:.{dp}f} {ls}")
        self.volume_row.set_value(f"{vol * vf:.{dp}f} {vs}")

    def update_dimensions(self, mesh_data, filename=None):
        """Update all dimension displays with mesh data."""
        from core.mesh_calculator import MeshCalculator
        
        if mesh_data is None:
            self.width_row.set_value("--")
            self.height_row.set_value("--")
            self.depth_row.set_value("--")
            self.volume_row.set_value("--")
            self.surface_total_row.set_value("--")
            self.surface_cm_row.set_value("--")
            self.weight_volume_row.set_value("--")
            self.current_volume_mm3 = 0.0
            self.current_dimensions = {'width': 0.0, 'height': 0.0, 'depth': 0.0}
            self.current_surface_area_cm2 = 0.0
            self.current_stl_filename = ""
            self.has_stl_loaded = False
            self.calculate_weight()
            self.reset_scale_results()
            self.calculate_scale_btn.setEnabled(False)
            self.update_pdf_button_state()
            return
        
        # Store filename
        if filename:
            self.current_stl_filename = os.path.basename(filename)
        
        # Store current dimensions (always in mm — display is converted by _refresh_dim_display)
        self.current_dimensions = {
            'width': mesh_data['width'],
            'height': mesh_data['height'],
            'depth': mesh_data['depth']
        }
        
        # Update surface area
        self.surface_total_row.set_value(f"{mesh_data['surface_area_mm2']:.2f} mm²")
        self.surface_cm_row.set_value(f"{mesh_data['surface_area_cm2']:.2f} cm²")
        self.current_surface_area_cm2 = mesh_data['surface_area_cm2']
        self.has_stl_loaded = True
        
        # Update weight calculator
        self.current_volume_mm3 = mesh_data['volume_mm3']
        self.weight_volume_row.set_value(f"{mesh_data['volume_cm3']:.4f} cm³")

        # Refresh dimension columns in the currently selected unit
        self._refresh_dim_display()
        
        # Update density field from selected material preset
        index = self.material_combo.currentIndex()
        if index >= 0 and index < len(self.MATERIALS):
            _, density = self.MATERIALS[index]
            self.weight_density_row.set_density_silent(density)
        
        # Calculate weight
        self.calculate_weight()
        
        # Update PDF button state
        self.update_pdf_button_state()
    
    def update_pdf_button_state(self):
        """Update the PDF export button based on available data."""
        if hasattr(self, 'export_pdf_btn'):
            self.export_pdf_btn.setEnabled(self.has_stl_loaded)
        if hasattr(self, 'export_review_btn'):
            self.export_review_btn.setEnabled(self.has_stl_loaded)
    
    def export_pdf_report(self):
        """Generate and export 3D PDF with multiple views."""
        if is_education():
            QMessageBox.information(
                self, "Education Version",
                "PDF export is not available in the Education version."
            )
            return
        if not self.has_stl_loaded:
            return
        
        # We need access to the current mesh - emit a signal to get it
        # For now, we'll need to get mesh from parent
        mesh = self._get_current_mesh()
        if mesh is None:
            QMessageBox.warning(
                self,
                "Export Error",
                "No 3D model loaded. Please load a model first."
            )
            return
        
        # Open save dialog
        default_name = f"3D_Model_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save 3D PDF",
            default_name,
            "PDF Files (*.pdf);;All Files (*)"
        )
        
        if not file_path:
            return
        
        # Ensure .pdf extension
        if not file_path.lower().endswith('.pdf'):
            file_path += '.pdf'
        
        try:
            from core.pdf3d_exporter import PDF3DExporter
            
            # Show progress message
            self.export_pdf_btn.setEnabled(False)
            self.export_pdf_btn.setText("Exporting...")
            QApplication.processEvents()
            
            success, result = PDF3DExporter.export_interactive_3d_pdf(
                mesh, 
                file_path, 
                title=self.current_stl_filename,
                allow_static_fallback=False,
            )
            
            # Restore button
            self.export_pdf_btn.setEnabled(True)
            self.export_pdf_btn.setText("Export 3D PDF")
            
            if success:
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"3D PDF exported successfully:\n{file_path}"
                )
            else:
                # Help the user quickly find detailed exporter logs
                try:
                    app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
                    log_path = os.path.join(app_root, "app_debug.log")
                except Exception:
                    log_path = "app_debug.log"

                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to export interactive 3D PDF:\n{result}\n\n"
                    f"Detailed logs: {log_path}"
                )
        except Exception as e:
            logger.error(f"Error exporting 3D PDF: {e}")
            self.export_pdf_btn.setEnabled(True)
            self.export_pdf_btn.setText("Export 3D PDF")

            try:
                app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
                log_path = os.path.join(app_root, "app_debug.log")
            except Exception:
                log_path = "app_debug.log"

            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export interactive 3D PDF:\n{str(e)}\n\nDetailed logs: {log_path}"
            )
    
    def _get_current_mesh(self):
        """Get the current mesh from the viewer widget."""
        # Navigate up to find the main window and get mesh from viewer
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, 'viewer_widget') and hasattr(parent.viewer_widget, 'current_mesh'):
                return parent.viewer_widget.current_mesh
            parent = parent.parent()
        return None
    
    def create_export_annotations_section(self):
        """Create the Export as .ecto section."""
        card = QFrame()
        card.setObjectName("exportAnnotationsCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)
        
        # Header row with title and icon
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        self.export_ecto_title_label = QLabel(t("sidebar.export_ecto_title"))
        title_font = make_font(size=14, bold=True)
        self.export_ecto_title_label.setFont(title_font)
        self.export_ecto_title_label.setStyleSheet(
            f"color: {default_theme.text_title}; margin-bottom: 4px; background: transparent; border: none;"
        )
        
        icon_label = QLabel("📦")
        icon_label.setStyleSheet(
            f"color: {default_theme.icon_blue}; font-size: 16px; background-color: transparent; background: transparent; border: none; padding: 0px;"
        )
        icon_label.setAlignment(Qt.AlignCenter)
        
        header_layout.addWidget(self.export_ecto_title_label)
        header_layout.addStretch()
        header_layout.addWidget(icon_label)
        card_layout.addLayout(header_layout)
        
        # Description
        self.export_ecto_desc_label = QLabel(t("sidebar.export_ecto_desc"))
        desc_font = make_font(size=11)
        self.export_ecto_desc_label.setFont(desc_font)
        self.export_ecto_desc_label.setStyleSheet(
            f"color: {default_theme.text_secondary}; background-color: transparent; background: transparent; border: none;"
        )
        self.export_ecto_desc_label.setWordWrap(True)
        card_layout.addWidget(self.export_ecto_desc_label)
        
        # Annotation count label
        self.annotation_count_label = QLabel(t("sidebar.no_annotations"))
        self.annotation_count_label.setStyleSheet(
            f"color: {default_theme.text_secondary}; font-style: italic; background-color: transparent; background: transparent; border: none;"
        )
        card_layout.addWidget(self.annotation_count_label)
        
        # Export button
        self.export_annotations_btn = QPushButton(t("sidebar.export_ecto_btn"))
        self.export_annotations_btn.setObjectName("exportAnnotationsBtn")
        self.export_annotations_btn.setMinimumHeight(44)
        self.export_annotations_btn.setEnabled(False)
        self.export_annotations_btn.setStyleSheet(f"""
            QPushButton#exportAnnotationsBtn {{
                background-color: #5B21B6;
                color: {default_theme.text_white};
                border: none;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#exportAnnotationsBtn:hover {{
                background-color: #4C1D95;
            }}
            QPushButton#exportAnnotationsBtn:pressed {{
                background-color: #3B0764;
            }}
            QPushButton#exportAnnotationsBtn:disabled {{
                background-color: #171a1f;
                color: {default_theme.text_secondary};
                border: 1px solid #2a2e34;
                border-radius: 8px;
            }}
        """)
        self.export_annotations_btn.clicked.connect(self.export_as_ecto)
        card_layout.addWidget(self.export_annotations_btn)
        
        # (Disclaimer moved to '?' help badge in section header)
        
        self._style_section_card(card)
        
        return card
    
    def update_annotation_count(self, count: int):
        """Update the annotation count label and button state."""
        self._annotation_count = count
        if count == 0:
            self.annotation_count_label.setText(t("sidebar.no_annotations"))
            self.export_annotations_btn.setEnabled(self.has_stl_loaded)
        else:
            self.annotation_count_label.setText(f"📌 {count} {t('sidebar.annotations_ready')}")
            self.export_annotations_btn.setEnabled(self.has_stl_loaded)
    
    def export_as_ecto(self):
        """Export the current model as an .ecto bundle file."""
        if not self.has_stl_loaded:
            QMessageBox.warning(
                self,
                "Export Error",
                "No 3D model loaded. Please load a model first."
            )
            return
        
        # Get current mesh
        mesh = self._get_current_mesh()
        if mesh is None:
            QMessageBox.warning(
                self,
                "Export Error",
                "No 3D model available for export."
            )
            return
        
        # Get annotations, drawings, and texture data
        annotations = self._get_annotations()
        drawings = self._get_drawings()
        texture_data = self._get_texture_data()
        
        if not annotations and not drawings:
            if not confirm_dialog(
                self,
                "No Annotations or Drawings",
                "There are no annotations or drawings to include.\nDo you want to export the model as .ecto without them?"
            ):
                return
        
        # Open save dialog
        default_name = f"{os.path.splitext(self.current_stl_filename)[0]}.lyns"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            t("sidebar.export_as_ecto_bundle"),
            default_name,
            "LYNS Bundle (*.lyns);;All Files (*)"
        )

        if not file_path:
            return

        # Ensure .lyns extension
        if not file_path.lower().endswith('.lyns'):
            file_path += '.lyns'
        
        try:
            from core.ecto_format import EctoFormat
            
            # Show progress
            self.export_annotations_btn.setEnabled(False)
            self.export_annotations_btn.setText(t("sidebar.exporting"))
            QApplication.processEvents()
            
            # Export as .ecto bundle (includes annotations, drawings, and texture)
            success, result, creator_token = EctoFormat.export(
                mesh=mesh,
                annotations=annotations,
                output_path=file_path,
                source_format='stl',
                original_filename=self.current_stl_filename,
                drawings=drawings,
                texture_data=texture_data
            )
            
            # Restore button
            self.export_annotations_btn.setEnabled(True)
            self.export_annotations_btn.setText(t("sidebar.export_ecto_btn"))
            
            if success:
                # Register creator token so sender can reopen in editor mode
                if creator_token:
                    try:
                        from core.creator_registry import register_creator_token
                        register_creator_token(creator_token)
                    except ImportError:
                        pass
                # Emit signal that annotations were exported
                self.annotations_exported.emit()
                
                # Build success message
                msg = f"Export complete!\n\nCreated: {os.path.basename(file_path)}"
                if annotations or drawings or texture_data:
                    msg += f"\n\n📦 Bundle contains:"
                    msg += f"\n• 3D Model (STL)"
                    if annotations:
                        msg += f"\n• {len(annotations)} annotation{'s' if len(annotations) != 1 else ''}"
                        image_count = sum(len(ann.get('image_paths', [])) for ann in annotations)
                        if image_count > 0:
                            msg += f"\n• {image_count} attached photo{'s' if image_count != 1 else ''}"
                    if drawings:
                        msg += f"\n• {len(drawings)} drawing stroke{'s' if len(drawings) != 1 else ''}"
                    if texture_data:
                        msg += f"\n• Material/texture preset"
                else:
                    msg += f"\n\n📦 Bundle contains: 3D Model only"
                
                msg += "\n\nRecipients can open this file in LYNS."

                QMessageBox.information(self, "Export Complete", msg)
            else:
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to create .lyns bundle:\n{result}"
                )
        except Exception as e:
            logger.error(f"Error exporting as .lyns: {e}")
            self.export_annotations_btn.setEnabled(True)
            self.export_annotations_btn.setText(t("sidebar.export_ecto_btn"))
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to create .lyns bundle:\n{str(e)}"
            )
    
    def create_export_review_section(self):
        """Create the Export as .lyns.review section."""
        card = QFrame()
        card.setObjectName("exportReviewCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        # Header row
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        title_lbl = QLabel(t("sidebar.export_review_title"))
        title_lbl.setFont(make_font(size=14, bold=True))
        title_lbl.setStyleSheet(
            f"color: {default_theme.text_title}; background: transparent; border: none;"
        )
        icon_lbl = QLabel("📤")
        icon_lbl.setStyleSheet(
            "font-size: 16px; background: transparent; border: none; padding: 0px;"
        )
        icon_lbl.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(icon_lbl)
        card_layout.addLayout(header_layout)

        # Description
        desc_lbl = QLabel(t("sidebar.export_review_desc"))
        desc_lbl.setFont(make_font(size=11))
        desc_lbl.setStyleSheet(
            f"color: {default_theme.text_secondary}; background: transparent; border: none;"
        )
        desc_lbl.setWordWrap(True)
        card_layout.addWidget(desc_lbl)

        # Export button
        self.export_review_btn = QPushButton(t("sidebar.export_review_btn"))
        self.export_review_btn.setObjectName("exportReviewBtn")
        self.export_review_btn.setMinimumHeight(44)
        self.export_review_btn.setEnabled(False)
        self.export_review_btn.setStyleSheet(f"""
            QPushButton#exportReviewBtn {{
                background-color: {default_theme.button_primary};
                color: {default_theme.text_white};
                border: none;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#exportReviewBtn:hover {{
                background-color: {default_theme.button_primary_hover};
            }}
            QPushButton#exportReviewBtn:disabled {{
                background-color: #171a1f;
                color: {default_theme.text_secondary};
                border: 1px solid #2a2e34;
                border-radius: 8px;
            }}
        """)
        self.export_review_btn.clicked.connect(self.export_as_lyns_review)
        card_layout.addWidget(self.export_review_btn)

        self._style_section_card(card)
        return card

    def export_as_lyns_review(self):
        """Export the current model + annotations as a .lyns.review file for a supplier."""
        if not self.has_stl_loaded:
            QMessageBox.warning(self, "Export Error", t("sidebar.export_review_no_model"))
            return

        mesh = self._get_current_mesh()
        if mesh is None:
            QMessageBox.warning(self, "Export Error", t("sidebar.no_model_available"))
            return

        annotations = self._get_annotations()
        drawings = self._get_drawings()
        texture_data = self._get_texture_data()

        default_name = f"{os.path.splitext(self.current_stl_filename)[0]}.lyns.review"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export as LYNS Supplier Review",
            default_name,
            "LYNS Review (*.lyns.review);;All Files (*)"
        )
        if not file_path:
            return
        if not file_path.endswith('.lyns.review'):
            file_path += '.lyns.review'

        try:
            from core.ecto_format import EctoFormat
            from core.identity import get_display_name
            import json
            from datetime import datetime, timezone

            self.export_review_btn.setEnabled(False)
            self.export_review_btn.setText(t("sidebar.exporting"))
            QApplication.processEvents()

            # Re-use EctoFormat.export to bundle the 3D data, then wrap in .lyns.review envelope
            import tempfile, zipfile
            with tempfile.NamedTemporaryFile(suffix='.lyns', delete=False) as tmp:
                tmp_path = tmp.name

            success, result, _ = EctoFormat.export(
                mesh=mesh,
                annotations=annotations,
                output_path=tmp_path,
                source_format='stl',
                original_filename=self.current_stl_filename,
                drawings=drawings,
                texture_data=texture_data
            )

            if not success:
                raise RuntimeError(result)

            # Read the bundle bytes and embed in .lyns.review JSON envelope
            with open(tmp_path, 'rb') as f:
                import base64
                bundle_b64 = base64.b64encode(f.read()).decode()
            os.unlink(tmp_path)

            review_data = {
                "file_type": "lyns.review",
                "version": "1.0",
                "exported_by": get_display_name(),
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "original_filename": self.current_stl_filename,
                "supplier_name": "",
                "supplier_company": "",
                "model_bundle_b64": bundle_b64,
                "annotation_count": len(annotations),
            }

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(review_data, f, indent=2, ensure_ascii=False)

            self.export_review_btn.setEnabled(True)
            self.export_review_btn.setText(t("sidebar.export_review_btn"))

            QMessageBox.information(
                self, "Export Complete",
                f"Supplier review exported!\n\n{os.path.basename(file_path)}\n\n"
                f"Send this file to your supplier.\nThey open it in LYNS Lite."
            )

        except Exception as e:
            logger.error(f"Error exporting .lyns.review: {e}")
            self.export_review_btn.setEnabled(True)
            self.export_review_btn.setText(t("sidebar.export_review_btn"))
            QMessageBox.critical(self, "Export Error", f"Failed to create .lyns.review:\n{str(e)}")

    def _get_annotations(self):
        """Get annotations from the annotation panel."""
        # Navigate up to find the main window and get annotations
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, 'annotation_panel') and hasattr(parent.annotation_panel, 'export_annotations'):
                return parent.annotation_panel.export_annotations()
            parent = parent.parent()
        return []

    def _get_drawings(self):
        """Get drawings (strokes) from the viewer widget for .ecto export."""
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, 'viewer_widget') and parent.viewer_widget is not None:
                vw = parent.viewer_widget
                if hasattr(vw, 'get_draw_strokes'):
                    return vw.get_draw_strokes()
            parent = parent.parent()
        return []

    def _get_texture_data(self):
        """Get current material/texture preset data from the viewer widget for .ecto export."""
        # Use direct reference to main window (set by stl_viewer.py)
        main_win = getattr(self, '_main_window', None)
        if main_win is not None:
            vw = getattr(main_win, 'viewer_widget', None)
            if vw is not None and hasattr(vw, 'get_texture_data'):
                data = vw.get_texture_data()
                logger.info(f"_get_texture_data: Got texture data: {data is not None}")
                return data
        # Fallback: walk parent chain
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, 'viewer_widget') and parent.viewer_widget is not None:
                vw = parent.viewer_widget
                if hasattr(vw, 'get_texture_data'):
                    return vw.get_texture_data()
            parent = parent.parent()
        logger.warning("_get_texture_data: Could not find viewer widget")
        return None

    def reset_all_data(self):
        """Reset all data displays to initial state."""
        # Reset dimensions
        self.width_row.set_value("--")
        self.height_row.set_value("--")
        self.depth_row.set_value("--")
        self.volume_row.set_value("--")
        
        # Reset surface area
        self.surface_total_row.set_value("--")
        self.surface_cm_row.set_value("--")
        
        # Reset weight — keep density showing the selected material
        self.weight_volume_row.set_value("--")
        idx = self.material_combo.currentIndex()
        if 0 <= idx < len(self.MATERIALS):
            _, d = self.MATERIALS[idx]
            self.weight_density_row.set_density_silent(d)
        else:
            self.weight_density_row.clear_density_silent()
        self.weight_result_row.set_value("--")
        
        # Reset scale results
        self.reset_scale_results()
        
        # Reset target weight input
        self.target_weight_input.clear()
        
        # Reset annotation count
        self.update_annotation_count(0)
        
        # Reset internal state
        self.current_volume_mm3 = 0.0
        self.current_weight_grams = 0.0
        self.current_dimensions = {'width': 0.0, 'height': 0.0, 'depth': 0.0}
        self.current_surface_area_cm2 = 0.0
        self.current_stl_filename = ""
        self.has_stl_loaded = False
        self.has_scaled_data = False
        self.calculated_scale_factor = 1.0
        
        # Update button states
        self.calculate_scale_btn.setEnabled(False)
        self.update_pdf_button_state()
        
        logger.info("reset_all_data: All sidebar data reset")

    def retranslate(self):
        """Update all sidebar labels for the current language."""
        self._title_label.setText(t("sidebar.title"))
        self.upload_btn.setText(t("sidebar.upload_btn"))
        self.upload_btn.setToolTip(t("sidebar.upload_tooltip"))
        self._info_label.setText(t("sidebar.upload_info"))
        self._dim_title.setText(t("sidebar.dimensions"))
        self.width_row.set_label(t("sidebar.length_x"))
        self.height_row.set_label(t("sidebar.width_y"))
        self.depth_row.set_label(t("sidebar.height_z"))
        self.volume_row.set_label(t("sidebar.volume"))
        self.surface_title_label.setText(t("sidebar.total_surface_area"))
        self.surface_total_row.set_label(t("sidebar.total_area"))
        self.surface_cm_row.set_label(t("sidebar.area_cm2"))
        self.weight_title_label.setText(t("sidebar.estimated_weight"))
        self._material_display_row.set_label(t("sidebar.material"))
        self.weight_volume_row.set_label(t("sidebar.volume"))
        self.weight_density_row.set_label(t("sidebar.density"))
        self.weight_result_row.set_label(t("sidebar.estimated_weight_result"))
        self.adjust_weight_title_label.setText(t("sidebar.adjust_target_weight"))
        self.results_label.setText(t("sidebar.scaled_results"))
        self.weight_comparison_label.setText(t("sidebar.weight_comparison"))
        self.calculate_scale_btn.setText(t("sidebar.calculate_scale"))
        self.scale_factor_row.set_label(t("sidebar.scale_factor"))
        self.new_x_row.set_label(t("sidebar.new_x"))
        self.new_y_row.set_label(t("sidebar.new_y"))
        self.new_z_row.set_label(t("sidebar.new_z"))
        self.new_volume_row.set_label(t("sidebar.new_volume"))
        self.original_weight_row.set_label(t("sidebar.original_weight"))
        self.target_weight_row.set_label(t("sidebar.target_weight"))
        self.export_scaled_btn.setText(t("sidebar.export_scaled_stl"))
        self.export_ecto_title_label.setText(t("sidebar.export_ecto_title"))
        self.export_ecto_desc_label.setText(t("sidebar.export_ecto_desc"))
        self.export_annotations_btn.setText(t("sidebar.export_ecto_btn"))
        self.target_weight_input.setPlaceholderText(t("sidebar.enter_target_weight"))
        self.update_annotation_count(self._annotation_count)
        for i, (key, density) in enumerate(self.MATERIALS):
            self.material_combo.setItemText(i, f"{self._material_label(key)} ({density} g/cm³)")
        self._update_material_display(self.material_combo.currentIndex())
        fm = self.adjust_weight_title_label.fontMetrics()
        self.adjust_weight_title_label.setMinimumWidth(fm.horizontalAdvance(self.adjust_weight_title_label.text()) + 8)

