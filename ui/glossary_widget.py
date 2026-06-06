"""
Glossary screen — alphabetical term/definition list with search, add, edit, delete.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QTextEdit, QSizePolicy, QDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal
from ui.styles import default_theme, make_font, TOOLTIP_STYLE
from ui.modal_utils import FormModal

logger = logging.getLogger(__name__)

# ── palette ───────────────────────────────────────────────────────────────────
_BG     = '#f8f9fa'
_CARD   = '#ffffff'
_BORDER = '#e5e7eb'
_TEXT   = '#1e2430'
_MUTED  = '#6b7280'
_ACCENT = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover

# ── styles ────────────────────────────────────────────────────────────────────
_INPUT = f"""
    QLineEdit, QTextEdit {{
        background-color: #f5f6f8; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 4px 8px; font-size: 11px;
    }}
    QLineEdit:focus, QTextEdit:focus {{ border-color: {_ACCENT}; }}
"""
_BTN_PRIMARY = f"""
    QPushButton {{
        background: {_ACCENT}; color: white; border: none;
        border-radius: 5px; padding: 5px 14px; font-size: 11px; font-weight: bold;
    }}
    QPushButton:hover {{ background: {_ACCENT_H}; }}
"""
_BTN_ICON = f"""
    QPushButton {{
        background: transparent; border: none;
        color: {_MUTED}; font-size: 13px; padding: 2px 6px;
    }}
    QPushButton:hover {{ color: {_ACCENT}; background: #e8f0fe; border-radius: 4px; }}
""" + TOOLTIP_STYLE
_BTN_DELETE = f"""
    QPushButton {{
        background: transparent; border: none;
        color: {_MUTED}; font-size: 13px; padding: 2px 6px;
    }}
    QPushButton:hover {{ color: #ef4444; background: #fee2e2; border-radius: 4px; }}
""" + TOOLTIP_STYLE


# ── data model ────────────────────────────────────────────────────────────────

@dataclass
class GlossaryTerm:
    id:         int
    term:       str = ""
    definition: str = ""


# ── Edit dialog ───────────────────────────────────────────────────────────────

class _TermDialog(FormModal):
    """Add / Edit a glossary term."""

    def __init__(self, term: Optional[GlossaryTerm] = None, parent=None):
        super().__init__(parent, "Edit Term" if term else "Add Term",
                         min_width=420)

        self.f_term = self.add_field("TERM", QLineEdit(term.term if term else ""), height=30)
        self.f_term.setPlaceholderText("e.g. CAD")

        self.f_def = self.add_field("DEFINITION", QTextEdit(), height_override=100)
        self.f_def.setPlaceholderText("Enter definition here...")
        if term:
            self.f_def.setPlainText(term.definition)

        self.finish()

    def get_data(self):
        return {
            "term":       self.f_term.text().strip(),
            "definition": self.f_def.toPlainText().strip(),
        }


# ── Term row widget ───────────────────────────────────────────────────────────

class _TermRow(QFrame):
    """Single row: term | definition | edit | delete."""

    edit_requested   = pyqtSignal(object)   # emits GlossaryTerm
    delete_requested = pyqtSignal(object)

    def __init__(self, term: GlossaryTerm, parent=None):
        super().__init__(parent)
        self._term = term
        self.setStyleSheet(f"""
            QFrame {{
                background: {_CARD};
                border: none;
                border-bottom: 1px solid {_BORDER};
            }}
        """)
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 10, 10)
        lay.setSpacing(12)

        # Term (bold, fixed width)
        self._term_lbl = QLabel(self._term.term)
        self._term_lbl.setFixedWidth(160)
        self._term_lbl.setWordWrap(True)
        self._term_lbl.setStyleSheet(
            f"color: {_TEXT}; font-size: 11px; font-weight: bold; background: transparent; border: none;"
        )
        lay.addWidget(self._term_lbl)

        # Divider
        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        vline.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-width: 1px; border: none;")
        lay.addWidget(vline)

        # Definition
        self._def_lbl = QLabel(self._term.definition)
        self._def_lbl.setWordWrap(True)
        self._def_lbl.setStyleSheet(
            f"color: {_MUTED}; font-size: 11px; background: transparent; border: none;"
        )
        self._def_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(self._def_lbl, 1)

        # Action buttons
        edit_btn = QPushButton("✎")
        edit_btn.setToolTip("Edit term")
        edit_btn.setFixedSize(28, 28)
        edit_btn.setStyleSheet(_BTN_ICON)
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._term))

        del_btn = QPushButton("🗑")
        del_btn.setToolTip("Delete term")
        del_btn.setFixedSize(28, 28)
        del_btn.setStyleSheet(_BTN_DELETE)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._term))

        lay.addWidget(edit_btn)
        lay.addWidget(del_btn)

    def refresh(self):
        self._term_lbl.setText(self._term.term)
        self._def_lbl.setText(self._term.definition)


# ── Alpha section header ──────────────────────────────────────────────────────

class _AlphaHeader(QWidget):
    """Sticky letter divider — A, B, C…"""

    def __init__(self, letter: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setStyleSheet(f"background: #f1f3f5;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lbl = QLabel(letter)
        lbl.setStyleSheet(
            f"color: {_ACCENT}; font-size: 12px; font-weight: bold; background: transparent; border: none;"
        )
        lay.addWidget(lbl)
        lay.addStretch()


# ── Main widget ───────────────────────────────────────────────────────────────

class GlossaryWidget(QWidget):
    """Full Glossary screen."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._terms: List[GlossaryTerm] = []
        self._next_id = 1
        self._filter = ""
        self.setStyleSheet(f"background: {_BG};")
        self._build_ui()
        self._refresh()

    # ── build ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        top = QWidget()
        top.setFixedHeight(56)
        top.setStyleSheet(f"background: {_BG}; border-bottom: 1px solid {_BORDER};")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 0, 16, 0)
        tl.setSpacing(10)

        t_col = QVBoxLayout()
        t_col.setSpacing(1)
        title = QLabel("Glossary")
        title.setFont(make_font(size=15, bold=True))
        title.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        subtitle = QLabel("Project-specific terms and definitions.")
        subtitle.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
        t_col.addWidget(title)
        t_col.addWidget(subtitle)
        tl.addLayout(t_col)
        tl.addStretch()

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search terms…")
        self._search.setFixedWidth(220)
        self._search.setFixedHeight(30)
        self._search.setStyleSheet(_INPUT)
        self._search.textChanged.connect(self._on_search)
        tl.addWidget(self._search)

        # Add term button
        add_btn = QPushButton("＋  Add term")
        add_btn.setStyleSheet(_BTN_PRIMARY)
        add_btn.setFixedHeight(30)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_term)
        tl.addWidget(add_btn)

        root.addWidget(top)

        # Column headers
        col_hdr = QWidget()
        col_hdr.setFixedHeight(28)
        col_hdr.setStyleSheet(f"background: #f1f3f5; border-bottom: 1px solid {_BORDER};")
        cl = QHBoxLayout(col_hdr)
        cl.setContentsMargins(16, 0, 10, 0)
        cl.setSpacing(12)

        def _hdr_lbl(text, w=None):
            l = QLabel(text)
            l.setStyleSheet(
                f"color: {_MUTED}; font-size: 9px; font-weight: bold; background: transparent; border: none;"
            )
            if w:
                l.setFixedWidth(w)
            return l

        cl.addWidget(_hdr_lbl("TERM", 160))
        cl.addWidget(_hdr_lbl("DEFINITION"))
        cl.addStretch()
        root.addWidget(col_hdr)

        # Scrollable list
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: {_BG}; border: none; }}
            QScrollBar:vertical {{ background: {_BG}; width: 8px; border-radius: 4px; }}
            QScrollBar::handle:vertical {{ background: {_BORDER}; border-radius: 4px; min-height: 30px; }}
        """)
        self._list_container = QWidget()
        self._list_container.setStyleSheet(f"background: {_BG};")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()
        self._scroll.setWidget(self._list_container)
        root.addWidget(self._scroll, 1)

    # ── rendering ──────────────────────────────────────────────────────────────

    def _refresh(self):
        """Rebuild the visible list from self._terms + current filter."""
        # Clear existing rows (everything except the trailing stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        query = self._filter.lower()
        filtered = [
            t for t in sorted(self._terms, key=lambda x: x.term.upper())
            if not query or query in t.term.lower() or query in t.definition.lower()
        ]

        if not filtered:
            empty = QLabel("No terms found. Click ＋ Add term to get started." if not query
                           else f'No results for "{self._filter}".')
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color: {_MUTED}; font-size: 12px; background: transparent; border: none;")
            empty.setContentsMargins(0, 40, 0, 0)
            self._list_layout.insertWidget(0, empty)
            return

        current_letter = ""
        insert_pos = 0
        for term in filtered:
            letter = term.term[0].upper() if term.term else "#"
            if letter != current_letter:
                current_letter = letter
                hdr = _AlphaHeader(letter)
                self._list_layout.insertWidget(insert_pos, hdr)
                insert_pos += 1

            row = _TermRow(term)
            row.edit_requested.connect(self._edit_term)
            row.delete_requested.connect(self._delete_term)
            self._list_layout.insertWidget(insert_pos, row)
            insert_pos += 1

    # ── CRUD ───────────────────────────────────────────────────────────────────

    def _add_term(self):
        dlg = _TermDialog(parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        d = dlg.get_data()
        if not d["term"]:
            return
        term = GlossaryTerm(id=self._next_id, term=d["term"], definition=d["definition"])
        self._next_id += 1
        self._terms.append(term)
        self._refresh()
        self.changed.emit()

    def _edit_term(self, term: GlossaryTerm):
        dlg = _TermDialog(term=term, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        d = dlg.get_data()
        if not d["term"]:
            return
        term.term = d["term"]
        term.definition = d["definition"]
        self._refresh()
        self.changed.emit()

    def _delete_term(self, term: GlossaryTerm):
        self._terms.remove(term)
        self._refresh()
        self.changed.emit()

    def _on_search(self, text: str):
        self._filter = text
        self._refresh()

    # ── serialisation ──────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        return {
            "next_id": self._next_id,
            "terms": [
                {"id": t.id, "term": t.term, "definition": t.definition}
                for t in self._terms
            ],
        }

    def set_data(self, data: dict):
        self._next_id = data.get("next_id", 1)
        self._terms = [
            GlossaryTerm(id=d["id"], term=d.get("term", ""), definition=d.get("definition", ""))
            for d in data.get("terms", [])
        ]
        self._refresh()
