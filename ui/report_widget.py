"""
Report screen — dated meeting reports with header, pages, photo grids, and lock mechanism.

Structure:
  ReportWidget (top level)
  ├── Report tabs  (Report 05.02.26 … + New Report)
  └── ReportEditor  (one per report)
      ├── Page tabs  (Page 1, Page 2 … + Add page | 🔒 Lock | Print)
      └── PageWidget  (scrollable content per page)
          ├── [Page 1 only] HeaderSection
          ├── Production follow-up text area
          ├── PhotoSection  (N rows of 4 photos + captions)
          └── Comments text area
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QTextEdit, QFileDialog,
    QStackedWidget, QSizePolicy, QGridLayout, QMessageBox,
    QDateEdit, QSplitter
)
from PyQt5.QtCore import Qt, QDate, QRect, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon, QColor, QPainter
from ui.styles import default_theme, make_font, dropdown_arrow_url as _get_arrow
from ui.modal_utils import StyledModalDialog

logger = logging.getLogger(__name__)

# ── palette ───────────────────────────────────────────────────────────────────
_BG       = '#f8f9fa'
_CARD     = '#ffffff'
_BORDER   = '#e5e7eb'
_TEXT     = '#1e2430'
_MUTED    = '#6b7280'
_ACCENT   = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover
_HDR_BG   = '#e8f5ee'   # soft green header background (matches mockup)
_HDR_TEXT = '#1a7a4a'

# ── styles ────────────────────────────────────────────────────────────────────
_INPUT = f"""
    QLineEdit, QTextEdit, QDateEdit {{
        background-color: #f5f6f8; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 6px; font-size: 11px;
    }}
    QLineEdit:focus, QTextEdit:focus, QDateEdit:focus {{ border-color: {_ACCENT}; }}
    QLineEdit:read-only, QTextEdit:read-only {{
        background-color: #f1f3f5; color: {_MUTED};
    }}
    QDateEdit::drop-down {{ border: none; width: 18px; }}
    QDateEdit::down-arrow {{ image: url({_get_arrow()}); width: 10px; height: 10px; }}
"""
_BTN_PRIMARY = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: white; border: none;
        border-radius: 5px; padding: 5px 14px; font-size: 11px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: {_ACCENT_H}; }}
    QPushButton:disabled {{ background-color: #b0c4cc; }}
"""
_BTN_SMALL = f"""
    QPushButton {{
        background-color: #f1f3f5; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 8px; font-size: 10px;
    }}
    QPushButton:hover {{ background-color: #e5e7eb; border-color: {_ACCENT}; color: {_ACCENT}; }}
    QPushButton:disabled {{ color: #9ca3af; background: #f9fafb; }}
"""
_BTN_OUTLINE = f"""
    QPushButton {{
        background-color: transparent; color: {_ACCENT};
        border: 1px solid {_ACCENT}; border-radius: 5px;
        padding: 4px 12px; font-size: 10px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: #dbeafe; }}
"""
_BTN_LOCK = f"""
    QPushButton {{
        background-color: #fef3c7; color: #b45309;
        border: 1px solid #fde68a; border-radius: 5px;
        padding: 4px 12px; font-size: 10px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: #fde68a; }}
    QPushButton:disabled {{ background-color: #f1f3f5; color: #9ca3af; border-color: {_BORDER}; }}
"""
_TAB_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: white; border: none;
        border-radius: 5px; padding: 5px 14px; font-size: 11px; font-weight: bold;
    }}
