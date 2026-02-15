"""
Annotation Panel UI for displaying and managing 3D model annotations.
Workflow: Gray dots (pending) → Click to open popup → Add text/photos → Done → Black dot (validated)
"""
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Callable
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QTextEdit, QLineEdit, QSizePolicy, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor, QPixmap, QPainter, QBrush, QPen
from ui.styles import default_theme

logger = logging.getLogger(__name__)

# Colors for annotation states
PENDING_COLOR = '#909d92'   # Light grey - unvalidated
VALIDATED_COLOR = '#1821b4'  # Blue - validated
READER_UNREAD_COLOR = '#36cd2e'  # Green - unread in reader mode
READER_READ_COLOR = '#1821b4'    # Blue - read in reader mode


def _rounded_text_pixmap(text: str, size: int = 28) -> QPixmap:
    """Create a rounded circle with text inside (light blue transparent fill, black border)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    # Light blue transparent fill, black outline
    painter.setBrush(QBrush(QColor("#DBEAFE")))
    painter.setPen(QPen(QColor("#000000"), 2))
    margin = 2
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    # Bold text centered
    font = QFont()
    font.setBold(True)
    n = len(str(text))
    font.setPointSize(8 if n > 10 else (9 if n > 3 else 10))
    painter.setFont(font)
    painter.setPen(QColor("#000000"))
    painter.drawText(0, 0, size, size, Qt.AlignCenter, str(text))
    painter.end()
    return pixmap


def _format_annotation_date(dt: datetime, include_time: bool = True) -> str:
    """Format date for display (e.g., '2/15/2025 14:32' or '2/15/2025')."""
    if not hasattr(dt, 'month'):
        return str(dt)[:5]
    if include_time:
        return f"{dt.month}/{dt.day}/{dt.year} {dt.hour}:{dt.minute:02d}"
    return f"{dt.month}/{dt.day}/{dt.year}"


@dataclass
class Annotation:
    """Data class for a 3D annotation."""
    id: int
    point: tuple  # (x, y, z) in world coordinates
    text: str = ""
    is_validated: bool = False  # Gray (pending) vs Black (validated)
    image_paths: List[str] = field(default_factory=list)
    is_expanded: bool = True
    is_read: bool = False  # For reader mode: Green (unread) vs Blue (read)
    label: str = "Point"  # Editable display name (default "Point")
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'point': list(self.point),
            'text': self.text,
            'is_validated': self.is_validated,
            'image_paths': self.image_paths,
            'label': self.label,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    def display_date(self) -> str:
        """Short date for badge (e.g. '2/8')."""
        if self.created_at:
            return _format_annotation_date(self.created_at)
        return str(self.id)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Annotation':
        """Create from dictionary."""
        created = data.get('created_at')
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace('Z', '+00:00'))
            except Exception:
                created = datetime.now()
        elif created is None:
            created = datetime.now()
        return cls(
            id=data['id'],
            point=tuple(data['point']),
            text=data.get('text', ''),
            is_validated=data.get('is_validated', False),
            image_paths=data.get('image_paths', []),
            label=data.get('label', 'Point'),
            created_at=created,
        )


class AnnotationCard(QFrame):
    """A compact card for a single annotation in the sidebar list."""
    
    # Signals
    clicked = pyqtSignal(int)  # annotation_id - opens popup
    delete_requested = pyqtSignal(int)   # annotation_id
    focus_requested = pyqtSignal(int)    # annotation_id
    label_edited = pyqtSignal(int, str)  # annotation_id, new_label
    hover_changed = pyqtSignal(int, bool)  # annotation_id, is_hovered
    
    def __init__(self, annotation: Annotation, reader_mode: bool = False, display_number: int = None, parent=None):
        super().__init__(parent)
        self.annotation = annotation
        self._reader_mode = reader_mode
        self._display_number = display_number if display_number is not None else annotation.id
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
        # Larger on Windows (font rendering differs from Mac)
        _dot_width = 22 if sys.platform == 'win32' else 16
        self.point_indicator = QLabel("●")
        self.point_indicator.setFixedWidth(_dot_width)
        self.point_indicator.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.point_indicator)
        
        # Rounded number badge (display number: 1, 2, 3...)
        self.date_icon = QLabel()
        self.date_icon.setPixmap(_rounded_text_pixmap(str(self._display_number)))
        self.date_icon.setFixedSize(28, 28)
        self.date_icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.date_icon)
        
        # Editable label (replaces "Point 1")
        self.label_edit = QLineEdit()
        self.label_edit.setText(self.annotation.label)
        self.label_edit.setPlaceholderText("Point")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        self.label_edit.setFont(title_font)
        self.label_edit.setStyleSheet(f"""
            QLineEdit {{
                color: {default_theme.text_primary};
                background: transparent;
                border: none;
                border-bottom: 1px solid transparent;
            }}
            QLineEdit:focus {{
                border-bottom: 1px solid {default_theme.border_light};
            }}
        """)
        self.label_edit.setFixedHeight(24)
        self.label_edit.editingFinished.connect(self._on_label_editing_finished)
        
        # Status label below the editable label
        self.status_label = QLabel()
        self.status_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 9px; background-color: transparent;")
        
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)
        info_layout.addWidget(self.label_edit)
        info_layout.addWidget(self.status_label)
        
        layout.addLayout(info_layout, 1)  # stretch
        layout.addStretch()
        
        # Date (small text) - where coordinates were shown
        date_text = _format_annotation_date(self.annotation.created_at, include_time=False) if self.annotation.created_at else str(self.annotation.id)
        self.coord_label = QLabel(date_text)
        self.coord_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 9px; background-color: transparent;")
        layout.addWidget(self.coord_label)
        
        # Delete button (cross)
        self.delete_btn = QPushButton("✕")
        self.delete_btn.setFixedSize(24, 24)
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setToolTip("Remove annotation")
        self.delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                font-size: 13px;
                color: {default_theme.text_secondary};
            }}
            QPushButton:hover {{
                background-color: #FEE2E2;
                color: #DC2626;
                border-radius: 12px;
            }}
        """)
        self.delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.annotation.id))
        layout.addWidget(self.delete_btn)
    
    def _on_label_editing_finished(self):
        """Handle label edit - emit to panel."""
        new_label = self.label_edit.text().strip() or "Point"
        if new_label != self.annotation.label:
            self.annotation.label = new_label
            self.label_edited.emit(self.annotation.id, new_label)
        self.label_edit.setText(self.annotation.label)
    
    def mousePressEvent(self, event):
        """Handle click to open popup."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.annotation.id)
        super().mousePressEvent(event)
    
    def enterEvent(self, event):
        """Hover entered - highlight 3D marker yellow."""
        self.hover_changed.emit(self.annotation.id, True)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Hover left - restore 3D marker color. Skip if entering a child widget."""
        rw = event.relatedWidget() if hasattr(event, 'relatedWidget') else None
        if rw is not None:
            w = rw
            while w and w != self:
                w = w.parent() if hasattr(w, 'parent') else None
            if w == self:  # entering a descendant of this card
                super().leaveEvent(event)
                return
        self.hover_changed.emit(self.annotation.id, False)
        super().leaveEvent(event)
    
    def _update_style(self):
        """Update the card style based on validation status and reader mode."""
        if self._reader_mode:
            # Reader mode: Green for unread, Blue for read
            if self.annotation.is_read:
                indicator_color = READER_READ_COLOR
                bg_color = "#F3F4F6"
                border_color = "#D1D5DB"
                self.status_label.setText("✓ Read")
            else:
                indicator_color = READER_UNREAD_COLOR
                bg_color = "#F0FFF0"
                border_color = "#86EFAC"
                self.status_label.setText("● Unread")
        elif self.annotation.is_validated:
            # Blue for validated
            indicator_color = VALIDATED_COLOR
            bg_color = "#F3F4F6"
            border_color = "#D1D5DB"
            self.status_label.setText("✓ Validated")
        else:
            # Gray for pending
            indicator_color = PENDING_COLOR
            bg_color = "#F9FAFB"
            border_color = "#E5E7EB"
            self.status_label.setText("Click to edit")
        
        _dot_font = 20 if sys.platform == 'win32' else 14
        self.point_indicator.setStyleSheet(f"color: {indicator_color}; font-size: {_dot_font}px; background-color: transparent;")
        self.setStyleSheet(f"""
            QFrame#annotationCard {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            QFrame#annotationCard:hover {{
                background-color: rgba(219, 234, 254, 0.7);
            }}
            QFrame#annotationCard QLabel {{
                background-color: transparent;
            }}
            QFrame#annotationCard QLineEdit {{
                background-color: transparent;
            }}
        """)
    
    def update_annotation(self, annotation: Annotation, display_number: int = None):
        """Update the card with new annotation data and optional display number (1, 2, 3...)."""
        self.annotation = annotation
        if display_number is not None:
            self._display_number = display_number
        self.date_icon.setPixmap(_rounded_text_pixmap(str(self._display_number)))
        self.coord_label.setText(_format_annotation_date(annotation.created_at, include_time=False) if annotation.created_at else str(self._display_number))
        self.label_edit.blockSignals(True)
        self.label_edit.setText(annotation.label)
        self.label_edit.blockSignals(False)
        self._update_style()
        self._update_tooltip()
    
    def _update_tooltip(self):
        """Update the hover tooltip with annotation details."""
        status = "✓ Validated" if self.annotation.is_validated else "⏳ Pending - Click to edit"
        date_str = _format_annotation_date(self.annotation.created_at, include_time=True) if self.annotation.created_at else f"#{self.annotation.id}"
        
        tooltip_parts = [
            f"<b>{self.annotation.label}</b> #{self._display_number}",
            f"<br><b>Status:</b> {status}",
            f"<br><b>Date:</b> {date_str}",
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
    annotation_validated = pyqtSignal(int, str, list, str)  # annotation_id, text, image_paths, label
    open_popup_requested = pyqtSignal(int)  # annotation_id - request to open popup
    open_viewer_popup_requested = pyqtSignal(int)  # annotation_id - request to open viewer popup (reader mode)
    focus_annotation = pyqtSignal(int)     # annotation_id
    annotation_hovered = pyqtSignal(int, bool)  # annotation_id, is_hovered (for 3D marker highlight)
    exit_annotation_mode = pyqtSignal()
    clear_all_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.annotations: List[Annotation] = []
        self.annotation_cards: dict = {}  # id -> AnnotationCard
        self._next_id = 1
        self._reader_mode = False  # Reader mode flag
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
        from ui.annotation_icon import get_annotation_icon_pixmap
        anno_icon = QLabel()
        pix = get_annotation_icon_pixmap(22)
        if not pix.isNull():
            anno_icon.setPixmap(pix)
        else:
            anno_icon.setText("📝")
        anno_icon.setFixedSize(22, 22)
        anno_icon.setAlignment(Qt.AlignCenter)
        title_row.addWidget(anno_icon)
        title_label = QLabel("Annotations")
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
        
        # Instructions / Reader Mode indicator
        self.instructions_label = QLabel("Click on the 3D model to add annotation points")
        self.instructions_label.setWordWrap(True)
        self.instructions_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 10px;")
        header_layout.addWidget(self.instructions_label)
        
        # Reader mode banner (hidden by default)
        self.reader_mode_banner = QFrame()
        self.reader_mode_banner.setStyleSheet(f"""
            QFrame {{
                background-color: #DBEAFE;
                border: 1px solid #93C5FD;
                border-radius: 6px;
            }}
        """)
        banner_layout = QHBoxLayout(self.reader_mode_banner)
        banner_layout.setContentsMargins(10, 8, 10, 8)
        reader_label = QLabel("📖 Reader Mode - View Only")
        reader_label.setStyleSheet("color: #1E40AF; font-size: 11px; font-weight: bold;")
        banner_layout.addWidget(reader_label)
        self.reader_mode_banner.hide()
        header_layout.addWidget(self.reader_mode_banner)
        
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
    
    def set_reader_mode(self, enabled: bool):
        """Enable or disable reader mode (view-only)."""
        self._reader_mode = enabled
        
        if enabled:
            # Show reader mode banner, hide instructions
            self.reader_mode_banner.show()
            self.instructions_label.hide()
            # Hide clear button
            self.clear_btn.hide()
            # Update card styling
        for card in self.annotation_cards.values():
                card._reader_mode = True
                card._update_style()
        else:
            # Show instructions, hide banner
            self.reader_mode_banner.hide()
            self.instructions_label.show()
            # Show clear button
            self.clear_btn.show()
    
    def is_reader_mode(self) -> bool:
        """Check if panel is in reader mode."""
        return self._reader_mode
    
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
        
        # Create card (display_number = position in list, 1-based)
        display_number = len(self.annotations)  # we just appended
        card = AnnotationCard(annotation, reader_mode=self._reader_mode, display_number=display_number)
        card.clicked.connect(self._on_card_clicked)
        card.delete_requested.connect(self._on_delete_requested)
        card.focus_requested.connect(self._on_focus_requested)
        card.label_edited.connect(self._on_label_edited)
        card.hover_changed.connect(self.annotation_hovered.emit)
        
        self.annotation_cards[annotation.id] = card
        self.content_layout.addWidget(card)
        
        # Update UI state
        self.empty_label.hide()
        self.clear_btn.setEnabled(True)
        
        self.annotation_added.emit(annotation)
        logger.info(f"Annotation added: id={annotation.id}, point={point}")
        
        return annotation
    
    def remove_annotation(self, annotation_id: int):
        """Remove an annotation by ID and renumber remaining (1, 2, 3...)."""
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
        
        # Renumber remaining cards (1, 2, 3...)
        self._refresh_display_numbers()
        
        self.annotation_deleted.emit(annotation_id)
        logger.info(f"Annotation removed: id={annotation_id}, renumbered to {[i+1 for i in range(len(self.annotations))]}")
    
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
    
    def get_display_number(self, annotation_id: int) -> int:
        """Get display number (1-based index) for an annotation. Returns 0 if not found."""
        for i, a in enumerate(self.annotations):
            if a.id == annotation_id:
                return i + 1
        return 0
    
    def _refresh_display_numbers(self):
        """Update display numbers on all cards after a delete (1, 2, 3...)."""
        for i, ann in enumerate(self.annotations):
            card = self.annotation_cards.get(ann.id)
            if card is not None:
                card.update_annotation(ann, display_number=i + 1)
    
    def load_annotations(self, data: List[dict]):
        """Load annotations from serialized data."""
        self.clear_all()
        for i, item in enumerate(data):
            annotation = Annotation.from_dict(item)
            self.annotations.append(annotation)
            
            # Create card (display_number = 1, 2, 3...)
            card = AnnotationCard(annotation, reader_mode=self._reader_mode, display_number=i + 1)
            card.clicked.connect(self._on_card_clicked)
            card.delete_requested.connect(self._on_delete_requested)
            card.focus_requested.connect(self._on_focus_requested)
            card.label_edited.connect(self._on_label_edited)
            card.hover_changed.connect(self.annotation_hovered.emit)
            
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
        """Handle card click - request to open popup (edit or view based on mode)."""
        if self._reader_mode:
            # Mark as read
            self.mark_as_read(annotation_id)
            self.open_viewer_popup_requested.emit(annotation_id)
        else:
            self.open_popup_requested.emit(annotation_id)
    
    def mark_as_read(self, annotation_id: int):
        """Mark an annotation as read (for reader mode)."""
        annotation = self.get_annotation_by_id(annotation_id)
        if annotation and not annotation.is_read:
            annotation.is_read = True
            if annotation_id in self.annotation_cards:
                self.annotation_cards[annotation_id].update_annotation(annotation)
            logger.info(f"Annotation marked as read: id={annotation_id}")
    
    def _on_delete_requested(self, annotation_id: int):
        """Handle delete request from a card."""
        self.remove_annotation(annotation_id)
    
    def _on_focus_requested(self, annotation_id: int):
        """Handle focus request from a card."""
        self.focus_annotation.emit(annotation_id)
    
    def _on_label_edited(self, annotation_id: int, new_label: str):
        """Handle label edited from a card."""
        annotation = self.get_annotation_by_id(annotation_id)
        if annotation:
            annotation.label = new_label
            logger.info(f"Annotation label updated: id={annotation_id}, label={new_label}")
    
    def _on_clear_all(self):
        """Handle clear all button click."""
        self.clear_all_requested.emit()
    
    def validate_annotation(self, annotation_id: int, text: str, image_paths: list, label: str = "Point"):
        """Validate an annotation (turn black) with text and images."""
        annotation = self.get_annotation_by_id(annotation_id)
        if annotation:
            annotation.is_validated = True
            annotation.text = text
            annotation.image_paths = image_paths
            annotation.label = label or "Point"
            
            # Update card display
            if annotation_id in self.annotation_cards:
                self.annotation_cards[annotation_id].update_annotation(annotation)
            
            self.annotation_validated.emit(annotation_id, text, image_paths, label or "Point")
            logger.info(f"Annotation validated: id={annotation_id}")
