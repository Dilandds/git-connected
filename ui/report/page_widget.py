"""Scrollable content widget for a single report page."""
from typing import Callable, List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFrame, QScrollArea, QTextEdit,
)
from PyQt5.QtCore import Qt, pyqtSignal

from .models import Report, ReportPage, PhotoRow
from .shared import _BG, _BORDER, _INPUT, _BTN_OUTLINE, _card, _sep, _lbl
from .photo_row import PhotoRowWidget
from .header_section import HeaderSection


class PageWidget(QScrollArea):
    """Content of a single report page."""

    changed = pyqtSignal()

    def __init__(self, page: ReportPage, report: Report, is_first: bool,
                 logo_fn: Callable, set_logo_fn: Callable, parent=None):
        super().__init__(parent)
        self._page    = page
        self._report  = report
        self._is_first = is_first
        self._photo_row_widgets: List[PhotoRowWidget] = []
        self._header: Optional[HeaderSection] = None
        self._locked = False

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(f"""
            QScrollArea {{ background: {_BG}; border: none; }}
            QScrollBar:vertical {{ background: {_BG}; width: 6px; border-radius: 3px; }}
            QScrollBar::handle:vertical {{ background: {_BORDER}; border-radius: 3px; }}
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
        w = PhotoRowWidget(pr)
        w.changed.connect(self.changed)
        self._photos_layout.addWidget(w)
        self._photo_row_widgets.append(w)

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
        self._add_photo_row_btn.setEnabled(False)
        self._followup.setReadOnly(True)
        self._comments.setReadOnly(True)
        for w in self._photo_row_widgets:
            w.lock()
        if self._header:
            self._header.lock()
