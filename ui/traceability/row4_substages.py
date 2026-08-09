"""Row 4: Sub-stage tab bar + parts table."""
import copy
from typing import Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QDialog, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtGui import QFont
from ui.modal_utils import ask_yes_no_dialog
from .models import TraceStage, TraceSubStage
from .shared import (
    _BG, _CARD, _BORDER, _TEXT, _MUTED, _ACCENT, _ACCENT_H,
    _BTN_SMALL, tab_active_style, tab_inactive_style, _MarqueeLabel,
    _SEL_BG, _SEL_BORDER, _SEL_NUM,
)
from .parts_table import _PartsTable
from .dialogs import _RenameSubStageDialog
from i18n import t


class _SubStagePanel(QWidget):
    changed     = pyqtSignal()
    tab_switched = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stage: Optional[TraceStage] = None
        self._current_sub = 0
        self._is_main = False
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
        hint = QLabel(t('project.traceability.hint_substage'))
        hint.setStyleSheet(f'color: {_MUTED}; font-size: 11px; background: transparent; border: none;')
        fl.addWidget(hint)
        root.addWidget(footer)

    def load_stage(self, stage: Optional[TraceStage], is_main: bool = False):
        self._stage = stage
        self._is_main = is_main
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
        _ta = tab_active_style(_ACCENT)
        _ti = tab_inactive_style(_BORDER, _MUTED, _TEXT, _ACCENT)

        for i, sub in enumerate(self._stage.sub_stages):
            is_active = (i == self._current_sub)
            _ca = f"""
                QPushButton {{
                    background: {_SEL_BORDER}; color: rgba(255,255,255,0.6);
                    border: none; border-left: 1px solid rgba(255,255,255,0.2);
                    border-radius: 0 5px 5px 0; font-size: 14px; font-weight: bold; padding: 0 5px;
                }}
                QPushButton:hover {{ color: white; background: #ef4444; }}
            """
            _ci = f"""
                QPushButton {{
                    background: transparent; color: {_MUTED};
                    border: 1px solid {_BORDER}; border-left: none;
                    border-radius: 0 5px 5px 0; font-size: 14px; font-weight: bold; padding: 0 5px;
                }}
                QPushButton:hover {{ color: #ef4444; background: #fee2e2; border-color: #fca5a5; }}
            """

            container = QWidget(); container.setStyleSheet('background: transparent;')
            ch = QHBoxLayout(container); ch.setContentsMargins(0, 0, 0, 0); ch.setSpacing(0)

            tab_font = QFont()
            tab_font.setPixelSize(14)
            tab_font.setBold(is_active)
            tab_color = 'white' if is_active else _MUTED

            # No hover state on the sub-stage tab itself (tracker task dc59603a) —
            # it didn't need one and just made the tab bar look noisy/inconsistent.
            _ta_w = f"""
                QWidget {{
                    background: {_SEL_BORDER}; border: none;
                    border-radius: 5px 0 0 5px;
                }}
            """
            _ti_w = f"""
                QWidget {{
                    background: transparent;
                    border: 1px solid {_BORDER}; border-radius: 5px 0 0 5px;
                }}
            """

            btn = QWidget()
            btn.setAttribute(Qt.WA_StyledBackground, True)
            btn.setAttribute(Qt.WA_Hover, True)
            btn.setFixedHeight(26)
            btn.setMaximumWidth(140)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_ta_w if is_active else _ti_w)
            btn.mousePressEvent = lambda _e, idx=i: self._switch_sub(idx)
            btn.mouseDoubleClickEvent = lambda _e, idx=i: self._rename_sub(idx)

            bl = QHBoxLayout(btn)
            bl.setContentsMargins(6, 0, 4, 0)
            bl.setSpacing(3)

            num_lbl = QLabel(f'{snum}.{i + 1}')
            num_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            num_lbl.setFont(tab_font)
            num_lbl.setStyleSheet(f'color: {tab_color}; background: transparent; border: none;')

            name_lbl = _MarqueeLabel(sub.name)
            name_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            name_lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            name_lbl.setFont(tab_font)
            name_lbl.setColor(tab_color)

            bl.addWidget(num_lbl)
            bl.addWidget(name_lbl)

            _da = f"""
                QPushButton {{
                    background: {_SEL_BORDER}; color: rgba(255,255,255,0.7);
                    border: none; border-left: 1px solid rgba(255,255,255,0.15);
                    border-radius: 0; font-size: 12px; font-weight: bold; padding: 0 5px;
                }}
                QPushButton:hover {{ color: white; background: {_SEL_NUM}; }}
            """
            _di = f"""
                QPushButton {{
                    background: transparent; color: {_MUTED};
                    border: 1px solid {_BORDER}; border-left: none;
                    border-radius: 0; font-size: 12px; padding: 0 5px;
                }}
                QPushButton:hover {{ color: {_SEL_NUM}; background: {_SEL_BG}; border-color: {_SEL_BORDER}; }}
            """

            dup = QPushButton('⧉')
            dup.setFixedSize(20, 26)
            dup.setCursor(Qt.PointingHandCursor)
            dup.setToolTip(t('project.traceability.duplicate_substage'))
            dup.setStyleSheet(_da if is_active else _di)
            dup.clicked.connect(lambda _, idx=i: self._duplicate_sub(idx))

            close = QPushButton('✕')
            close.setFixedSize(20, 26)
            close.setCursor(Qt.PointingHandCursor)
            close.setStyleSheet(_ca if is_active else _ci)
            close.clicked.connect(lambda _, idx=i: self._remove_sub(idx))

            ch.addWidget(btn); ch.addWidget(dup); ch.addWidget(close)
            self._tab_layout.addWidget(container)

        add_btn = QPushButton(t('project.traceability.add_substage'))
        add_btn.setStyleSheet(_BTN_SMALL)
        add_btn.setFixedHeight(26)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_sub)
        self._tab_layout.addWidget(add_btn)
        self._tab_layout.addStretch()

    def selected_tab_center_x(self) -> int:
        """X-center (in this widget's coordinates) of the active sub-stage tab."""
        idx = self._current_sub
        if idx < self._tab_layout.count():
            item = self._tab_layout.itemAt(idx)
            if item and item.widget():
                w = item.widget()
                return w.mapTo(self, QPoint(w.width() // 2, 0)).x()
        return self.width() // 2

    def _switch_sub(self, idx: int):
        self._current_sub = idx
        self._refresh_tabs()
        self._refresh_table()
        self.tab_switched.emit()

    def _rename_sub(self, idx: int):
        if not self._stage or idx >= len(self._stage.sub_stages):
            return
        sub = self._stage.sub_stages[idx]
        dlg = _RenameSubStageDialog(sub.name, parent=self)
        if dlg.exec_() == QDialog.Accepted and dlg.name:
            sub.name = dlg.name
            self._refresh_tabs()
            self.changed.emit()

    def _add_sub(self):
        if not self._stage:
            return
        new_id = max((s.id for s in self._stage.sub_stages), default=0) + 1
        n = len(self._stage.sub_stages) + 1
        name = t('project.traceability.default_substage_name').format(n=n)
        self._stage.sub_stages.append(TraceSubStage(id=new_id, name=name))
        self._current_sub = len(self._stage.sub_stages) - 1
        self._refresh_tabs()
        self._refresh_table()
        self.changed.emit()
        self.tab_switched.emit()

    def _renumber_substages(self):
        import re
        # Build the "still using the auto-generated name" pattern from the
        # current language's template, not a hardcoded English one — an
        # unrenamed "Sous-étape 2" in French must still get caught here.
        template = t('project.traceability.default_substage_name')
        pattern = '^' + re.escape(template).replace(re.escape('{n}'), r'\d+') + '$'
        for i, sub in enumerate(self._stage.sub_stages):
            if re.match(pattern, sub.name):
                sub.name = template.format(n=i + 1)

    def _duplicate_sub(self, idx: int):
        if not self._stage or idx >= len(self._stage.sub_stages):
            return
        dup = copy.deepcopy(self._stage.sub_stages[idx])
        dup.id = max((s.id for s in self._stage.sub_stages), default=0) + 1
        for j, part in enumerate(dup.parts):
            part.id = j + 1
        self._stage.sub_stages.insert(idx + 1, dup)
        self._renumber_substages()
        self._current_sub = idx + 1
        self._refresh_tabs()
        self._refresh_table()
        self.changed.emit()

    def _remove_sub(self, idx: int):
        if not self._stage:
            return
        sub = self._stage.sub_stages[idx]
        if not ask_yes_no_dialog(self, t('project.traceability.remove_substage'),
                                  t('project.traceability.remove_sub_confirm').format(name=sub.name)):
            return
        self._stage.sub_stages.pop(idx)
        self._renumber_substages()
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
            msg = QLabel(t('project.traceability.no_substages'))
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet(
                f'color: {_MUTED}; font-size: 13px; '
                f'background: transparent; border: none; padding: 40px;'
            )
            self._content_layout.addWidget(msg)
            return

        idx = min(self._current_sub, len(self._stage.sub_stages) - 1)
        sub = self._stage.sub_stages[idx]
        table = _PartsTable(sub,
                            stage_num=self._stage.number,
                            sub_num=idx + 1,
                            flat_mode=self._is_main)
        table.changed.connect(self.changed)
        self._content_layout.addWidget(table)
        self._content_layout.addStretch()
