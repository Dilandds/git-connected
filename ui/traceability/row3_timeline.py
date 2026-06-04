"""Row 3: Horizontal stage progress timeline."""
from typing import List
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QComboBox, QLineEdit, QDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal
from ui.modal_utils import ask_yes_no_dialog
from .models import TraceStage, TraceSubStage
from .shared import (
    _BG, _CARD, _BORDER, _TEXT, _MUTED, _ACCENT, _ACCENT_H,
    _STATUS_COLORS, _TOOLTIP_STYLE,
)
from .dialogs import _EditStageDialog


class _StageTimelineRow(QWidget):
    stage_selected = pyqtSignal(int)
    changed        = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stages:  List[TraceStage] = []
        self._selected = 0
        self.setFixedHeight(86)
        self.setStyleSheet(f'background: {_BG}; border-bottom: 2px solid {_BORDER};')
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        def _nav_btn(text):
            b = QPushButton(text)
            b.setFixedSize(28, 86)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {_MUTED};
                    border: none; font-size: 20px; font-weight: bold;
                }}
                QPushButton:hover {{ background: #e8f0fe; color: {_ACCENT}; }}
            """)
            return b

        self._prev_btn = _nav_btn('‹')
        self._prev_btn.setStyleSheet(
            self._prev_btn.styleSheet() + f'border-right: 1px solid {_BORDER};'
        )
        self._prev_btn.clicked.connect(lambda: self._scroll(-150))
        root.addWidget(self._prev_btn)

        self._scroll_area = QScrollArea()
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet(f'background: {_BG}; border: none;')
        self._inner = QWidget(); self._inner.setStyleSheet(f'background: {_BG};')
        self._inner_l = QHBoxLayout(self._inner)
        self._inner_l.setContentsMargins(10, 8, 10, 8)
        self._inner_l.setSpacing(0)
        self._scroll_area.setWidget(self._inner)
        root.addWidget(self._scroll_area, 1)

        self._next_btn = _nav_btn('›')
        self._next_btn.setStyleSheet(
            self._next_btn.styleSheet() + f'border-left: 1px solid {_BORDER};'
        )
        self._next_btn.clicked.connect(lambda: self._scroll(150))
        root.addWidget(self._next_btn)

    def load_stages(self, stages: List[TraceStage], selected: int = 0):
        self._stages   = stages
        self._selected = selected
        self._refresh()

    def _refresh(self):
        while self._inner_l.count():
            item = self._inner_l.takeAt(0)
            if item.widget():
                item.widget().hide(); item.widget().setParent(None)

        for i, stage in enumerate(self._stages):
            if i > 0:
                arr = QLabel('→')
                arr.setFixedWidth(22)
                arr.setAlignment(Qt.AlignVCenter)
                arr.setStyleSheet(f'color: {_MUTED}; font-size: 13px; background: transparent; border: none;')
                self._inner_l.addWidget(arr)
            self._inner_l.addWidget(self._make_card(stage, i))

        add = QPushButton('＋  Add stage')
        add.setFixedHeight(34)
        add.setStyleSheet(f"""
            QPushButton {{
                background: #e8f0fe; color: {_ACCENT};
                border: 1px dashed {_ACCENT}; border-radius: 5px;
                padding: 0 12px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {_ACCENT}; color: white; border: 1px solid {_ACCENT}; }}
        """)
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self._add_stage)
        self._inner_l.addSpacing(8)
        self._inner_l.addWidget(add)
        self._inner_l.addStretch()

        n = len(self._stages)
        w = n * 116 + max(0, n - 1) * 22 + 110 + 20
        self._inner.setFixedSize(max(w, 350), 70)

    def _make_card(self, stage: TraceStage, idx: int) -> QWidget:
        is_sel = (idx == self._selected)
        status_color = _STATUS_COLORS.get(stage.status, _MUTED)

        card = QWidget()
        card.setFixedWidth(116)
        card.setCursor(Qt.PointingHandCursor)
        card.setToolTip('Double-click to rename')
        card.setStyleSheet(f"""
            QWidget {{
                background: white;
                border: {'2px' if is_sel else '1px'} solid {_ACCENT if is_sel else _BORDER};
                border-radius: 7px;
            }}
            {'QWidget:hover { border-color: ' + _ACCENT + '; background: #f0f7ff; }' if not is_sel else ''}
        """ + _TOOLTIP_STYLE)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(8, 6, 8, 6)
        cl.setSpacing(3)

        num_row = QHBoxLayout(); num_row.setSpacing(4); num_row.setContentsMargins(0, 0, 0, 0)
        num_lbl = QLabel(f'{stage.number:02d}')
        num_lbl.setStyleSheet(
            f'color: {_ACCENT}; font-size: 13px; font-weight: bold; background: transparent; border: none;'
        )
        num_row.addWidget(num_lbl)
        num_row.addStretch()
        if stage.status == 'Completed':
            icon = QLabel('✓')
            icon.setStyleSheet(
                f'color: {_STATUS_COLORS["Completed"]}; font-size: 11px; background: transparent; border: none;'
            )
            num_row.addWidget(icon)

        del_btn = QPushButton('×')
        del_btn.setFixedSize(16, 16)
        del_btn.setStyleSheet("""
            QPushButton {
                background: #fee2e2; color: #ef4444;
                border: none; border-radius: 8px;
                font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #ef4444; color: white; }
        """)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setToolTip(f'Remove {stage.name}')
        del_btn.clicked.connect(lambda _, i=idx: self._remove_stage(i))
        num_row.addWidget(del_btn)
        cl.addLayout(num_row)

        name_lbl = QLabel(stage.name)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet(
            f'color: {_TEXT}; font-size: 10px; font-weight: bold; background: transparent; border: none;'
        )
        cl.addWidget(name_lbl)

        st_lbl = QLabel(stage.status)
        st_lbl.setStyleSheet(f'color: {status_color}; font-size: 9px; background: transparent; border: none;')
        cl.addWidget(st_lbl)

        card.mousePressEvent       = lambda _, i=idx: self._select(i)
        card.mouseDoubleClickEvent = lambda _, i=idx: self._edit_stage(i)
        return card

    def _remove_stage(self, idx: int):
        if not self._stages or idx >= len(self._stages):
            return
        stage = self._stages[idx]
        if not ask_yes_no_dialog(self, 'Remove Stage', f"Remove '{stage.name}' and all its sub-stages?"):
            return
        self._stages.pop(idx)
        self._selected = min(self._selected, max(0, len(self._stages) - 1))
        self._refresh()
        self.stage_selected.emit(self._selected)
        self.changed.emit()

    def _select(self, idx: int):
        self._selected = idx
        self._refresh()
        self.stage_selected.emit(idx)

    def _edit_stage(self, idx: int):
        stage = self._stages[idx]
        dlg = _EditStageDialog(stage, self._stages, parent=self)
        result = dlg.exec_()
        if result == QDialog.Accepted:
            n = dlg.f_name.text().strip()
            if n:
                stage.name = n
            stage.status = dlg.f_status.currentText()
            self._refresh()
            self.changed.emit()
        elif result == 2:
            if ask_yes_no_dialog(self, 'Delete Stage',
                                  f"Delete '{stage.name}' and all its sub-stages?"):
                self._stages.pop(idx)
                self._selected = min(self._selected, max(0, len(self._stages) - 1))
                self._refresh()
                self.stage_selected.emit(self._selected)
                self.changed.emit()

    def _add_stage(self):
        n      = len(self._stages) + 1
        new_id = max((s.id for s in self._stages), default=0) + 1
        self._stages.append(TraceStage(
            id=new_id, number=n, name=f'Stage {n}', status='Upcoming',
            sub_stages=[TraceSubStage(id=1, name='Sub-stage 1')]
        ))
        self._select(len(self._stages) - 1)
        self.changed.emit()

    def _scroll(self, delta: int):
        bar = self._scroll_area.horizontalScrollBar()
        bar.setValue(max(0, min(bar.maximum(), bar.value() + delta)))

    def get_selected(self) -> int:
        return self._selected
