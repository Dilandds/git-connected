"""
Annotation Panel UI for displaying and managing 3D model annotations.
Updated: Test commit for local sync verification.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QTextEdit, QSizePolicy, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor
from ui.styles import default_theme

logger = logging.getLogger(__name__)


@dataclass
class Annotation:
    """Data class for a 3D annotation."""
    id: int
    point: tuple  # (x, y, z) in world coordinates
    text: str = ""
    is_read: bool = False
    is_expanded: bool = True
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'point': list(self.point),
            'text': self.text,
            'is_read': self.is_read,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Annotation':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            point=tuple(data['point']),
            text=data.get('text', ''),
            is_read=data.get('is_read', False),
        )


class AnnotationCard(QFrame):
    """A collapsible card for a single annotation."""
    
    # Signals
    text_changed = pyqtSignal(int, str)  # annotation_id, new_text
    delete_requested = pyqtSignal(int)   # annotation_id
    focus_requested = pyqtSignal(int)    # annotation_id
    expanded_changed = pyqtSignal(int, bool)  # annotation_id, is_expanded
    read_status_changed = pyqtSignal(int, bool)  # annotation_id, is_read
    
    def __init__(self, annotation: Annotation, parent=None):
        super().__init__(parent)
        self.annotation = annotation
        self.is_expanded = annotation.is_expanded
        self.setObjectName("annotationCard")
        self.init_ui()
        self._update_style()
    
    def init_ui(self):
        """Initialize the card UI."""
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header (always visible)
        self.header = QFrame()
        self.header.setObjectName("annotationHeader")
        self.header.setCursor(Qt.PointingHandCursor)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setSpacing(8)
        
        # Point indicator (colored dot)
        self.point_indicator = QLabel("●")
        self.point_indicator.setFixedWidth(16)
        self.point_indicator.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.point_indicator)
        
        # Title
        self.title_label = QLabel(f"Point {self.annotation.id}")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet(f"color: {default_theme.text_primary};")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        # Coordinates (small text)
        coord_text = f"({self.annotation.point[0]:.1f}, {self.annotation.point[1]:.1f}, {self.annotation.point[2]:.1f})"
        self.coord_label = QLabel(coord_text)
        self.coord_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 9px;")
        header_layout.addWidget(self.coord_label)
        
        # Expand/collapse button
        self.toggle_btn = QPushButton("▼" if self.is_expanded else "▶")
        self.toggle_btn.setFixedSize(24, 24)
        self.toggle_btn.setFlat(True)
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                color: {default_theme.text_secondary};
                border: none;
                background: transparent;
                font-size: 10px;
            }}
            QPushButton:hover {{
                color: {default_theme.text_primary};
            }}
        """)
        self.toggle_btn.clicked.connect(self._toggle_expanded)
        header_layout.addWidget(self.toggle_btn)
        
        main_layout.addWidget(self.header)
        
        # Content (collapsible)
        self.content = QFrame()
        self.content.setObjectName("annotationContent")
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(10, 0, 10, 10)
        content_layout.setSpacing(8)
        
        # Text input
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Add annotation text...")
        self.text_edit.setText(self.annotation.text)
        self.text_edit.setMinimumHeight(60)
        self.text_edit.setMaximumHeight(100)
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {default_theme.input_bg};
                border: 1px solid {default_theme.input_border};
                border-radius: 6px;
                padding: 6px;
                font-size: 11px;
                color: {default_theme.text_primary};
            }}
            QTextEdit:focus {{
                border: 2px solid {default_theme.button_primary};
            }}
        """)
        self.text_edit.textChanged.connect(self._on_text_changed)
        content_layout.addWidget(self.text_edit)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        self.focus_btn = QPushButton("🎯 Focus")
        self.focus_btn.setFixedHeight(28)
        self.focus_btn.setCursor(Qt.PointingHandCursor)
        self.focus_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                border: 1px solid {default_theme.border_light};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 10px;
                color: {default_theme.text_primary};
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """)
        self.focus_btn.clicked.connect(lambda: self.focus_requested.emit(self.annotation.id))
        btn_layout.addWidget(self.focus_btn)
        
        btn_layout.addStretch()
        
        self.delete_btn = QPushButton("🗑 Delete")
        self.delete_btn.setFixedHeight(28)
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #FEE2E2;
                border: 1px solid #FECACA;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 10px;
                color: #DC2626;
            }}
            QPushButton:hover {{
                background-color: #FECACA;
            }}
        """)
        self.delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.annotation.id))
        btn_layout.addWidget(self.delete_btn)
        
        content_layout.addLayout(btn_layout)
        
        main_layout.addWidget(self.content)
        
        # Set initial visibility
        self.content.setVisible(self.is_expanded)
        
        # Make header clickable
        self.header.mousePressEvent = lambda e: self._toggle_expanded()
    
    def _toggle_expanded(self):
        """Toggle the expanded state."""
        self.is_expanded = not self.is_expanded
        self.annotation.is_expanded = self.is_expanded
        self.content.setVisible(self.is_expanded)
        self.toggle_btn.setText("▼" if self.is_expanded else "▶")
        
        # Mark as read when collapsed
        if not self.is_expanded and not self.annotation.is_read:
            self.annotation.is_read = True
            self._update_style()
            self.read_status_changed.emit(self.annotation.id, True)
        
        self.expanded_changed.emit(self.annotation.id, self.is_expanded)
    
    def _on_text_changed(self):
        """Handle text changes."""
        self.annotation.text = self.text_edit.toPlainText()
        self.text_changed.emit(self.annotation.id, self.annotation.text)
    
    def _update_style(self):
        """Update the card style based on read status."""
        if self.annotation.is_read:
            # Green for read
            indicator_color = "#10B981"
            bg_color = "#ECFDF5"
            border_color = "#A7F3D0"
        else:
            # Blue for unread
            indicator_color = "#3B82F6"
            bg_color = "#EFF6FF"
            border_color = "#BFDBFE"
        
        self.point_indicator.setStyleSheet(f"color: {indicator_color}; font-size: 14px;")
        self.setStyleSheet(f"""
            QFrame#annotationCard {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """)
        self.header.setStyleSheet(f"""
            QFrame#annotationHeader {{
                background-color: transparent;
                border: none;
            }}
        """)
    
    def set_read(self, is_read: bool):
        """Set the read status."""
        self.annotation.is_read = is_read
        self._update_style()
    
    def collapse(self):
        """Collapse the card (marks as read)."""
        if self.is_expanded:
            self._toggle_expanded()


