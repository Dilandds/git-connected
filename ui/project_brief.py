"""
Project Brief screen — light-themed content area inside the dark ECTOFORM shell.
"""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QScrollArea, QFrame, QGridLayout,
    QDateEdit, QFileDialog, QSizePolicy
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QPixmap, QColor, QPainter
from ui.styles import default_theme, make_font, dropdown_arrow_url as _get_arrow
_ARROW_URL = _get_arrow()

logger = logging.getLogger(__name__)

# Light theme for the content area
_BG        = '#f8f9fa'
_CARD      = '#ffffff'
_CARD2     = '#f1f3f5'
_BORDER    = '#e5e7eb'
_BORDER_L  = '#d1d5db'
_TEXT      = '#1e2430'
_MUTED     = '#6b7280'
_ACCENT    = default_theme.button_primary      # '#2596BE' — keep brand blue
_ACCENT_H  = default_theme.button_primary_hover
_INPUT_BG  = '#f5f6f8'

_SECTION_HEADER_STYLE = f"""
    QLabel {{
        color: {_ACCENT};
        font-size: 11px;
        font-weight: bold;
        letter-spacing: 1px;
        background: transparent;
        border: none;
        padding: 0;
    }}
"""

_CARD_STYLE = f"""
    QFrame {{
        background-color: {_CARD};
        border: 1px solid {_BORDER};
        border-radius: 10px;
    }}
"""

_INPUT_STYLE = f"""
    QLineEdit, QTextEdit {{
        background-color: {_INPUT_BG};
        color: {_TEXT};
        border: 1px solid {_BORDER};
        border-radius: 5px;
        padding: 5px 8px;
        font-size: 11px;
    }}
    QLineEdit:focus, QTextEdit:focus {{
        border: 1px solid {_ACCENT};
    }}
    QLineEdit:disabled, QTextEdit:disabled {{
        color: {_MUTED};
        background-color: {_CARD};
    }}
"""

_DATE_STYLE = f"""
    QDateEdit {{
        background-color: {_INPUT_BG};
        color: {_TEXT};
        border: 1px solid {_BORDER};
        border-radius: 5px;
        padding: 4px 8px;
        font-size: 11px;
    }}
    QDateEdit:focus {{ border: 1px solid {_ACCENT}; }}
    QDateEdit:disabled {{ color: {_MUTED}; background-color: {_CARD}; }}
    QDateEdit::drop-down {{
        border: none;
        width: 20px;
    }}
    QDateEdit::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
"""

_BTN_PRIMARY = f"""
    QPushButton {{
        background-color: {_ACCENT};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 6px 16px;
        font-size: 11px;
        font-weight: bold;
    }}
    QPushButton:hover {{ background-color: {_ACCENT_H}; }}
    QPushButton:pressed {{ background-color: {default_theme.button_primary_pressed}; }}
"""

_BTN_SECONDARY = f"""
    QPushButton {{
        background-color: {_CARD2};
        color: {_TEXT};
        border: 1px solid {_BORDER_L};
        border-radius: 6px;
        padding: 6px 16px;
        font-size: 11px;
    }}
    QPushButton:hover {{
        background-color: {_BORDER_L};
        border-color: {_ACCENT};
        color: {_ACCENT};
    }}
"""

_ADD_BTN_STYLE = f"""
    QPushButton {{
        background-color: transparent;
        color: {_ACCENT};
        border: none;
        font-size: 11px;
        font-weight: bold;
        padding: 2px 0;
        text-align: left;
    }}
    QPushButton:hover {{ color: {_ACCENT_H}; }}
"""

_LABEL_STYLE = f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;"
_VALUE_STYLE = f"color: {_TEXT}; font-size: 11px; background: transparent; border: none;"


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(_SECTION_HEADER_STYLE)
    return lbl


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(_LABEL_STYLE)
    lbl.setFixedWidth(160)
    return lbl


def _card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setStyleSheet(_CARD_STYLE)
    return f


def _input(placeholder: str = "", min_height: int = 28) -> QLineEdit:
    w = QLineEdit()
    w.setPlaceholderText(placeholder)
    w.setMinimumHeight(min_height)
    w.setStyleSheet(_INPUT_STYLE)
    return w


