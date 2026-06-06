"""
Color picker popup for the freehand drawing tool.
Displays a grid of preset color swatches and a custom color option.
"""
from PyQt5.QtWidgets import (
    QWidget, QGridLayout, QPushButton, QVBoxLayout, QHBoxLayout,
    QColorDialog, QLabel, QDialog, QAbstractButton
)
from PyQt5.QtCore import pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QColor
from ui.styles import default_theme, TOOLTIP_STYLE
from ui.modal_utils import BaseModal


from ui.color_palette import PALETTE as PRESET_COLORS

_TEXT = '#b8ccd8'
_BG = '#22262c'
_CARD = '#2a2e34'
_INPUT_BG = '#1e2228'
_BORDER = '#3a4050'
_ACCENT = default_theme.button_primary        # '#2596BE'
_ACCENT_HOVER = default_theme.button_primary_hover  # '#1E7FA3'
_ACCENT_PRESS = default_theme.button_primary_pressed  # '#186A8A'
_BTN_BG = '#32363e'
_BTN_HOVER = '#3d4350'

_DIALOG_STYLESHEET = f"""
    QDialog, QWidget {{
        background-color: {_BG};
        color: {_TEXT};
        font-size: 12px;
    }}
    QLabel {{
        color: {_TEXT};
        background: transparent;
        border: none;
    }}
    QLineEdit, QSpinBox, QDoubleSpinBox {{
        background-color: {_INPUT_BG};
        color: {_TEXT};
        border: 1px solid {_BORDER};
        border-radius: 4px;
        padding: 2px 6px;
        selection-background-color: {_ACCENT};
    }}
    QToolButton {{
        background-color: {_BTN_BG};
        color: {_TEXT};
        border: 1px solid {_BORDER};
        border-radius: 5px;
        padding: 4px 10px;
    }}
    QToolButton:hover {{
        background-color: {_BTN_HOVER};
        border-color: {_ACCENT};
        color: white;
    }}
    QToolButton:pressed {{
        background-color: {_ACCENT_PRESS};
    }}
    QScrollBar:vertical {{
        background: {_BG};
        width: 6px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical {{
        background: {_BORDER};
        border-radius: 3px;
    }}
"""

_OK_BTN_STYLE = f"""
    QPushButton {{
        background-color: {_ACCENT};
        color: white;
        border: none;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
        padding: 7px 24px;
    }}
    QPushButton:hover {{ background-color: {_ACCENT_HOVER}; }}
    QPushButton:pressed {{ background-color: {_ACCENT_PRESS}; }}
"""

_CANCEL_BTN_STYLE = f"""
    QPushButton {{
        background-color: {_BTN_BG};
        color: {_TEXT};
        border: 1px solid {_BORDER};
        border-radius: 6px;
        font-size: 13px;
        padding: 7px 24px;
    }}
    QPushButton:hover {{
        background-color: {_BTN_HOVER};
        border-color: {_ACCENT};
        color: white;
    }}
    QPushButton:pressed {{ background-color: {_ACCENT_PRESS}; color: white; }}
"""


class DrawColorPicker(QWidget):
    """Popup widget showing preset color swatches and a custom color button."""

    color_selected = pyqtSignal(str)  # hex color string

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {default_theme.card_background};
                border: 1px solid {default_theme.border_standard};
                border-radius: 8px;
            }}
        """)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 10)
        layout.setSpacing(6)

        title = QLabel("Pen Color")
        title.setStyleSheet(f"color: {_TEXT}; font-size: 11px; font-weight: bold; border: none;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(4)
        for i, color in enumerate(PRESET_COLORS):
            btn = QPushButton()
            btn.setFixedSize(24, 24)
            border_color = '#aaa' if color.upper() == '#FFFFFF' else 'transparent'
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: 1px solid {border_color};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border: 2px solid {default_theme.button_primary};
                    padding: 0px;
                }}
            """ + TOOLTIP_STYLE)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(color)
            btn.clicked.connect(lambda checked, c=color: self._pick(c))
            grid.addWidget(btn, i // 4, i % 4)
        layout.addLayout(grid)

        custom_btn = QPushButton("More colors…")
        custom_btn.setMinimumHeight(30)
        custom_btn.setCursor(Qt.PointingHandCursor)
        custom_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                color: {_TEXT};
                border: 1px solid {default_theme.border_standard};
                border-radius: 6px;
                font-size: 11px;
                padding: 5px 10px 6px 10px;
            }}
            QPushButton:hover {{
                background-color: {_BTN_HOVER};
                border-color: {_ACCENT};
                color: white;
            }}
            QPushButton:pressed {{
                background-color: {_ACCENT_PRESS};
                color: white;
            }}
        """)
        custom_btn.clicked.connect(self._pick_custom)
        layout.addWidget(custom_btn)

    def _pick(self, color: str):
        self.color_selected.emit(color)
        self.close()

    def _pick_custom(self):
        wrapper = BaseModal(self.parent(), "Choose Pen Color")
        outer = wrapper._root
        outer.setSpacing(14)

        # Embed QColorDialog as a plain widget (NoButtons so we supply our own)
        picker = QColorDialog(wrapper)
        picker.setWindowFlags(Qt.Widget)
        picker.setOptions(QColorDialog.DontUseNativeDialog | QColorDialog.NoButtons)
        picker.setCurrentColor(QColor('#FF0000'))
        outer.addWidget(picker)

        # Defer hiding until the event loop starts (widgets not fully built yet at this point)
        def _hide_unwanted():
            from PyQt5.QtWidgets import QWidget as _QWidget

            # 1. Hide "Custom colors" label directly
            for lbl in picker.findChildren(QLabel):
                txt = (lbl.text() or '').strip()
                if txt in ('Custom colors', 'Custom Colors'):
                    lbl.setVisible(False)

            # 2. Hide "Add to Custom Colors" + "Pick Screen Color" buttons
            for btn in picker.findChildren(QAbstractButton):
                txt = (btn.text() or '').strip()
                if ('Add' in txt and 'Custom' in txt) or 'Screen' in txt or 'Pick' in txt:
                    btn.setVisible(False)

            # 3. Hide the custom-colours swatch grid (Qt calls it QWellArray internally).
            #    Qt places two QWellArray widgets in the dialog: standard colours first,
            #    custom colours second.  We hide the second one.
            well_arrays = [
                c for c in picker.findChildren(_QWidget)
                if 'Well' in c.metaObject().className()
            ]
            if len(well_arrays) >= 2:
                for wa in well_arrays[1:]:
                    wa.setVisible(False)

        QTimer.singleShot(0, _hide_unwanted)

        # Styled OK / Cancel row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        cancel_btn = QPushButton("Cancel")
        ok_btn = QPushButton("OK")
        for b in (cancel_btn, ok_btn):
            b.setFixedHeight(36)
            b.setMinimumWidth(100)
            b.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(_CANCEL_BTN_STYLE)
        ok_btn.setStyleSheet(_OK_BTN_STYLE)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        outer.addLayout(btn_row)

        cancel_btn.clicked.connect(wrapper.reject)
        ok_btn.clicked.connect(wrapper.accept)

        try:
            accepted = wrapper.exec_()
        except TypeError:
            accepted = wrapper.exec()

        if accepted == QDialog.Accepted:
            col = picker.selectedColor()
            if col.isValid():
                self.color_selected.emit(col.name())
        self.close()
