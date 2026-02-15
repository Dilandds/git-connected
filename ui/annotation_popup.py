"""
Annotation Popup Dialog for editing annotation text and adding photos.
"""
import os
import logging
from typing import List, Optional
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QFileDialog, QScrollArea, QFrame, QWidget, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap
from ui.styles import default_theme

logger = logging.getLogger(__name__)


class ImageThumbnail(QFrame):
    """A thumbnail widget for displaying an attached image."""
    
    remove_requested = pyqtSignal(str)  # image_path
    
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(100, 100)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the thumbnail UI."""
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {default_theme.card_background};
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        
        # Image label - expands to fill
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.img_label.setStyleSheet("border: none;")
        self.img_label.setScaledContents(False)
        
        # Load image
        self._pixmap = None
        if os.path.exists(self.image_path):
            self._pixmap = QPixmap(self.image_path)
            if self._pixmap.isNull():
                self._pixmap = None
                self.img_label.setText("❌")
        else:
            self.img_label.setText("❌")
        
        layout.addWidget(self.img_label)
        
        # Remove button
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(20, 20)
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #FEE2E2;
                border: none;
                border-radius: 10px;
                color: #DC2626;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #FECACA;
            }}
        """)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.image_path))
        
        # Position remove button at top-right
        remove_btn.setParent(self)
        remove_btn.raise_()
        self._remove_btn = remove_btn
    
    def resizeEvent(self, event):
        """Rescale image on resize."""
        super().resizeEvent(event)
        if self._pixmap:
            scaled = self._pixmap.scaled(
                self.img_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.img_label.setPixmap(scaled)
        # Reposition remove button
        self._remove_btn.move(self.width() - 24, 4)


class AnnotationPopup(QDialog):
    """Popup dialog for editing an annotation."""
    
    # Signals
    annotation_validated = pyqtSignal(int, str, list)  # annotation_id, text, image_paths
    annotation_deleted = pyqtSignal(int)  # annotation_id
    
    def __init__(self, annotation_id: int, point: tuple, text: str = "", 
                 image_paths: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self.annotation_id = annotation_id
        self.point = point
        self.text = text
        self.image_paths = image_paths or []
        
        self.setWindowTitle(f"Annotation Point {annotation_id}")
        self.setModal(False)  # Non-modal so user can still interact with 3D view
        self.setMinimumSize(500, 550)
        self.setMaximumSize(700, 800)
        self.resize(550, 600)
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the popup UI."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {default_theme.card_background};
                border: 1px solid {default_theme.border_standard};
                border-radius: 10px;
            }}
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)
        
        # Header
        header_layout = QHBoxLayout()
        
        title_label = QLabel(f"📍 Point {self.annotation_id}")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(13)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {default_theme.text_title};")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Coordinates
        coord_text = f"({self.point[0]:.2f}, {self.point[1]:.2f}, {self.point[2]:.2f})"
        coord_label = QLabel(coord_text)
        coord_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 10px;")
        header_layout.addWidget(coord_label)
        
        main_layout.addLayout(header_layout)
        
        # Text input
        text_label = QLabel("Comment:")
        text_label.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 11px;")
        main_layout.addWidget(text_label)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Add your annotation comment here...")
        self.text_edit.setText(self.text)
        self.text_edit.setMinimumHeight(80)
        self.text_edit.setMaximumHeight(120)
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {default_theme.input_bg};
                border: 1px solid {default_theme.input_border};
                border-radius: 6px;
                padding: 8px;
                font-size: 11px;
                color: {default_theme.text_primary};
            }}
            QTextEdit:focus {{
                border: 2px solid {default_theme.button_primary};
            }}
        """)
        main_layout.addWidget(self.text_edit)
        
        # Photos section
        photos_header = QHBoxLayout()
        photos_label = QLabel("Photos:")
        photos_label.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 11px;")
        photos_header.addWidget(photos_label)
        
        photos_header.addStretch()
        
        add_photo_btn = QPushButton("📷 Add Photo")
        add_photo_btn.setFixedHeight(28)
        add_photo_btn.setCursor(Qt.PointingHandCursor)
        add_photo_btn.setStyleSheet(f"""
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
        add_photo_btn.clicked.connect(self._add_photo)
        photos_header.addWidget(add_photo_btn)
        
        main_layout.addLayout(photos_header)
        
        # Photo thumbnails container
        self.photos_scroll = QScrollArea()
        self.photos_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.photos_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.photos_scroll.setWidgetResizable(True)
        self.photos_scroll.setMinimumHeight(250)
        self.photos_scroll.setFrameShape(QFrame.NoFrame)
        self.photos_scroll.setStyleSheet("background: transparent;")
        self.photos_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.photos_container = QWidget()
        self.photos_layout = QVBoxLayout(self.photos_container)
        self.photos_layout.setContentsMargins(0, 0, 0, 0)
        self.photos_layout.setSpacing(8)
        
        self.photos_scroll.setWidget(self.photos_container)
        main_layout.addWidget(self.photos_scroll, 1)  # stretch factor 1 to fill space
        
        # Load existing thumbnails
        self._refresh_thumbnails()
        
        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        delete_btn = QPushButton("🗑 Delete")
        delete_btn.setFixedHeight(36)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #FEE2E2;
                border: 1px solid #FECACA;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                color: #DC2626;
            }}
            QPushButton:hover {{
                background-color: #FECACA;
            }}
        """)
        delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(delete_btn)
        
        btn_layout.addStretch()
        
        done_btn = QPushButton("✓ Done")
        done_btn.setFixedHeight(36)
        done_btn.setCursor(Qt.PointingHandCursor)
        done_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #10B981;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 12px;
                font-weight: bold;
                color: white;
            }}
            QPushButton:hover {{
                background-color: #059669;
            }}
        """)
        done_btn.clicked.connect(self._on_done)
        btn_layout.addWidget(done_btn)
        
        main_layout.addLayout(btn_layout)
    
    def _add_photo(self):
        """Open file dialog to add a photo."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Photos",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All Files (*)"
        )
        
        for path in file_paths:
            if path and path not in self.image_paths:
                self.image_paths.append(path)
        
        self._refresh_thumbnails()
    
    def _remove_photo(self, image_path: str):
        """Remove a photo from the list."""
        if image_path in self.image_paths:
            self.image_paths.remove(image_path)
        self._refresh_thumbnails()
    
    def _refresh_thumbnails(self):
        """Refresh the photo thumbnails."""
        # Clear existing
        while self.photos_layout.count():
            item = self.photos_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add new thumbnails - each fills full width
        for path in self.image_paths:
            thumb = ImageThumbnail(path)
            thumb.setMinimumHeight(350)
            thumb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            thumb.remove_requested.connect(self._remove_photo)
            self.photos_layout.addWidget(thumb)
        
        # Add placeholder if empty
        if not self.image_paths:
            placeholder = QLabel("No photos attached")
            placeholder.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 10px;")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setMinimumHeight(80)
            self.photos_layout.addWidget(placeholder)
        
        self.photos_layout.addStretch()
    
    def _on_done(self):
        """Handle Done button - validate the annotation."""
        self.text = self.text_edit.toPlainText()
        self.annotation_validated.emit(self.annotation_id, self.text, self.image_paths)
        self.accept()
    
    def _on_delete(self):
        """Handle Delete button."""
        self.annotation_deleted.emit(self.annotation_id)
        self.reject()
