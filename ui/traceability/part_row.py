from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QMenu, QWidget,
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from .models import TracePart
from .shared import (
    _TEXT, _MUTED, _BORDER, _CARD, _ACCENT,
    _BTN_ICON, _MENU_STYLE, _PART_PALETTE,
    _vline, _status_badge, _PartBadge, _ProgressBar,
)


class _PartRow(QFrame):
    edit_requested    = pyqtSignal(object)
    delete_requested  = pyqtSignal(object)
    comment_requested = pyqtSignal(object)

    def __init__(self, part: TracePart, index: int, parent=None):
        super().__init__(parent)
        self._part  = part
        self._index = index
        self.setStyleSheet(f"""
            QFrame {{
                background: {_CARD}; border: none;
                border-bottom: 1px solid {_BORDER};
            }}
        """)
        self.setFixedHeight(56)
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(0)

        # Badge + name
        bw = QWidget(); bw.setFixedWidth(100); bw.setStyleSheet('background: transparent;')
        bl = QHBoxLayout(bw); bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(6)
        bl.addWidget(_PartBadge(self._index + 1, _PART_PALETTE[self._index % len(_PART_PALETTE)]))
        n = QLabel(self._part.name)
        n.setStyleSheet(
            f'color: {_TEXT}; font-size: 10px; font-weight: bold; background: transparent; border: none;'
        )
        bl.addWidget(n)
        lay.addWidget(bw)
        lay.addWidget(_vline())
        lay.addSpacing(6)

        # Suppliers & Action
        sw = QWidget(); sw.setFixedWidth(160); sw.setStyleSheet('background: transparent;')
        sl = QVBoxLayout(sw); sl.setContentsMargins(0, 0, 0, 0); sl.setSpacing(1)
        s1 = QLabel(f'Suppliers: {self._part.suppliers}' if self._part.suppliers else 'Suppliers: —')
        s1.setStyleSheet(f'color: {_TEXT}; font-size: 9px; background: transparent; border: none;')
        s1.setWordWrap(True)
        s2 = QLabel(f'Action: {self._part.action}' if self._part.action else '')
        s2.setStyleSheet(f'color: {_MUTED}; font-size: 9px; background: transparent; border: none;')
        s2.setWordWrap(True)
        sl.addWidget(s1); sl.addWidget(s2)
        lay.addWidget(sw)
        lay.addWidget(_vline())
        lay.addSpacing(6)

        # Current task
        tw = QLabel(self._part.current_task or '—')
        tw.setWordWrap(True)
        tw.setFixedWidth(150)
        tw.setStyleSheet(f'color: {_TEXT}; font-size: 9px; background: transparent; border: none;')
        lay.addWidget(tw)
        lay.addWidget(_vline())
        lay.addSpacing(6)

        # Start date
        sd = QLabel(self._part.start_date or '—')
        sd.setFixedWidth(75)
        sd.setStyleSheet(f'color: {_MUTED}; font-size: 9px; background: transparent; border: none;')
        lay.addWidget(sd)
        lay.addWidget(_vline())
        lay.addSpacing(6)

        # Due date
        dd = QLabel(self._part.due_date or '—')
        dd.setFixedWidth(75)
        dd.setStyleSheet(f'color: {_MUTED}; font-size: 9px; background: transparent; border: none;')
        lay.addWidget(dd)
        lay.addWidget(_vline())
        lay.addSpacing(6)

        # Status
        sb = _status_badge(self._part.status)
        sb.setFixedWidth(78)
        lay.addWidget(sb)
        lay.addWidget(_vline())
        lay.addSpacing(6)

        # Progress
        pw = QWidget(); pw.setFixedWidth(95); pw.setStyleSheet('background: transparent;')
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(2); pl.setAlignment(Qt.AlignVCenter)
        pct = QLabel(f'{self._part.progress} %')
        pct.setStyleSheet(
            f'color: {_TEXT}; font-size: 9px; font-weight: bold; background: transparent; border: none;'
        )
        pb = _ProgressBar(self._part.progress)
        pl.addWidget(pct); pl.addWidget(pb)
        lay.addWidget(pw)
        lay.addWidget(_vline())
        lay.addSpacing(6)

        # Comments
        cb = QPushButton(f'💬  {len(self._part.comments)}')
        cb.setStyleSheet(_BTN_ICON)
        cb.setFixedWidth(48)
        cb.setCursor(Qt.PointingHandCursor)
        cb.clicked.connect(lambda: self.comment_requested.emit(self._part))
        lay.addWidget(cb)
        lay.addStretch()

        # ⋮ context menu
        mb = QPushButton('⋮')
        mb.setFixedSize(24, 24)
        mb.setStyleSheet(_BTN_ICON)
        mb.setCursor(Qt.PointingHandCursor)
        mb.clicked.connect(lambda: self._show_menu(mb))
        lay.addWidget(mb)

    def _show_menu(self, btn: QPushButton):
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_STYLE)
        edit_a = menu.addAction('✎  Edit')
        del_a  = menu.addAction('🗑  Delete')
        chosen = menu.exec_(btn.mapToGlobal(QPoint(0, btn.height())))
        if chosen == edit_a:
            self.edit_requested.emit(self._part)
        elif chosen == del_a:
            self.delete_requested.emit(self._part)
