"""
Parts List Panel for hiding/showing individual sub-meshes of a 3D model.
Allows users to isolate interior components by toggling visibility.
"""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QSizePolicy
)
from PyQt5.QtCore import pyqtSignal, Qt
from ui.styles import default_theme

logger = logging.getLogger(__name__)


class PartCard(QFrame):
    """A single part entry in the list."""
    selected = pyqtSignal(int)
    visibility_toggled = pyqtSignal(int, bool)  # part_id, visible

    def __init__(self, part_id: int, name: str, face_count: int = 0, parent=None):
        super().__init__(parent)
        self.part_id = part_id
        self._is_selected = False
        self._is_visible = True
        self.face_count = face_count
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self._build_ui(name)
        self._update_style()

    def _build_ui(self, name: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Eye toggle button
        self.eye_btn = QPushButton("👁")
        self.eye_btn.setFixedSize(26, 26)
        self.eye_btn.setCursor(Qt.PointingHandCursor)
        self.eye_btn.setToolTip("Toggle visibility")
        self.eye_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; font-size: 13px; padding: 2px; min-width: 26px; min-height: 26px; border-radius: 4px; }}
            QPushButton:hover {{ background: {default_theme.row_bg_hover}; }}
        """)
        self.eye_btn.clicked.connect(self._toggle_visibility)
        layout.addWidget(self.eye_btn)

        # Part info
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(0)

        self.name_label = QLabel(name)
        self.name_label.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 11px; font-weight: 500; border: none; background: transparent;")
        info_layout.addWidget(self.name_label)

        if face_count > 0:
            face_label = QLabel(f"{face_count:,} faces")
            face_label.setStyleSheet(f"color: {default_theme.text_subtext}; font-size: 9px; border: none; background: transparent;")
            info_layout.addWidget(face_label)

        layout.addLayout(info_layout, 1)

    def _toggle_visibility(self):
        self._is_visible = not self._is_visible
        self.eye_btn.setText("👁" if self._is_visible else "👁‍🗨")
        self.eye_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; font-size: 13px; padding: 2px; min-width: 26px; min-height: 26px; border-radius: 4px; opacity: {'1.0' if self._is_visible else '0.4'}; }}
            QPushButton:hover {{ background: {default_theme.row_bg_hover}; }}
        """)
        self._update_style()
        self.visibility_toggled.emit(self.part_id, self._is_visible)

    def _update_style(self):
        if self._is_selected:
            self.setStyleSheet(f"""
                QFrame {{ background-color: {default_theme.row_bg_hover}; border: 2px solid {default_theme.button_primary}; border-radius: 6px; }}
            """)
        elif not self._is_visible:
            self.setStyleSheet(f"""
                QFrame {{ background-color: {default_theme.background}; border: 1px solid {default_theme.border_standard}; border-radius: 6px; opacity: 0.5; }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{ background-color: {default_theme.row_bg_standard}; border: 1px solid {default_theme.border_standard}; border-radius: 6px; }}
                QFrame:hover {{ background-color: {default_theme.row_bg_hover}; }}
            """)

    def set_selected(self, selected: bool):
        self._is_selected = selected
        self._update_style()

    def set_visible_state(self, visible: bool):
        """Set visibility without emitting signal."""
        self._is_visible = visible
        self.eye_btn.setText("👁" if visible else "👁‍🗨")
        self._update_style()

    def mousePressEvent(self, event):
        self.selected.emit(self.part_id)
        super().mousePressEvent(event)


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 10px; font-weight: bold; border: none; background: transparent; letter-spacing: 0.5px;")
    return lbl


