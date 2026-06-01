"""
Traceability screen — step-by-step change log with component tabs,
KPI summary bar, impact metrics, and version tracking.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QTextEdit, QFileDialog,
    QSizePolicy, QDialog, QDialogButtonBox, QComboBox,
    QSpinBox, QDateEdit, QCheckBox, QScrollBar,
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon, QColor, QPainter, QBrush, QPen
from ui.styles import default_theme, make_font, dropdown_arrow_url as _get_arrow, arrow_up_url, arrow_down_url

logger = logging.getLogger(__name__)
_ARROW_URL  = _get_arrow()
_ARROW_UP   = arrow_up_url()
_ARROW_DOWN = arrow_down_url()

# ── palette ───────────────────────────────────────────────────────────────────
_BG     = '#f8f9fa'
_CARD   = '#ffffff'
_BORDER = '#e5e7eb'
_TEXT   = '#1e2430'
_MUTED  = '#6b7280'
_ACCENT = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover

_STATUS_COLORS = {
    "Approved":     "#22c55e",
    "Completed":    "#3b82f6",
    "Under review": "#f59e0b",
    "In progress":  "#6b7280",
}

_COMP_PALETTE = [
    "#3b82f6", "#8b5cf6", "#10b981", "#f59e0b",
    "#ef4444", "#06b6d4", "#f97316", "#14b8a6",
    "#6366f1", "#ec4899",
]

# ── styles ────────────────────────────────────────────────────────────────────
_INPUT = f"""
    QLineEdit, QTextEdit, QComboBox, QDateEdit, QSpinBox {{
        background-color: #f5f6f8; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 6px; font-size: 11px;
    }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
    QDateEdit:focus, QSpinBox:focus {{ border-color: {_ACCENT}; }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
    QDateEdit::drop-down {{ border: none; width: 20px; }}
    QDateEdit::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
    QComboBox QAbstractItemView {{
        background: {_CARD}; color: {_TEXT};
        border: 1px solid {_BORDER};
        selection-background-color: {_ACCENT}; selection-color: white;
    }}
    QSpinBox::up-button {{
        subcontrol-origin: border; subcontrol-position: top right;
        width: 18px; height: 13px;
        background: #e5e7eb; border-left: 1px solid {_BORDER};
        border-top-right-radius: 3px;
    }}
    QSpinBox::up-button:hover {{ background: {_ACCENT}; }}
    QSpinBox::up-arrow {{ image: url({_ARROW_UP}); width: 8px; height: 8px; }}
    QSpinBox::down-button {{
        subcontrol-origin: border; subcontrol-position: bottom right;
        width: 18px; height: 13px;
        background: #e5e7eb; border-left: 1px solid {_BORDER};
        border-bottom-right-radius: 3px;
    }}
    QSpinBox::down-button:hover {{ background: {_ACCENT}; }}
    QSpinBox::down-arrow {{ image: url({_ARROW_DOWN}); width: 8px; height: 8px; }}
"""
_BTN_PRIMARY = f"""
    QPushButton {{
        background: {_ACCENT}; color: white; border: none;
        border-radius: 5px; padding: 5px 14px; font-size: 11px; font-weight: bold;
    }}
    QPushButton:hover {{ background: {_ACCENT_H}; }}
"""
_BTN_SMALL = f"""
    QPushButton {{
        background: #f1f3f5; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 8px; font-size: 10px;
    }}
    QPushButton:hover {{ background: #e5e7eb; border-color: {_ACCENT}; color: {_ACCENT}; }}
"""
_BTN_OUTLINE = f"""
    QPushButton {{
        background: transparent; color: {_ACCENT};
        border: 1px solid {_ACCENT}; border-radius: 4px;
        padding: 3px 8px; font-size: 10px; font-weight: bold;
    }}
    QPushButton:hover {{ background: #dbeafe; }}
"""
_BTN_ICON = f"""
    QPushButton {{
        background: transparent; border: none;
        color: {_MUTED}; font-size: 13px; padding: 2px 5px;
    }}
    QPushButton:hover {{ color: {_ACCENT}; background: #e8f0fe; border-radius: 4px; }}
"""
_BTN_DELETE = f"""
    QPushButton {{
        background: transparent; border: none;
        color: {_MUTED}; font-size: 13px; padding: 2px 5px;
    }}
    QPushButton:hover {{ color: #ef4444; background: #fee2e2; border-radius: 4px; }}
"""
_TAB_ACTIVE = f"""
    QPushButton {{
        background: {_ACCENT}; color: white; border: none;
        border-radius: 5px 0 0 5px; padding: 5px 12px; font-size: 10px; font-weight: bold;
    }}
"""
_TAB_INACTIVE = f"""
    QPushButton {{
        background: transparent; color: {_MUTED};
        border: 1px solid {_BORDER}; border-radius: 5px 0 0 5px;
        padding: 5px 12px; font-size: 10px;
    }}
    QPushButton:hover {{ color: {_TEXT}; border-color: {_ACCENT}; background: #e8f0fe; }}
"""
_CLOSE_ACTIVE = f"""
    QPushButton {{
        background: {_ACCENT}; color: rgba(255,255,255,0.6);
        border: none; border-left: 1px solid rgba(255,255,255,0.2);
        border-radius: 0 5px 5px 0; font-size: 12px; font-weight: bold; padding: 0 6px;
    }}
    QPushButton:hover {{ color: white; background: #ef4444; }}
"""
_CLOSE_INACTIVE = f"""
    QPushButton {{
        background: transparent; color: {_MUTED};
        border: 1px solid {_BORDER}; border-left: none;
        border-radius: 0 5px 5px 0; font-size: 12px; font-weight: bold; padding: 0 6px;
    }}
    QPushButton:hover {{ color: #ef4444; background: #fee2e2; border-color: #fca5a5; }}
"""


# ── data model ────────────────────────────────────────────────────────────────

@dataclass
class ImpactMetric:
    label: str = ""
    value: str = ""


@dataclass
class TraceStep:
    id:             int
    step_number:    int          = 0
    date:           str          = ""
    added_by:       str          = ""
    title:          str          = ""
    description:    str          = ""
    photo_path:     str          = ""
    modifications:  List[str]    = field(default_factory=list)
    component_tags: List[str]    = field(default_factory=list)
    time_hours:     int          = 0
    time_minutes:   int          = 0
    impact_metrics: List[ImpactMetric] = field(default_factory=list)
    status:         str          = "In progress"
    version:        str          = "V1.0"


# ── helpers ───────────────────────────────────────────────────────────────────

def _comp_color(name: str, all_names: List[str]) -> str:
    try:
        idx = all_names.index(name)
    except ValueError:
        idx = hash(name) % len(_COMP_PALETTE)
    return _COMP_PALETTE[idx % len(_COMP_PALETTE)]


def _tag_chip(label: str, color: str) -> QLabel:
    chip = QLabel(label)
    chip.setStyleSheet(f"""
        QLabel {{
            background: {color}22;
            color: {color};
            border: 1px solid {color}66;
            border-radius: 3px;
            padding: 1px 6px;
            font-size: 9px;
            font-weight: bold;
        }}
    """)
    chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return chip


def _status_badge(status: str) -> QLabel:
    color = _STATUS_COLORS.get(status, _MUTED)
    badge = QLabel(status)
    badge.setStyleSheet(f"""
        QLabel {{
            background: {color}22;
            color: {color};
            border: 1px solid {color}66;
            border-radius: 4px;
            padding: 2px 8px;
            font-size: 9px;
            font-weight: bold;
        }}
    """)
    badge.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    badge.setWordWrap(False)
    return badge


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-height: 1px; border: none;")
    return f


# ── Step badge (circle with number) ──────────────────────────────────────────

class _StepBadge(QWidget):
    def __init__(self, number: int, status: str, parent=None):
        super().__init__(parent)
        self._number = number
        self._color = QColor(_STATUS_COLORS.get(status, _MUTED))
        self.setFixedSize(28, 28)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(self._color))
        p.setPen(Qt.NoPen)
        p.drawEllipse(2, 2, 24, 24)
        p.setPen(QColor("white"))
        p.setFont(make_font(size=9, bold=True))
        p.drawText(self.rect(), Qt.AlignCenter, str(self._number))
        p.end()


# ── Add / Edit step dialog ────────────────────────────────────────────────────

class _StepDialog(QDialog):

    def __init__(self, step: Optional[TraceStep] = None,
                 all_components: Optional[List[str]] = None,
                 parent=None):
        super().__init__(parent)
        self._all_components = all_components or []
        self.setWindowTitle("Edit Step" if step else "Add Step")
        self.setMinimumWidth(480)
        self.setMinimumHeight(560)
        self.setStyleSheet(f"QDialog {{ background: {_CARD}; color: {_TEXT}; }}")
        self._build(step)

    def _build(self, step: Optional[TraceStep]):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {_CARD}; border: none; }}")
        body = QWidget()
        body.setStyleSheet(f"background: {_CARD};")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(16, 14, 16, 10)
        lay.setSpacing(10)

        def _lbl(text):
            l = QLabel(text)
            l.setStyleSheet(f"color: {_MUTED}; font-size: 9px; font-weight: bold; "
                            f"background: transparent; border: none;")
            return l

        # Date + By row
        row = QHBoxLayout()
        date_col = QVBoxLayout(); date_col.setSpacing(3)
        date_col.addWidget(_lbl("DATE"))
        self.f_date = QDateEdit()
        self.f_date.setDisplayFormat("dd/MM/yyyy")
        self.f_date.setCalendarPopup(True)
        self.f_date.setStyleSheet(_INPUT)
        self.f_date.setFixedHeight(28)
        if step and step.date:
            d = QDate.fromString(step.date, "dd/MM/yyyy")
            self.f_date.setDate(d if d.isValid() else QDate.currentDate())
        else:
            self.f_date.setDate(QDate.currentDate())
        date_col.addWidget(self.f_date)

        by_col = QVBoxLayout(); by_col.setSpacing(3)
        by_col.addWidget(_lbl("BY (USER)"))
        self.f_by = QLineEdit(step.added_by if step else "")
        self.f_by.setPlaceholderText("Name")
        self.f_by.setStyleSheet(_INPUT)
        self.f_by.setFixedHeight(28)
        by_col.addWidget(self.f_by)

        row.addLayout(date_col, 2)
        row.addSpacing(10)
        row.addLayout(by_col, 2)
        lay.addLayout(row)

        # Title
        lay.addWidget(_lbl("TITLE"))
        self.f_title = QLineEdit(step.title if step else "")
        self.f_title.setPlaceholderText("Step title")
        self.f_title.setStyleSheet(_INPUT)
        self.f_title.setFixedHeight(28)
        lay.addWidget(self.f_title)

        # Description
        lay.addWidget(_lbl("DESCRIPTION"))
        self.f_desc = QTextEdit()
        self.f_desc.setPlaceholderText("Step description...")
        self.f_desc.setStyleSheet(_INPUT)
        self.f_desc.setFixedHeight(60)
        if step:
            self.f_desc.setPlainText(step.description)
        lay.addWidget(self.f_desc)

        # Modifications (dynamic bullet list)
        mods_hdr = QHBoxLayout()
        mods_hdr.addWidget(_lbl("MODIFICATIONS"))
        mods_hdr.addStretch()
        add_mod_btn = QPushButton("+ Add")
        add_mod_btn.setStyleSheet(_BTN_OUTLINE)
        add_mod_btn.setFixedHeight(22)
        add_mod_btn.setCursor(Qt.PointingHandCursor)
        mods_hdr.addWidget(add_mod_btn)
        lay.addLayout(mods_hdr)

        self._mods_layout = QVBoxLayout()
        self._mods_layout.setSpacing(4)
        self._mod_inputs: List[QLineEdit] = []
        lay.addLayout(self._mods_layout)

        initial_mods = step.modifications if step else [""]
        for m in initial_mods:
            self._add_mod_row(m)
        add_mod_btn.clicked.connect(lambda: self._add_mod_row(""))

        # Component tags
        if self._all_components:
            lay.addWidget(_lbl("COMPONENT TAGS"))
            tags_widget = QWidget()
            tags_widget.setStyleSheet("background: transparent;")
            tags_layout = QVBoxLayout(tags_widget)
            tags_layout.setContentsMargins(0, 0, 0, 0)
            tags_layout.setSpacing(4)
            self._comp_checks: List[tuple] = []
            for comp in self._all_components:
                cb = QCheckBox(comp)
                cb.setStyleSheet(f"""
                    QCheckBox {{ color: {_TEXT}; font-size: 11px;
                                 background: transparent; border: none; }}
                    QCheckBox::indicator {{ width: 14px; height: 14px; }}
                    QCheckBox::indicator:checked {{
                        background: {_ACCENT}; border-radius: 2px;
                    }}
                """)
                if step and comp in step.component_tags:
                    cb.setChecked(True)
                tags_layout.addWidget(cb)
                self._comp_checks.append((comp, cb))
            lay.addWidget(tags_widget)
        else:
            self._comp_checks = []

        # Time spent
        time_hdr = QHBoxLayout()
        time_hdr.addWidget(_lbl("TIME SPENT"))
        time_hdr.addStretch()
        lay.addLayout(time_hdr)
        time_row = QHBoxLayout(); time_row.setSpacing(6)
        self.f_hours = QSpinBox()
        self.f_hours.setRange(0, 999)
        self.f_hours.setValue(step.time_hours if step else 0)
        self.f_hours.setStyleSheet(_INPUT)
        self.f_hours.setFixedHeight(28)
        self.f_hours.setFixedWidth(70)
        time_row.addWidget(self.f_hours)
        time_row.addWidget(QLabel("h"))
        self.f_minutes = QSpinBox()
        self.f_minutes.setRange(0, 59)
        self.f_minutes.setValue(step.time_minutes if step else 0)
        self.f_minutes.setStyleSheet(_INPUT)
        self.f_minutes.setFixedHeight(28)
        self.f_minutes.setFixedWidth(70)
        time_row.addWidget(self.f_minutes)
        time_row.addWidget(QLabel("min"))
        time_row.addStretch()
        for l in time_row.children():
            if isinstance(l, QLabel):
                l.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
        lay.addLayout(time_row)

        # Impact metrics (dynamic)
        impact_hdr = QHBoxLayout()
        impact_hdr.addWidget(_lbl("IMPACT METRICS"))
        impact_hdr.addStretch()
        add_imp_btn = QPushButton("+ Add")
        add_imp_btn.setStyleSheet(_BTN_OUTLINE)
        add_imp_btn.setFixedHeight(22)
        add_imp_btn.setCursor(Qt.PointingHandCursor)
        impact_hdr.addWidget(add_imp_btn)
        lay.addLayout(impact_hdr)

        self._impact_layout = QVBoxLayout()
        self._impact_layout.setSpacing(4)
        self._impact_rows: List[tuple] = []
        lay.addLayout(self._impact_layout)

        initial_metrics = step.impact_metrics if step else []
        for m in initial_metrics:
            self._add_impact_row(m.label, m.value)
        if not initial_metrics:
            self._add_impact_row("", "")
        add_imp_btn.clicked.connect(lambda: self._add_impact_row("", ""))

        # Status
        lay.addWidget(_lbl("STATUS"))
        self.f_status = QComboBox()
        self.f_status.addItems(["In progress", "Approved", "Under review", "Completed"])
        self.f_status.setStyleSheet(_INPUT)
        self.f_status.setFixedHeight(28)
        if step:
            idx = self.f_status.findText(step.status)
            if idx >= 0:
                self.f_status.setCurrentIndex(idx)
        lay.addWidget(self.f_status)

        lay.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # Button bar
        btn_bar = QWidget()
        btn_bar.setStyleSheet(f"background: {_CARD}; border-top: 1px solid {_BORDER};")
        bl = QHBoxLayout(btn_bar)
        bl.setContentsMargins(16, 8, 16, 8)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT}; color: white; border: none;
                border-radius: 4px; padding: 6px 16px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {_ACCENT_H}; }}
        """)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        bl.addStretch()
        bl.addWidget(btns)
        root.addWidget(btn_bar)

    def _add_mod_row(self, text: str = ""):
        row = QHBoxLayout(); row.setSpacing(4)
        bullet = QLabel("•")
        bullet.setFixedWidth(10)
        bullet.setStyleSheet(f"color: {_ACCENT}; font-size: 12px; background: transparent; border: none;")
        inp = QLineEdit(text)
        inp.setPlaceholderText("Modification...")
        inp.setStyleSheet(_INPUT)
        inp.setFixedHeight(26)
        row.addWidget(bullet)
        row.addWidget(inp, 1)
        self._mods_layout.addLayout(row)
        self._mod_inputs.append(inp)

    def _add_impact_row(self, label: str = "", value: str = ""):
        row = QHBoxLayout(); row.setSpacing(6)
        lbl_inp = QLineEdit(label)
        lbl_inp.setPlaceholderText("Metric (e.g. Weight)")
        lbl_inp.setStyleSheet(_INPUT)
        lbl_inp.setFixedHeight(26)
        val_inp = QLineEdit(value)
        val_inp.setPlaceholderText("Value (e.g. -9g)")
        val_inp.setStyleSheet(_INPUT)
        val_inp.setFixedHeight(26)
        row.addWidget(lbl_inp, 2)
        row.addWidget(val_inp, 1)
        self._impact_layout.addLayout(row)
        self._impact_rows.append((lbl_inp, val_inp))

    def get_data(self) -> dict:
        return {
            "date":          self.f_date.date().toString("dd/MM/yyyy"),
            "added_by":      self.f_by.text().strip(),
            "title":         self.f_title.text().strip(),
            "description":   self.f_desc.toPlainText().strip(),
            "modifications": [i.text().strip() for i in self._mod_inputs if i.text().strip()],
            "component_tags":[c for c, cb in self._comp_checks if cb.isChecked()],
            "time_hours":    self.f_hours.value(),
            "time_minutes":  self.f_minutes.value(),
            "impact_metrics":[
                {"label": l.text().strip(), "value": v.text().strip()}
                for l, v in self._impact_rows
                if l.text().strip() or v.text().strip()
            ],
            "status": self.f_status.currentText(),
        }


# ── Step row widget ───────────────────────────────────────────────────────────

class _StepRow(QFrame):

    edit_requested   = pyqtSignal(object)
    delete_requested = pyqtSignal(object)

    def __init__(self, step: TraceStep, all_components: List[str], parent=None):
        super().__init__(parent)
        self._step = step
        self._all_components = all_components
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
        lay.setContentsMargins(12, 10, 8, 10)
        lay.setSpacing(0)

        # ── STEP col (date, badge, by) ──
        step_col = QVBoxLayout()
        step_col.setSpacing(3)
        step_col.setAlignment(Qt.AlignTop)

        date_lbl = QLabel(self._step.date)
        date_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 9px; background: transparent; border: none;")

        badge_row = QHBoxLayout()
        badge_row.setSpacing(4)
        badge_row.addWidget(_StepBadge(self._step.step_number, self._step.status))
        badge_row.addStretch()

        by_lbl = QLabel(f"By {self._step.added_by}" if self._step.added_by else "")
        by_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 9px; background: transparent; border: none;")

        step_col.addWidget(date_lbl)
        step_col.addLayout(badge_row)
        step_col.addWidget(by_lbl)

        step_frame = QWidget()
        step_frame.setFixedWidth(100)
        step_frame.setStyleSheet("background: transparent;")
        step_frame.setLayout(step_col)
        lay.addWidget(step_frame)
        lay.addSpacing(4)

        self._add_vline(lay)

        # ── TITLE / DESCRIPTION col ──
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title_col.setAlignment(Qt.AlignTop)

        title_lbl = QLabel(self._step.title)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11px; font-weight: bold; background: transparent; border: none;")

        desc_lbl = QLabel(self._step.description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")

        title_col.addWidget(title_lbl)
        if self._step.description:
            title_col.addWidget(desc_lbl)

        # Thumbnail
        if self._step.photo_path:
            pix = QPixmap(self._step.photo_path)
            if not pix.isNull():
                thumb = QLabel()
                thumb.setFixedSize(48, 48)
                thumb.setPixmap(pix.scaled(48, 48, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
                thumb.setStyleSheet("border-radius: 4px; border: 1px solid #e5e7eb;")
                title_col.addWidget(thumb)

        title_widget = QWidget()
        title_widget.setFixedWidth(170)
        title_widget.setStyleSheet("background: transparent;")
        title_widget.setLayout(title_col)
        lay.addSpacing(8)
        lay.addWidget(title_widget)
        lay.addSpacing(4)
        self._add_vline(lay)

        # ── MODIFICATIONS & COMPONENTS col ──
        mod_col = QVBoxLayout()
        mod_col.setSpacing(3)
        mod_col.setAlignment(Qt.AlignTop)

        for m in self._step.modifications:
            if m:
                ml = QLabel(f"• {m}")
                ml.setWordWrap(True)
                ml.setStyleSheet(f"color: {_TEXT}; font-size: 10px; background: transparent; border: none;")
                mod_col.addWidget(ml)

        if self._step.component_tags:
            tags_row = QHBoxLayout()
            tags_row.setSpacing(4)
            tags_row.setAlignment(Qt.AlignLeft)
            comp_lbl = QLabel("Components :")
            comp_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 9px; background: transparent; border: none;")
            mod_col.addWidget(comp_lbl)
            for tag in self._step.component_tags:
                color = _comp_color(tag, self._all_components)
                tags_row.addWidget(_tag_chip(tag, color))
            tags_row.addStretch()
            mod_col.addLayout(tags_row)

        mod_widget = QWidget()
        mod_widget.setFixedWidth(200)
        mod_widget.setStyleSheet("background: transparent;")
        mod_widget.setLayout(mod_col)
        lay.addSpacing(8)
        lay.addWidget(mod_widget)
        lay.addSpacing(4)
        self._add_vline(lay)

        # ── TIME SPENT col ──
        h, m = self._step.time_hours, self._step.time_minutes
        time_str = f"{h}h {m:02d}m" if (h or m) else "—"
        time_lbl = QLabel(f"⏱ {time_str}")
        time_lbl.setAlignment(Qt.AlignTop)
        time_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
        time_lbl.setFixedWidth(72)
        lay.addSpacing(8)
        lay.addWidget(time_lbl)
        lay.addSpacing(4)
        self._add_vline(lay)

        # ── IMPACT col ──
        impact_col = QVBoxLayout()
        impact_col.setSpacing(3)
        impact_col.setAlignment(Qt.AlignTop)
        for metric in self._step.impact_metrics:
            if not metric.label and not metric.value:
                continue
            mr = QHBoxLayout(); mr.setSpacing(6)
            ml = QLabel(metric.label)
            ml.setStyleSheet(f"color: {_MUTED}; font-size: 9px; background: transparent; border: none;")
            val = metric.value
            is_pos = val.startswith("+") if val else False
            is_neg = val.startswith("-") if val else False
            val_color = "#ef4444" if is_pos else ("#22c55e" if is_neg else _TEXT)
            mv = QLabel(val)
            mv.setStyleSheet(f"color: {val_color}; font-size: 10px; font-weight: bold; background: transparent; border: none;")
            mr.addWidget(ml)
            mr.addWidget(mv)
            mr.addStretch()
            impact_col.addLayout(mr)

        if not self._step.impact_metrics:
            impact_col.addWidget(QLabel("—"))

        impact_widget = QWidget()
        impact_widget.setFixedWidth(120)
        impact_widget.setStyleSheet("background: transparent;")
        for i in range(impact_col.count()):
            item = impact_col.itemAt(i)
            if item and item.widget():
                item.widget().setStyleSheet(
                    item.widget().styleSheet().replace("border: none;", "border: none; background: transparent;")
                )
        impact_widget.setLayout(impact_col)
        lay.addSpacing(8)
        lay.addWidget(impact_widget)
        lay.addSpacing(4)
        self._add_vline(lay)

        # ── STATUS col ──
        status_col = QVBoxLayout()
        status_col.setSpacing(4)
        status_col.setAlignment(Qt.AlignTop)
        status_col.addWidget(_status_badge(self._step.status))
        ver_lbl = QLabel(self._step.version)
        ver_lbl.setStyleSheet(f"color: {_ACCENT}; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        status_col.addWidget(ver_lbl)

        status_widget = QWidget()
        status_widget.setFixedWidth(116)
        status_widget.setStyleSheet("background: transparent;")
        status_widget.setLayout(status_col)
        lay.addSpacing(8)
        lay.addWidget(status_widget)
        lay.addSpacing(4)

        # ── Action buttons ──
        btn_col = QVBoxLayout()
        btn_col.setAlignment(Qt.AlignTop)
        edit_btn = QPushButton("✎")
        edit_btn.setFixedSize(26, 26)
        edit_btn.setStyleSheet(_BTN_ICON)
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setToolTip("Edit step")
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._step))
        del_btn = QPushButton("🗑")
        del_btn.setFixedSize(26, 26)
        del_btn.setStyleSheet(_BTN_DELETE)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setToolTip("Delete step")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._step))
        btn_col.addWidget(edit_btn)
        btn_col.addWidget(del_btn)
        lay.addLayout(btn_col)

    @staticmethod
    def _add_vline(layout):
        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        vline.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-width: 1px; border: none;")
        layout.addWidget(vline)


# ── KPI summary bar ───────────────────────────────────────────────────────────

class _KpiBar(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setStyleSheet(f"background: {_CARD}; border-bottom: 1px solid {_BORDER};")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(16, 0, 16, 0)
        self._lay.setSpacing(0)
        self._cells: List[tuple] = []

        specs = [
            ("Total number of steps",  "0"),
            ("Total project time",     "0h 00m"),
            ("Total modifications",    "0"),
            ("Components impacted",    "0"),
            ("Current version",        "—"),
            ("Overall status",         "—"),
        ]
        for i, (label, value) in enumerate(specs):
            cell = QWidget()
            cell.setStyleSheet("background: transparent;")
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(16, 8, 16, 8)
            cl.setSpacing(2)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {_MUTED}; font-size: 9px; background: transparent; border: none;")
            val = QLabel(value)
            val.setStyleSheet(f"color: {_TEXT}; font-size: 14px; font-weight: bold; background: transparent; border: none;")
            cl.addWidget(lbl)
            cl.addWidget(val)
            self._lay.addWidget(cell, 1)
            self._cells.append((lbl, val))
            if i < len(specs) - 1:
                vline = QFrame()
                vline.setFrameShape(QFrame.VLine)
                vline.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-width: 1px; border: none;")
                self._lay.addWidget(vline)

    def update_stats(self, steps: List[TraceStep], all_components: List[str]):
        n = len(steps)
        total_h = sum(s.time_hours for s in steps)
        total_m = sum(s.time_minutes for s in steps)
        total_h += total_m // 60
        total_m = total_m % 60
        total_mods = sum(len(s.modifications) for s in steps)
        impacted = len({t for s in steps for t in s.component_tags})
        cur_ver = steps[-1].version if steps else "—"
        cur_status = steps[-1].status if steps else "—"

        vals = [str(n), f"{total_h}h {total_m:02d}m", str(total_mods),
                str(impacted), cur_ver, cur_status]
        for (lbl_w, val_w), v in zip(self._cells, vals):
            val_w.setText(v)
            if lbl_w.text() == "Overall status":
                color = _STATUS_COLORS.get(v, _MUTED)
                val_w.setStyleSheet(
                    f"color: {color}; font-size: 13px; font-weight: bold; background: transparent; border: none;"
                )
            elif lbl_w.text() == "Current version":
                val_w.setStyleSheet(
                    f"color: {_ACCENT}; font-size: 14px; font-weight: bold; background: transparent; border: none;"
                )


# ── Main widget ───────────────────────────────────────────────────────────────

class TraceabilityWidget(QWidget):
    """Top-level Traceability screen."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._steps: List[TraceStep] = []
        self._components: List[str] = []   # from Project Brief
        self._current_component: Optional[str] = None   # None = All
        self._next_id = 1
        self._next_version_minor = 0       # V1.0, V1.1, V1.2…
        self.setStyleSheet(f"background: {_BG};")
        self._build_ui()
        self._refresh()

    # ── build ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Component tabs bar ──
        self._comp_bar = QWidget()
        self._comp_bar.setStyleSheet(f"background: {_BG}; border-bottom: 1px solid {_BORDER};")
        self._comp_bar.setFixedHeight(42)
        self._comp_bar_layout = QHBoxLayout(self._comp_bar)
        self._comp_bar_layout.setContentsMargins(12, 5, 12, 5)
        self._comp_bar_layout.setSpacing(6)
        self._comp_bar_layout.addStretch()
        root.addWidget(self._comp_bar)

        # ── Title bar ──
        title_bar = QWidget()
        title_bar.setFixedHeight(52)
        title_bar.setStyleSheet(f"background: {_BG}; border-bottom: 1px solid {_BORDER};")
        tbl = QHBoxLayout(title_bar)
        tbl.setContentsMargins(16, 0, 16, 0)

        title_col = QVBoxLayout(); title_col.setSpacing(1)
        self._title_lbl = QLabel("TRACEABILITY")
        self._title_lbl.setFont(make_font(size=14, bold=True))
        self._title_lbl.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        subtitle = QLabel("Track all changes, steps and impacts from step 1 to project completion.")
        subtitle.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
        title_col.addWidget(self._title_lbl)
        title_col.addWidget(subtitle)
        tbl.addLayout(title_col)
        tbl.addStretch()

        add_step_btn = QPushButton("＋  Add step")
        add_step_btn.setStyleSheet(_BTN_PRIMARY)
        add_step_btn.setFixedHeight(30)
        add_step_btn.setCursor(Qt.PointingHandCursor)
        add_step_btn.clicked.connect(self._add_step)
        tbl.addWidget(add_step_btn)

        root.addWidget(title_bar)

        # ── KPI bar ──
        self._kpi_bar = _KpiBar()
        root.addWidget(self._kpi_bar)

        # ── Column headers ──
        col_hdr = QWidget()
        col_hdr.setFixedHeight(28)
        col_hdr.setStyleSheet(f"background: #f1f3f5; border-bottom: 1px solid {_BORDER};")
        chl = QHBoxLayout(col_hdr)
        chl.setContentsMargins(12, 0, 8, 0)
        chl.setSpacing(0)

        def _ch(text, w):
            l = QLabel(text)
            l.setFixedWidth(w)
            l.setStyleSheet(f"color: {_MUTED}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
            return l

        chl.addWidget(_ch("STEP", 108))
        chl.addWidget(_ch("TITLE / DESCRIPTION", 190))
        chl.addWidget(_ch("MODIFICATIONS & COMPONENTS", 220))
        chl.addWidget(_ch("TIME SPENT", 90))
        chl.addWidget(_ch("IMPACT", 138))
        chl.addWidget(_ch("STATUS", 110))
        chl.addStretch()
        root.addWidget(col_hdr)

        # ── Scrollable step list ──
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

        # ── Footer ──
        self._footer = QWidget()
        self._footer.setFixedHeight(26)
        self._footer.setStyleSheet(f"background: #f1f3f5; border-top: 1px solid {_BORDER};")
        fl = QHBoxLayout(self._footer)
        fl.setContentsMargins(16, 0, 16, 0)
        self._footer_lbl = QLabel("")
        self._footer_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 9px; background: transparent; border: none;")
        ver_lbl = QLabel("ECTOFORM v1.2.0")
        ver_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 9px; background: transparent; border: none;")
        fl.addWidget(self._footer_lbl)
        fl.addStretch()
        fl.addWidget(ver_lbl)
        root.addWidget(self._footer)

    # ── component tabs ─────────────────────────────────────────────────────────

    def _rebuild_comp_tabs(self):
        while self._comp_bar_layout.count():
            item = self._comp_bar_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # "All" tab (None = no filter)
        all_active = self._current_component is None
        all_btn = QPushButton("All components")
        all_btn.setFixedHeight(28)
        all_btn.setCursor(Qt.PointingHandCursor)
        all_btn.setStyleSheet(_TAB_ACTIVE.replace("border-radius: 5px 0 0 5px;", "border-radius: 5px;")
                              if all_active else
                              _TAB_INACTIVE.replace("border-radius: 5px 0 0 5px;", "border-radius: 5px;"))
        all_btn.clicked.connect(lambda: self._select_component(None))
        self._comp_bar_layout.addWidget(all_btn)

        for comp in self._components:
            is_active = (comp == self._current_component)
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            ch = QHBoxLayout(container)
            ch.setContentsMargins(0, 0, 0, 0)
            ch.setSpacing(0)
            btn = QPushButton(comp)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_TAB_ACTIVE if is_active else _TAB_INACTIVE)
            btn.clicked.connect(lambda _, c=comp: self._select_component(c))
            close = QPushButton("×")
            close.setFixedSize(22, 28)
            close.setCursor(Qt.PointingHandCursor)
            close.setStyleSheet(_CLOSE_ACTIVE if is_active else _CLOSE_INACTIVE)
            close.clicked.connect(lambda _, c=comp: self._remove_component(c))
            ch.addWidget(btn)
            ch.addWidget(close)
            self._comp_bar_layout.addWidget(container)

        add_comp_btn = QPushButton("＋ Add a component")
        add_comp_btn.setStyleSheet(_BTN_SMALL)
        add_comp_btn.setFixedHeight(28)
        add_comp_btn.setCursor(Qt.PointingHandCursor)
        add_comp_btn.clicked.connect(self._add_component)
        self._comp_bar_layout.addWidget(add_comp_btn)
        self._comp_bar_layout.addStretch()

    def _select_component(self, comp: Optional[str]):
        self._current_component = comp
        name = comp if comp else "All components"
        self._title_lbl.setText(f"TRACEABILITY — {name.upper()}")
        self._rebuild_comp_tabs()
        self._refresh()

    def _add_component(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Component")
        dlg.setFixedWidth(340)
        dlg.setStyleSheet(f"""
            QDialog {{ background: {_CARD}; color: {_TEXT}; }}
            QLabel {{ color: {_MUTED}; font-size: 10px; font-weight: bold;
                      background: transparent; border: none; }}
        """)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lay.addWidget(QLabel("COMPONENT NAME"))
        inp = QLineEdit()
        inp.setPlaceholderText("e.g. Bezel")
        inp.setStyleSheet(_INPUT)
        inp.setFixedHeight(30)
        lay.addWidget(inp)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT}; color: white; border: none;
                border-radius: 4px; padding: 6px 16px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {_ACCENT_H}; }}
        """)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        inp.setFocus()
        if dlg.exec_() == QDialog.Accepted:
            name = inp.text().strip()
            if name and name not in self._components:
                self._components.append(name)
                self._rebuild_comp_tabs()
                self.changed.emit()

    def _remove_component(self, comp: str):
        if comp in self._components:
            self._components.remove(comp)
        if self._current_component == comp:
            self._current_component = None
            self._title_lbl.setText("TRACEABILITY")
        self._rebuild_comp_tabs()
        self._refresh()
        self.changed.emit()

    # ── step list ──────────────────────────────────────────────────────────────

    def _filtered_steps(self) -> List[TraceStep]:
        if self._current_component is None:
            return self._steps
        return [s for s in self._steps if self._current_component in s.component_tags]

    def _refresh(self):
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        visible = self._filtered_steps()
        if not visible:
            empty = QLabel("No steps yet. Click ＋ Add step to begin.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color: {_MUTED}; font-size: 12px; background: transparent; border: none;")
            empty.setContentsMargins(0, 40, 0, 0)
            self._list_layout.insertWidget(0, empty)
        else:
            for i, step in enumerate(visible):
                row = _StepRow(step, self._components)
                row.edit_requested.connect(self._edit_step)
                row.delete_requested.connect(self._delete_step)
                self._list_layout.insertWidget(i, row)

        self._kpi_bar.update_stats(visible, self._components)
        self._rebuild_comp_tabs()

        from datetime import date
        today = date.today().strftime("%d %B %Y")
        self._footer_lbl.setText(f"Document generated on {today}")

    # ── CRUD ───────────────────────────────────────────────────────────────────

    def _next_version(self) -> str:
        v = f"V1.{self._next_version_minor}"
        self._next_version_minor += 1
        return v

    def _add_step(self):
        dlg = _StepDialog(all_components=self._components, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        d = dlg.get_data()
        if not d["title"]:
            return
        step = TraceStep(
            id=self._next_id,
            step_number=len(self._steps) + 1,
            version=self._next_version(),
            **{k: v for k, v in d.items()},
        )
        # Convert impact dict list to ImpactMetric objects
        step.impact_metrics = [ImpactMetric(**m) for m in d["impact_metrics"]]
        self._next_id += 1
        self._steps.append(step)
        self._refresh()
        self.changed.emit()

    def _edit_step(self, step: TraceStep):
        dlg = _StepDialog(step=step, all_components=self._components, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        d = dlg.get_data()
        step.date          = d["date"]
        step.added_by      = d["added_by"]
        step.title         = d["title"]
        step.description   = d["description"]
        step.modifications = d["modifications"]
        step.component_tags = d["component_tags"]
        step.time_hours    = d["time_hours"]
        step.time_minutes  = d["time_minutes"]
        step.impact_metrics = [ImpactMetric(**m) for m in d["impact_metrics"]]
        step.status        = d["status"]
        self._refresh()
        self.changed.emit()

    def _delete_step(self, step: TraceStep):
        from ui.modal_utils import ask_yes_no_dialog
        if not ask_yes_no_dialog(
            self, "Delete Step", f"Delete step '{step.title}'?\nThis cannot be undone."
        ):
            return
        self._steps.remove(step)
        # Re-number remaining steps
        for i, s in enumerate(self._steps):
            s.step_number = i + 1
        self._refresh()
        self.changed.emit()

    # ── Brief integration ──────────────────────────────────────────────────────

    def update_components_from_brief(self, brief_components: list):
        """Called when Project Brief components change. brief_components = [[name, mat, col], ...]"""
        names = [row[0].strip() for row in brief_components if row and row[0].strip()]
        for name in names:
            if name not in self._components:
                self._components.append(name)
        self._rebuild_comp_tabs()

    # ── serialisation ──────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        def _ser_step(s: TraceStep) -> dict:
            return {
                "id": s.id, "step_number": s.step_number,
                "date": s.date, "added_by": s.added_by,
                "title": s.title, "description": s.description,
                "photo_path": s.photo_path,
                "modifications": s.modifications,
                "component_tags": s.component_tags,
                "time_hours": s.time_hours, "time_minutes": s.time_minutes,
                "impact_metrics": [{"label": m.label, "value": m.value}
                                   for m in s.impact_metrics],
                "status": s.status, "version": s.version,
            }
        return {
            "next_id": self._next_id,
            "next_version_minor": self._next_version_minor,
            "components": self._components,
            "current_component": self._current_component,
            "steps": [_ser_step(s) for s in self._steps],
        }

    def set_data(self, data: dict):
        self._next_id = data.get("next_id", 1)
        self._next_version_minor = data.get("next_version_minor", 0)
        self._components = data.get("components", [])
        self._current_component = data.get("current_component", None)
        self._steps = []
        for sd in data.get("steps", []):
            s = TraceStep(
                id=sd["id"], step_number=sd.get("step_number", 0),
                date=sd.get("date", ""), added_by=sd.get("added_by", ""),
                title=sd.get("title", ""), description=sd.get("description", ""),
                photo_path=sd.get("photo_path", ""),
                modifications=sd.get("modifications", []),
                component_tags=sd.get("component_tags", []),
                time_hours=sd.get("time_hours", 0),
                time_minutes=sd.get("time_minutes", 0),
                impact_metrics=[ImpactMetric(**m) for m in sd.get("impact_metrics", [])],
                status=sd.get("status", "In progress"),
                version=sd.get("version", "V1.0"),
            )
            self._steps.append(s)
        self._refresh()
