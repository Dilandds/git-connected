"""
Technical Overview Sidebar — metadata fields for the technical document.
Fields: Property, Title, Manufacturer, Start Date, Deadline, Comments.
"""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QTextEdit,
    QDateEdit, QFrame, QSizePolicy, QScrollArea, QPushButton, QHBoxLayout
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal
from PyQt5.QtGui import QFont
from ui.styles import default_theme, make_font

logger = logging.getLogger(__name__)


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 10px; font-weight: bold; margin-top: 6px;")
    return lbl


def _line_edit(placeholder: str = "") -> QLineEdit:
    le = QLineEdit()
    le.setPlaceholderText(placeholder)
    le.setFixedHeight(30)
    le.setStyleSheet(f"""
        QLineEdit {{
            background-color: {default_theme.input_bg};
            border: 1px solid {default_theme.input_border};
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 11px;
            color: {default_theme.text_primary};
        }}
        QLineEdit:focus {{
            border: 2px solid {default_theme.button_primary};
        }}
    """)
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
        self.setFixedWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Title header
        header = QLabel("Technical Overview")
        hfont = make_font(size=13, bold=True)
        header.setFont(hfont)
        header.setStyleSheet(f"color: {default_theme.text_title};")
        layout.addWidget(header)

        # Upload button
        self.upload_btn = QPushButton("📄 Upload Image / PDF / .ecto")
        self.upload_btn.setFixedHeight(34)
        self.upload_btn.setCursor(Qt.PointingHandCursor)
        self.upload_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
                padding: 6px 12px; font-size: 11px; font-weight: bold;
                color: {default_theme.text_primary};
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """)
        self.upload_btn.clicked.connect(lambda: self.upload_requested.emit())
        layout.addWidget(self.upload_btn)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {default_theme.separator};")
        layout.addWidget(sep)

        # Property
        layout.addWidget(_section_label("PROPERTY"))
        self.property_edit = _line_edit("e.g. Company")
        layout.addWidget(self.property_edit)

        # Title
        layout.addWidget(_section_label("OBJECT TITLE"))
        self.title_edit = _line_edit("e.g. HVAC Unit #12")
        layout.addWidget(self.title_edit)

        # Manufacturer(s)
        mfr_header = QHBoxLayout()
        mfr_header.addWidget(_section_label("MANUFACTURER"))
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
        """)
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
        layout.addWidget(_section_label("START DATE"))
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate())
        self.start_date.setFixedHeight(30)
        self._style_date_edit(self.start_date)
        layout.addWidget(self.start_date)

        layout.addWidget(_section_label("DEADLINE"))
        self.deadline_date = QDateEdit()
        self.deadline_date.setCalendarPopup(True)
        self.deadline_date.setDate(QDate.currentDate().addMonths(1))
        self.deadline_date.setFixedHeight(30)
        self._style_date_edit(self.deadline_date)
        layout.addWidget(self.deadline_date)

        # Comments
        layout.addWidget(_section_label("COMMENTS"))
        self.comments_edit = QTextEdit()
        self.comments_edit.setPlaceholderText("Add notes, observations, or instructions…")
        self.comments_edit.setMinimumHeight(120)
        self.comments_edit.setMaximumHeight(250)
        self.comments_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {default_theme.input_bg};
                border: 1px solid {default_theme.input_border};
                border-radius: 6px;
                padding: 8px;
                font-size: 11px;
                color: {default_theme.text_primary};
            }}
            QTextEdit:focus {{
                border: 2px solid {default_theme.button_primary};
            }}
        """)
        layout.addWidget(self.comments_edit)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"color: {default_theme.separator};")
        layout.addWidget(sep2)

        # Annotate toggle button
        self.annotate_btn = QPushButton("📌 Annotate")
        self.annotate_btn.setFixedHeight(34)
        self.annotate_btn.setCursor(Qt.PointingHandCursor)
        self.annotate_btn.setCheckable(True)
        self._annotation_mode = False
        self.annotate_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
                padding: 6px 12px; font-size: 11px;
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
        self.export_btn = QPushButton("📦 Export .ecto")
        self.export_btn.setFixedHeight(34)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #10B981;
                border: none; border-radius: 6px;
                padding: 6px 12px; font-size: 11px; font-weight: bold;
                color: white;
            }}
            QPushButton:hover {{
                background-color: #059669;
            }}
        """)
        self.export_btn.clicked.connect(lambda: self.export_requested.emit())
        layout.addWidget(self.export_btn)

        # Export PDF button
        self.export_pdf_btn = QPushButton("📄 Export PDF Report")
        self.export_pdf_btn.setFixedHeight(34)
        self.export_pdf_btn.setCursor(Qt.PointingHandCursor)
        self.export_pdf_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #3B82F6;
                border: none; border-radius: 6px;
                padding: 6px 12px; font-size: 11px; font-weight: bold;
                color: white;
            }}
            QPushButton:hover {{
                background-color: #2563EB;
            }}
        """)
        self.export_pdf_btn.clicked.connect(lambda: self.export_pdf_requested.emit())
        layout.addWidget(self.export_pdf_btn)

        layout.addSpacing(12)

        # Reset button
        self.reset_btn = QPushButton("🔄 Reset Workspace")
        self.reset_btn.setFixedHeight(34)
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #B91C1C;
                border: none; border-radius: 6px;
                padding: 6px 12px; font-size: 11px; font-weight: bold;
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

    def _style_date_edit(self, de: QDateEdit):
        de.setStyleSheet(f"""
            QDateEdit {{
                background-color: {default_theme.input_bg};
                border: 1px solid {default_theme.input_border};
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                color: {default_theme.text_primary};
            }}
            QDateEdit:focus {{
                border: 2px solid {default_theme.button_primary};
            }}
            QDateEdit::drop-down {{
                border: none;
                width: 20px;
            }}
        """)

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
