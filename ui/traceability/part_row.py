from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QMenu, QWidget,
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from .models import TracePart
from .shared import (
    _TEXT, _MUTED, _BORDER, _CARD, _ACCENT,
    _BTN_ICON, _MENU_STYLE, _PART_PALETTE,
    _PartBadge, _ProgressBar,
)

# Column widths — must match headers in parts_table.py
_W_TASK     = 260
_W_COMMENTS = 130
_W_DATE     = 105
_W_STATUS   = 108
_W_PROGRESS = 200   # includes % + bar + comment count
_ROW_H      = 80


def _date_cell(date_str: str) -> QWidget:
    """Calendar icon + date text."""
    w = QWidget(); w.setFixedWidth(_W_DATE); w.setStyleSheet('background: transparent;')
    lay = QHBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(5)
    icon = QLabel('📅')
    icon.setStyleSheet('font-size: 11px; background: transparent; border: none;')
    lbl = QLabel(date_str or '—')
    lbl.setStyleSheet(f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;')
    lay.addWidget(icon); lay.addWidget(lbl); lay.addStretch()
    return w


def _status_pill(status: str) -> QLabel:
    """Colored rounded-corner pill matching reference style."""
    colors = {
        'Completed':   ('#16a34a', '#dcfce7'),
        'In Progress': ('#2563eb', '#dbeafe'),
        'Upcoming':    ('#6b7280', '#f3f4f6'),
    }
    fg, bg = colors.get(status, ('#6b7280', '#f3f4f6'))
    lbl = QLabel(status)
    lbl.setFixedWidth(_W_STATUS)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(f"""
        QLabel {{
            background: {bg}; color: {fg};
            border: 1px solid {fg}55;
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 10px; font-weight: 700;
        }}
    """)
    return lbl


class _PartRow(QFrame):
    edit_requested    = pyqtSignal(object)
    delete_requested  = pyqtSignal(object)
    comment_requested = pyqtSignal(object)

    def __init__(self, part: TracePart, index: int,
                 stage_num: int = 1, sub_num: int = 1, parent=None):
        super().__init__(parent)
        self._part      = part
        self._index     = index
        self._stage_num = stage_num
        self._sub_num   = sub_num
        self.setStyleSheet(f"""
            QFrame {{
                background: {_CARD}; border: none;
                border-bottom: 1px solid {_BORDER};
            }}
        """)
        self.setFixedHeight(_ROW_H)
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 12, 10)
        lay.setSpacing(0)

        # ── Badge ─────────────────────────────────────────────────────────
        badge_label = f'{self._stage_num}.{self._sub_num}.{self._index + 1}'
        badge = _PartBadge(
            self._index + 1,
            _PART_PALETTE[self._index % len(_PART_PALETTE)],
            label=badge_label,
            size=38,
        )
        lay.addWidget(badge, 0, Qt.AlignVCenter)
        lay.addSpacing(12)

        # ── TASK: name + description ───────────────────────────────────────
        task_w = QWidget(); task_w.setFixedWidth(_W_TASK)
        task_w.setStyleSheet('background: transparent;')
        task_l = QVBoxLayout(task_w)
        task_l.setContentsMargins(0, 0, 0, 0); task_l.setSpacing(3)

        name_lbl = QLabel(self._part.name)
        name_lbl.setStyleSheet(
            f'color: {_TEXT}; font-size: 12px; font-weight: 700;'
            f' background: transparent; border: none;'
        )
        task_l.addWidget(name_lbl)

        desc_parts = []
        if self._part.suppliers:
            desc_parts.append(self._part.suppliers)
        if self._part.action:
            desc_parts.append(self._part.action)
        if self._part.current_task:
            desc_parts.append(self._part.current_task)
        desc_text = '  ·  '.join(desc_parts) if desc_parts else ''
        if desc_text:
            desc_lbl = QLabel(desc_text)
            desc_lbl.setStyleSheet(
                f'color: {_MUTED}; font-size: 10px;'
                f' background: transparent; border: none;'
            )
            desc_lbl.setWordWrap(True)
            task_l.addWidget(desc_lbl)

        lay.addWidget(task_w)
        lay.addStretch(1)

        # ── COMMENTS ──────────────────────────────────────────────────────
        comm_w = QWidget(); comm_w.setFixedWidth(_W_COMMENTS)
        comm_w.setStyleSheet('background: transparent;')
        comm_l = QHBoxLayout(comm_w)
        comm_l.setContentsMargins(0, 0, 0, 0); comm_l.setSpacing(6)

        if self._part.comments:
            comm_btn = QPushButton(f'💬  {len(self._part.comments)} comment{"s" if len(self._part.comments) != 1 else ""}')
        else:
            comm_btn = QPushButton('💬  Add comments')
        comm_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {_ACCENT}; font-size: 10px;
                padding: 0; text-align: left;
            }}
            QPushButton:hover {{ color: #1d4ed8; text-decoration: underline; }}
        """)
        comm_btn.setCursor(Qt.PointingHandCursor)
        comm_btn.clicked.connect(lambda: self.comment_requested.emit(self._part))
        comm_l.addWidget(comm_btn); comm_l.addStretch()
        lay.addWidget(comm_w)

        # ── START DATE ────────────────────────────────────────────────────
        lay.addWidget(_date_cell(self._part.start_date))

        # ── DUE DATE ──────────────────────────────────────────────────────
        lay.addWidget(_date_cell(self._part.due_date))

        # ── STATUS ────────────────────────────────────────────────────────
        lay.addWidget(_status_pill(self._part.status), 0, Qt.AlignVCenter)
        lay.addSpacing(12)

        # ── PROGRESS: % + bar + comment count ─────────────────────────────
        prog_w = QWidget(); prog_w.setFixedWidth(_W_PROGRESS)
        prog_w.setStyleSheet('background: transparent;')
        prog_l = QHBoxLayout(prog_w)
        prog_l.setContentsMargins(0, 0, 0, 0); prog_l.setSpacing(10)

        pct_bar = QWidget(); pct_bar.setStyleSheet('background: transparent;')
        pct_bar_l = QVBoxLayout(pct_bar)
        pct_bar_l.setContentsMargins(0, 0, 0, 0); pct_bar_l.setSpacing(4)

        pct_lbl = QLabel(f'{self._part.progress} %')
        pct_lbl.setStyleSheet(
            f'color: {_TEXT}; font-size: 12px; font-weight: 700;'
            f' background: transparent; border: none;'
        )
        pct_bar_l.addWidget(pct_lbl)
        pct_bar_l.addWidget(_ProgressBar(self._part.progress))
        prog_l.addWidget(pct_bar)

        # Comment count bubble
        n_comments = len(self._part.comments)
        count_btn = QPushButton(f'  {n_comments}')
        count_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {_MUTED}; font-size: 10px; padding: 0;
            }}
            QPushButton:hover {{ color: {_ACCENT}; }}
        """)
        count_btn.setFixedWidth(34)
        count_btn.setCursor(Qt.PointingHandCursor)
        count_btn.clicked.connect(lambda: self.comment_requested.emit(self._part))
        prog_l.addWidget(count_btn, 0, Qt.AlignVCenter)
        prog_l.addStretch()

        lay.addWidget(prog_w, 0, Qt.AlignVCenter)

        # ── ⋮ context menu ────────────────────────────────────────────────
        mb = QPushButton('⋮')
        mb.setFixedSize(28, 28)
        mb.setStyleSheet(_BTN_ICON)
        mb.setCursor(Qt.PointingHandCursor)
        mb.clicked.connect(lambda: self._show_menu(mb))
        lay.addWidget(mb, 0, Qt.AlignVCenter)

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
