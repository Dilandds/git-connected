"""
Reusable compound widgets shared across Brief sections.
Dialogs are imported from ui/brief/dialogs.py — never built inline here.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDialog,
)
from PyQt5.QtCore import Qt
from .shared import (
    _ACCENT, _MUTED, _TEXT, _BORDER,
    ADD_BTN_STYLE, TOOLTIP_STYLE, make_input, separator,
)
from i18n import t


# ── Bullet list ───────────────────────────────────────────────────────────────

class BulletListWidget(QWidget):
    """
    Dynamic bullet list.
    In read mode: items are read-only labels.
    In edit mode: items are editable inputs; '+ Add' opens _AddBulletDialog.
    """

    def __init__(self, label: str = 'Item', initial_count: int = 4, parent=None):
        super().__init__(parent)
        self._label = label
        self.setStyleSheet('background: transparent;')
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._inputs = []
        self._row_widgets = []

        self._add_btn = QPushButton(t('project.brief.s6_add_bullet'))
        self._add_btn.setStyleSheet(ADD_BTN_STYLE)
        self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.clicked.connect(self._on_add_clicked)

        for _ in range(initial_count):
            self._append_row()
        self._layout.addWidget(self._add_btn, alignment=Qt.AlignLeft)

    # ── internal ──────────────────────────────────────────────────────────────

    def _append_row(self, text: str = ''):
        row_w = QWidget()
        row_w.setStyleSheet('background: transparent;')
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        bullet = QLabel('•')
        bullet.setStyleSheet(
            f'color: {_ACCENT}; font-size: 13px; background: transparent; border: none;'
        )
        bullet.setFixedWidth(12)

        inp = make_input('…')
        inp.setMinimumHeight(26)
        inp.setText(text)
        self._inputs.append(inp)
        self._row_widgets.append(row_w)

        del_btn = QPushButton('×')
        del_btn.setFixedSize(18, 18)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_MUTED};
                border: none; font-size: 13px; font-weight: bold; padding: 0;
            }}
            QPushButton:hover {{ color: #ef4444; }}
        """)
        del_btn.clicked.connect(lambda _, w=row_w, i=inp: self._remove_row(w, i))

        row.addWidget(bullet)
        row.addWidget(inp)
        row.addWidget(del_btn)
        self._layout.insertWidget(self._layout.count() - 1, row_w)

    def _on_add_clicked(self):
        from .dialogs import _AddBulletDialog
        dlg = _AddBulletDialog(label=self._label, parent=self)
        if dlg.exec_() == QDialog.Accepted and dlg.text:
            self._append_row(dlg.text)

    def _remove_row(self, row_w: QWidget, inp):
        if inp in self._inputs:
            self._inputs.remove(inp)
        if row_w in self._row_widgets:
            self._row_widgets.remove(row_w)
        row_w.hide()
        row_w.setParent(None)

    # ── public API ────────────────────────────────────────────────────────────

    def get_values(self) -> list:
        return [i.text() for i in self._inputs]

    def set_values(self, values: list):
        while len(self._inputs) < len(values):
            self._append_row()
        for i, v in enumerate(values):
            self._inputs[i].setText(v)

    def set_edit_mode(self, enabled: bool):
        self._add_btn.setVisible(enabled)
        for row_w in self._row_widgets:
            # del button is the last widget in each row
            layout = row_w.layout()
            if layout and layout.count() > 0:
                del_btn = layout.itemAt(layout.count() - 1).widget()
                if del_btn:
                    del_btn.setVisible(enabled)
        for inp in self._inputs:
            inp.setReadOnly(not enabled)


# ── Components table ──────────────────────────────────────────────────────────

# Fixed pixel widths shared between header and data rows so columns truly align
_NUM_W  = 24   # row-number column
_BTN_W  = 24   # edit button
_DEL_W  = 24   # delete button
_ROW_SP = 6    # spacing inside each row

_EDIT_BTN_CSS = f"""
    QPushButton {{
        background: transparent; color: {_MUTED};
        border: none; font-size: 12px; border-radius: 4px;
    }}
    QPushButton:hover {{ color: {_ACCENT}; background: #e8f0fe; }}
"""
_DEL_BTN_CSS = f"""
    QPushButton {{
        background: transparent; color: {_MUTED};
        border: none; font-size: 13px; font-weight: bold; border-radius: 4px;
    }}
    QPushButton:hover {{ color: #ef4444; background: #fee2e2; }}
"""