"""
_TAB_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {_MUTED};
        border: 1px solid {_BORDER}; border-radius: 5px; padding: 5px 14px; font-size: 11px;
    }}
    QPushButton:hover {{ color: {_TEXT}; border-color: {_ACCENT}; background-color: #e8f0fe; }}
"""
_TAB_ACTIVE_L   = _TAB_ACTIVE.replace("border-radius: 5px;", "border-radius: 5px 0 0 5px;")
_TAB_INACTIVE_L = _TAB_INACTIVE.replace("border-radius: 5px;", "border-radius: 5px 0 0 5px;")
_CLOSE_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: rgba(255,255,255,0.55);
        border: none; border-left: 1px solid rgba(255,255,255,0.18);
        border-radius: 0 5px 5px 0; font-size: 13px; font-weight: bold; padding: 0 5px;
    }}
    QPushButton:hover {{ color: white; background-color: #ef4444; }}
"""
_CLOSE_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {_MUTED};
        border: 1px solid {_BORDER}; border-left: none;
        border-radius: 0 5px 5px 0; font-size: 13px; font-weight: bold; padding: 0 5px;
    }}
    QPushButton:hover {{ color: #ef4444; background-color: #fee2e2; border-color: #fca5a5; }}
"""

# ── data model ────────────────────────────────────────────────────────────────

@dataclass
class PhotoCell:
    caption:    str = ""
    image_path: str = ""


@dataclass
class PhotoRow:
    photos: List[PhotoCell] = field(default_factory=lambda: [PhotoCell() for _ in range(4)])


@dataclass
class AttendeeColumn:
    header: str = ""
    name:   str = ""


@dataclass
class CompanyRow:
    label: str = ""
    value: str = ""


@dataclass
class ReportPage:
    id:         int
    followup:   str = ""
    comments:   str = ""
    photo_rows: List[PhotoRow] = field(default_factory=list)


@dataclass
class Report:
    id:                int
    date:              str  = ""
    locked:            bool = False
    launch_deadline:   str  = ""
    project_name:      str  = ""
    project_reference: str  = ""
    project_manager:   str  = ""
    technical_manager: str  = ""
    quality_lead:      str  = ""
    company_extras:    List[CompanyRow]     = field(default_factory=list)
    partner_1:         str  = ""
    partner_2:         str  = ""
    partner_3:         str  = ""
    partner_extras:    List[CompanyRow]     = field(default_factory=list)
    attendees:         List[AttendeeColumn] = field(default_factory=list)
    pages:             List[ReportPage]     = field(default_factory=list)

    def display_name(self) -> str:
        prefix = "🔒  " if self.locked else ""
        if self.date:
            parts = self.date.split("/")
            if len(parts) == 3:
                return f"{prefix}Report  {parts[0]}.{parts[1]}.{parts[2][-2:]}"
        return f"{prefix}Report {self.id}"


def _default_report(rid: int) -> Report:
    today = QDate.currentDate().toString("dd/MM/yyyy")
    r = Report(id=rid, date=today)
    r.company_extras  = []
    r.partner_extras  = []
    r.attendees = [
        AttendeeColumn(h, "") for h in
        ["Production", "Studio", "Marketing", "Partners 1", "Other", "Other"]
    ]
    page = ReportPage(id=1)
    page.photo_rows = [PhotoRow()]
    r.pages = [page]
    return r


# ── helpers ───────────────────────────────────────────────────────────────────

class _VerticalLabel(QWidget):
    """Label that renders text rotated 90° (bottom-to-top), used for section sidebars."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self.setFixedWidth(22)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#f1f3f5'))
        p.setPen(QColor(_MUTED))
        from ui.styles import make_font
        p.setFont(make_font(size=9, bold=True))
        p.translate(0, self.height())
        p.rotate(-90)
        p.drawText(QRect(0, 0, self.height(), self.width()), Qt.AlignCenter, self._text)
        p.end()


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-height: 1px; border: none;")
    return f


def _card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setStyleSheet(
        f"QFrame {{ background-color: {_CARD}; border: 1px solid {_BORDER}; border-radius: 8px; }}"
    )
    return f


def _lbl(text: str, muted=True, bold=False, size=10) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(
        f"color: {'#6b7280' if muted else _TEXT}; font-size: {size}px; "
        f"font-weight: {'bold' if bold else 'normal'}; background: transparent; border: none;"
    )
    return l


def _field(placeholder="", h=26) -> QLineEdit:
    w = QLineEdit()
    w.setPlaceholderText(placeholder)
    w.setStyleSheet(_INPUT)
    w.setFixedHeight(h)
    return w


# ── Photo row widget ──────────────────────────────────────────────────────────

class PhotoRowWidget(QWidget):
    """4 photo slots with captions — one row in the Components section."""

    changed = pyqtSignal()

    def __init__(self, row_data: PhotoRow, parent=None):
        super().__init__(parent)
        self._row = row_data
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        photo_row   = QHBoxLayout()
        caption_row = QHBoxLayout()
        photo_row.setSpacing(8)
        caption_row.setSpacing(8)

        self._photo_btns:    List[QPushButton] = []
        self._caption_edits: List[QLineEdit]   = []

        for i, cell in enumerate(self._row.photos):
            btn = QPushButton("＋\nAdd photo")
            btn.setFixedSize(130, 100)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #f1f3f5; border: 1px dashed {_BORDER};
                    border-radius: 6px; color: {_MUTED}; font-size: 10px;
                }}
                QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
            """)
            btn.clicked.connect(lambda _, idx=i: self._upload(idx))
            if cell.image_path:
                self._apply_image(btn, cell.image_path)

            cap = _field("text here")
            cap.setText(cell.caption)
            cap.setFixedWidth(130)
            cap.textChanged.connect(lambda t, idx=i: self._on_caption(idx, t))

            photo_row.addWidget(btn)
            caption_row.addWidget(cap)
            self._photo_btns.append(btn)
            self._caption_edits.append(cap)

        photo_row.addStretch()
        caption_row.addStretch()
        layout.addLayout(photo_row)
        layout.addLayout(caption_row)

    def _upload(self, idx: int):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Photo", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            self._row.photos[idx].image_path = path
            self._apply_image(self._photo_btns[idx], path)
            self.changed.emit()

    def _apply_image(self, btn: QPushButton, path: str):
        pix = QPixmap(path)
        if not pix.isNull():
            btn.setIcon(QIcon(
                pix.scaled(btn.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            ))
            btn.setIconSize(btn.size())
            btn.setText("")

    def _on_caption(self, idx: int, text: str):
        self._row.photos[idx].caption = text
        self.changed.emit()

    def lock(self):
        for btn in self._photo_btns:
            btn.setEnabled(False)
        for cap in self._caption_edits:
            cap.setReadOnly(True)


# ── Header Section (Page 1 only) ──────────────────────────────────────────────

class HeaderSection(QWidget):
    """The full meeting report header — logo, date, company grid, attendees."""

    changed = pyqtSignal()

    def __init__(self, report: Report, logo_fn: Callable[[], Optional[QPixmap]],
                 set_logo_fn: Callable[[QPixmap, str], None], parent=None):
        super().__init__(parent)
        self._report     = report
        self._logo_fn    = logo_fn
        self._set_logo   = set_logo_fn
        self.setStyleSheet(f"background: {_BG};")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 4, 0)
        root.setSpacing(8)

        # ── Top strip: logo | meeting title | launch deadline ──
        top = QFrame()
        top.setStyleSheet(f"""
            QFrame {{
                background-color: {_CARD};
                border: 1px solid {_BORDER}; border-radius: 8px;
            }}
        """)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(10, 8, 10, 8)
        tl.setSpacing(10)

        # Logo
        self._logo_btn = QPushButton("＋  Add logo\nof the company")
        self._logo_btn.setFixedSize(110, 60)
        self._logo_btn.setCursor(Qt.PointingHandCursor)
        self._logo_btn.setStyleSheet(f"""
            QPushButton {{
                background: #f1f3f5; border: 1px dashed {_BORDER};
                border-radius: 6px; color: {_MUTED}; font-size: 9px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
        """)
        self._logo_btn.clicked.connect(self._upload_logo)
        tl.addWidget(self._logo_btn)

        # Refresh logo from shared store
        pix = self._logo_fn()
        if pix:
            self._apply_logo(pix)

        # Title + project fields
        mid = QVBoxLayout()
        mid.setSpacing(4)

        title_row = QHBoxLayout()
        meeting_lbl = QLabel("Meeting report of")
        meeting_lbl.setStyleSheet(
            f"color: {_HDR_TEXT}; font-size: 13px; font-weight: bold; background: transparent; border: none;"
        )
        from ui.date_picker import EctoDateEdit
        self._date_edit = EctoDateEdit()
        self._date_edit.setFixedHeight(26)
        self._date_edit.setFixedWidth(110)
        if self._report.date:
            d = QDate.fromString(self._report.date, "dd/MM/yyyy")
            if d.isValid():
                self._date_edit.setDate(d)
        else:
            self._date_edit.setDate(QDate.currentDate())
        self._date_edit.dateChanged.connect(
            lambda d: setattr(self._report, 'date', d.toString("dd/MM/yyyy")) or self.changed.emit()
        )
        title_row.addWidget(meeting_lbl)
        title_row.addWidget(self._date_edit)
        title_row.addStretch()
        mid.addLayout(title_row)

        proj_row = QHBoxLayout()
        proj_row.setSpacing(8)
        self._f_project = _field("Name of the project")
        self._f_project.setText(self._report.project_name)
        self._f_project.textChanged.connect(
            lambda v: setattr(self._report, 'project_name', v) or self.changed.emit()
        )
        self._f_reference = _field("Reference of the project")
        self._f_reference.setText(self._report.project_reference)
        self._f_reference.textChanged.connect(
            lambda v: setattr(self._report, 'project_reference', v) or self.changed.emit()
        )
        proj_row.addWidget(self._f_project, 1)
        proj_row.addWidget(self._f_reference, 1)
        mid.addLayout(proj_row)
        tl.addLayout(mid, 1)

        # Launch deadline
        dl_col = QVBoxLayout()
        dl_col.setSpacing(4)
        dl_lbl = QLabel("launch deadline :")
        dl_lbl.setStyleSheet(
            f"color: {_HDR_TEXT}; font-size: 10px; font-weight: bold; background: transparent; border: none;"
        )
        self._f_deadline = _field("dd/mm/yyyy")
        self._f_deadline.setText(self._report.launch_deadline)
        self._f_deadline.setFixedWidth(120)
        self._f_deadline.textChanged.connect(
            lambda v: setattr(self._report, 'launch_deadline', v) or self.changed.emit()
        )
        dl_col.addWidget(dl_lbl)
        dl_col.addWidget(self._f_deadline)
        dl_col.addStretch()
        tl.addLayout(dl_col)
        root.addWidget(top)

        # ── Company & Partners grid ──
        grid_card = _card()
        gl = QHBoxLayout(grid_card)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(0)

        # Company column (with vertical label)
        company_col = self._build_rotated_section(
            "Company",
            [
                ("Project manager :", "_f_pm"),
                ("Technical manager :", "_f_tm"),
                ("Quality lead :", "_f_ql"),
            ],
            self._report.company_extras,
            "company"
        )
        gl.addWidget(company_col, 3)

        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-width: 1px; border: none;")
        gl.addWidget(div)

        # Partners column (with vertical label)
        partners_col = self._build_rotated_section(
            "Suppliers\n& partners",
            [
                ("Partner 1 :", "_f_p1"),
                ("Partner 2 :", "_f_p2"),
                ("Partner 3 :", "_f_p3"),
            ],
            self._report.partner_extras,
            "partner"
        )
        gl.addWidget(partners_col, 2)
        root.addWidget(grid_card)

        # ── Present Attendees ──
        att_card = _card()
        al = QVBoxLayout(att_card)
        al.setContentsMargins(10, 8, 10, 8)
        al.setSpacing(6)

        att_header = QHBoxLayout()
        att_lbl = QLabel("Present attendees")
        att_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        att_header.addWidget(att_lbl)
        att_header.addStretch()
        self._add_attendee_btn = QPushButton("+ Add column")
        self._add_attendee_btn.setStyleSheet(_BTN_OUTLINE)
        self._add_attendee_btn.setFixedHeight(24)
        self._add_attendee_btn.setCursor(Qt.PointingHandCursor)
        self._add_attendee_btn.clicked.connect(self._add_attendee_col)
        att_header.addWidget(self._add_attendee_btn)
        al.addLayout(att_header)

        self._att_grid = QHBoxLayout()
        self._att_grid.setSpacing(6)
        self._att_col_widgets: List[tuple] = []
        for att in self._report.attendees:
            self._add_att_col_widget(att)
        self._att_grid.addStretch()
        al.addLayout(self._att_grid)
        root.addWidget(att_card)

    def _build_rotated_section(self, section_label: str, fixed_rows: list,
                                extras: List[CompanyRow], prefix: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("background: transparent;")
        row_l = QHBoxLayout(frame)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.setSpacing(0)

        # Vertical label (rotated text)
        vert = _VerticalLabel(section_label)
        row_l.addWidget(vert)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(8, 6, 8, 6)
        cl.setSpacing(4)

        for label, attr in fixed_rows:
            r = QHBoxLayout()
            r.setSpacing(6)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
            lbl.setFixedWidth(140)
            inp = _field("")
            value = ""
            if attr == "_f_pm":   value = self._report.project_manager
            elif attr == "_f_tm": value = self._report.technical_manager
            elif attr == "_f_ql": value = self._report.quality_lead
            elif attr == "_f_p1": value = self._report.partner_1
            elif attr == "_f_p2": value = self._report.partner_2
            elif attr == "_f_p3": value = self._report.partner_3
            inp.setText(value)
            setattr(self, attr, inp)
            # Wire changes back to report
            if attr == "_f_pm":
                inp.textChanged.connect(lambda v: setattr(self._report, 'project_manager', v) or self.changed.emit())
            elif attr == "_f_tm":
                inp.textChanged.connect(lambda v: setattr(self._report, 'technical_manager', v) or self.changed.emit())
            elif attr == "_f_ql":
                inp.textChanged.connect(lambda v: setattr(self._report, 'quality_lead', v) or self.changed.emit())
            elif attr == "_f_p1":
                inp.textChanged.connect(lambda v: setattr(self._report, 'partner_1', v) or self.changed.emit())
            elif attr == "_f_p2":
                inp.textChanged.connect(lambda v: setattr(self._report, 'partner_2', v) or self.changed.emit())
            elif attr == "_f_p3":
                inp.textChanged.connect(lambda v: setattr(self._report, 'partner_3', v) or self.changed.emit())
            r.addWidget(lbl)
            r.addWidget(inp, 1)
            cl.addLayout(r)

        for extra in extras:
            self._add_extra_row(cl, extra, at_end=True)

        add_btn = QPushButton("+ Add row")
        add_btn.setStyleSheet(_BTN_OUTLINE)
        add_btn.setFixedHeight(24)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(lambda: self._add_extra(cl, extras, add_btn))
        cl.addWidget(add_btn, alignment=Qt.AlignLeft)
        row_l.addWidget(content, 1)
        return frame

    def _add_extra_row(self, layout: QVBoxLayout, extra: CompanyRow, at_end: bool = False):
        r = QHBoxLayout()
        r.setSpacing(6)
        lbl_inp = _field("Label")
        lbl_inp.setText(extra.label)
        lbl_inp.setFixedWidth(140)
        lbl_inp.textChanged.connect(lambda v, e=extra: setattr(e, 'label', v) or self.changed.emit())
        val_inp = _field("")
        val_inp.setText(extra.value)
        val_inp.textChanged.connect(lambda v, e=extra: setattr(e, 'value', v) or self.changed.emit())
        r.addWidget(lbl_inp)
        r.addWidget(val_inp, 1)
        if at_end:
            layout.addLayout(r)
        else:
            layout.insertLayout(layout.count() - 1, r)

    def _add_extra(self, layout: QVBoxLayout, extras: List[CompanyRow], btn: QPushButton):
        extra = CompanyRow("", "")
        extras.append(extra)
        self._add_extra_row(layout, extra)
        self.changed.emit()

    def _add_att_col_widget(self, att: AttendeeColumn):
        col = QVBoxLayout()
        col.setSpacing(3)
        hdr_inp = _field("Column header")
        hdr_inp.setText(att.header)
        hdr_inp.setFixedWidth(110)
        hdr_inp.setStyleSheet(_INPUT + "QLineEdit { font-weight: bold; }")
        hdr_inp.textChanged.connect(lambda v, a=att: setattr(a, 'header', v) or self.changed.emit())
        name_inp = _field("Name")
        name_inp.setText(att.name)
        name_inp.setFixedWidth(110)
        name_inp.textChanged.connect(lambda v, a=att: setattr(a, 'name', v) or self.changed.emit())
        col.addWidget(hdr_inp)
        col.addWidget(name_inp)
        idx = self._att_grid.count() - 1
        self._att_grid.insertLayout(idx, col)
        self._att_col_widgets.append((hdr_inp, name_inp))

    def _add_attendee_col(self):
        att = AttendeeColumn("", "")
        self._report.attendees.append(att)
        self._add_att_col_widget(att)
        self.changed.emit()

    def _upload_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Company Logo", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            pix = QPixmap(path)
            if not pix.isNull():
                self._set_logo(pix, path)
                self._apply_logo(pix)
                self.changed.emit()

    def _apply_logo(self, pix: QPixmap):
        scaled = pix.scaled(
            self._logo_btn.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self._logo_btn.setIcon(QIcon(scaled))
        self._logo_btn.setIconSize(self._logo_btn.size())
        self._logo_btn.setText("")

    def update_project_info(self, info: dict):
        self._f_project.setText(info.get("title", "") or "")
        self._report.project_name = self._f_project.text()
        self._f_reference.setText(info.get("number", "") or "")
        self._report.project_reference = self._f_reference.text()

    def lock(self):
        self._logo_btn.setEnabled(False)
        self._date_edit.setEnabled(False)
        self._f_deadline.setReadOnly(True)
        self._add_attendee_btn.setEnabled(False)
        for w in (self._f_project, self._f_reference,
                  self._f_pm, self._f_tm, self._f_ql,
                  self._f_p1, self._f_p2, self._f_p3):
            w.setReadOnly(True)
        for hdr, name in self._att_col_widgets:
            hdr.setReadOnly(True)
            name.setReadOnly(True)


# ── Page Widget ───────────────────────────────────────────────────────────────

class PageWidget(QScrollArea):
    """Content of a single report page."""

    changed = pyqtSignal()

    def __init__(self, page: Report, report: Report, is_first: bool,
                 logo_fn: Callable, set_logo_fn: Callable, parent=None):
        super().__init__(parent)
        self._page    = page
        self._report  = report
        self._is_first = is_first
        self._photo_row_widgets: List[PhotoRowWidget] = []
        self._photo_row_containers: List[QWidget] = []
        self._header: Optional[HeaderSection] = None
        self._locked = False

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(f"""
            QScrollArea {{ background: {_BG}; border: none; }}
            QScrollBar:vertical {{ background: {_BG}; width: 12px; border-radius: 6px; }}
            QScrollBar::handle:vertical {{ background: {_ACCENT}; border-radius: 6px; min-height: 30px; }}
        """)
        body = QWidget()
        body.setStyleSheet(f"background: {_BG};")
        self._root = QVBoxLayout(body)
        self._root.setContentsMargins(16, 14, 16, 14)
        self._root.setSpacing(12)

        # Header (page 1 only)
        if is_first:
            self._header = HeaderSection(report, logo_fn, set_logo_fn)
            self._header.changed.connect(self.changed)
            self._root.addWidget(self._header)

        # Production follow-up
        fu_card = _card()
        fl = QVBoxLayout(fu_card)
        fl.setContentsMargins(14, 10, 14, 10)
        fl.setSpacing(6)
        fl.addWidget(_lbl("Production follow-up and meeting summary", muted=False, bold=True))
        fl.addWidget(_sep())
        self._followup = QTextEdit()
        self._followup.setPlaceholderText("Production follow-up and meeting summary...")
        self._followup.setMinimumHeight(80)
        self._followup.setStyleSheet(_INPUT)
        self._followup.setPlainText(page.followup)
        self._followup.textChanged.connect(
            lambda: setattr(self._page, 'followup', self._followup.toPlainText()) or self.changed.emit()
        )
        fl.addWidget(self._followup)
        self._root.addWidget(fu_card)

        # Photos section
        photos_card = _card()
        pl = QVBoxLayout(photos_card)
        pl.setContentsMargins(14, 10, 14, 10)
        pl.setSpacing(8)
        ph_hdr = QHBoxLayout()
        ph_hdr.addWidget(_lbl("Components and photos for modification", muted=False, bold=True))
        ph_hdr.addStretch()
        self._add_photo_row_btn = QPushButton("+ Add photo row")
        self._add_photo_row_btn.setStyleSheet(_BTN_OUTLINE)
        self._add_photo_row_btn.setFixedHeight(26)
        self._add_photo_row_btn.setCursor(Qt.PointingHandCursor)
        self._add_photo_row_btn.clicked.connect(self._add_photo_row)
        ph_hdr.addWidget(self._add_photo_row_btn)
        pl.addLayout(ph_hdr)
        pl.addWidget(_sep())
        self._photos_layout = QVBoxLayout()
        self._photos_layout.setSpacing(14)
        pl.addLayout(self._photos_layout)
        self._root.addWidget(photos_card)

        # Populate existing photo rows
        for pr in page.photo_rows:
            self._add_photo_row_widget(pr)

        # Comments
        co_card = _card()
        co = QVBoxLayout(co_card)
        co.setContentsMargins(14, 10, 14, 10)
        co.setSpacing(6)
        co.addWidget(_lbl("Comments", muted=False, bold=True))
        co.addWidget(_sep())
        self._comments = QTextEdit()
        self._comments.setPlaceholderText("Comments...")
        self._comments.setMinimumHeight(70)
        self._comments.setStyleSheet(_INPUT)
        self._comments.setPlainText(page.comments)
        self._comments.textChanged.connect(
            lambda: setattr(self._page, 'comments', self._comments.toPlainText()) or self.changed.emit()
        )
        co.addWidget(self._comments)
        self._root.addWidget(co_card)
        self._root.addStretch()
        self.setWidget(body)

    def _add_photo_row(self):
        pr = PhotoRow()
        self._page.photo_rows.append(pr)
        self._add_photo_row_widget(pr)
        self.changed.emit()

    def _add_photo_row_widget(self, pr: PhotoRow):
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(4)

        del_row = QHBoxLayout()
        del_row.setContentsMargins(0, 0, 0, 0)
        del_row.addStretch()
        del_btn = QPushButton("× Remove row")
        del_btn.setFixedHeight(20)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_MUTED};
                border: none; font-size: 10px; padding: 0 4px;
            }}
            QPushButton:hover {{ color: #ef4444; }}
        """)
        del_btn.clicked.connect(lambda _, c=container, p=pr: self._remove_photo_row(c, p))
        del_row.addWidget(del_btn)
        cl.addLayout(del_row)

        w = PhotoRowWidget(pr)
        w.changed.connect(self.changed)
        cl.addWidget(w)

        self._photos_layout.addWidget(container)
        self._photo_row_widgets.append(w)
        self._photo_row_containers.append(container)

    def _remove_photo_row(self, container: QWidget, pr: 'PhotoRow'):
        if pr in self._page.photo_rows:
            self._page.photo_rows.remove(pr)
        if container in self._photo_row_containers:
            self._photo_row_containers.remove(container)
        container.hide()
        container.setParent(None)
        self.changed.emit()

    def update_project_info(self, info: dict):
        if self._header:
            self._header.update_project_info(info)

    def refresh_logo(self, logo_fn: Callable):
        if self._header:
            pix = logo_fn()
            if pix:
                self._header._apply_logo(pix)

    def lock(self):
        self._locked = True
        self._add_photo_row_btn.setEnabled(False)
        self._followup.setReadOnly(True)
        self._comments.setReadOnly(True)
        for w in self._photo_row_widgets:
            w.lock()
        for c in self._photo_row_containers:
            layout = c.layout()
            if layout and layout.count() > 0:
                del_row = layout.itemAt(0)
                if del_row and del_row.layout():
                    for j in range(del_row.layout().count()):
                        item = del_row.layout().itemAt(j)
                        if item and item.widget():
                            item.widget().setEnabled(False)
        if self._header:
            self._header.lock()


# ── Report Editor ─────────────────────────────────────────────────────────────

class ReportEditor(QWidget):
    """Editing view for one report — page tabs + content."""

    changed = pyqtSignal()

    def __init__(self, report: Report, logo_fn: Callable, set_logo_fn: Callable,
                 parent=None):
        super().__init__(parent)
        self._report      = report
        self._logo_fn     = logo_fn
        self._set_logo_fn = set_logo_fn
        self._current_page = 0
        self._page_widgets: List[PageWidget] = []
        self._next_page_id = 2
        self.setStyleSheet(f"background: {_BG};")
        self._build_ui()
        self._rebuild_pages()
        self._switch_page(0)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Page tabs bar
        self._page_bar = QWidget()
        self._page_bar.setFixedHeight(38)
        self._page_bar.setStyleSheet(f"background: {_BG}; border-bottom: 1px solid {_BORDER};")
        self._page_layout = QHBoxLayout(self._page_bar)
        self._page_layout.setContentsMargins(12, 4, 12, 4)
        self._page_layout.setSpacing(6)

        self._add_page_btn = QPushButton("＋  Add page")
        self._add_page_btn.setStyleSheet(_BTN_SMALL)
        self._add_page_btn.setFixedHeight(26)
        self._add_page_btn.setCursor(Qt.PointingHandCursor)
        self._add_page_btn.clicked.connect(self._add_page)

        self._lock_btn = QPushButton("🔒  Lock Report")
        self._lock_btn.setStyleSheet(_BTN_LOCK)
        self._lock_btn.setFixedHeight(26)
        self._lock_btn.setCursor(Qt.PointingHandCursor)
        self._lock_btn.clicked.connect(self._lock_report)
        if self._report.locked:
            self._lock_btn.setEnabled(False)
            self._lock_btn.setText("🔒  Locked")

        self._page_layout.addStretch()
        root.addWidget(self._page_bar)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

    def _refresh_page_tabs(self):
        _permanent = (self._add_page_btn, self._lock_btn)
        while self._page_layout.count():
            item = self._page_layout.takeAt(0)
            w = item.widget()
            if w and w not in _permanent:
                w.deleteLater()

        for i, page in enumerate(self._report.pages):
            is_active = (i == self._current_page)
            if len(self._report.pages) > 1:
                container = QWidget()
                container.setStyleSheet("background: transparent;")
                ch = QHBoxLayout(container)
                ch.setContentsMargins(0, 0, 0, 0)
                ch.setSpacing(0)
                btn = QPushButton(f"Page {i + 1}")
                btn.setFixedHeight(26)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setStyleSheet(_TAB_ACTIVE_L if is_active else _TAB_INACTIVE_L)
                btn.clicked.connect(lambda _, idx=i: self._switch_page(idx))
                close = QPushButton("×")
                close.setFixedSize(22, 26)
                close.setCursor(Qt.PointingHandCursor)
                close.setStyleSheet(_CLOSE_ACTIVE if is_active else _CLOSE_INACTIVE)
                close.clicked.connect(lambda _, idx=i: self._remove_page(idx))
                close.setEnabled(not self._report.locked)
                ch.addWidget(btn)
                ch.addWidget(close)
                self._page_layout.addWidget(container)
            else:
                btn = QPushButton("Page 1")
                btn.setFixedHeight(26)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setStyleSheet(_TAB_ACTIVE if is_active else _TAB_INACTIVE)
                btn.clicked.connect(lambda: self._switch_page(0))
                self._page_layout.addWidget(btn)

        self._page_layout.addWidget(self._add_page_btn)
        self._page_layout.addStretch()
        self._page_layout.addWidget(self._lock_btn)

    def _rebuild_pages(self):
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.deleteLater()
        self._page_widgets.clear()

        for i, page in enumerate(self._report.pages):
            pw = PageWidget(
                page, self._report, is_first=(i == 0),
                logo_fn=self._logo_fn, set_logo_fn=self._set_logo_fn
            )
            pw.changed.connect(self.changed)
            self._stack.addWidget(pw)
            self._page_widgets.append(pw)
            if page.id >= self._next_page_id:
                self._next_page_id = page.id + 1

        if self._report.locked:
            for pw in self._page_widgets:
                pw.lock()

    def _switch_page(self, idx: int):
        self._current_page = idx
        if 0 <= idx < len(self._page_widgets):
            self._stack.setCurrentWidget(self._page_widgets[idx])
        self._refresh_page_tabs()

    def _add_page(self):
        page = ReportPage(id=self._next_page_id)
        page.photo_rows = [PhotoRow()]
        self._next_page_id += 1
        self._report.pages.append(page)
        pw = PageWidget(
            page, self._report, is_first=False,
            logo_fn=self._logo_fn, set_logo_fn=self._set_logo_fn
        )
        pw.changed.connect(self.changed)
        self._stack.addWidget(pw)
        self._page_widgets.append(pw)
        self._switch_page(len(self._report.pages) - 1)
        self.changed.emit()

    def _remove_page(self, idx: int):
        if len(self._report.pages) <= 1:
            return
        self._report.pages.pop(idx)
        pw = self._page_widgets.pop(idx)
        self._stack.removeWidget(pw)
        pw.deleteLater()
        new_idx = min(self._current_page, len(self._report.pages) - 1)
        self._current_page = -1
        self._switch_page(new_idx)
        self.changed.emit()

    def _lock_report(self):
        dlg = StyledModalDialog(
            self, "Lock this report?",
            "This will permanently lock the report and cannot be undone.\nAre you sure?",
            primary_text="Yes, Lock",
            secondary_text="Cancel",
        )
        dlg.primary_btn.clicked.connect(dlg.accept)
        dlg.secondary_btn.clicked.connect(dlg.reject)
        if dlg.exec_() != dlg.Accepted:
            return
        self._report.locked = True
        self._lock_btn.setEnabled(False)
        self._lock_btn.setText("🔒  Locked")
        self._add_page_btn.setEnabled(False)
        for pw in self._page_widgets:
            pw.lock()
        self._refresh_page_tabs()
        self.changed.emit()

    def update_project_info(self, info: dict):
        for pw in self._page_widgets:
            pw.update_project_info(info)

    def refresh_logo(self):
        for pw in self._page_widgets:
            pw.refresh_logo(self._logo_fn)


# ── Main ReportWidget ─────────────────────────────────────────────────────────

class ReportWidget(QWidget):
    """Top-level Report screen."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reports:        List[Report]        = [_default_report(1)]
        self._editors:        List[ReportEditor]  = []
        self._current_idx     = 0
        self._next_id         = 2
        self._project_info: dict = {}
        self._logo_pix:  Optional[QPixmap] = None
        self._logo_path: str = ""
        self.setStyleSheet(f"background: {_BG};")
        self._build_ui()
        self._rebuild_all()
        self._switch_report(0)

    # ── build ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        top = QWidget()
        top.setFixedHeight(46)
        top.setStyleSheet(f"background: {_BG}; border-bottom: 1px solid {_BORDER};")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 0, 16, 0)
        title = QLabel("Report")
        title.setFont(make_font(size=15, bold=True))
        title.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        subtitle = QLabel("Meeting reports with pages, photos and formal sign-off.")
        subtitle.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
        t_col = QVBoxLayout()
        t_col.setSpacing(1)
        t_col.addWidget(title)
        t_col.addWidget(subtitle)
        tl.addLayout(t_col)
        tl.addStretch()
        new_btn = QPushButton("＋  New Report")
        new_btn.setStyleSheet(_BTN_PRIMARY)
        new_btn.setFixedHeight(30)
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.clicked.connect(self._add_report)
        tl.addWidget(new_btn)
        root.addWidget(top)

        # Report tabs bar
        self._tabs_bar = QWidget()
        self._tabs_bar.setFixedHeight(40)
        self._tabs_bar.setStyleSheet(f"background: {_BG}; border-bottom: 2px solid {_BORDER};")
        self._tabs_layout = QHBoxLayout(self._tabs_bar)
        self._tabs_layout.setContentsMargins(12, 5, 12, 5)
        self._tabs_layout.setSpacing(6)
        self._tabs_layout.addStretch()
        root.addWidget(self._tabs_bar)

        # Stacked editors
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

    # ── report management ──────────────────────────────────────────────────────

    def _rebuild_all(self):
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.deleteLater()
        self._editors.clear()

        for report in self._reports:
            ed = ReportEditor(report, self._get_logo, self._set_logo)
            ed.changed.connect(self.changed)
            self._stack.addWidget(ed)
            self._editors.append(ed)
            if report.id >= self._next_id:
                self._next_id = report.id + 1

        if self._project_info:
            for ed in self._editors:
                ed.update_project_info(self._project_info)

    def _refresh_tabs(self):
        while self._tabs_layout.count():
            item = self._tabs_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, report in enumerate(self._reports):
            is_active = (i == self._current_idx)
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            ch = QHBoxLayout(container)
            ch.setContentsMargins(0, 0, 0, 0)
            ch.setSpacing(0)
            btn = QPushButton(report.display_name())
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_TAB_ACTIVE_L if is_active else _TAB_INACTIVE_L)
            btn.clicked.connect(lambda _, idx=i: self._switch_report(idx))
            close = QPushButton("×")
            close.setFixedSize(22, 28)
            close.setCursor(Qt.PointingHandCursor)
            close.setStyleSheet(_CLOSE_ACTIVE if is_active else _CLOSE_INACTIVE)
            close.clicked.connect(lambda _, idx=i: self._remove_report(idx))
            ch.addWidget(btn)
            ch.addWidget(close)
            self._tabs_layout.addWidget(container)

        self._tabs_layout.addStretch()

    def _switch_report(self, idx: int):
        self._current_idx = idx
        if 0 <= idx < len(self._editors):
            self._stack.setCurrentWidget(self._editors[idx])
        self._refresh_tabs()

    def _add_report(self):
        report = _default_report(self._next_id)
        if self._project_info:
            report.project_name      = self._project_info.get("title", "")
            report.project_reference = self._project_info.get("number", "")
        self._next_id += 1
        self._reports.append(report)
        ed = ReportEditor(report, self._get_logo, self._set_logo)
        ed.changed.connect(self.changed)
        if self._project_info:
            ed.update_project_info(self._project_info)
        self._stack.addWidget(ed)
        self._editors.append(ed)
        self._switch_report(len(self._reports) - 1)
        self.changed.emit()

    def _remove_report(self, idx: int):
        report = self._reports[idx]
        dlg = StyledModalDialog(
            self, "Remove Report",
            f"Remove '{report.display_name()}'?\nThis cannot be undone.",
            primary_text="Remove",
            secondary_text="Cancel",
        )
        dlg.primary_btn.clicked.connect(dlg.accept)
        dlg.secondary_btn.clicked.connect(dlg.reject)
        if dlg.exec_() != dlg.Accepted:
            return
        self._reports.pop(idx)
        ed = self._editors.pop(idx)
        self._stack.removeWidget(ed)
        ed.deleteLater()
        new_idx = min(self._current_idx, len(self._reports) - 1) if self._reports else 0
        self._current_idx = -1
        if self._reports:
            self._switch_report(new_idx)
        else:
            self._refresh_tabs()
        self.changed.emit()

    # ── logo management ────────────────────────────────────────────────────────

    def _get_logo(self) -> Optional[QPixmap]:
        return self._logo_pix

    def _set_logo(self, pix: QPixmap, path: str):
        self._logo_pix  = pix
        self._logo_path = path
        for ed in self._editors:
            ed.refresh_logo()
        self.changed.emit()

    # ── project info ──────────────────────────────────────────────────────────

    def update_project_info(self, info: dict):
        self._project_info = info
        for ed in self._editors:
            ed.update_project_info(info)

    # ── serialisation ──────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        def _ser_cell(c: PhotoCell) -> dict:
            return {"caption": c.caption, "image_path": c.image_path}
        def _ser_photo_row(pr: PhotoRow) -> dict:
            return {"photos": [_ser_cell(c) for c in pr.photos]}
        def _ser_page(p: ReportPage) -> dict:
            return {"id": p.id, "followup": p.followup, "comments": p.comments,
                    "photo_rows": [_ser_photo_row(pr) for pr in p.photo_rows]}
        def _ser_att(a: AttendeeColumn) -> dict:
            return {"header": a.header, "name": a.name}
        def _ser_extra(e: CompanyRow) -> dict:
            return {"label": e.label, "value": e.value}
        def _ser_report(r: Report) -> dict:
            return {
                "id": r.id, "date": r.date, "locked": r.locked,
                "launch_deadline": r.launch_deadline,
                "project_name": r.project_name, "project_reference": r.project_reference,
                "project_manager": r.project_manager, "technical_manager": r.technical_manager,
                "quality_lead": r.quality_lead,
                "company_extras":  [_ser_extra(e) for e in r.company_extras],
                "partner_1": r.partner_1, "partner_2": r.partner_2, "partner_3": r.partner_3,
                "partner_extras":  [_ser_extra(e) for e in r.partner_extras],
                "attendees": [_ser_att(a) for a in r.attendees],
                "pages": [_ser_page(p) for p in r.pages],
            }
        return {
            "logo_path": self._logo_path,
            "reports":   [_ser_report(r) for r in self._reports],
        }

    def set_data(self, data: dict):
        self._logo_path = data.get("logo_path", "")
        if self._logo_path:
            pix = QPixmap(self._logo_path)
            if not pix.isNull():
                self._logo_pix = pix

        reports = []
        for rd in data.get("reports", []):
            r = Report(
                id=rd["id"], date=rd.get("date", ""), locked=rd.get("locked", False),
                launch_deadline=rd.get("launch_deadline", ""),
                project_name=rd.get("project_name", ""),
                project_reference=rd.get("project_reference", ""),
                project_manager=rd.get("project_manager", ""),
                technical_manager=rd.get("technical_manager", ""),
                quality_lead=rd.get("quality_lead", ""),
                company_extras=[CompanyRow(**e) for e in rd.get("company_extras", [])],
                partner_1=rd.get("partner_1", ""), partner_2=rd.get("partner_2", ""),
                partner_3=rd.get("partner_3", ""),
                partner_extras=[CompanyRow(**e) for e in rd.get("partner_extras", [])],
                attendees=[AttendeeColumn(**a) for a in rd.get("attendees", [])],
            )
            for pd in rd.get("pages", []):
                page = ReportPage(id=pd["id"], followup=pd.get("followup", ""),
                                  comments=pd.get("comments", ""))
                for prd in pd.get("photo_rows", []):
                    pr = PhotoRow(photos=[
                        PhotoCell(**c) for c in prd.get("photos", [])
                    ])
                    page.photo_rows.append(pr)
                r.pages.append(page)
            reports.append(r)

        if reports:
            self._reports = reports
        self._rebuild_all()
        self._switch_report(0)
