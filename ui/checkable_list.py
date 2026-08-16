"""
Shared checkable-list building blocks for light-themed (white) dialogs —
originally built for ui/export_review_dialog.py, reused by
ui/annotation_merge_dialog.py.

The checkboxes are a custom-painted _CheckRow (same approach as
ui/components.py's ReportCheckbox/CheckboxIndicator), not QListWidgetItem's
native checkable flag — a QSS `image:` on ::indicator:checked turned out to
not reliably render the checkmark glyph across platforms/styles, leaving a
plain filled square with no tick. Painting it ourselves guarantees the same
look everywhere. Rows also highlight on hover and, if given a thumbnail,
pop up a larger preview near the cursor.
"""
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget, QListWidget, QListWidgetItem
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QCursor
from ui.styles import default_theme

LIST_STYLE = """
    QListWidget {
        background-color: #ffffff;
        border: 1px solid #d1d5db;
        border-radius: 8px;
        outline: none;
        padding: 4px;
    }
    QListWidget::item { border: none; }
"""


class CheckIndicator(QWidget):
    """Small rounded checkbox square, painted by hand — see module docstring
    for why (QSS ::indicator:checked wouldn't reliably show a checkmark)."""

    def __init__(self, checked: bool = True, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self._checked = checked

    def set_checked(self, checked: bool):
        self._checked = checked
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        accent = QColor(default_theme.button_primary)
        if self._checked:
            painter.setBrush(accent)
            painter.setPen(accent)
        else:
            painter.setBrush(QColor('#ffffff'))
            painter.setPen(QColor('#9ca3af'))
        painter.drawRoundedRect(rect, 4, 4)
        if self._checked:
            pen = QPen(QColor('#ffffff'), 1.6)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(4, 8, 7, 11)
            painter.drawLine(7, 11, 12, 5)


class CheckRow(QWidget):
    """One checkable row: indicator + optional thumbnail + label(s). Clicking
    anywhere on the row toggles it (bigger, easier click target than just
    the 16px square). Hovering highlights the row and, if it has a
    thumbnail, pops up a larger preview near the cursor.

    `extra` lets a caller add arbitrary widgets after the label (e.g. a
    small subtitle column) — see ui/annotation_merge_dialog.py.
    """

    toggled = pyqtSignal(bool)

    _HOVER_BG = 'background-color: #f3f4f6; border-radius: 6px;'
    _NORMAL_BG = 'background-color: transparent; border-radius: 6px;'
    _PREVIEW_SIZE = 220

    def __init__(self, value, text: str, icon: QPixmap = None, checked: bool = True,
                 subtitle: str = '', parent=None):
        super().__init__(parent)
        self.value = value
        self._icon = icon  # full-res pixmap, kept for the hover preview (the inline label only shows a scaled-down copy)
        self._preview = None
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(self._NORMAL_BG)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        self._indicator = CheckIndicator(checked)
        layout.addWidget(self._indicator)

        if icon is not None and not icon.isNull():
            icon_lbl = QLabel()
            icon_lbl.setFixedSize(32, 32)
            icon_lbl.setScaledContents(True)
            icon_lbl.setPixmap(icon)
            layout.addWidget(icon_lbl)

        if subtitle:
            text_col = QWidget()
            from PyQt5.QtWidgets import QVBoxLayout
            col_lay = QVBoxLayout(text_col)
            col_lay.setContentsMargins(0, 0, 0, 0)
            col_lay.setSpacing(1)
            label = QLabel(text)
            label.setStyleSheet('color: #111827; background: transparent; border: none; font-size: 13px;')
            sub_label = QLabel(subtitle)
            sub_label.setStyleSheet('color: #6b7280; background: transparent; border: none; font-size: 11px;')
            col_lay.addWidget(label)
            col_lay.addWidget(sub_label)
            layout.addWidget(text_col)
        else:
            label = QLabel(text)
            label.setStyleSheet('color: #111827; background: transparent; border: none; font-size: 13px;')
            layout.addWidget(label)

        layout.addStretch()

    def is_checked(self) -> bool:
        return self._indicator._checked

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            checked = not self.is_checked()
            self._indicator.set_checked(checked)
            self.toggled.emit(checked)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self.setStyleSheet(self._HOVER_BG)
        self._show_preview()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(self._NORMAL_BG)
        self._hide_preview()
        super().leaveEvent(event)

    def _show_preview(self):
        if self._icon is None or self._icon.isNull():
            return
        if self._preview is None:
            # Parented to self (not None) so it's destroyed along with this
            # row despite the ToolTip flag making it render as a top-level
            # window — otherwise it'd leak as an orphaned widget.
            self._preview = QLabel(self, Qt.ToolTip | Qt.FramelessWindowHint)
            self._preview.setStyleSheet(
                'background-color: #ffffff; border: 1px solid #d1d5db; border-radius: 8px; padding: 6px;'
            )
        scaled = self._icon.scaled(
            self._PREVIEW_SIZE, self._PREVIEW_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self._preview.setPixmap(scaled)
        self._preview.adjustSize()
        pos = QCursor.pos()
        self._preview.move(pos.x() + 18, pos.y() + 18)
        self._preview.show()

    def _hide_preview(self):
        if self._preview is not None:
            self._preview.hide()


def add_checkable_row(list_widget: QListWidget, value, text: str, icon: QPixmap = None,
                       checked: bool = True, subtitle: str = '') -> CheckRow:
    item = QListWidgetItem()
    row = CheckRow(value, text, icon=icon, checked=checked, subtitle=subtitle)
    item.setSizeHint(row.sizeHint())
    list_widget.addItem(item)
    list_widget.setItemWidget(item, row)
    return row


def checked_values(list_widget: QListWidget) -> list:
    values = []
    for i in range(list_widget.count()):
        row = list_widget.itemWidget(list_widget.item(i))
        if row is not None and row.is_checked():
            values.append(row.value)
    return values


def section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        'color: #111827; font-weight: bold; font-size: 12px; '
        'background: transparent; border: none;'
    )
    return lbl
