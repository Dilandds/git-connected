"""Scrollable content widget for a single report page."""
from typing import Callable, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QFrame, QScrollArea, QTextEdit,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

from .models import Report, ReportPage
from .shared import _BG, _BORDER, _ACCENT, _INPUT, _card, _sep, _lbl
from i18n import t
from .photo_block import PhotoBlockFlow
from .header_section import HeaderSection


class PageWidget(QScrollArea):
    """Content of a single report page."""

    changed = pyqtSignal()

    def __init__(self, page: ReportPage, report: Report, is_first: bool,
                 logo_fn: Callable, set_logo_fn: Callable, parent=None):
        super().__init__(parent)
        self._page     = page
        self._report   = report
        self._is_first = is_first
        self._header: Optional[HeaderSection] = None
        self._locked   = False

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

        if is_first:
            self._header = HeaderSection(report, logo_fn, set_logo_fn)
            self._header.changed.connect(self.changed)
            self._root.addWidget(self._header)

        # Production follow-up
        fu_card = _card()
        fl = QVBoxLayout(fu_card)
        fl.setContentsMargins(14, 10, 14, 10)
        fl.setSpacing(6)
        fl.addWidget(_lbl(t("project.report.page_follow_title"), muted=False, bold=True))
        fl.addWidget(_sep())
        self._followup = QTextEdit()
        self._followup.setPlaceholderText(t("project.report.page_follow_ph"))
        self._followup.setMinimumHeight(80)
        self._followup.setStyleSheet(_INPUT)
        self._followup.setPlainText(page.followup)
        self._followup.textChanged.connect(
            lambda: setattr(self._page, 'followup', self._followup.toPlainText()) or self.changed.emit()
        )
        fl.addWidget(self._followup)
        self._root.addWidget(fu_card)

        # Photos section — block-based flow (2×3 photos per block + comment)
        photos_card = _card()
        pl = QVBoxLayout(photos_card)
        pl.setContentsMargins(14, 10, 14, 10)
        pl.setSpacing(8)
        ph_hdr = QHBoxLayout()
        ph_hdr.addWidget(_lbl(t("project.report.page_components"), muted=False, bold=True))
        ph_hdr.addStretch()
        pl.addLayout(ph_hdr)
        pl.addWidget(_sep())

        self._flow = PhotoBlockFlow(page)
        self._flow.changed.connect(self.changed)
        pl.addWidget(self._flow)
        self._root.addWidget(photos_card)

        # Comments
        co_card = _card()
        co = QVBoxLayout(co_card)
        co.setContentsMargins(14, 10, 14, 10)
        co.setSpacing(6)
        co.addWidget(_lbl(t("project.report.page_comments"), muted=False, bold=True))
        co.addWidget(_sep())
        self._comments = QTextEdit()
        self._comments.setPlaceholderText(t("project.report.page_comments_ph"))
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

    def add_screenshot_to_report(self, pixmap: QPixmap) -> bool:
        """Fill the first empty block slot (or add a new block) with this screenshot."""
        if not isinstance(pixmap, QPixmap) or pixmap.isNull():
            return False
        return self._flow.add_screenshot(pixmap)

    # ── public API ────────────────────────────────────────────────────────────

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
        self._followup.setReadOnly(True)
        self._comments.setReadOnly(True)
        self._flow.lock()
        if self._header:
            self._header.lock()
