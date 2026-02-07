"""
Annotation Panel UI for displaying and managing 3D model annotations.
Workflow: Gray dots (pending) → Click to open popup → Add text/photos → Done → Black dot (validated)
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

# Colors for annotation states
PENDING_COLOR = '#9CA3AF'   # Gray - unvalidated
VALIDATED_COLOR = '#000000'  # Black - validated


@dataclass
class Annotation:
    """Data class for a 3D annotation."""
    id: int
    point: tuple  # (x, y, z) in world coordinates
    text: str = ""
    is_validated: bool = False  # Gray (pending) vs Black (validated)
    image_paths: List[str] = field(default_factory=list)
    is_expanded: bool = True
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'point': list(self.point),
            'text': self.text,
            'is_validated': self.is_validated,
            'image_paths': self.image_paths,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Annotation':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            point=tuple(data['point']),
            text=data.get('text', ''),
            is_validated=data.get('is_validated', False),
            image_paths=data.get('image_paths', []),
        )


class AnnotationCard(QFrame):
    """A compact card for a single annotation in the sidebar list."""
    
    # Signals
    clicked = pyqtSignal(int)  # annotation_id - opens popup
    delete_requested = pyqtSignal(int)   # annotation_id
    focus_requested = pyqtSignal(int)    # annotation_id
    
    def __init__(self, annotation: Annotation, parent=None):
        super().__init__(parent)
        self.annotation = annotation
        self.setObjectName("annotationCard")
        self.setCursor(Qt.PointingHandCursor)
        self.init_ui()
        self._update_style()
        self._update_tooltip()
    
    def init_ui(self):
        """Initialize the card UI."""
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        
        # Point indicator (colored dot) - Gray for pending, Black for validated
        self.point_indicator = QLabel("●")
        self.point_indicator.setFixedWidth(16)
        self.point_indicator.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.point_indicator)
        
        # Title and status
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        self.title_label = QLabel(f"Point {self.annotation.id}")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet(f"color: {default_theme.text_primary};")
        info_layout.addWidget(self.title_label)
        
        # Status label
        self.status_label = QLabel()
        self.status_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 9px;")
        info_layout.addWidget(self.status_label)
        
        layout.addLayout(info_layout)
        layout.addStretch()
        
        # Coordinates (small text)
        coord_text = f"({self.annotation.point[0]:.1f}, {self.annotation.point[1]:.1f}, {self.annotation.point[2]:.1f})"
        self.coord_label = QLabel(coord_text)
        self.coord_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 9px;")
        layout.addWidget(self.coord_label)
        
        # Focus button
        self.focus_btn = QPushButton("🎯")
        self.focus_btn.setFixedSize(24, 24)
        self.focus_btn.setCursor(Qt.PointingHandCursor)
        self.focus_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
                border-radius: 12px;
            }}
        """)
        self.focus_btn.clicked.connect(lambda: self.focus_requested.emit(self.annotation.id))
        layout.addWidget(self.focus_btn)
    
    def mousePressEvent(self, event):
        """Handle click to open popup."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.annotation.id)
        super().mousePressEvent(event)
    
    def _update_style(self):
        """Update the card style based on validation status."""
        if self.annotation.is_validated:
            # Black for validated
            indicator_color = VALIDATED_COLOR
            bg_color = "#F3F4F6"  # Light gray
            border_color = "#D1D5DB"
            self.status_label.setText("✓ Validated")
        else:
            # Gray for pending
            indicator_color = PENDING_COLOR
            bg_color = "#F9FAFB"  # Very light gray
            border_color = "#E5E7EB"
            self.status_label.setText("Click to edit")
        
        self.point_indicator.setStyleSheet(f"color: {indicator_color}; font-size: 14px;")
        self.setStyleSheet(f"""
            QFrame#annotationCard {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            QFrame#annotationCard:hover {{
                background-color: #E5E7EB;
            }}
        """)
    
    def update_annotation(self, annotation: Annotation):
        """Update the card with new annotation data."""
        self.annotation = annotation
        self._update_style()
        self._update_tooltip()
    
    def _update_tooltip(self):
        """Update the hover tooltip with annotation details."""
        status = "✓ Validated" if self.annotation.is_validated else "⏳ Pending - Click to edit"
        coord = f"({self.annotation.point[0]:.2f}, {self.annotation.point[1]:.2f}, {self.annotation.point[2]:.2f})"
        
        tooltip_parts = [
            f"<b>Point {self.annotation.id}</b>",
            f"<br><b>Status:</b> {status}",
            f"<br><b>Location:</b> {coord}",
        ]
        
        if self.annotation.text:
            # Truncate long text
            text_preview = self.annotation.text[:100] + "..." if len(self.annotation.text) > 100 else self.annotation.text
            tooltip_parts.append(f"<br><b>Note:</b> {text_preview}")
        
        if self.annotation.image_paths:
            tooltip_parts.append(f"<br><b>Photos:</b> {len(self.annotation.image_paths)} attached")
        
        self.setToolTip("".join(tooltip_parts))


class AnnotationPanel(QWidget):
    """Panel for managing all annotations with popup editing."""
    
    # Signals
    annotation_added = pyqtSignal(object)  # Annotation
    annotation_deleted = pyqtSignal(int)   # annotation_id
    annotation_validated = pyqtSignal(int, str, list)  # annotation_id, text, image_paths
    open_popup_requested = pyqtSignal(int)  # annotation_id - request to open popup
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
        
        main_layout.addWidget(btn_frame)
    
    def add_annotation(self, point: tuple) -> Annotation:
        """Add a new annotation at the given point (gray, pending)."""
        annotation = Annotation(
            id=self._next_id,
            point=point,
            text="",
            is_validated=False,  # Gray - pending
            image_paths=[],
        )
        self._next_id += 1
        self.annotations.append(annotation)
        
        # Create card
        card = AnnotationCard(annotation)
        card.clicked.connect(self._on_card_clicked)
        card.delete_requested.connect(self._on_delete_requested)
        card.focus_requested.connect(self._on_focus_requested)
        
        self.annotation_cards[annotation.id] = card
        self.content_layout.addWidget(card)
        
        # Update UI state
        self.empty_label.hide()
        self.clear_btn.setEnabled(True)
        
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
            card.clicked.connect(self._on_card_clicked)
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
    
    def export_annotations(self) -> List[dict]:
        """Export all annotations as serializable data."""
        return [a.to_dict() for a in self.annotations]
    
    def _on_card_clicked(self, annotation_id: int):
        """Handle card click - request to open popup."""
        self.open_popup_requested.emit(annotation_id)
    
    def _on_delete_requested(self, annotation_id: int):
        """Handle delete request from a card."""
        self.remove_annotation(annotation_id)
    
    def _on_focus_requested(self, annotation_id: int):
        """Handle focus request from a card."""
        self.focus_annotation.emit(annotation_id)
    
    def _on_clear_all(self):
        """Handle clear all button click."""
        self.clear_all_requested.emit()
    
    def validate_annotation(self, annotation_id: int, text: str, image_paths: list):
        """Validate an annotation (turn black) with text and images."""
        annotation = self.get_annotation_by_id(annotation_id)
        if annotation:
            annotation.is_validated = True
            annotation.text = text
            annotation.image_paths = image_paths
            
            # Update card display
            if annotation_id in self.annotation_cards:
                self.annotation_cards[annotation_id].update_annotation(annotation)
            
            self.annotation_validated.emit(annotation_id, text, image_paths)
            logger.info(f"Annotation validated: id={annotation_id}")
