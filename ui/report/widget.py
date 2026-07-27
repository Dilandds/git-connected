"""
ReportWidget — top-level Report screen.
Manages the report tab bar, shared logo state, and serialization.
"""
import logging
from typing import List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

from ui.styles import make_font
from ui.modal_utils import MessageModal
from .models import (
    Report, ReportPage, PhotoRow, PhotoCell,
    AttendeeColumn, CompanyRow, _default_report,
)
from .shared import (
    _BG, _BORDER, _TEXT, _MUTED,
    _BTN_PRIMARY,
    _TAB_ACTIVE_L, _TAB_INACTIVE_L,
    _CLOSE_ACTIVE, _CLOSE_INACTIVE,
)
from .editor import ReportEditor
from i18n import t

logger = logging.getLogger(__name__)


class ReportWidget(QWidget):
    """Top-level Report screen."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reports:     List[Report]       = [_default_report(1)]
        self._editors:     List[ReportEditor] = []
        self._current_idx  = 0
        self._next_id      = 2
        self._project_info: dict = {}
        self._logo_pix:  Optional[QPixmap] = None
        self._logo_path: str = ""
        self.setStyleSheet(f"background: {_BG};")
        self._build_ui()
        self._rebuild_all()
        self._switch_report(0)

    # ── construction ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QWidget()
        top.setFixedHeight(46)
        top.setStyleSheet(f"background: {_BG}; border-bottom: 1px solid {_BORDER};")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 0, 16, 0)
        title = QLabel(t("project.report.title"))
        title.setFont(make_font(size=15, bold=True))
        title.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        subtitle = QLabel(t("project.report.subtitle"))
        subtitle.setStyleSheet(
            f"color: {_MUTED}; font-size: 14px; background: transparent; border: none;"
        )
        t_col = QVBoxLayout()
        t_col.setSpacing(1)
        t_col.addWidget(title)
        t_col.addWidget(subtitle)
        tl.addLayout(t_col)
        tl.addStretch()
        new_btn = QPushButton(t("project.report.new_report"))
        new_btn.setStyleSheet(_BTN_PRIMARY)
        new_btn.setFixedHeight(30)
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.clicked.connect(self._add_report)
        tl.addWidget(new_btn)
        root.addWidget(top)

        self._tabs_bar = QWidget()
        self._tabs_bar.setFixedHeight(40)
        self._tabs_bar.setStyleSheet(
            f"background: {_BG}; border-bottom: 2px solid {_BORDER};"
        )
        self._tabs_layout = QHBoxLayout(self._tabs_bar)
        self._tabs_layout.setContentsMargins(12, 5, 12, 5)
        self._tabs_layout.setSpacing(6)
        self._tabs_layout.addStretch()
        root.addWidget(self._tabs_bar)

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
        dlg = MessageModal(
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

    def get_logo_pixmap(self) -> Optional[QPixmap]:
        """Public accessor for the company logo set on this report — used by
        TheProjectWidget to auto-copy the same logo into the Quality Control
        screen so it doesn't need to be uploaded twice."""
        return self._logo_pix

    def _set_logo(self, pix: QPixmap, path: str):
        self._logo_pix  = pix
        self._logo_path = path
        for ed in self._editors:
            ed.refresh_logo()
        self.changed.emit()

    def add_screenshot_to_report(self, pixmap: QPixmap) -> bool:
        """Send a QPixmap to the first empty photo slot in the current report/page."""
        if 0 <= self._current_idx < len(self._editors):
            return self._editors[self._current_idx].add_screenshot_to_report(pixmap)
        return False

    # ── public API ────────────────────────────────────────────────────────────

    def update_project_info(self, info: dict):
        self._project_info = info
        for ed in self._editors:
            ed.update_project_info(info)

    # ── serialisation ──────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        def _ser_cell(c: PhotoCell) -> dict:
            return {"caption": c.caption, "image_path": c.image_path}

        def _ser_block(b) -> dict:
            return {
                "photos": [_ser_cell(c) for c in b.photos],
                "comment": b.comment,
            }

        def _ser_page(p: ReportPage) -> dict:
            return {
                "id": p.id, "followup": p.followup, "comments": p.comments,
                "photo_blocks": [_ser_block(b) for b in p.photo_blocks],
            }

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
                "project_photo_path": r.project_photo_path,
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
                project_photo_path=rd.get("project_photo_path", ""),
            )
            for pd in rd.get("pages", []):
                page = ReportPage(
                    id=pd["id"],
                    followup=pd.get("followup", ""),
                    comments=pd.get("comments", ""),
                )
                from .models import PhotoBlock
                for bd in pd.get("photo_blocks", []):
                    cells = [PhotoCell(**c) for c in bd.get("photos", [])]
                    while len(cells) < 6:
                        cells.append(PhotoCell())
                    blk = PhotoBlock(photos=cells, comment=bd.get("comment", ""))
                    page.photo_blocks.append(blk)
                # Migrate legacy photo_rows → one block per old row
                if not page.photo_blocks:
                    for prd in pd.get("photo_rows", []):
                        old_cells = [PhotoCell(**c) for c in prd.get("photos", [])]
                        cells = old_cells[:6]
                        while len(cells) < 6:
                            cells.append(PhotoCell())
                        page.photo_blocks.append(PhotoBlock(photos=cells))
                # Default: one empty block if none
                if not page.photo_blocks:
                    page.photo_blocks.append(PhotoBlock())
                r.pages.append(page)
            reports.append(r)

        if reports:
            self._reports = reports
        self._rebuild_all()
        self._switch_report(0)