def _textarea(placeholder: str = "", min_height: int = 70) -> QTextEdit:
    w = QTextEdit()
    w.setPlaceholderText(placeholder)
    w.setMinimumHeight(min_height)
    w.setStyleSheet(_INPUT_STYLE)
    return w


def _date_edit() -> QDateEdit:
    w = QDateEdit()
    w.setDisplayFormat("dd/MM/yyyy")
    w.setCalendarPopup(True)
    w.setDate(QDate.currentDate())
    w.setStyleSheet(_DATE_STYLE)
    w.setMinimumHeight(28)
    return w


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet(f"color: {_BORDER}; background-color: {_BORDER}; border: none; max-height: 1px;")
    return sep


class _BulletListWidget(QWidget):
    """A dynamic list of single-line text inputs with bullet points and an Add button."""

    def __init__(self, placeholder: str = "...", initial_count: int = 4, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._inputs = []
        self._add_btn = QPushButton("+ Add")
        self._add_btn.setStyleSheet(_ADD_BTN_STYLE)
        self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.clicked.connect(self._add_row)
        for _ in range(initial_count):
            self._add_row()
        self._layout.addWidget(self._add_btn, alignment=Qt.AlignLeft)

    def _add_row(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        bullet = QLabel("•")
        bullet.setStyleSheet(f"color: {_ACCENT}; font-size: 13px; background: transparent; border: none;")
        bullet.setFixedWidth(12)
        inp = _input("...")
        inp.setMinimumHeight(26)
        self._inputs.append(inp)
        row.addWidget(bullet)
        row.addWidget(inp)
        # Insert before the Add button
        self._layout.insertLayout(self._layout.count() - 1, row)

    def get_values(self):
        return [i.text() for i in self._inputs]

    def set_values(self, values):
        while len(self._inputs) < len(values):
            self._add_row()
        for i, v in enumerate(values):
            self._inputs[i].setText(v)

    def set_read_only(self, ro: bool):
        self._add_btn.setVisible(not ro)
        for inp in self._inputs:
            inp.setReadOnly(ro)


class _ComponentsTable(QWidget):
    """Editable table for Components, Materials & Colors."""

    HEADERS = ["Component", "Material", "Colour"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(4)
        self._rows = []

        # Header row
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        for h in self.HEADERS:
            lbl = QLabel(h)
            lbl.setStyleSheet(f"color: {_ACCENT}; font-size: 10px; font-weight: bold; background: transparent; border: none;")
            hdr.addWidget(lbl, 1)
        self._outer.addLayout(hdr)
        self._outer.addWidget(_separator())

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(4)
        self._outer.addLayout(self._rows_layout)

        # Add 5 default rows
        for i in range(5):
            self._add_row(f"Component {i + 1}")

        # Add button
        add_btn = QPushButton("+ Add a component")
        add_btn.setStyleSheet(_ADD_BTN_STYLE)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_row)
        self._outer.addWidget(add_btn, alignment=Qt.AlignLeft)

    def _add_row(self, default_name: str = ""):
        row_w = QWidget()
        row_w.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row_w)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        num = QLabel(str(len(self._rows) + 1))
        num.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
        num.setFixedWidth(16)

        inputs = []
        for j, placeholder in enumerate(["Component name", "Material", "Colour"]):
            inp = _input(placeholder)
            inp.setMinimumHeight(26)
            if j == 0 and default_name:
                inp.setPlaceholderText(default_name)
            inputs.append(inp)
            row_layout.addWidget(inp, 1)

        row_layout.insertWidget(0, num)
        self._rows.append(inputs)
        self._rows_layout.addWidget(row_w)

    def set_read_only(self, ro: bool):
        for row in self._rows:
            for inp in row:
                inp.setReadOnly(ro)


class ProjectBriefWidget(QWidget):
    """Full Project Brief screen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edit_mode = False
        self.setStyleSheet(f"background-color: {_BG};")
        self._build_ui()
        self._set_edit_mode(False)

    # ── build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── top bar ──
        top_bar = QWidget()
        top_bar.setStyleSheet(f"background-color: {_BG}; border-bottom: 1px solid {_BORDER};")
        top_bar.setFixedHeight(52)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(24, 0, 24, 0)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        page_title = QLabel("Project Brief")
        page_title.setFont(make_font(size=15, bold=True))
        page_title.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        subtitle = QLabel("Define the essential information and objectives of the project.")
        subtitle.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
        title_col.addWidget(page_title)
        title_col.addWidget(subtitle)
        top_layout.addLayout(title_col)
        top_layout.addStretch()

        self._edit_btn = QPushButton("✎  Edit Brief")
        self._edit_btn.setStyleSheet(_BTN_SECONDARY)
        self._edit_btn.setFixedHeight(32)
        self._edit_btn.setCursor(Qt.PointingHandCursor)
        self._edit_btn.clicked.connect(self._toggle_edit)
        top_layout.addWidget(self._edit_btn)

        root.addWidget(top_bar)

        # ── scrollable body ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background-color: {_BG}; border: none; }}
            QScrollBar:vertical {{
                background: {_BG}; width: 6px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {_BORDER_L}; border-radius: 3px;
            }}
        """)

        body = QWidget()
        body.setStyleSheet(f"background-color: {_BG};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 24)
        body_layout.setSpacing(16)

        # Row 1: Product Overview + Techniques
        row1 = QHBoxLayout()
        row1.setSpacing(16)
        row1.addWidget(self._build_product_overview(), 2)
        row1.addWidget(self._build_techniques(), 3)
        body_layout.addLayout(row1)

        # Row 2: Target Points + Target Dates + Inspiration
        row2 = QHBoxLayout()
        row2.setSpacing(16)
        row2.addWidget(self._build_target_points(), 2)
        row2.addWidget(self._build_target_dates(), 2)
        row2.addWidget(self._build_inspiration(), 3)
        body_layout.addLayout(row2)

        # Row 3: Components + Notes
        row3 = QHBoxLayout()
        row3.setSpacing(16)
        row3.addWidget(self._build_components(), 3)
        row3.addWidget(self._build_notes(), 2)
        body_layout.addLayout(row3)

        # Footer
        body_layout.addWidget(self._build_footer())
        body_layout.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll)

    # ── sections ───────────────────────────────────────────────────────────

    def _build_product_overview(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_label("1. Product Overview"))
        layout.addWidget(_separator())

        # Image placeholder
        self._product_image_label = QLabel()
        self._product_image_label.setFixedHeight(110)
        self._product_image_label.setAlignment(Qt.AlignCenter)
        self._product_image_label.setStyleSheet(f"""
            background-color: {_INPUT_BG};
            border: 1px dashed {_BORDER_L};
            border-radius: 6px;
            color: {_MUTED};
            font-size: 10px;
        """)
        self._product_image_label.setText("No image")

        self._upload_img_btn = QPushButton("+ Upload image")
        self._upload_img_btn.setStyleSheet(_ADD_BTN_STYLE)
        self._upload_img_btn.setCursor(Qt.PointingHandCursor)
        self._upload_img_btn.clicked.connect(self._upload_product_image)

        layout.addWidget(self._product_image_label)
        layout.addWidget(self._upload_img_btn, alignment=Qt.AlignLeft)
        layout.addWidget(_separator())

        fields = [
            ("Product name",    "_f_product_name"),
            ("Reference / Version", "_f_reference"),
            ("Short description", "_f_description"),
            ("Intended use",    "_f_intended_use"),
            ("Image / Visual (links)", "_f_visual_links"),
        ]
        for label, attr in fields:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(_field_label(label))
            inp = _input(label)
            setattr(self, attr, inp)
            row.addWidget(inp)
            layout.addLayout(row)

        return card

    def _build_techniques(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_label("2. Planned Techniques / Watch Points"))
        layout.addWidget(_separator())

        cols = QHBoxLayout()
        cols.setSpacing(16)

        # Techniques
        left = QVBoxLayout()
        left.setSpacing(6)
        tech_lbl = QLabel("Techniques Considered")
        tech_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        tech_hint = QLabel("List manufacturing techniques\nor approaches considered.")
        tech_hint.setStyleSheet(f"color: {_MUTED}; font-size: 9px; background: transparent; border: none;")
        tech_hint.setWordWrap(True)
        self._techniques_list = _BulletListWidget("...", 4)
        left.addWidget(tech_lbl)
        left.addWidget(self._techniques_list)
        left.addWidget(tech_hint)
        left.addStretch()

        # Watch points
        right = QVBoxLayout()
        right.setSpacing(6)
        watch_lbl = QLabel("Watch Points")
        watch_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        watch_hint = QLabel("Identify critical points, risks\nand constraints to monitor.")
        watch_hint.setStyleSheet(f"color: {_MUTED}; font-size: 9px; background: transparent; border: none;")
        watch_hint.setWordWrap(True)
        self._watchpoints_list = _BulletListWidget("...", 4)
        right.addWidget(watch_lbl)
        right.addWidget(self._watchpoints_list)
        right.addWidget(watch_hint)
        right.addStretch()

        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        layout.addLayout(cols)
        return card

    def _build_target_points(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_label("3. Target Points"))
        layout.addWidget(_separator())

        hint = QLabel("Preliminary indications — to be refined as the project progresses.")
        hint.setStyleSheet(f"color: {_MUTED}; font-size: 9px; background: transparent; border: none;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        fields = [
            ("Dimensions",          "_f_dimensions",   ""),
            ("Target weight",       "_f_weight",       "g"),
            ("Target total cost",   "_f_cost",         "€"),
            ("Other constraints",   "_f_constraints",  ""),
        ]
        for label, attr, unit in fields:
            row = QHBoxLayout()
            row.setSpacing(6)
            lbl = QLabel(label)
            lbl.setStyleSheet(_LABEL_STYLE)
            row.addWidget(lbl, 1)
            inp = _input("")
            inp.setMinimumHeight(26)
            setattr(self, attr, inp)
            row.addWidget(inp, 2)
            if unit:
                u = QLabel(unit)
                u.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
                u.setFixedWidth(14)
                row.addWidget(u)
            layout.addLayout(row)

        layout.addStretch()
        return card

    def _build_target_dates(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_label("4. Target Dates"))
        layout.addWidget(_separator())

        date_fields = [
            ("Expected delivery date",        "_d_delivery"),
            ("Expected mockup / prototype",   "_d_prototype"),
            ("Expected production start",     "_d_production"),
        ]
        for label, attr in date_fields:
            row = QHBoxLayout()
            row.setSpacing(6)
            lbl = QLabel(label)
            lbl.setStyleSheet(_LABEL_STYLE)
            lbl.setWordWrap(True)
            row.addWidget(lbl, 2)
            d = _date_edit()
            setattr(self, attr, d)
            row.addWidget(d, 2)
            layout.addLayout(row)

        layout.addWidget(_separator())
        notes_lbl = QLabel("Notes")
        notes_lbl.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(notes_lbl)
        self._f_date_notes = _textarea("Notes and additional details...", 60)
        layout.addWidget(self._f_date_notes)
        layout.addStretch()
        return card

    def _build_inspiration(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_label("5. Inspiration / Idea / Direction"))
        layout.addWidget(_separator())
        hint = QLabel("References, ideas, visual atmosphere, design direction.")
        hint.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._f_inspiration = _textarea(
            "Describe the main idea, the inspiration and the design direction...",
            min_height=120
        )
        layout.addWidget(self._f_inspiration)
        layout.addStretch()
        return card

    def _build_components(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_label("6. Components, Materials & Colours"))
        layout.addWidget(_separator())
        self._components_table = _ComponentsTable()
        layout.addWidget(self._components_table)
        layout.addStretch()
        return card

    def _build_notes(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_label("7. Notes"))
        layout.addWidget(_separator())
        hint = QLabel("Any additional information, remarks, ideas...")
        hint.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._f_notes = _textarea("Additional notes...", min_height=120)
        layout.addWidget(self._f_notes)
        layout.addStretch()
        return card

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 8, 0, 0)
        from datetime import date
        today = date.today().strftime("%d %B %Y")
        gen_lbl = QLabel(f"Document generated on {today}")
        gen_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 9px; background: transparent; border: none;")
        ver_lbl = QLabel("ECTOFORM v1.2.0")
        ver_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 9px; background: transparent; border: none;")
        layout.addWidget(gen_lbl)
        layout.addStretch()
        layout.addWidget(ver_lbl)
        return w

    # ── logic ──────────────────────────────────────────────────────────────

    def _toggle_edit(self):
        self._set_edit_mode(not self._edit_mode)

    def _set_edit_mode(self, enabled: bool):
        self._edit_mode = enabled
        ro = not enabled
        self._edit_btn.setText("✔  Save Brief" if enabled else "✎  Edit Brief")
        self._edit_btn.setStyleSheet(_BTN_PRIMARY if enabled else _BTN_SECONDARY)
        self._upload_img_btn.setVisible(enabled)

        # All text inputs
        for attr in ("_f_product_name", "_f_reference", "_f_description",
                     "_f_intended_use", "_f_visual_links", "_f_dimensions",
                     "_f_weight", "_f_cost", "_f_constraints",
                     "_f_date_notes", "_f_inspiration", "_f_notes"):
            w = getattr(self, attr, None)
            if w:
                w.setReadOnly(ro)

        # Date edits
        for attr in ("_d_delivery", "_d_prototype", "_d_production"):
            w = getattr(self, attr, None)
            if w:
                w.setEnabled(enabled)

        # Bullet lists
        self._techniques_list.set_read_only(ro)
        self._watchpoints_list.set_read_only(ro)

        # Components table
        self._components_table.set_read_only(ro)

    # ── serialisation ──────────────────────────────────────────────────────

    def get_data(self) -> dict:
        """Return all brief fields as a plain dict for saving."""
        return {
            "product_name":    self._f_product_name.text(),
            "reference":       self._f_reference.text(),
            "description":     self._f_description.text(),
            "intended_use":    self._f_intended_use.text(),
            "visual_links":    self._f_visual_links.text(),
            "dimensions":      self._f_dimensions.text(),
            "weight":          self._f_weight.text(),
            "cost":            self._f_cost.text(),
            "constraints":     self._f_constraints.text(),
            "date_notes":      self._f_date_notes.toPlainText(),
            "inspiration":     self._f_inspiration.toPlainText(),
            "notes":           self._f_notes.toPlainText(),
            "delivery_date":   self._d_delivery.date().toString("dd/MM/yyyy"),
            "prototype_date":  self._d_prototype.date().toString("dd/MM/yyyy"),
            "production_date": self._d_production.date().toString("dd/MM/yyyy"),
            "techniques":      self._techniques_list.get_values(),
            "watchpoints":     self._watchpoints_list.get_values(),
            "components": [
                [inp.text() for inp in row]
                for row in self._components_table._rows
            ],
        }

    def set_data(self, data: dict):
        """Populate all brief fields from a saved dict."""
        from PyQt5.QtCore import QDate
        self._f_product_name.setText(data.get("product_name", ""))
        self._f_reference.setText(data.get("reference", ""))
        self._f_description.setText(data.get("description", ""))
        self._f_intended_use.setText(data.get("intended_use", ""))
        self._f_visual_links.setText(data.get("visual_links", ""))
        self._f_dimensions.setText(data.get("dimensions", ""))
        self._f_weight.setText(data.get("weight", ""))
        self._f_cost.setText(data.get("cost", ""))
        self._f_constraints.setText(data.get("constraints", ""))
        self._f_date_notes.setPlainText(data.get("date_notes", ""))
        self._f_inspiration.setPlainText(data.get("inspiration", ""))
        self._f_notes.setPlainText(data.get("notes", ""))
        for attr, key in [
            ("_d_delivery", "delivery_date"),
            ("_d_prototype", "prototype_date"),
            ("_d_production", "production_date"),
        ]:
            val = data.get(key, "")
            if val:
                d = QDate.fromString(val, "dd/MM/yyyy")
                if d.isValid():
                    getattr(self, attr).setDate(d)
        if data.get("techniques"):
            self._techniques_list.set_values(data["techniques"])
        if data.get("watchpoints"):
            self._watchpoints_list.set_values(data["watchpoints"])

    def _upload_product_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Product Image", "",
            "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            pix = QPixmap(path)
            if not pix.isNull():
                pix = pix.scaled(
                    self._product_image_label.width(),
                    self._product_image_label.height(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self._product_image_label.setPixmap(pix)
                self._product_image_label.setText("")
