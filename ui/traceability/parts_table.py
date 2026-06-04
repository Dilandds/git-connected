from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal
from ui.modal_utils import ask_yes_no_dialog
from .models import TracePart, TraceSubStage
from .shared import (
    _BG, _CARD, _BORDER, _TEXT, _MUTED, _ACCENT,
    _INPUT, _BTN_PRIMARY, _BTN_SMALL, _BTN_OUTLINE,
)
from .dialogs import _PartDialog, _CommentsDialog
from .part_row import _PartRow


class _PartsTable(QWidget):
    changed = pyqtSignal()

    def __init__(self, sub_stage: TraceSubStage, parent=None):
        super().__init__(parent)
        self._sub     = sub_stage
        self._next_id = max((p.id for p in sub_stage.parts), default=0) + 1
        self.setStyleSheet(f'background: {_CARD};')
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Column header
        hdr = QWidget(); hdr.setFixedHeight(30)
        hdr.setStyleSheet(f'background: #f1f3f5; border-bottom: 1px solid {_BORDER};')
        hl = QHBoxLayout(hdr); hl.setContentsMargins(8, 0, 8, 0); hl.setSpacing(0)

        def _ch(text, w):
            l = QLabel(text); l.setFixedWidth(w)
            l.setStyleSheet(
                f'color: {_MUTED}; font-size: 9px; font-weight: bold; '
                f'background: transparent; border: none; letter-spacing: 0.5px;'
            )
            return l

        hl.addWidget(_ch('PARTS', 100))
        hl.addWidget(_ch('SUPPLIERS & ACTION', 167))
        hl.addWidget(_ch('CURRENT TASK', 157))
        hl.addWidget(_ch('START DATE', 82))
        hl.addWidget(_ch('DUE DATE', 82))
        hl.addWidget(_ch('STATUS', 85))
        hl.addWidget(_ch('PROGRESS', 102))
        hl.addWidget(_ch('COMMENTS', 54))
        hl.addStretch()
        root.addWidget(hdr)

        # Part rows container
        self._rows_w = QWidget(); self._rows_w.setStyleSheet(f'background: {_CARD};')
        self._rows_l = QVBoxLayout(self._rows_w)
        self._rows_l.setContentsMargins(0, 0, 0, 0)
        self._rows_l.setSpacing(0)
        root.addWidget(self._rows_w)

        # Add-part footer
        footer = QWidget(); footer.setFixedHeight(36)
        footer.setStyleSheet(f'background: {_BG}; border-top: 1px dashed {_BORDER};')
        fl = QHBoxLayout(footer); fl.setContentsMargins(8, 0, 8, 0)

        add_circle = QPushButton('+')
        add_circle.setFixedSize(22, 22)
        add_circle.setStyleSheet(f"""
            QPushButton {{
                background: #e8f0fe; color: {_ACCENT};
                border: 1px dashed {_ACCENT}; border-radius: 11px;
                font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {_ACCENT}; color: white; }}
        """)
        add_circle.setCursor(Qt.PointingHandCursor)
        add_circle.clicked.connect(self._add_part)

        add_lbl = QLabel('Add Part')
        add_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;')
        fl.addWidget(add_circle); fl.addSpacing(6); fl.addWidget(add_lbl); fl.addStretch()

        add_btn = QPushButton('＋  Add Part')
        add_btn.setStyleSheet(_BTN_OUTLINE)
        add_btn.setFixedHeight(24)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_part)
        fl.addWidget(add_btn)
        root.addWidget(footer)

        self._refresh_rows()

    def _refresh_rows(self):
        while self._rows_l.count():
            item = self._rows_l.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().setParent(None)

        if not self._sub.parts:
            empty = QLabel('No parts yet. Click ＋ Add Part to begin.')
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                f'color: {_MUTED}; font-size: 11px; '
                f'background: transparent; border: none; padding: 24px;'
            )
            self._rows_l.addWidget(empty)
            return

        for i, part in enumerate(self._sub.parts):
            row = _PartRow(part, i)
            row.edit_requested.connect(self._edit_part)
            row.delete_requested.connect(self._delete_part)
            row.comment_requested.connect(self._show_comments)
            self._rows_l.addWidget(row)

    def _add_part(self):
        dlg = _PartDialog(parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        self._sub.parts.append(TracePart(id=self._next_id, **dlg.get_data()))
        self._next_id += 1
        self._refresh_rows()
        self.changed.emit()

    def _edit_part(self, part: TracePart):
        dlg = _PartDialog(part=part, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        for k, v in dlg.get_data().items():
            setattr(part, k, v)
        self._refresh_rows()
        self.changed.emit()

    def _delete_part(self, part: TracePart):
        if not ask_yes_no_dialog(self, 'Delete Part', f"Delete '{part.name}'? This cannot be undone."):
            return
        self._sub.parts.remove(part)
        self._refresh_rows()
        self.changed.emit()

    def _show_comments(self, part: TracePart):
        _CommentsDialog(part, parent=self).exec_()
        self._refresh_rows()
        self.changed.emit()
