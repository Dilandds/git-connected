"""Row 2: Horizontal product component selector — compact inline list style."""
from typing import List
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtGui import QPixmap
from ui.modal_utils import ask_yes_no_dialog
from .models import TraceComponent, TraceStage, TraceSubStage
from .shared import (
    _CARD, _BORDER, _TEXT, _MUTED, _ACCENT,
    _BTN_SMALL, _BTN_DEL_CIRCLE, _TOOLTIP_STYLE,
)
from .dialogs import _AddComponentDialog, _EditComponentDialog

_ITEM_H   = 72   # height of each component pill
_IMG_SIZE = 58   # image thumbnail size (circle diameter)


class _ComponentsRow(QWidget):
    component_selected = pyqtSignal(int)
    changed            = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._components: List[TraceComponent] = []
        self._selected = 0
        self.setFixedHeight(108)
        self.setStyleSheet(f'background: {_CARD}; border-bottom: 1px solid {_BORDER};')
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 8, 16, 0)
        root.setSpacing(4)

        # Section title
        title = QLabel('Product Components')
        title.setStyleSheet(
            f'color: {_TEXT}; font-size: 13px; font-weight: bold;'
            f' background: transparent; border: none;'
        )
        root.addWidget(title)

        # Horizontal scroll area for the component pills
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
        self._cw = QWidget()
        self._cw.setStyleSheet('background: transparent;')
        self._cl = QHBoxLayout(self._cw)
        self._cl.setContentsMargins(0, 0, 0, 0)
        self._cl.setSpacing(20)
        self._scroll.setWidget(self._cw)
        root.addWidget(self._scroll, 1)

    def selected_center_x(self) -> int:
        """X-center (in this widget's coordinates) of the selected component pill."""
        idx = self._selected
        if 0 <= idx < self._cl.count():
            item = self._cl.itemAt(idx)
            if item and item.widget():
                w = item.widget()
                return w.mapTo(self, QPoint(w.width() // 2, 0)).x()
        return self.width() // 2

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
            self._cl.addWidget(self._make_item(comp, i, i == self._selected))

        # Separator before add button
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedHeight(28)
        sep.setStyleSheet(f'color: {_BORDER}; background: {_BORDER};')
        self._cl.addWidget(sep, 0, Qt.AlignVCenter)

        add = QPushButton('＋  Add Component')
        add.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {_ACCENT}; font-size: 13px; font-weight: 600;
                padding: 4px 8px;
            }}
            QPushButton:hover {{ color: #1d4ed8; text-decoration: underline; }}
        """)
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self._add_component)
        self._cl.addWidget(add, 0, Qt.AlignVCenter)

        self._cl.addStretch()

        # Size the content widget
        ITEM_W  = 170
        spacing = 20
        n       = len(self._components)
        total_w = n * (ITEM_W + spacing) + 180 + spacing
        self._cw.setFixedSize(max(total_w, 380), _ITEM_H)

    def _make_item(self, comp: TraceComponent, idx: int, is_sel: bool) -> QWidget:
        """Compact horizontal pill: [image] [name / (Main Product)]  [×]"""
        item = QWidget()
        item.setObjectName('compItem')
        item.setFixedHeight(_ITEM_H)
        item.setCursor(Qt.PointingHandCursor)
        item.setToolTip('Double-click to edit')
        item.setStyleSheet(f"""
            QWidget#compItem {{
                background: {'#eff6ff' if is_sel else 'transparent'};
                border: {'2px' if is_sel else '1px'} solid {_ACCENT if is_sel else 'transparent'};
                border-radius: 10px;
            }}
            {'QWidget#compItem:hover { background: #f0f4ff; border-color: ' + _ACCENT + '; }' if not is_sel else ''}
        """ + _TOOLTIP_STYLE)

        row = QHBoxLayout(item)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(8)

        # Thumbnail
        img_frame = QWidget()
        img_frame.setFixedSize(_IMG_SIZE, _IMG_SIZE)
        img_frame.setStyleSheet(f"""
            QWidget {{
                background: {'#dbeafe' if is_sel else '#f1f5f9'};
                border-radius: {_IMG_SIZE // 2}px; border: none;
            }}
        """)
        img_fl = QVBoxLayout(img_frame)
        img_fl.setContentsMargins(0, 0, 0, 0)
        img_fl.setAlignment(Qt.AlignCenter)
        img = QLabel()
        img.setAlignment(Qt.AlignCenter)
        img.setStyleSheet('background: transparent; border: none;')
        if comp.image_path:
            pix = QPixmap(comp.image_path)
            if not pix.isNull():
                img.setPixmap(pix.scaled(_IMG_SIZE, _IMG_SIZE,
                                         Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            else:
                img.setText('📦')
                img.setStyleSheet('font-size: 20px; background: transparent; border: none;')
        else:
            img.setText('📦')
            img.setStyleSheet('font-size: 20px; background: transparent; border: none;')
        img_fl.addWidget(img)
        row.addWidget(img_frame, 0, Qt.AlignVCenter)

        # Text column
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        name_lbl = QLabel(comp.name)
        name_lbl.setStyleSheet(
            f'color: {_ACCENT if is_sel else _TEXT}; font-size: 13px;'
            f' font-weight: {"700" if is_sel else "600"}; background: transparent; border: none;'
        )
        text_col.addWidget(name_lbl)

        if comp.is_main:
            sub_lbl = QLabel('(Main Product)')
            sub_lbl.setStyleSheet(
                f'color: {_ACCENT}; font-size: 11px; background: transparent; border: none;'
            )
            text_col.addWidget(sub_lbl)

        row.addLayout(text_col)
        row.addStretch()

        # Delete button (non-main only)
        if not comp.is_main:
            del_btn = QPushButton('✕')
            del_btn.setFixedSize(16, 16)
            del_btn.setStyleSheet(_BTN_DEL_CIRCLE)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setToolTip(f'Remove {comp.name}')
            del_btn.clicked.connect(lambda _, i=idx: self._remove_component(i))
            row.addWidget(del_btn, 0, Qt.AlignTop)

        # Adjust width to fit content
        min_w = _IMG_SIZE + 8 + 100 + (26 if not comp.is_main else 0) + 12
        item.setMinimumWidth(min_w)
        item.setMaximumWidth(200)

        item.mousePressEvent       = lambda _, i=idx: self._select(i)
        item.mouseDoubleClickEvent = lambda _, i=idx: self._edit_component(i)
        return item

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
