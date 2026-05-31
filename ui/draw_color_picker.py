"""
Color picker popup for the freehand drawing tool.
Displays a grid of preset color swatches and a custom color option.
"""
from PyQt5.QtWidgets import (
    QWidget, QGridLayout, QPushButton, QVBoxLayout, QColorDialog, QLabel,
    QSpinBox, QLineEdit, QToolButton
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QColor
from ui.styles import default_theme


from ui.color_palette import PALETTE as PRESET_COLORS


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
        title.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 11px; font-weight: bold; border: none;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(4)
        for i, color in enumerate(PRESET_COLORS):
            btn = QPushButton()
            btn.setFixedSize(24, 24)
            border_color = '#aaa' if color.upper() == '#FFFFFF' else 'transparent'
            # Hover shows a prominent outline to indicate selection affordance
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
            """)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(color)
            btn.clicked.connect(lambda checked, c=color: self._pick(c))
            grid.addWidget(btn, i // 4, i % 4)
        layout.addLayout(grid)

        custom_btn = QPushButton("Custom…")
        custom_btn.setMinimumHeight(30)
        custom_btn.setCursor(Qt.PointingHandCursor)
        custom_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.border_standard};
                border-radius: 6px;
                font-size: 11px;
                padding: 5px 10px 6px 10px;
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """)
        custom_btn.clicked.connect(self._pick_custom)
        layout.addWidget(custom_btn)

    def _pick(self, color: str):
        self.color_selected.emit(color)
        self.close()

    def _pick_custom(self):
        # Use a Qt-based (non-native) QColorDialog so we can enforce readable text
        dialog = QColorDialog(self.parent())
        dialog.setWindowTitle("Choose Pen Color")
        dialog.setCurrentColor(QColor('#FF0000'))
        # Force Qt dialog (don't use the OS native color picker) so stylesheet applies
        dialog.setOption(QColorDialog.DontUseNativeDialog, True)
        # Force black text color for labels/inputs/buttons inside the dialog (Windows native pickers can be unreadable)
        dialog.setStyleSheet("""
            QWidget, QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QToolButton, QPushButton {
                color: #000000 !important;
            }
        """)
        # Remove advanced controls (HSV/RGB spinners, HTML field, custom colors grid)
        # by hiding common widget classes used in that panel. This keeps the
        # dialog minimal (picker + OK/Cancel) as requested.
        try:
            # Hide labels that match the unwanted controls
            banned_labels = ('Hue', 'Hue:', 'Sat', 'Sat:', 'Val', 'Val:', 'Red', 'Green', 'Blue', 'HTML', 'Custom colors', 'Add to Custom Colors', 'Pick Screen Color')
            for lbl in dialog.findChildren(QLabel):
                try:
                    txt = lbl.text() or ''
                    if any(b in txt for b in banned_labels):
                        parent = lbl.parent()
                        if parent is not None:
                            parent.setVisible(False)
                        else:
                            lbl.setVisible(False)
                except Exception:
                    continue

            # Hide numeric inputs and free-form HTML field if present
            for sp in dialog.findChildren(QSpinBox):
                sp.setVisible(False)
            for le in dialog.findChildren(QLineEdit):
                # Hide the HTML field and any small text inputs used for RGB/HSV
                le.setVisible(False)
            # Hide small tool buttons that belong to the advanced panel
            for tb in dialog.findChildren(QToolButton):
                tb.setVisible(False)
        except Exception:
            # If anything goes wrong with hiding heuristics, fall back to showing the dialog as-is
            pass

        # Exec the dialog and emit the selected color if accepted
        try:
            accepted = dialog.exec_()
        except TypeError:
            accepted = dialog.exec()

        if accepted == QColorDialog.Accepted:
            col = dialog.selectedColor()
            if col.isValid():
                self.color_selected.emit(col.name())
        self.close()
