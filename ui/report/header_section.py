"""Full meeting-report header — logo, date, company/partners grid, and attendees table."""
from typing import Callable, List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QFileDialog, QDateEdit,
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon

from .models import Report, AttendeeColumn, CompanyRow
from .shared import (
    _BG, _CARD, _BORDER, _MUTED, _ACCENT, _HDR_TEXT,
    _INPUT, _BTN_OUTLINE,
    _card, _field, _VerticalLabel,
)


class HeaderSection(QWidget):
    """The full meeting report header — logo, date, company grid, attendees."""

    changed = pyqtSignal()

    def __init__(self, report: Report, logo_fn: Callable[[], Optional[QPixmap]],
                 set_logo_fn: Callable[[QPixmap, str], None], parent=None):
        super().__init__(parent)
        self._report   = report
        self._logo_fn  = logo_fn
        self._set_logo = set_logo_fn
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

        # Company logo
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

        pix = self._logo_fn()
        if pix:
            self._apply_logo(pix)

        # Project photo
        self._project_photo_btn = QPushButton("＋  Add project\nphoto")
        self._project_photo_btn.setFixedSize(110, 60)
        self._project_photo_btn.setCursor(Qt.PointingHandCursor)
        self._project_photo_btn.setStyleSheet(f"""
            QPushButton {{
                background: #f1f3f5; border: 1px dashed {_BORDER};
                border-radius: 6px; color: {_MUTED}; font-size: 9px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
        """)
        self._project_photo_btn.clicked.connect(self._upload_project_photo)
        tl.addWidget(self._project_photo_btn)

        if self._report.project_photo_path:
            pix2 = QPixmap(self._report.project_photo_path)
            if not pix2.isNull():
                self._apply_project_photo(pix2)

        # Title + project fields
        mid = QVBoxLayout()
        mid.setSpacing(4)

        title_row = QHBoxLayout()
        meeting_lbl = QLabel("Meeting report of")
        meeting_lbl.setStyleSheet(
            f"color: {_HDR_TEXT}; font-size: 13px; font-weight: bold; background: transparent; border: none;"
        )
        self._date_edit = QDateEdit()
        self._date_edit.setDisplayFormat("dd/MM/yyyy")
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setStyleSheet(_INPUT)
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
        att_lbl.setStyleSheet(
            f"color: {_MUTED}; font-size: 10px; font-weight: bold; background: transparent; border: none;"
        )
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
            lbl.setStyleSheet(
                f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;"
            )
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
            if attr == "_f_pm":
                inp.textChanged.connect(
                    lambda v: setattr(self._report, 'project_manager', v) or self.changed.emit()
                )
            elif attr == "_f_tm":
                inp.textChanged.connect(
                    lambda v: setattr(self._report, 'technical_manager', v) or self.changed.emit()
                )
            elif attr == "_f_ql":
                inp.textChanged.connect(
                    lambda v: setattr(self._report, 'quality_lead', v) or self.changed.emit()
                )
            elif attr == "_f_p1":
                inp.textChanged.connect(
                    lambda v: setattr(self._report, 'partner_1', v) or self.changed.emit()
                )
            elif attr == "_f_p2":
                inp.textChanged.connect(
                    lambda v: setattr(self._report, 'partner_2', v) or self.changed.emit()
                )
            elif attr == "_f_p3":
                inp.textChanged.connect(
                    lambda v: setattr(self._report, 'partner_3', v) or self.changed.emit()
                )
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
        lbl_inp.textChanged.connect(
            lambda v, e=extra: setattr(e, 'label', v) or self.changed.emit()
        )
        val_inp = _field("")
        val_inp.setText(extra.value)
        val_inp.textChanged.connect(
            lambda v, e=extra: setattr(e, 'value', v) or self.changed.emit()
        )
        r.addWidget(lbl_inp)
        r.addWidget(val_inp, 1)
        if at_end:
            layout.addLayout(r)
        else:
            layout.insertLayout(layout.count() - 1, r)

    def _add_extra(self, layout: QVBoxLayout, extras: List[CompanyRow], btn: QPushButton):
        extra = CompanyRow("other (To be specified)", "")
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
        hdr_inp.textChanged.connect(
            lambda v, a=att: setattr(a, 'header', v) or self.changed.emit()
        )
        name_inp = _field("Name")
        name_inp.setText(att.name)
        name_inp.setFixedWidth(110)
        name_inp.textChanged.connect(
            lambda v, a=att: setattr(a, 'name', v) or self.changed.emit()
        )
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

    def _upload_project_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Project Photo", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            pix = QPixmap(path)
            if not pix.isNull():
                self._report.project_photo_path = path
                self._apply_project_photo(pix)
                self.changed.emit()

    def _apply_project_photo(self, pix: QPixmap):
        scaled = pix.scaled(
            self._project_photo_btn.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self._project_photo_btn.setIcon(QIcon(scaled))
        self._project_photo_btn.setIconSize(self._project_photo_btn.size())
        self._project_photo_btn.setText("")

    # ── public API ────────────────────────────────────────────────────────────

    def update_project_info(self, info: dict):
        self._f_project.setText(info.get("title", "") or "")
        self._report.project_name = self._f_project.text()
        self._f_reference.setText(info.get("number", "") or "")
        self._report.project_reference = self._f_reference.text()

    def lock(self):
        self._logo_btn.setEnabled(False)
        self._project_photo_btn.setEnabled(False)
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
