"""Row 3: Horizontal stage progress timeline."""
from typing import List
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen
from ui.modal_utils import ask_yes_no_dialog
from .models import TraceStage, TraceSubStage
from .shared import (
    _BG, _CARD, _BORDER, _TEXT, _MUTED, _ACCENT, _ACCENT_H,
    _STATUS_COLORS, _TOOLTIP_STYLE, _BTN_DEL_CIRCLE,
)
from .dialogs import _EditStageDialog

_CARD_W  = 180   # stage card width
_CARD_H  = 76    # stage card height
_ROW_H   = 104   # total row height
_ARROW_W = 36    # arrow separator width


class _StatusDot(QWidget):
    """Small filled circle used as the status icon."""
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(10, 10)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(self._color))
        p.drawEllipse(1, 1, 8, 8)


class _StageTimelineRow(QWidget):
    stage_selected = pyqtSignal(int)
    changed        = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stages:  List[TraceStage] = []
        self._selected = 0
        self.setFixedHeight(_ROW_H)
        self.setStyleSheet(f'background: {_BG}; border-bottom: 2px solid {_BORDER};')
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        def _nav_btn(text, border_side):
            b = QPushButton(text)
            b.setFixedSize(32, _ROW_H)
            border_css = (
                f'border-right: 1px solid {_BORDER};' if border_side == 'right'
                else f'border-left: 1px solid {_BORDER};'
            )
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {_TEXT};
                    {border_css}
                    border-top: none; border-bottom: none;
                    font-size: 20px; font-weight: 600;
                    padding: 0;
                }}
                QPushButton:hover {{
                    background: #e8f0fe;
                    color: {_ACCENT};
                }}
                QPushButton:disabled {{ color: {_BORDER}; }}
            """)
            b.setCursor(Qt.PointingHandCursor)
            return b

        self._prev_btn = _nav_btn('‹', 'right')
        self._prev_btn.clicked.connect(lambda: self._scroll(-200))
        root.addWidget(self._prev_btn)

        self._scroll_area = QScrollArea()
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet(f'background: {_BG}; border: none;')

        self._inner = QWidget()
        self._inner.setStyleSheet(f'background: {_BG};')
        self._inner_l = QHBoxLayout(self._inner)
        self._inner_l.setContentsMargins(12, 0, 12, 0)
        self._inner_l.setSpacing(0)
        self._inner_l.setAlignment(Qt.AlignVCenter)

        self._scroll_area.setWidget(self._inner)
        root.addWidget(self._scroll_area, 1)

        self._next_btn = _nav_btn('›', 'left')
        self._next_btn.clicked.connect(lambda: self._scroll(200))
        root.addWidget(self._next_btn)

    def selected_center_x(self) -> int:
        """X-center (in this widget's coordinates) of the selected stage card."""
        idx = self._selected
        layout_pos = idx * 2  # arrows sit at odd positions (2i+1)
        if layout_pos < self._inner_l.count():
            item = self._inner_l.itemAt(layout_pos)
            if item and item.widget():
                w = item.widget()
                return w.mapTo(self, QPoint(w.width() // 2, 0)).x()
        return self.width() // 2

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
                arr.setFixedWidth(_ARROW_W)
                arr.setAlignment(Qt.AlignCenter)
                arr.setStyleSheet(
                    f'color: {_MUTED}; font-size: 16px; background: transparent; border: none;'
                )
                self._inner_l.addWidget(arr, 0, Qt.AlignVCenter)
            self._inner_l.addWidget(self._make_card(stage, i), 0, Qt.AlignVCenter)

        # "+ Add stage" button
        add = QPushButton('＋  Add stage')
        add.setFixedHeight(36)
        add.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_ACCENT};
                border: 1.5px dashed {_ACCENT}; border-radius: 7px;
                padding: 0 14px; font-size: 11px; font-weight: 600;
            }}
            QPushButton:hover {{ background: #eff6ff; }}
        """)
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self._add_stage)
        self._inner_l.addSpacing(12)
        self._inner_l.addWidget(add, 0, Qt.AlignVCenter)
        self._inner_l.addStretch()

        n = len(self._stages)
        total_w = n * (_CARD_W + _ARROW_W) + 140 + 24
        self._inner.setFixedSize(max(total_w, 400), _ROW_H)

    def _make_card(self, stage: TraceStage, idx: int) -> QWidget:
        is_sel = (idx == self._selected)
        status = stage.status
        status_color = _STATUS_COLORS.get(status, _MUTED)

        card = QWidget()
        card.setObjectName('stageCard')
        card.setFixedSize(_CARD_W, _CARD_H)
        card.setCursor(Qt.PointingHandCursor)
        card.setToolTip('Double-click to rename')
        # Use #stageCard selector so child widgets are NOT affected
        card.setStyleSheet(f"""
            QWidget#stageCard {{
                background: {'#eff6ff' if is_sel else 'white'};
                border: {'2px' if is_sel else '1px'} solid {_ACCENT if is_sel else _BORDER};
                border-radius: 9px;
            }}
            {'QWidget#stageCard:hover { border-color: ' + _ACCENT + '; background: #f0f7ff; }' if not is_sel else ''}
        """ + _TOOLTIP_STYLE)

        outer = QVBoxLayout(card)
        outer.setContentsMargins(10, 9, 8, 9)
        outer.setSpacing(6)

        # ── top row: [num]  [name ···]  [×] ─────────────────────────────
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)

        num_lbl = QLabel(f'{stage.number:02d}')
        num_lbl.setFixedWidth(26)
        num_lbl.setStyleSheet(
            f'color: {_ACCENT}; font-size: 15px; font-weight: 800;'
            f' background: transparent; border: none;'
        )
        top.addWidget(num_lbl, 0, Qt.AlignVCenter)

        name_lbl = QLabel(stage.name)
        name_lbl.setStyleSheet(
            f'color: {_TEXT}; font-size: 11px; font-weight: 700;'
            f' background: transparent; border: none;'
        )
        name_lbl.setWordWrap(False)
        top.addWidget(name_lbl, 1, Qt.AlignVCenter)

        del_btn = QPushButton('✕')
        del_btn.setFixedSize(16, 16)
        del_btn.setStyleSheet(_BTN_DEL_CIRCLE)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setToolTip(f'Remove {stage.name}')
        del_btn.clicked.connect(lambda _, i=idx: self._remove_stage(i))
        top.addWidget(del_btn, 0, Qt.AlignVCenter)

        outer.addLayout(top)

        # ── status row: [dot]  [label] ────────────────────────────────────
        st_row = QHBoxLayout()
        st_row.setContentsMargins(0, 0, 0, 0)
        st_row.setSpacing(5)

        dot = _StatusDot(status_color)
        st_row.addWidget(dot, 0, Qt.AlignVCenter)

        st_lbl = QLabel(status)
        st_lbl.setStyleSheet(
            f'color: {status_color}; font-size: 10px; font-weight: 500;'
            f' background: transparent; border: none;'
        )
        st_row.addWidget(st_lbl, 0, Qt.AlignVCenter)
        st_row.addStretch()

        outer.addLayout(st_row)

        card.mousePressEvent       = lambda _, i=idx: self._select(i)
        card.mouseDoubleClickEvent = lambda _, i=idx: self._edit_stage(i)
        return card

    def _remove_stage(self, idx: int):
        if not self._stages or idx >= len(self._stages):
            return
        stage = self._stages[idx]
        if not ask_yes_no_dialog(self, 'Remove Stage',
                                  f"Remove '{stage.name}' and all its sub-stages?"):
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
