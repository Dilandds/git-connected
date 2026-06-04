"""Row 4: Sub-stage tab bar + parts table."""
from typing import Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QInputDialog, QDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal
from ui.modal_utils import ask_yes_no_dialog
from .models import TraceStage, TraceSubStage
from .shared import (
    _BG, _CARD, _BORDER, _TEXT, _MUTED, _ACCENT, _ACCENT_H,
    _BTN_SMALL,
)
from .parts_table import _PartsTable


class _SubStagePanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stage: Optional[TraceStage] = None
        self._current_sub = 0
        self.setStyleSheet(f'background: {_CARD};')
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tab_bar = QWidget()
        self._tab_bar.setFixedHeight(38)
        self._tab_bar.setStyleSheet(f'background: {_BG}; border-bottom: 1px solid {_BORDER};')
        self._tab_layout = QHBoxLayout(self._tab_bar)
        self._tab_layout.setContentsMargins(12, 4, 12, 4)
        self._tab_layout.setSpacing(6)
        self._tab_layout.addStretch()
        root.addWidget(self._tab_bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: {_CARD}; border: none; }}
            QScrollBar:vertical {{ background: {_BG}; width: 8px; border-radius: 4px; }}
            QScrollBar::handle:vertical {{ background: {_BORDER}; border-radius: 4px; }}
        """)
        self._content = QWidget(); self._content.setStyleSheet(f'background: {_CARD};')
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._scroll.setWidget(self._content)
        root.addWidget(self._scroll, 1)

        footer = QWidget(); footer.setFixedHeight(24)
        footer.setStyleSheet(f'background: #f1f3f5; border-top: 1px solid {_BORDER};')
        fl = QHBoxLayout(footer); fl.setContentsMargins(12, 0, 12, 0)
        hint = QLabel('ℹ  Click on a sub-stage to view details, add comments, and track progress.')
        hint.setStyleSheet(f'color: {_MUTED}; font-size: 9px; background: transparent; border: none;')
        fl.addWidget(hint)
        root.addWidget(footer)

    def load_stage(self, stage: Optional[TraceStage]):
        self._stage = stage
        self._current_sub = 0
        self._refresh_tabs()
        self._refresh_table()

    def _refresh_tabs(self):
        while self._tab_layout.count():
            item = self._tab_layout.takeAt(0)
            if item.widget():
                item.widget().hide(); item.widget().setParent(None)

        if not self._stage:
            self._tab_layout.addStretch()
            return

        snum = self._stage.number
        for i, sub in enumerate(self._stage.sub_stages):
            is_active = (i == self._current_sub)

            _ta = f"""
                QPushButton {{
                    background: {_ACCENT}; color: white; border: none;
                    border-radius: 5px 0 0 5px; padding: 4px 10px;
                    font-size: 10px; font-weight: bold;
                }}
            """
            _ti = f"""
                QPushButton {{
                    background: transparent; color: {_MUTED};
                    border: 1px solid {_BORDER}; border-radius: 5px 0 0 5px;
                    padding: 4px 10px; font-size: 10px;
                }}
                QPushButton:hover {{ color: {_TEXT}; border-color: {_ACCENT}; background: #e8f0fe; }}
            """
            _ca = f"""
                QPushButton {{
                    background: {_ACCENT}; color: rgba(255,255,255,0.6);
                    border: none; border-left: 1px solid rgba(255,255,255,0.2);
                    border-radius: 0 5px 5px 0; font-size: 12px; font-weight: bold; padding: 0 5px;
                }}
                QPushButton:hover {{ color: white; background: #ef4444; }}
            """
            _ci = f"""
                QPushButton {{
                    background: transparent; color: {_MUTED};
                    border: 1px solid {_BORDER}; border-left: none;
                    border-radius: 0 5px 5px 0; font-size: 12px; font-weight: bold; padding: 0 5px;
                }}
                QPushButton:hover {{ color: #ef4444; background: #fee2e2; border-color: #fca5a5; }}
            """

            container = QWidget(); container.setStyleSheet('background: transparent;')
            ch = QHBoxLayout(container); ch.setContentsMargins(0, 0, 0, 0); ch.setSpacing(0)

            btn = QPushButton(f'{snum}.{i + 1}  {sub.name}')
            btn.setFixedHeight(26)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_ta if is_active else _ti)
            btn.setToolTip('Double-click to rename')
            btn.clicked.connect(lambda _, idx=i: self._switch_sub(idx))
            btn.mouseDoubleClickEvent = lambda _e, idx=i: self._rename_sub(idx)

            close = QPushButton('×')
            close.setFixedSize(20, 26)
            close.setCursor(Qt.PointingHandCursor)
            close.setStyleSheet(_ca if is_active else _ci)
            close.clicked.connect(lambda _, idx=i: self._remove_sub(idx))

            ch.addWidget(btn); ch.addWidget(close)
            self._tab_layout.addWidget(container)

        add_btn = QPushButton('＋  Add Sub-stage')
        add_btn.setStyleSheet(_BTN_SMALL)
        add_btn.setFixedHeight(26)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_sub)
        self._tab_layout.addWidget(add_btn)
        self._tab_layout.addStretch()

    def _switch_sub(self, idx: int):
        self._current_sub = idx
        self._refresh_tabs()
        self._refresh_table()

    def _rename_sub(self, idx: int):
        if not self._stage or idx >= len(self._stage.sub_stages):
            return
        sub = self._stage.sub_stages[idx]
        name, ok = QInputDialog.getText(self, 'Rename Sub-stage', 'Name:', text=sub.name)
        if ok and name.strip():
            sub.name = name.strip()
            self._refresh_tabs()
            self.changed.emit()

    def _add_sub(self):
        if not self._stage:
            return
        new_id = max((s.id for s in self._stage.sub_stages), default=0) + 1
        n = len(self._stage.sub_stages) + 1
        self._stage.sub_stages.append(TraceSubStage(id=new_id, name=f'Sub-stage {n}'))
        self._current_sub = len(self._stage.sub_stages) - 1
        self._refresh_tabs()
        self._refresh_table()
        self.changed.emit()

    def _remove_sub(self, idx: int):
        if not self._stage:
            return
        sub = self._stage.sub_stages[idx]
        if not ask_yes_no_dialog(self, 'Remove Sub-stage', f"Remove '{sub.name}' and all its parts?"):
            return
        self._stage.sub_stages.pop(idx)
        self._current_sub = min(self._current_sub, max(0, len(self._stage.sub_stages) - 1))
        self._refresh_tabs()
        self._refresh_table()
        self.changed.emit()

    def _refresh_table(self):
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().hide(); item.widget().setParent(None)

        if not self._stage or not self._stage.sub_stages:
            msg = QLabel('No sub-stages yet. Click ＋ Add Sub-stage to begin.')
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet(
                f'color: {_MUTED}; font-size: 11px; '
                f'background: transparent; border: none; padding: 40px;'
            )
            self._content_layout.addWidget(msg)
            return

        idx = min(self._current_sub, len(self._stage.sub_stages) - 1)
        sub = self._stage.sub_stages[idx]
        table = _PartsTable(sub)
        table.changed.connect(self.changed)
        self._content_layout.addWidget(table)
        self._content_layout.addStretch()
