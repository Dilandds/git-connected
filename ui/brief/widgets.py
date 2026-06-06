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

        self._add_btn = QPushButton('+ Add')
        self._add_btn.setStyleSheet(ADD_BTN_STYLE)
        self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.clicked.connect(self._on_add_clicked)

        for _ in range(initial_count):
            self._append_row()
        self._layout.addWidget(self._add_btn, alignment=Qt.AlignLeft)

    # ── internal ──────────────────────────────────────────────────────────────

    def _append_row(self, text: str = ''):
        row = QHBoxLayout()
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

        row.addWidget(bullet)
        row.addWidget(inp)
        self._layout.insertLayout(self._layout.count() - 1, row)

    def _on_add_clicked(self):
        from .dialogs import _AddBulletDialog
        dlg = _AddBulletDialog(label=self._label, parent=self)
        if dlg.exec_() == QDialog.Accepted and dlg.text:
            self._append_row(dlg.text)

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
        for inp in self._inputs:
            inp.setReadOnly(not enabled)


# ── Components table ──────────────────────────────────────────────────────────

class ComponentsTable(QWidget):
    """
    Editable 3-column table: Component | Material | Colour.
    '+ Add a component' opens _AddComponentRowDialog.
    Each row has an edit (✎) button that opens _AddComponentRowDialog pre-filled.
    """

    HEADERS = ['Component', 'Material', 'Colour']

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet('background: transparent;')
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(4)
        self._rows = []          # list of [QLineEdit, QLineEdit, QLineEdit]
        self._row_widgets = []   # list of QWidget (full row container)

        # Column headers
        hdr = QHBoxLayout(); hdr.setSpacing(8)
        hdr.addSpacing(20)  # align with numbered rows
        for h in self.HEADERS:
            lbl = QLabel(h)
            lbl.setStyleSheet(
                f'color: {_ACCENT}; font-size: 10px; font-weight: bold; '
                f'background: transparent; border: none;'
            )
            hdr.addWidget(lbl, 1)
        hdr.addSpacing(30)  # space for edit button column
        self._outer.addLayout(hdr)
        self._outer.addWidget(separator())

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(4)
        self._outer.addLayout(self._rows_layout)

        for i in range(5):
            self._append_row(f'Component {i + 1}', '', '')

        self._add_btn = QPushButton('+ Add a component')
        self._add_btn.setStyleSheet(ADD_BTN_STYLE)
        self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.clicked.connect(self._on_add_clicked)
        self._outer.addWidget(self._add_btn, alignment=Qt.AlignLeft)

    # ── internal ──────────────────────────────────────────────────────────────

    def _append_row(self, component: str = '', material: str = '', colour: str = ''):
        idx = len(self._rows)
        row_w = QWidget(); row_w.setStyleSheet('background: transparent;')
        row_layout = QHBoxLayout(row_w)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        num = QLabel(str(idx + 1))
        num.setStyleSheet(
            f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;'
        )
        num.setFixedWidth(16)
        row_layout.addWidget(num)

        inputs = []
        for val, placeholder in zip(
            [component, material, colour],
            ['Component name', 'Material', 'Colour'],
        ):
            inp = make_input(placeholder)
            inp.setMinimumHeight(26)
            inp.setText(val)
            inputs.append(inp)
            row_layout.addWidget(inp, 1)

        # Edit button — opens dialog pre-filled with current values
        edit_btn = QPushButton('✎')
        edit_btn.setFixedSize(24, 24)
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setToolTip('Edit this row')
        edit_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_MUTED};
                border: none; font-size: 12px; border-radius: 4px;
            }}
            QPushButton:hover {{ color: {_ACCENT}; background: #e8f0fe; }}
        """ + TOOLTIP_STYLE)
        edit_btn.clicked.connect(lambda _, i=idx: self._on_edit_row(i))
        row_layout.addWidget(edit_btn)

        self._rows.append(inputs)
        self._row_widgets.append(row_w)
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
        elif result == 2:  # delete_btn returns done(2)
            self._remove_row(idx)

    def _remove_row(self, idx: int):
        if idx >= len(self._rows):
            return
        w = self._row_widgets.pop(idx)
        self._rows.pop(idx)
        w.hide(); w.setParent(None)
        # Renumber remaining rows
        for i, row_w in enumerate(self._row_widgets):
            num_lbl = row_w.layout().itemAt(0).widget()
            if isinstance(num_lbl, QLabel):
                num_lbl.setText(str(i + 1))

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

    def set_edit_mode(self, enabled: bool):
        self._add_btn.setVisible(enabled)
        for row_w, inputs in zip(self._row_widgets, self._rows):
            # show/hide the edit button (last widget in the row)
            layout = row_w.layout()
            edit_btn = layout.itemAt(layout.count() - 1).widget()
            if edit_btn:
                edit_btn.setVisible(enabled)
            for inp in inputs:
                inp.setReadOnly(not enabled)
