"""
Arrow Manipulator Control Panel.
Provides buttons to select, rotate, resize, move, and delete 3D arrows.
"""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QSizePolicy
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QColor
from ui.styles import default_theme, FONTS

logger = logging.getLogger(__name__)


class ArrowCard(QFrame):
    """A single arrow entry in the list."""
    selected = pyqtSignal(int)
    delete_requested = pyqtSignal(int)

    def __init__(self, arrow_id: int, display_number: int, color: str = '#E53935', parent=None):
        super().__init__(parent)
        self.arrow_id = arrow_id
        self._is_selected = False
        self.color = color
        self.setFixedHeight(36)
        self.setCursor(Qt.PointingHandCursor)
        self._build_ui(display_number)
        self._update_style()

    def _build_ui(self, display_number: int):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Color dot
        self.color_dot = QLabel()
        self.color_dot.setFixedSize(14, 14)
        self._update_color_dot()
        layout.addWidget(self.color_dot)

        self.label = QLabel(f"Arrow {display_number}")
        self.label.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 12px; border: none; background: transparent;")
        layout.addWidget(self.label, 1)

        del_btn = QPushButton("\u00D7")  # × - cleaner close icon
        del_btn.setFixedSize(22, 22)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {default_theme.text_secondary}; border: none; font-size: 14px; font-weight: 500; border-radius: 4px; padding: 2px; min-width: 22px; min-height: 22px; }}
            QPushButton:hover {{ background: #FEE2E2; color: #DC2626; }}
        """)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.arrow_id))
        layout.addWidget(del_btn)

    def _update_color_dot(self):
        self.color_dot.setStyleSheet(
            f"background-color: {self.color}; border-radius: 7px; border: 1px solid {default_theme.border_standard};"
        )

    def _update_style(self):
        if self._is_selected:
            self.setStyleSheet(f"""
                QFrame {{ background-color: {default_theme.row_bg_hover}; border: 2px solid {default_theme.button_primary}; border-radius: 6px; }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{ background-color: {default_theme.row_bg_standard}; border: 1px solid {default_theme.border_standard}; border-radius: 6px; }}
                QFrame:hover {{ background-color: {default_theme.row_bg_hover}; }}
            """)

    def set_selected(self, selected: bool):
        self._is_selected = selected
        self._update_style()

    def set_color(self, color: str):
        self.color = color
        self._update_color_dot()

    def mousePressEvent(self, event):
        self.selected.emit(self.arrow_id)
        super().mousePressEvent(event)


def _control_button(text: str, tooltip: str = "") -> QPushButton:
    """Create a small square control button with icon-blue symbol."""
    btn = QPushButton(text)
    btn.setFixedSize(40, 36)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setToolTip(tooltip)
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {default_theme.row_bg_standard};
            color: {default_theme.icon_blue};
            border: 1px solid {default_theme.border_standard};
            border-radius: 6px;
            font-size: 14px;
            font-weight: 600;
            padding: 4px 6px;
            min-width: 40px;
            min-height: 36px;
        }}
        QPushButton:hover {{
            background-color: {default_theme.row_bg_hover};
            border-color: {default_theme.button_primary};
            color: {default_theme.button_primary};
        }}
        QPushButton:pressed {{
            background-color: {default_theme.button_primary};
            color: white;
        }}
        QPushButton:disabled {{
            color: {default_theme.text_subtext};
            background-color: {default_theme.background};
        }}
    """)
    return btn


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 10px; font-weight: bold; border: none; background: transparent; letter-spacing: 0.5px;")
    return lbl


class ArrowPanel(QWidget):
    """Right-side panel for managing 3D arrows."""

    # Signals to viewer
    rotate_requested = pyqtSignal(int, str, float)   # arrow_id, axis ('x','y','z'), angle_deg
    scale_requested = pyqtSignal(int, float)          # arrow_id, factor
    move_requested = pyqtSignal(int, float, float, float)  # arrow_id, dx, dy, dz
    color_changed = pyqtSignal(int, str)              # arrow_id, hex color
    delete_requested = pyqtSignal(int)                # arrow_id
    clear_all_requested = pyqtSignal()
    undo_last_requested = pyqtSignal()
    exit_arrow_mode = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)
        self._selected_arrow_id = None
        self._arrow_cards = {}  # arrow_id -> ArrowCard
        self._arrow_color = '#E53935'
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        icon_lbl = QLabel("\u2192")  # Right arrow (→)
        icon_lbl.setStyleSheet(f"color: {default_theme.icon_blue}; font-size: 16px; font-weight: bold; border: none; background: transparent; padding: 0 2px;")
        icon_lbl.setFixedSize(26, 24)
        icon_lbl.setAlignment(Qt.AlignCenter)
        header.addWidget(icon_lbl)
        title = QLabel("Arrows")
        title.setStyleSheet(f"color: {default_theme.text_title}; font-size: 14px; font-weight: bold; border: none; background: transparent;")
        header.addWidget(title)
        header.addStretch()
        exit_btn = QPushButton("\u00D7")  # Multiplication sign (×) - renders cleaner than ✕
        exit_btn.setFixedSize(24, 24)
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {default_theme.text_secondary}; border: none; font-size: 16px; font-weight: 500; border-radius: 4px; padding: 2px; min-width: 24px; min-height: 24px; }}
            QPushButton:hover {{ background: #FEE2E2; color: #DC2626; }}
        """)
        exit_btn.clicked.connect(self.exit_arrow_mode.emit)
        header.addWidget(exit_btn)
        layout.addLayout(header)

        # Info label
        info = QLabel("Click on model to place arrows.\nSelect an arrow below to adjust it.")
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {default_theme.text_subtext}; font-size: 10px; border: none; background: transparent;")
        layout.addWidget(info)

        # Arrow list
        layout.addWidget(_section_label("PLACED ARROWS"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(160)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(3)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll)

        self._no_arrows_label = QLabel("No arrows placed yet")
        self._no_arrows_label.setAlignment(Qt.AlignCenter)
        self._no_arrows_label.setStyleSheet(f"color: {default_theme.text_subtext}; font-size: 11px; border: none; background: transparent; padding: 8px;")
        self._list_layout.insertWidget(0, self._no_arrows_label)

        # ---- Controls (disabled when no arrow selected) ----
        self._controls_container = QWidget()
        ctrl_layout = QVBoxLayout(self._controls_container)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(6)

        # Rotation
        ctrl_layout.addWidget(_section_label("ROTATION"))
        rot_grid = QVBoxLayout()
        rot_grid.setSpacing(3)

        row1 = QHBoxLayout()
        row1.setSpacing(3)
        self._rot_left = _control_button("\u2190", "Rotate Left (Y-axis)")   # ←
        self._rot_right = _control_button("\u2192", "Rotate Right (Y-axis)")  # →
        self._rot_up = _control_button("\u2191", "Rotate Up (X-axis)")    # ↑
        self._rot_down = _control_button("\u2193", "Rotate Down (X-axis)")  # ↓
        row1.addWidget(self._rot_left)
        row1.addWidget(self._rot_right)
        row1.addWidget(self._rot_up)
        row1.addWidget(self._rot_down)
        rot_grid.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(3)
        self._rot_cw = _control_button("\u21BB", "Tilt Clockwise (Z-axis)")   # ↻
        self._rot_ccw = _control_button("\u21BA", "Tilt Counter-Clockwise (Z-axis)")  # ↺
        row2.addWidget(self._rot_cw)
        row2.addWidget(self._rot_ccw)
        row2.addStretch()
        rot_grid.addLayout(row2)
        ctrl_layout.addLayout(rot_grid)

        # Connect rotation buttons
        self._rot_left.clicked.connect(lambda: self._emit_rotate('y', -15))
        self._rot_right.clicked.connect(lambda: self._emit_rotate('y', 15))
        self._rot_up.clicked.connect(lambda: self._emit_rotate('x', -15))
        self._rot_down.clicked.connect(lambda: self._emit_rotate('x', 15))
        self._rot_cw.clicked.connect(lambda: self._emit_rotate('z', 15))
        self._rot_ccw.clicked.connect(lambda: self._emit_rotate('z', -15))

        # Size
        ctrl_layout.addWidget(_section_label("SIZE"))
        size_row = QHBoxLayout()
        size_row.setSpacing(3)
        self._size_plus = _control_button("+", "Lengthen arrow")
        self._size_minus = _control_button("\u2212", "Shorten arrow")  # − (minus sign)
        size_row.addWidget(self._size_plus)
        size_row.addWidget(self._size_minus)
        size_row.addStretch()
        ctrl_layout.addLayout(size_row)

        self._size_plus.clicked.connect(lambda: self._emit_scale(1.15))
        self._size_minus.clicked.connect(lambda: self._emit_scale(0.85))

        # Move
        ctrl_layout.addWidget(_section_label("MOVE"))
        move_grid = QVBoxLayout()
        move_grid.setSpacing(3)

        mrow1 = QHBoxLayout()
        mrow1.setSpacing(3)
        self._move_xp = _control_button("X+", "Move along X+")
        self._move_xn = _control_button("X-", "Move along X-")
        self._move_yp = _control_button("Y+", "Move along Y+")
        self._move_yn = _control_button("Y-", "Move along Y-")
        mrow1.addWidget(self._move_xp)
        mrow1.addWidget(self._move_xn)
        mrow1.addWidget(self._move_yp)
        mrow1.addWidget(self._move_yn)
        move_grid.addLayout(mrow1)

        mrow2 = QHBoxLayout()
        mrow2.setSpacing(3)
        self._move_zp = _control_button("Z+", "Move along Z+")
        self._move_zn = _control_button("Z-", "Move along Z-")
        mrow2.addWidget(self._move_zp)
        mrow2.addWidget(self._move_zn)
        mrow2.addStretch()
        move_grid.addLayout(mrow2)
        ctrl_layout.addLayout(move_grid)

        self._move_xp.clicked.connect(lambda: self._emit_move(1, 0, 0))
        self._move_xn.clicked.connect(lambda: self._emit_move(-1, 0, 0))
        self._move_yp.clicked.connect(lambda: self._emit_move(0, 1, 0))
        self._move_yn.clicked.connect(lambda: self._emit_move(0, -1, 0))
        self._move_zp.clicked.connect(lambda: self._emit_move(0, 0, 1))
        self._move_zn.clicked.connect(lambda: self._emit_move(0, 0, -1))

        # Color
        ctrl_layout.addWidget(_section_label("COLOR"))
        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(28, 28)
        self._color_btn.setCursor(Qt.PointingHandCursor)
        self._color_btn.setToolTip("Change arrow color")
        self._update_color_btn_style()
        self._color_btn.clicked.connect(self._pick_color)
        color_row.addWidget(self._color_btn)
        color_label = QLabel("Change color")
        color_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 11px; border: none; background: transparent;")
        color_row.addWidget(color_label)
        color_row.addStretch()
        ctrl_layout.addLayout(color_row)

        layout.addWidget(self._controls_container)
        self._controls_container.setEnabled(False)

        layout.addStretch()

        # Bottom actions
        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        undo_btn = QPushButton("Undo Last")
        undo_btn.setCursor(Qt.PointingHandCursor)
        undo_btn.setFixedHeight(30)
        undo_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.border_standard};
                border-radius: 6px; font-size: 11px;
            }}
            QPushButton:hover {{ background-color: {default_theme.row_bg_hover}; }}
        """)
        undo_btn.clicked.connect(self.undo_last_requested.emit)
        bottom.addWidget(undo_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setFixedHeight(30)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #3A2020;
                color: #F87171;
                border: 1px solid #5A3030;
                border-radius: 6px; font-size: 11px;
            }}
            QPushButton:hover {{ background-color: #4A2828; color: white; }}
        """)
        clear_btn.clicked.connect(self.clear_all_requested.emit)
        bottom.addWidget(clear_btn)
        layout.addLayout(bottom)

    # ---- Public API ----

    def add_arrow(self, arrow_id: int):
        """Add an arrow card to the list."""
        display_num = len(self._arrow_cards) + 1
        card = ArrowCard(arrow_id, display_num, self._arrow_color)
        card.selected.connect(self._on_arrow_selected)
        card.delete_requested.connect(self.delete_requested.emit)
        self._arrow_cards[arrow_id] = card
        # Insert before the stretch
        self._list_layout.insertWidget(self._list_layout.count() - 1, card)
        self._no_arrows_label.hide()
        # Auto-select the new arrow
        self._on_arrow_selected(arrow_id)

    def remove_arrow(self, arrow_id: int):
        """Remove an arrow card from the list."""
        card = self._arrow_cards.pop(arrow_id, None)
        if card:
            self._list_layout.removeWidget(card)
            card.deleteLater()
        if self._selected_arrow_id == arrow_id:
            self._selected_arrow_id = None
            self._controls_container.setEnabled(False)
        if not self._arrow_cards:
            self._no_arrows_label.show()
        self._renumber()

    def clear_all(self):
        """Remove all arrow cards."""
        for card in list(self._arrow_cards.values()):
            self._list_layout.removeWidget(card)
            card.deleteLater()
        self._arrow_cards.clear()
        self._selected_arrow_id = None
        self._controls_container.setEnabled(False)
        self._no_arrows_label.show()

    def get_selected_arrow_id(self):
        return self._selected_arrow_id

    # ---- Internal ----

    def _renumber(self):
        for i, (aid, card) in enumerate(self._arrow_cards.items(), 1):
            card.label.setText(f"Arrow {i}")

    def _on_arrow_selected(self, arrow_id: int):
        self._selected_arrow_id = arrow_id
        self._controls_container.setEnabled(True)
        for aid, card in self._arrow_cards.items():
            card.set_selected(aid == arrow_id)

    def _emit_rotate(self, axis: str, angle: float):
        if self._selected_arrow_id is not None:
            self.rotate_requested.emit(self._selected_arrow_id, axis, angle)

    def _emit_scale(self, factor: float):
        if self._selected_arrow_id is not None:
            self.scale_requested.emit(self._selected_arrow_id, factor)

    def _emit_move(self, dx, dy, dz):
        if self._selected_arrow_id is not None:
            self.move_requested.emit(self._selected_arrow_id, float(dx), float(dy), float(dz))

    def _update_color_btn_style(self):
        self._color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._arrow_color};
                border: 2px solid {default_theme.border_standard};
                border-radius: 6px;
            }}
            QPushButton:hover {{ border-color: {default_theme.button_primary}; }}
        """)

    def _pick_color(self):
        from PyQt5.QtWidgets import QColorDialog
        color = QColorDialog.getColor(QColor(self._arrow_color), self, "Choose Arrow Color")
        if color.isValid():
            self._arrow_color = color.name()
            self._update_color_btn_style()
            if self._selected_arrow_id is not None:
                card = self._arrow_cards.get(self._selected_arrow_id)
                if card:
                    card.set_color(self._arrow_color)
                self.color_changed.emit(self._selected_arrow_id, self._arrow_color)