class ComponentsTable(QWidget):
    """
    Editable 3-column table: Component | Material | Colour.
    Header row uses identical column widths as data rows — always aligned.
    Each row has an inline edit (✎) and delete (×) button.
    """

    # ── header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(_ROW_SP)

        # Phantom number column — same fixed width as data rows
        num_ph = QLabel()
        num_ph.setFixedWidth(_NUM_W)
        num_ph.setFixedHeight(20)
        num_ph.setStyleSheet('background: transparent; border: none;')
        hdr.addWidget(num_ph)

        for key in ['project.brief.s6_component', 'project.brief.s6_material', 'project.brief.s6_colour']:
            lbl = QLabel(t(key))
            lbl.setFixedHeight(20)
            lbl.setStyleSheet(
                f'color: {_ACCENT}; font-size: 10px; font-weight: bold; '
                f'background: transparent; border: none;'
            )
            hdr.addWidget(lbl, 1)

        # Phantom action-button column — same total width as edit + del
        btn_ph = QWidget()
        btn_ph.setFixedWidth(_BTN_W + _ROW_SP + _DEL_W)
        btn_ph.setFixedHeight(20)
        btn_ph.setStyleSheet('background: transparent; border: none;')
        hdr.addWidget(btn_ph)

        return hdr

    # ── constructor ───────────────────────────────────────────────────────────

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet('background: transparent;')
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(4)
        self._rows = []          # list of [QLineEdit, QLineEdit, QLineEdit]
        self._row_widgets = []   # list of QWidget (full row container)
        self._action_btns = []   # list of (edit_btn, del_btn)

        self._outer.addLayout(self._build_header())
        self._outer.addWidget(separator())

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(4)
        self._outer.addLayout(self._rows_layout)

        self._append_row('Component 1', '', '')

        # Add-row button — prominent, top-aligned, blue
        self._add_btn = QPushButton(t('project.brief.s6_add'))
        self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT}; color: #ffffff;
                border: none; border-radius: 6px;
                font-size: 12px; font-weight: 600;
                padding: 6px 14px;
            }}
            QPushButton:hover {{ background: #1a6fba; }}
        """)
        self._add_btn.clicked.connect(self._on_add_clicked)
        self._outer.addWidget(self._add_btn, alignment=Qt.AlignLeft)
        self._outer.addStretch()

    # ── internal ──────────────────────────────────────────────────────────────

    def _append_row(self, component: str = '', material: str = '', colour: str = ''):
        idx = len(self._rows)

        row_w = QWidget()
        row_w.setStyleSheet('background: transparent;')
        row_layout = QHBoxLayout(row_w)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(_ROW_SP)

        num = QLabel(str(idx + 1))
        num.setFixedWidth(_NUM_W)
        num.setStyleSheet(
            f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;'
        )
        row_layout.addWidget(num)

        inputs = []
        for val, placeholder in zip(
            [component, material, colour],
            [t('project.brief.s6_comp_name'), t('project.brief.s6_material'), t('project.brief.s6_colour')],
        ):
            inp = make_input(placeholder)
            inp.setMinimumHeight(30)
            inp.setText(val)
            inputs.append(inp)
            row_layout.addWidget(inp, 1)

        # Edit button
        edit_btn = QPushButton('✎')
        edit_btn.setFixedSize(_BTN_W, 28)
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setToolTip(t('project.brief.s6_edit_row'))
        edit_btn.setStyleSheet(_EDIT_BTN_CSS + TOOLTIP_STYLE)
        edit_btn.clicked.connect(lambda _, i=idx: self._on_edit_row(i))
        row_layout.addWidget(edit_btn)

        # Delete button
        del_btn = QPushButton('×')
        del_btn.setFixedSize(_DEL_W, 28)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setToolTip('Delete row')
        del_btn.setStyleSheet(_DEL_BTN_CSS + TOOLTIP_STYLE)
        del_btn.clicked.connect(lambda _, i=idx: self._remove_row(i))
        row_layout.addWidget(del_btn)

        self._rows.append(inputs)
        self._row_widgets.append(row_w)
        self._action_btns.append((edit_btn, del_btn))
        self._rows_layout.addWidget(row_w)

    def _on_add_clicked(self):
        from .dialogs import _AddComponentRowDialog
        dlg = _AddComponentRowDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            comp, mat, col = dlg.values
            if comp or mat or col:
                self._append_row(comp, mat, col)

    def _on_edit_row(self, idx: int):
        from .dialogs import _AddComponentRowDialog
        inputs = self._rows[idx]
        dlg = _AddComponentRowDialog(
            component=inputs[0].text(),
            material=inputs[1].text(),
            colour=inputs[2].text(),
            parent=self,
        )
        result = dlg.exec_()
        if result == QDialog.Accepted:
            for inp, val in zip(inputs, dlg.values):
                inp.setText(val)
        elif result == 2:
            self._remove_row(idx)

    def _remove_row(self, idx: int):
        if idx >= len(self._rows):
            return
        w = self._row_widgets.pop(idx)
        self._rows.pop(idx)
        self._action_btns.pop(idx)
        w.hide()
        w.setParent(None)
        # Reconnect buttons with updated indices and renumber labels
        for i, (row_w, (edit_btn, del_btn)) in enumerate(
            zip(self._row_widgets, self._action_btns)
        ):
            num_lbl = row_w.layout().itemAt(0).widget()
            if isinstance(num_lbl, QLabel):
                num_lbl.setText(str(i + 1))
            # Rebind to current index
            try:
                edit_btn.clicked.disconnect()
                del_btn.clicked.disconnect()
            except TypeError:
                pass
            edit_btn.clicked.connect(lambda _, i=i: self._on_edit_row(i))
            del_btn.clicked.connect(lambda _, i=i: self._remove_row(i))

    # ── public API ────────────────────────────────────────────────────────────

    def get_data(self) -> list:
        return [[inp.text() for inp in row] for row in self._rows]

    def set_data(self, data: list):
        for i, row_data in enumerate(data):
            while len(self._rows) <= i:
                self._append_row()
            for j, val in enumerate(row_data):
                if j < len(self._rows[i]):
                    self._rows[i][j].setText(val)

    def replace_data(self, data: list):
        for w in list(self._row_widgets):
            w.hide()
            w.setParent(None)
        self._rows.clear()
        self._row_widgets.clear()
        self._action_btns.clear()
        for row_data in data:
            comp = row_data[0] if len(row_data) > 0 else ''
            mat  = row_data[1] if len(row_data) > 1 else ''
            col  = row_data[2] if len(row_data) > 2 else ''
            self._append_row(comp, mat, col)

    def set_edit_mode(self, enabled: bool):
        self._add_btn.setVisible(enabled)
        for (edit_btn, del_btn) in self._action_btns:
            edit_btn.setVisible(enabled)
            del_btn.setVisible(enabled)
        for inputs in self._rows:
            for inp in inputs:
                inp.setReadOnly(not enabled)