class PartsPanel(QWidget):
    """Right-side panel for managing 3D model part visibility."""

    # Signals to viewer
    part_visibility_changed = pyqtSignal(int, bool)   # part_id, visible
    part_selected = pyqtSignal(int)                    # part_id
    show_all_requested = pyqtSignal()
    hide_all_requested = pyqtSignal()
    invert_visibility_requested = pyqtSignal()
    isolate_selected_requested = pyqtSignal(int)       # part_id
    exit_parts_mode = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)
        self._selected_part_id = None
        self._part_cards = {}  # part_id -> PartCard
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        icon_lbl = QLabel("🧩")
        icon_lbl.setStyleSheet(f"color: {default_theme.icon_blue}; font-size: 14px; border: none; background: transparent; padding: 0 2px;")
        icon_lbl.setFixedSize(26, 24)
        icon_lbl.setAlignment(Qt.AlignCenter)
        header.addWidget(icon_lbl)
        title = QLabel("Parts")
        title.setStyleSheet(f"color: {default_theme.text_title}; font-size: 14px; font-weight: bold; border: none; background: transparent;")
        header.addWidget(title)
        header.addStretch()

        # Part count badge
        self._count_label = QLabel("0 parts")
        self._count_label.setStyleSheet(f"color: {default_theme.text_subtext}; font-size: 10px; border: none; background: transparent;")
        header.addWidget(self._count_label)

        exit_btn = QPushButton("\u00D7")
        exit_btn.setFixedSize(24, 24)
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {default_theme.text_secondary}; border: none; font-size: 16px; font-weight: 500; border-radius: 4px; padding: 2px; min-width: 24px; min-height: 24px; }}
            QPushButton:hover {{ background: #FEE2E2; color: #DC2626; }}
        """)
        exit_btn.clicked.connect(self.exit_parts_mode.emit)
        header.addWidget(exit_btn)
        layout.addLayout(header)

        # Info
        info = QLabel("Toggle visibility of individual parts.\nClick to select, use eye icon to hide/show.")
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {default_theme.text_subtext}; font-size: 10px; border: none; background: transparent;")
        layout.addWidget(info)

        # Parts list
        layout.addWidget(_section_label("MODEL PARTS"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(3)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll, 1)

        self._no_parts_label = QLabel("No parts detected")
        self._no_parts_label.setAlignment(Qt.AlignCenter)
        self._no_parts_label.setStyleSheet(f"color: {default_theme.text_subtext}; font-size: 11px; border: none; background: transparent; padding: 8px;")
        self._list_layout.insertWidget(0, self._no_parts_label)

        # Bulk actions
        layout.addWidget(_section_label("ACTIONS"))
        actions_row1 = QHBoxLayout()
        actions_row1.setSpacing(4)

        show_all_btn = self._action_button("Show All")
        show_all_btn.clicked.connect(self._on_show_all)
        actions_row1.addWidget(show_all_btn)

        hide_all_btn = self._action_button("Hide All")
        hide_all_btn.clicked.connect(self._on_hide_all)
        actions_row1.addWidget(hide_all_btn)

        layout.addLayout(actions_row1)

        actions_row2 = QHBoxLayout()
        actions_row2.setSpacing(4)

        invert_btn = self._action_button("Invert")
        invert_btn.clicked.connect(self._on_invert)
        actions_row2.addWidget(invert_btn)

        self._isolate_btn = self._action_button("Isolate Selected")
        self._isolate_btn.setEnabled(False)
        self._isolate_btn.clicked.connect(self._on_isolate)
        actions_row2.addWidget(self._isolate_btn)

        layout.addLayout(actions_row2)

    def _action_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(28)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.border_standard};
                border-radius: 6px; font-size: 10px;
            }}
            QPushButton:hover {{ background-color: {default_theme.row_bg_hover}; }}
            QPushButton:disabled {{ color: {default_theme.text_subtext}; background-color: {default_theme.background}; }}
        """)
        return btn

    # ---- Public API ----

    def set_parts(self, parts_list: list):
        """Set the parts list. Each item: {'id': int, 'name': str, 'face_count': int, 'visible': bool}."""
        self.clear_all()
        for part in parts_list:
            card = PartCard(part['id'], part['name'], part.get('face_count', 0))
            card.set_visible_state(part.get('visible', True))
            card.selected.connect(self._on_part_selected)
            card.visibility_toggled.connect(self._on_visibility_toggled)
            self._part_cards[part['id']] = card
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)

        if self._part_cards:
            self._no_parts_label.hide()
        self._count_label.setText(f"{len(self._part_cards)} part{'s' if len(self._part_cards) != 1 else ''}")

    def clear_all(self):
        """Remove all part cards."""
        for card in list(self._part_cards.values()):
            self._list_layout.removeWidget(card)
            card.deleteLater()
        self._part_cards.clear()
        self._selected_part_id = None
        self._isolate_btn.setEnabled(False)
        self._no_parts_label.show()
        self._count_label.setText("0 parts")

    def get_selected_part_id(self):
        return self._selected_part_id

    # ---- Internal ----

    def _on_part_selected(self, part_id: int):
        self._selected_part_id = part_id
        self._isolate_btn.setEnabled(True)
        for pid, card in self._part_cards.items():
            card.set_selected(pid == part_id)
        self.part_selected.emit(part_id)

    def _on_visibility_toggled(self, part_id: int, visible: bool):
        self.part_visibility_changed.emit(part_id, visible)

    def _on_show_all(self):
        for card in self._part_cards.values():
            card.set_visible_state(True)
        self.show_all_requested.emit()

    def _on_hide_all(self):
        for card in self._part_cards.values():
            card.set_visible_state(False)
        self.hide_all_requested.emit()

    def _on_invert(self):
        for card in self._part_cards.values():
            card.set_visible_state(not card._is_visible)
        self.invert_visibility_requested.emit()

    def _on_isolate(self):
        if self._selected_part_id is None:
            return
        # Hide all except selected
        for pid, card in self._part_cards.items():
            card.set_visible_state(pid == self._selected_part_id)
        self.isolate_selected_requested.emit(self._selected_part_id)
