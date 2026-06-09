"""
Technical Overview Sidebar — metadata fields for the technical document.
Fields: Property, Title, Manufacturer, Start Date, Deadline, Comments.
"""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QTextEdit,
    QDateEdit, QFrame, QSizePolicy, QScrollArea, QPushButton, QHBoxLayout,
    QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal
from PyQt5.QtGui import QPalette, QColor
from ui.styles import default_theme, make_font, sidebar_section_card_stylesheet, get_button_style, TOOLTIP_STYLE
from i18n import t, on_language_changed
from core.edition import is_education

logger = logging.getLogger(__name__)

# Input fields: white surface, black text (Technical Overview sidebar)
_FIELD_BG = "#ffffff"
_FIELD_TEXT = "#111827"
_FIELD_BORDER = "#d1d5db"
_FIELD_PLACEHOLDER = "#6b7280"


def _apply_field_palette(widget):
    """Ensure typed text is dark and placeholder is muted (global theme may use light-on-dark)."""
    pal = widget.palette()
    pal.setColor(QPalette.Text, QColor(_FIELD_TEXT))
    pal.setColor(QPalette.PlaceholderText, QColor(_FIELD_PLACEHOLDER))
    widget.setPalette(pal)


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 14px; font-weight: bold; margin-top: 6px;")
    return lbl


def _line_edit(placeholder: str = "") -> QLineEdit:
    le = QLineEdit()
    le.setPlaceholderText(placeholder)
    le.setFixedHeight(30)
    le.setStyleSheet(f"""
        QLineEdit {{
            background-color: {_FIELD_BG};
            border: 1px solid {_FIELD_BORDER};
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 15px;
            color: {_FIELD_TEXT};
        }}
        QLineEdit:focus {{
            border: 2px solid {default_theme.button_primary};
        }}
    """)
    _apply_field_palette(le)
    return le