class AnnotationPanel(QWidget):
    """Panel for managing all annotations."""
    
    # Signals
    annotation_added = pyqtSignal(object)  # Annotation
    annotation_deleted = pyqtSignal(int)   # annotation_id
    annotation_updated = pyqtSignal(int, str)  # annotation_id, new_text
    annotation_read_changed = pyqtSignal(int, bool)  # annotation_id, is_read
    focus_annotation = pyqtSignal(int)     # annotation_id
    exit_annotation_mode = pyqtSignal()
    clear_all_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.annotations: List[Annotation] = []
        self.annotation_cards: dict = {}  # id -> AnnotationCard
        self._next_id = 1
        self.init_ui()
    
    def init_ui(self):
        """Initialize the panel UI."""
        self.setMinimumWidth(280)
        self.setMaximumWidth(350)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Header
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {default_theme.card_background};
                border: 1px solid {default_theme.border_standard};
                border-radius: 8px;
            }}
        """)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(6)
        
        # Title row
        title_row = QHBoxLayout()
        title_label = QLabel("📝 Annotations")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {default_theme.text_title};")
        title_row.addWidget(title_label)
        title_row.addStretch()
        
        # Close button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {default_theme.text_secondary};
                font-size: 14px;
            }}
            QPushButton:hover {{
                color: {default_theme.text_primary};
                background-color: {default_theme.row_bg_hover};
                border-radius: 12px;
            }}
        """)
        close_btn.clicked.connect(self.exit_annotation_mode.emit)
        title_row.addWidget(close_btn)
        
        header_layout.addLayout(title_row)
        
        # Instructions
        instructions = QLabel("Click on the 3D model to add annotation points")
        instructions.setWordWrap(True)
        instructions.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 10px;")
        header_layout.addWidget(instructions)
        
        main_layout.addWidget(header)
        
        # Scroll area for annotation cards
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
        """)
        
        # Content widget
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)
        self.content_layout.setAlignment(Qt.AlignTop)
        
        # Empty state
        self.empty_label = QLabel("No annotations yet.\nClick on the model to add one.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 11px; padding: 20px;")
        self.content_layout.addWidget(self.empty_label)
        
        scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(scroll_area, 1)
        
        # Action buttons
        btn_frame = QFrame()
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)
        
        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.setFixedHeight(32)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setEnabled(False)
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                color: {default_theme.text_primary};
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
            QPushButton:disabled {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_secondary};
            }}
        """)
        self.clear_btn.clicked.connect(self._on_clear_all)
        btn_layout.addWidget(self.clear_btn)
        
        btn_layout.addStretch()
        
        self.collapse_all_btn = QPushButton("Collapse All")
        self.collapse_all_btn.setFixedHeight(32)
        self.collapse_all_btn.setCursor(Qt.PointingHandCursor)
        self.collapse_all_btn.setEnabled(False)
        self.collapse_all_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.button_primary};
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                color: white;
            }}
            QPushButton:hover {{
                background-color: {default_theme.button_primary_hover};
            }}
            QPushButton:disabled {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_secondary};
            }}
        """)
        self.collapse_all_btn.clicked.connect(self._collapse_all)
        btn_layout.addWidget(self.collapse_all_btn)
        
        main_layout.addWidget(btn_frame)
    
    def add_annotation(self, point: tuple) -> Annotation:
        """Add a new annotation at the given point."""
        annotation = Annotation(
            id=self._next_id,
            point=point,
            text="",
            is_read=False,
            is_expanded=True,
        )
        self._next_id += 1
        self.annotations.append(annotation)
        
        # Create card
        card = AnnotationCard(annotation)
        card.text_changed.connect(self._on_text_changed)
        card.delete_requested.connect(self._on_delete_requested)
        card.focus_requested.connect(self._on_focus_requested)
        card.read_status_changed.connect(self._on_read_status_changed)
        
        self.annotation_cards[annotation.id] = card
        self.content_layout.addWidget(card)
        
        # Update UI state
        self.empty_label.hide()
        self.clear_btn.setEnabled(True)
        self.collapse_all_btn.setEnabled(True)
        
        self.annotation_added.emit(annotation)
        logger.info(f"Annotation added: id={annotation.id}, point={point}")
        
        return annotation
    
    def remove_annotation(self, annotation_id: int):
        """Remove an annotation by ID."""
        # Find and remove from list
        self.annotations = [a for a in self.annotations if a.id != annotation_id]
        
        # Remove card
        if annotation_id in self.annotation_cards:
            card = self.annotation_cards.pop(annotation_id)
            self.content_layout.removeWidget(card)
            card.deleteLater()
        
        # Update UI state
        if not self.annotations:
            self.empty_label.show()
            self.clear_btn.setEnabled(False)
            self.collapse_all_btn.setEnabled(False)
        
        self.annotation_deleted.emit(annotation_id)
        logger.info(f"Annotation removed: id={annotation_id}")
    
    def clear_all(self):
        """Remove all annotations."""
        for annotation_id in list(self.annotation_cards.keys()):
            self.remove_annotation(annotation_id)
        self._next_id = 1
    
    def get_annotations(self) -> List[Annotation]:
        """Get all annotations."""
        return self.annotations.copy()
    
    def get_annotation_by_id(self, annotation_id: int) -> Optional[Annotation]:
        """Get an annotation by ID."""
        for a in self.annotations:
            if a.id == annotation_id:
                return a
        return None
    
    def load_annotations(self, data: List[dict]):
        """Load annotations from serialized data."""
        self.clear_all()
        for item in data:
            annotation = Annotation.from_dict(item)
            self.annotations.append(annotation)
            
            # Create card
            card = AnnotationCard(annotation)
            card.text_changed.connect(self._on_text_changed)
            card.delete_requested.connect(self._on_delete_requested)
            card.focus_requested.connect(self._on_focus_requested)
            
            self.annotation_cards[annotation.id] = card
            self.content_layout.addWidget(card)
            
            # Update next ID
            if annotation.id >= self._next_id:
                self._next_id = annotation.id + 1
        
        if self.annotations:
            self.empty_label.hide()
            self.clear_btn.setEnabled(True)
            self.collapse_all_btn.setEnabled(True)
    
    def export_annotations(self) -> List[dict]:
        """Export all annotations as serializable data."""
        return [a.to_dict() for a in self.annotations]
    
    def _on_text_changed(self, annotation_id: int, text: str):
        """Handle text change in a card."""
        self.annotation_updated.emit(annotation_id, text)
    
    def _on_delete_requested(self, annotation_id: int):
        """Handle delete request from a card."""
        self.remove_annotation(annotation_id)
    
    def _on_focus_requested(self, annotation_id: int):
        """Handle focus request from a card."""
        self.focus_annotation.emit(annotation_id)
    
    def _on_clear_all(self):
        """Handle clear all button click."""
        self.clear_all_requested.emit()
    
    def _on_read_status_changed(self, annotation_id: int, is_read: bool):
        """Handle read status change from a card."""
        self.annotation_read_changed.emit(annotation_id, is_read)
    
    def _collapse_all(self):
        """Collapse all annotation cards."""
        for card in self.annotation_cards.values():
            card.collapse()
