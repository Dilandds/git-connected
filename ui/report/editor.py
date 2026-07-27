"""ReportEditor — page tab bar, lock flow, and stacked PageWidgets for one report."""
from typing import Callable, List

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QStackedWidget,
)
from PyQt5.QtCore import Qt, pyqtSignal

from .models import Report, ReportPage, PhotoRow
from .shared import (
    _BG, _BORDER,
    _BTN_SMALL,
    _TAB_ACTIVE, _TAB_INACTIVE, _TAB_ACTIVE_L, _TAB_INACTIVE_L,
    _CLOSE_ACTIVE, _CLOSE_INACTIVE,
)
from .page_widget import PageWidget
from i18n import t


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

        self._page_bar = QWidget()
        self._page_bar.setFixedHeight(38)
        self._page_bar.setStyleSheet(f"background: {_BG}; border-bottom: 1px solid {_BORDER};")
        self._page_layout = QHBoxLayout(self._page_bar)
        self._page_layout.setContentsMargins(12, 4, 12, 4)
        self._page_layout.setSpacing(6)

        self._add_page_btn = QPushButton(t("project.report.add_page"))
        self._add_page_btn.setStyleSheet(_BTN_SMALL)
        self._add_page_btn.setFixedHeight(26)
        self._add_page_btn.setCursor(Qt.PointingHandCursor)
        self._add_page_btn.clicked.connect(self._add_page)

        self._page_layout.addStretch()
        root.addWidget(self._page_bar)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

    def _refresh_page_tabs(self):
        _permanent = (self._add_page_btn,)
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
                btn = QPushButton(f"{t('project.report.page_label')} {i + 1}")
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
                btn = QPushButton(f"{t('project.report.page_label')} 1")
                btn.setFixedHeight(26)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setStyleSheet(_TAB_ACTIVE if is_active else _TAB_INACTIVE)
                btn.clicked.connect(lambda: self._switch_page(0))
                self._page_layout.addWidget(btn)

        self._page_layout.addWidget(self._add_page_btn)
        self._page_layout.addStretch()

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

    def add_screenshot_to_report(self, pixmap) -> bool:
        """Forward to the currently visible page."""
        if 0 <= self._current_page < len(self._page_widgets):
            return self._page_widgets[self._current_page].add_screenshot_to_report(pixmap)
        return False

    # ── public API ────────────────────────────────────────────────────────────

    def update_project_info(self, info: dict):
        for pw in self._page_widgets:
            pw.update_project_info(info)

    def refresh_logo(self):
        for pw in self._page_widgets:
            pw.refresh_logo(self._logo_fn)