class TechnicalSidebar(QWidget):
    """Left sidebar for Technical Overview metadata."""

    annotate_toggled = pyqtSignal(bool)  # True = enter annotation mode
    upload_requested = pyqtSignal()
    export_requested = pyqtSignal()  # Export .ecto
    export_pdf_requested = pyqtSignal()  # Export PDF report
    reset_requested = pyqtSignal()  # Reset workspace

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._init_ui()

    def _add_card_shadow(self, widget, blur_radius=26, y_offset=8, alpha=110):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(blur_radius)
        shadow.setXOffset(0)
        shadow.setYOffset(y_offset)
        shadow.setColor(QColor(0, 0, 0, alpha))
        widget.setGraphicsEffect(shadow)

    def _style_section_card(self, card: QFrame):
        name = card.objectName()
        if not name:
            return
        card.setStyleSheet(f"QFrame#{name} {{ {sidebar_section_card_stylesheet(default_theme)} }}")
        card.setAttribute(Qt.WA_StyledBackground, True)
        self._add_card_shadow(card)

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setObjectName("sidebarScrollArea")
        scroll.setMinimumWidth(350)
        scroll.setStyleSheet(f"""
            QScrollArea#sidebarScrollArea {{
                background-color: {default_theme.background};
                border: none;
            }}
            QScrollArea#sidebarScrollArea > QWidget > QWidget {{
                background-color: {default_theme.background};
            }}
        """)
        scroll.viewport().setStyleSheet(f"background-color: {default_theme.background};")

        container = QWidget()
        container.setObjectName("sidebarContent")
        container.setStyleSheet(f"background-color: {default_theme.background};")
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(10, 14, 20, 18)
        layout.setSpacing(15)

        upload_card = QFrame()
        upload_card.setObjectName("uploadCard")
        self._style_section_card(upload_card)
        upload_card_layout = QVBoxLayout(upload_card)
        upload_card_layout.setContentsMargins(16, 18, 16, 18)
        upload_card_layout.setSpacing(10)

        # Title header
        self.header = QLabel(t("technical.title"))
        hfont = make_font(size=16, bold=True)
        self.header.setFont(hfont)
        self.header.setAlignment(Qt.AlignCenter)
        self.header.setStyleSheet(f"background: transparent; border: none; color: {default_theme.text_title};")
        upload_card_layout.addWidget(self.header)

        self.upload_btn = QPushButton(t("technical.upload_btn"))
        self.upload_btn.setObjectName("technicalUploadBtn")
        self.upload_btn.setMinimumHeight(50)
        self.upload_btn.setCursor(Qt.PointingHandCursor)
        self.upload_btn.setStyleSheet(get_button_style("technicalUploadBtn"))
        self.upload_btn.setAttribute(Qt.WA_StyledBackground, True)
        self._add_card_shadow(self.upload_btn, blur_radius=34, y_offset=9, alpha=210)
        self.upload_btn.clicked.connect(lambda: self.upload_requested.emit())
        upload_card_layout.addWidget(self.upload_btn)

        layout.addWidget(upload_card)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {default_theme.separator};")
        layout.addWidget(sep)

        # Property
        self.property_label = _section_label(t("technical.property"))
        layout.addWidget(self.property_label)
        self.property_edit = _line_edit("e.g. Company")
        layout.addWidget(self.property_edit)

        # Title
        self.object_title_label = _section_label(t("technical.object_title"))
        layout.addWidget(self.object_title_label)
        self.title_edit = _line_edit("e.g. HVAC Unit #12")
        layout.addWidget(self.title_edit)

        # Manufacturer(s)
        mfr_header = QHBoxLayout()
        self.manufacturer_label = _section_label(t("technical.manufacturer"))
        mfr_header.addWidget(self.manufacturer_label)
        mfr_header.addStretch()
        add_mfr_btn = QPushButton("+")
        add_mfr_btn.setFixedSize(26, 26)
        add_mfr_btn.setCursor(Qt.PointingHandCursor)
        add_mfr_btn.setToolTip("Add another manufacturer")
        add_mfr_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.button_primary};
                border: none; border-radius: 13px;
                color: white; font-size: 16px; font-weight: bold;
                padding: 0; min-width: 26px; min-height: 26px;
            }}
            QPushButton:hover {{
                background-color: {default_theme.button_primary_hover};
            }}
        """ + TOOLTIP_STYLE)
        add_mfr_btn.clicked.connect(self._add_manufacturer_field)
        mfr_header.addWidget(add_mfr_btn)
        layout.addLayout(mfr_header)

        self._manufacturer_container = QVBoxLayout()
        self._manufacturer_container.setSpacing(4)
        self._manufacturer_edits = []
        first_mfr = self._create_manufacturer_row("e.g. Carrier, Daikin", removable=False)
        self._manufacturer_container.addWidget(first_mfr)
        layout.addLayout(self._manufacturer_container)

        # Dates
        self.start_date_label = _section_label(t("technical.start_date"))
        layout.addWidget(self.start_date_label)
        from ui.date_picker import EctoDateEdit
        self.start_date = EctoDateEdit(QDate.currentDate())
        self.start_date.setFixedHeight(30)
        layout.addWidget(self.start_date)

        self.deadline_label = _section_label(t("technical.deadline"))
        layout.addWidget(self.deadline_label)
        self.deadline_date = EctoDateEdit(QDate.currentDate().addMonths(1))
        self.deadline_date.setFixedHeight(30)
        layout.addWidget(self.deadline_date)

        # Comments
        self.comments_label = _section_label(t("technical.comments"))
        layout.addWidget(self.comments_label)
        self.comments_edit = QTextEdit()
        self.comments_edit.setPlaceholderText("Add notes, observations, or instructions…")
        self.comments_edit.setMinimumHeight(120)
        self.comments_edit.setMaximumHeight(250)
        self.comments_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {_FIELD_BG};
                border: 1px solid {_FIELD_BORDER};
                border-radius: 6px;
                padding: 8px;
                font-size: 15px;
                color: {_FIELD_TEXT};
            }}
            QTextEdit:focus {{
                border: 2px solid {default_theme.button_primary};
            }}
        """)
        _apply_field_palette(self.comments_edit)
        layout.addWidget(self.comments_edit)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"color: {default_theme.separator};")
        layout.addWidget(sep2)

        # Annotate toggle button
        self.annotate_btn = QPushButton(t("technical.annotate"))
        self.annotate_btn.setFixedHeight(34)
        self.annotate_btn.setCursor(Qt.PointingHandCursor)
        self.annotate_btn.setCheckable(True)
        self._annotation_mode = False
        self.annotate_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                border: 1px solid {default_theme.border_light};
                border-radius: 8px;
                padding: 6px 12px; font-size: 15px;
                color: {default_theme.text_primary};
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
            QPushButton:checked {{
                background-color: {default_theme.row_bg_highlight};
                border: 1px solid {default_theme.border_highlight};
            }}
        """)
        self.annotate_btn.clicked.connect(self._on_annotate_toggled)
        layout.addWidget(self.annotate_btn)

        # Export .ecto button
        self.export_btn = QPushButton(t("technical.export_ecto"))
        self.export_btn.setFixedHeight(34)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #10B981;
                border: none; border-radius: 8px;
                padding: 6px 12px; font-size: 15px; font-weight: bold;
                color: white;
            }}
            QPushButton:hover {{
                background-color: #059669;
            }}
        """)
        self.export_btn.clicked.connect(lambda: self.export_requested.emit())
        layout.addWidget(self.export_btn)

        # Export PDF button (hidden in Education edition)
        self.export_pdf_btn = QPushButton(t("technical.export_pdf"))
        self.export_pdf_btn.setFixedHeight(34)
        self.export_pdf_btn.setCursor(Qt.PointingHandCursor)
        self.export_pdf_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #3B82F6;
                border: none; border-radius: 8px;
                padding: 6px 12px; font-size: 15px; font-weight: bold;
                color: white;
            }}
            QPushButton:hover {{
                background-color: #2563EB;
            }}
        """)
        self.export_pdf_btn.clicked.connect(lambda: self.export_pdf_requested.emit())
        if is_education():
            self.export_pdf_btn.hide()
        layout.addWidget(self.export_pdf_btn)

        layout.addSpacing(12)

        # Reset button
        self.reset_btn = QPushButton(t("technical.reset_workspace"))
        self.reset_btn.setFixedHeight(34)
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #B91C1C;
                border: none; border-radius: 8px;
                padding: 6px 12px; font-size: 15px; font-weight: bold;
                color: white;
            }}
            QPushButton:hover {{
                background-color: #991B1B;
            }}
        """)
        self.reset_btn.clicked.connect(lambda: self.reset_requested.emit())
        layout.addWidget(self.reset_btn)

        layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)
        self._update_texts()
        on_language_changed(self._update_texts)

    def _style_date_edit(self, de: QDateEdit):
        de.setStyleSheet(f"""
            QDateEdit {{
                background-color: {_FIELD_BG};
                border: 1px solid {_FIELD_BORDER};
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 15px;
                color: {_FIELD_TEXT};
            }}
            QDateEdit:focus {{
                border: 2px solid {default_theme.button_primary};
            }}
            QDateEdit::drop-down {{
                border: none;
                width: 20px;
            }}
        """)
        _apply_field_palette(de)

    def _update_texts(self):
        self.header.setText(t("technical.title"))
        self.property_label.setText(t("technical.property"))
        self.object_title_label.setText(t("technical.object_title"))
        self.manufacturer_label.setText(t("technical.manufacturer"))
        self.start_date_label.setText(t("technical.start_date"))
        self.deadline_label.setText(t("technical.deadline"))
        self.comments_label.setText(t("technical.comments"))
        self.upload_btn.setText(t("technical.upload_btn"))
        self.annotate_btn.setText(t("technical.annotate"))
        self.export_btn.setText(t("technical.export_ecto"))
        self.export_pdf_btn.setText(t("technical.export_pdf"))
        self.reset_btn.setText(t("technical.reset_workspace"))

    def _on_annotate_toggled(self):
        self._annotation_mode = self.annotate_btn.isChecked()
        self.annotate_toggled.emit(self._annotation_mode)

    def set_annotation_mode(self, enabled: bool):
        """Programmatically set annotation mode state."""
        self._annotation_mode = enabled
        self.annotate_btn.setChecked(enabled)

    def get_metadata(self) -> dict:
        """Return all metadata fields as a dict."""
        manufacturers = [e.text().strip() for e in self._manufacturer_edits if e.text().strip()]
        return {
            "property": self.property_edit.text().strip(),
            "title": self.title_edit.text().strip(),
            "manufacturers": manufacturers,
            "start_date": self.start_date.date().toString(Qt.ISODate),
            "deadline": self.deadline_date.date().toString(Qt.ISODate),
            "comments": self.comments_edit.toPlainText().strip(),
        }

    def reset(self):
        """Clear all fields."""
        self.property_edit.clear()
        self.title_edit.clear()
        # Remove extra manufacturer rows, keep first
        while len(self._manufacturer_edits) > 1:
            row = self._manufacturer_edits.pop()
            row.parent().deleteLater()
        if self._manufacturer_edits:
            self._manufacturer_edits[0].clear()
        self.start_date.setDate(QDate.currentDate())
        self.deadline_date.setDate(QDate.currentDate().addMonths(1))
        self.comments_edit.clear()
        self.set_annotation_mode(False)

    def set_metadata(self, meta: dict):
        """Populate sidebar fields from a metadata dict (e.g. from .ecto import)."""
        self.property_edit.setText(meta.get('property', ''))
        self.title_edit.setText(meta.get('title', ''))
        # Manufacturers
        manufacturers = meta.get('manufacturers', [])
        # Clear existing
        while len(self._manufacturer_edits) > 1:
            row = self._manufacturer_edits.pop()
            row.parent().deleteLater()
        if self._manufacturer_edits:
            self._manufacturer_edits[0].setText(manufacturers[0] if manufacturers else '')
        for m in manufacturers[1:]:
            self._add_manufacturer_field()
            self._manufacturer_edits[-1].setText(m)
        # Dates
        if meta.get('start_date'):
            d = QDate.fromString(meta['start_date'], Qt.ISODate)
            if d.isValid():
                self.start_date.setDate(d)
        if meta.get('deadline'):
            d = QDate.fromString(meta['deadline'], Qt.ISODate)
            if d.isValid():
                self.deadline_date.setDate(d)
        self.comments_edit.setPlainText(meta.get('comments', ''))

    def _create_manufacturer_row(self, placeholder: str, removable: bool = True):
        """Create a manufacturer input row, optionally with a remove button."""
        if not removable:
            le = _line_edit(placeholder)
            self._manufacturer_edits.append(le)
            return le
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        le = _line_edit(placeholder)
        self._manufacturer_edits.append(le)
        rl.addWidget(le)
        rm_btn = QPushButton("✕")
        rm_btn.setFixedSize(26, 26)
        rm_btn.setCursor(Qt.PointingHandCursor)
        rm_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A1518; border: none; border-radius: 13px;
                color: #F87171; font-size: 14px; font-weight: bold;
                padding: 0; min-width: 26px; min-height: 26px;
            }
            QPushButton:hover { background-color: #351E22; }
        """)
        rm_btn.clicked.connect(lambda: self._remove_manufacturer_row(row, le))
        rl.addWidget(rm_btn)
        return row

    def _add_manufacturer_field(self):
        """Add another manufacturer input row."""
        row = self._create_manufacturer_row("e.g. Another manufacturer")
        self._manufacturer_container.addWidget(row)

    def _remove_manufacturer_row(self, row_widget, line_edit):
        """Remove a manufacturer row."""
        if line_edit in self._manufacturer_edits:
            self._manufacturer_edits.remove(line_edit)
        row_widget.deleteLater()
