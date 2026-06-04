"""Row 2: Horizontal product component selector with image cards."""
from typing import List
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from ui.modal_utils import ask_yes_no_dialog
from .models import TraceComponent, TraceStage, TraceSubStage
from .shared import (
    _CARD, _BORDER, _TEXT, _MUTED, _ACCENT,
    _BTN_SMALL, _TOOLTIP_STYLE,
)
from .dialogs import _AddComponentDialog, _EditComponentDialog


class _ComponentsRow(QWidget):
    component_selected = pyqtSignal(int)
    changed            = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._components: List[TraceComponent] = []
        self._selected = 0
        self.setFixedHeight(120)
        self.setStyleSheet(f'background: {_CARD}; border-bottom: 1px solid {_BORDER};')
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(0)

        title = QLabel('Product Components')
        title.setStyleSheet(
            f'color: {_TEXT}; font-size: 11px; font-weight: bold; background: transparent; border: none;'
        )
        title.setFixedWidth(132)
        root.addWidget(title)

        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setWidgetResizable(False)
        self._scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:horizontal { height: 4px; background: transparent; }
            QScrollBar::handle:horizontal { background: #d1d5db; border-radius: 2px; }
        """)
        self._cw = QWidget(); self._cw.setStyleSheet('background: transparent;')
        self._cl = QHBoxLayout(self._cw)
        self._cl.setContentsMargins(0, 0, 0, 0)
        self._cl.setSpacing(8)
        self._scroll.setWidget(self._cw)
        root.addWidget(self._scroll, 1)

    def load_components(self, components: List[TraceComponent], selected: int = 0):
        self._components = components
        self._selected   = selected
        self._refresh()

    def _refresh(self):
        while self._cl.count():
            item = self._cl.takeAt(0)
            w = item.widget()
            if w:
                w.hide(); w.setParent(None)

        for i, comp in enumerate(self._components):
            self._cl.addWidget(self._make_card(comp, i, i == self._selected))

        add = QPushButton('＋  Add\nComponent')
        add.setStyleSheet(_BTN_SMALL)
        add.setFixedSize(100, 96)
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self._add_component)
        self._cl.addWidget(add)

        CARD_W  = 110
        spacing = 10
        n       = len(self._components)
        total_w = n * (CARD_W + spacing) + 100 + spacing
        self._cw.setFixedSize(max(total_w, 260), 96)

    def _make_card(self, comp: TraceComponent, idx: int, is_sel: bool) -> QWidget:
        card = QWidget(); card.setFixedSize(110, 96)
        card.setCursor(Qt.PointingHandCursor)
        card.setToolTip('Double-click to edit')
        card.setStyleSheet(f"""
            QWidget {{
                background: {'#eff6ff' if is_sel else '#f9fafb'};
                border: {'2px' if is_sel else '1px'} solid {_ACCENT if is_sel else _BORDER};
                border-radius: 10px;
            }}
            {'QWidget:hover { border-color: ' + _ACCENT + '; background: #eff6ff; }' if not is_sel else ''}
        """ + _TOOLTIP_STYLE)

        cl = QVBoxLayout(card); cl.setContentsMargins(4, 4, 4, 4)
        cl.setSpacing(2); cl.setAlignment(Qt.AlignCenter)

        if not comp.is_main:
            top_row = QHBoxLayout(); top_row.setContentsMargins(0, 0, 0, 0)
            top_row.addStretch()
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
            del_btn.setToolTip(f'Remove {comp.name}')
            del_btn.clicked.connect(lambda _, i=idx: self._remove_component(i))
            top_row.addWidget(del_btn)
            cl.addLayout(top_row)

        img_frame = QWidget(); img_frame.setFixedSize(48, 48)
        img_frame.setStyleSheet(f"""
            QWidget {{
                background: {'#dbeafe' if is_sel else '#f1f5f9'};
                border-radius: 8px; border: none;
            }}
        """)
        img_fl = QVBoxLayout(img_frame); img_fl.setContentsMargins(0, 0, 0, 0)
        img = QLabel(); img.setAlignment(Qt.AlignCenter)
        img.setStyleSheet('background: transparent; border: none;')
        if comp.image_path:
            pix = QPixmap(comp.image_path)
            if not pix.isNull():
                img.setPixmap(pix.scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                img.setText('📦')
                img.setStyleSheet('font-size: 22px; background: transparent; border: none;')
        else:
            img.setText('📦')
            img.setStyleSheet('font-size: 22px; background: transparent; border: none;')
        img_fl.addWidget(img)
        cl.addWidget(img_frame, 0, Qt.AlignHCenter)

        n = QLabel(comp.name); n.setWordWrap(True); n.setAlignment(Qt.AlignCenter)
        n.setStyleSheet(
            f'color: {_TEXT}; font-size: 9px; font-weight: bold; background: transparent; border: none;'
        )
        cl.addWidget(n)

        if comp.is_main:
            m = QLabel('(Main Product)'); m.setAlignment(Qt.AlignCenter)
            m.setStyleSheet(f'color: {_ACCENT}; font-size: 8px; background: transparent; border: none;')
            cl.addWidget(m)

        card.mousePressEvent       = lambda _, i=idx: self._select(i)
        card.mouseDoubleClickEvent = lambda _, i=idx: self._edit_component(i)
        return card

    def _select(self, idx: int):
        self._selected = idx
        self.component_selected.emit(idx)

    def _remove_component(self, idx: int):
        if idx < 0 or idx >= len(self._components):
            return
        comp = self._components[idx]
        if comp.is_main:
            return
        if not ask_yes_no_dialog(self, 'Remove Component',
                                  f"Remove '{comp.name}' and all its stages/parts?"):
            return
        self._components.pop(idx)
        new_sel = min(self._selected, max(0, len(self._components) - 1))
        self._selected = new_sel
        self._refresh()
        self.component_selected.emit(new_sel)
        self.changed.emit()

    def _add_component(self):
        dlg = _AddComponentDialog(parent=self)
        if dlg.exec_() != QDialog.Accepted or not dlg.name:
            return
        new_id = max((c.id for c in self._components), default=0) + 1
        self._components.append(TraceComponent(
            id=new_id, name=dlg.name, image_path=dlg.image_path,
            stages=[TraceStage(id=1, number=1, name='Stage 1', status='Upcoming',
                               sub_stages=[TraceSubStage(id=1, name='Sub-stage 1')])]
        ))
        self._select(len(self._components) - 1)
        self.changed.emit()

    def _edit_component(self, idx: int):
        comp = self._components[idx]
        dlg = _EditComponentDialog(comp, parent=self)
        result = dlg.exec_()
        if result == QDialog.Accepted:
            if dlg.name:
                comp.name = dlg.name
            comp.image_path = dlg.image_path
            self._refresh()
            self.changed.emit()
        elif result == 2:
            if ask_yes_no_dialog(self, 'Delete Component',
                                  f"Delete '{comp.name}' and all its data?"):
                self._components.pop(idx)
                self._selected = 0
                self._refresh()
                self.component_selected.emit(0)
                self.changed.emit()
