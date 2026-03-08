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
from ui.styles import default_theme

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
        hfont = QFont()
        hfont.setBold(True)
        hfont.setPointSize(13)
        header.setFont(hfont)
        header.setStyleSheet(f"color: {default_theme.text_title};")
        layout.addWidget(header)

        # Upload button
        self.upload_btn = QPushButton("📄 Upload Image / PDF")
        self.upload_btn.setFixedHeight(34)
        self.upload_btn.setCursor(Qt.PointingHandCursor)
        self.upload_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.button_primary};
                border: none; border-radius: 6px;
                padding: 6px 12px; font-size: 11px; font-weight: bold;
                color: white;
            }}
            QPushButton:hover {{
                background-color: {default_theme.button_primary_hover};
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
        self.property_edit = _line_edit("e.g. Building A, Floor 3")
        layout.addWidget(self.property_edit)

        # Title
        layout.addWidget(_section_label("OBJECT TITLE"))
        self.title_edit = _line_edit("e.g. HVAC Unit #12")
        layout.addWidget(self.title_edit)

        # Manufacturer
        layout.addWidget(_section_label("MANUFACTURER"))
        self.manufacturer_edit = _line_edit("e.g. Carrier, Daikin")
        layout.addWidget(self.manufacturer_edit)

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
        return {
            "property": self.property_edit.text().strip(),
            "title": self.title_edit.text().strip(),
            "manufacturer": self.manufacturer_edit.text().strip(),
            "start_date": self.start_date.date().toString(Qt.ISODate),
            "deadline": self.deadline_date.date().toString(Qt.ISODate),
            "comments": self.comments_edit.toPlainText().strip(),
        }

    def reset(self):
        """Clear all fields."""
        self.property_edit.clear()
        self.title_edit.clear()
        self.manufacturer_edit.clear()
        self.start_date.setDate(QDate.currentDate())
        self.deadline_date.setDate(QDate.currentDate().addMonths(1))
        self.comments_edit.clear()
        self.set_annotation_mode(False)
