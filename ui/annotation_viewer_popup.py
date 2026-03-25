"""
Annotation Viewer Popup - Read-only popup for viewing annotations.
Used when opening files with existing annotations (Reader Mode).
"""
import os
import shutil
import logging
from typing import List, Optional
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QWidget, QTextEdit, QFileDialog, QMenu,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
)
from PyQt5.QtCore import Qt, pyqtSignal, QRectF
from PyQt5.QtGui import QFont, QPixmap, QCursor, QPainter
from ui.styles import default_theme, make_font

logger = logging.getLogger(__name__)


class ImageViewerDialog(QDialog):
    """Zoomable image viewer dialog with mouse wheel zoom, drag to pan, and download option."""
    
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # Remove ? help button on Windows
        self.image_path = image_path
        self.setWindowTitle("View Image - Scroll to zoom, drag to pan")
        self.setModal(True)
        self.setMinimumSize(600, 500)
        self._zoom_factor = 1.0
        self._base_pixmap = None
        from ui.annotation_icon import get_app_window_icon
        icon = get_app_window_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the viewer UI."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {default_theme.card_background};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Zoom controls
        zoom_layout = QHBoxLayout()
        zoom_in_btn = QPushButton("➕ Zoom In")
        zoom_out_btn = QPushButton("➖ Zoom Out")
        zoom_reset_btn = QPushButton("⟲ Reset")
        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 11px;")
        for btn in (zoom_in_btn, zoom_out_btn, zoom_reset_btn):
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {default_theme.row_bg_standard};
                    border: 1px solid {default_theme.border_light};
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 11px;
                    color: {default_theme.text_primary};
                }}
                QPushButton:hover {{ background-color: {default_theme.row_bg_hover}; }}
            """)
        zoom_in_btn.clicked.connect(lambda: self._zoom(1.25))
        zoom_out_btn.clicked.connect(lambda: self._zoom(0.8))
        zoom_reset_btn.clicked.connect(self._reset_zoom)
        zoom_layout.addWidget(zoom_in_btn)
        zoom_layout.addWidget(zoom_out_btn)
        zoom_layout.addWidget(zoom_reset_btn)
        zoom_layout.addWidget(self.zoom_label)
        zoom_layout.addStretch()
        layout.addLayout(zoom_layout)
        
        # Graphics view for zoom/pan
        self.graphics_view = QGraphicsView()
        self.graphics_view.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.graphics_view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.graphics_view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.graphics_view.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.graphics_view.setStyleSheet("background: #2a2a2a; border-radius: 4px;")
        self.scene = QGraphicsScene(self)
        self.graphics_view.setScene(self.scene)
        
        if os.path.exists(self.image_path):
            self._base_pixmap = QPixmap(self.image_path)
            if not self._base_pixmap.isNull():
                self.pixmap_item = QGraphicsPixmapItem(self._base_pixmap)
                self.scene.addItem(self.pixmap_item)
                self.scene.setSceneRect(QRectF(self._base_pixmap.rect()))
                self.graphics_view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
                self._zoom_factor = 1.0
                self.resize(min(self._base_pixmap.width() + 80, 900), min(self._base_pixmap.height() + 140, 750))
            else:
                from PyQt5.QtWidgets import QGraphicsTextItem
                err = QGraphicsTextItem("❌ Failed to load image")
                self.scene.addItem(err)
        else:
            from PyQt5.QtWidgets import QGraphicsTextItem
            err = QGraphicsTextItem("❌ Image not found")
            self.scene.addItem(err)
        
        layout.addWidget(self.graphics_view, 1)
        
        # File path label
        filename = os.path.basename(self.image_path)
        path_label = QLabel(f"📁 {filename}")
        path_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 10px;")
        path_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(path_label)
        
        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        # Download button
        download_btn = QPushButton("💾 Save As...")
        download_btn.setFixedHeight(36)
        download_btn.setCursor(Qt.PointingHandCursor)
        download_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #5294E2;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 12px;
                color: white;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #4A84D2;
            }}
        """)
        download_btn.clicked.connect(self._download_image)
        btn_layout.addWidget(download_btn)
        
        btn_layout.addStretch()
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(36)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 12px;
                color: {default_theme.text_primary};
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        if hasattr(self, 'pixmap_item'):
            self.graphics_view.installEventFilter(self)
    
    def eventFilter(self, obj, event):
        """Handle mouse wheel zoom on graphics view."""
        from PyQt5.QtCore import QEvent
        if obj == self.graphics_view and event.type() == QEvent.Wheel and hasattr(self, 'pixmap_item'):
            delta = event.angleDelta().y()
            if delta > 0:
                self._zoom(1.15)
            else:
                self._zoom(0.87)
            return True
        return super().eventFilter(obj, event)
    
    def _zoom(self, factor: float):
        """Zoom in/out by factor."""
        if not hasattr(self, 'pixmap_item'):
            return
        self._zoom_factor *= factor
        self._zoom_factor = max(0.25, min(10.0, self._zoom_factor))
        self.graphics_view.scale(factor, factor)
        self.zoom_label.setText(f"{int(self._zoom_factor * 100)}%")
    
    def _reset_zoom(self):
        """Reset to fit-in-view."""
        if not hasattr(self, 'pixmap_item'):
            return
        self.graphics_view.resetTransform()
        self.graphics_view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
        self._zoom_factor = 1.0
        self.zoom_label.setText("100%")
    
    def _download_image(self):
        """Save the image to user-selected location."""
        if not os.path.exists(self.image_path):
            return
        
        # Get original filename and extension
        original_name = os.path.basename(self.image_path)
        _, ext = os.path.splitext(original_name)
        
        # Open save dialog
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Image",
            original_name,
            f"Image Files (*{ext});;All Files (*.*)"
        )
        
        if save_path:
            try:
                shutil.copy2(self.image_path, save_path)
                logger.info(f"Image saved to {save_path}")
            except Exception as e:
                logger.error(f"Failed to save image: {e}")


class ImageViewThumbnail(QFrame):
    """A read-only thumbnail widget for displaying an attached image with maximize/download options."""
    
    clicked = pyqtSignal(str)  # Emits image path when clicked
    
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.init_ui()
    
    def init_ui(self):
        """Initialize the thumbnail UI."""
        self.setFixedSize(80, 80)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click to view full size\nRight-click for options")
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {default_theme.card_background};
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
            }}
            QFrame:hover {{
                border: 2px solid #5294E2;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        
        # Image label
        self.img_label = QLabel()
        self.img_label.setFixedSize(72, 72)
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setStyleSheet("border: none;")
        
        # Load and scale image
        if os.path.exists(self.image_path):
            pixmap = QPixmap(self.image_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    72, 72,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.img_label.setPixmap(scaled)
            else:
                self.img_label.setText("❌")
        else:
            self.img_label.setText("❌")
        
        layout.addWidget(self.img_label)
    
    def mousePressEvent(self, event):
        """Handle mouse clicks."""
        if event.button() == Qt.LeftButton:
            self._show_full_image()
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPos())
        super().mousePressEvent(event)
    
    def _show_full_image(self):
        """Open the image in a full-size viewer dialog."""
        dialog = ImageViewerDialog(self.image_path, self)
        dialog.exec_()
    
    def _show_context_menu(self, pos):
        """Show context menu with options."""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {default_theme.card_background};
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {default_theme.row_bg_hover};
            }}
        """)
        
        view_action = menu.addAction("🔍 View Full Size")
        download_action = menu.addAction("💾 Save As...")
        
        action = menu.exec_(pos)
        
        if action == view_action:
            self._show_full_image()
        elif action == download_action:
            self._download_image()
    
    def _download_image(self):
        """Save the image to user-selected location."""
        if not os.path.exists(self.image_path):
            return
        
        original_name = os.path.basename(self.image_path)
        _, ext = os.path.splitext(original_name)
        
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Image",
            original_name,
            f"Image Files (*{ext});;All Files (*.*)"
        )
        
        if save_path:
            try:
                shutil.copy2(self.image_path, save_path)
                logger.info(f"Image saved to {save_path}")
            except Exception as e:
                logger.error(f"Failed to save image: {e}")


class AnnotationViewerPopup(QDialog):
    """Read-only popup dialog for viewing an annotation."""
    
    def __init__(self, annotation_id: int, point: tuple, text: str = "", 
                 image_paths: Optional[List[str]] = None, label: str = "Point",
                 created_at=None, display_number: int = None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # Remove ? help button on Windows
        self.annotation_id = annotation_id
        self.point = point
        self.text = text
        self.image_paths = image_paths or []
        self.label = label
        self.created_at = created_at
        self._display_number = display_number if display_number is not None else annotation_id
        
        self.setWindowTitle(f"View Annotation {label} {self._display_number}")
        self.setModal(False)
        self.setMinimumSize(320, 300)
        from ui.annotation_icon import get_app_window_icon
        icon = get_app_window_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.setMaximumSize(400, 450)
        
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
        
        # Header with annotation icon
        header_layout = QHBoxLayout()
        from ui.annotation_icon import get_annotation_icon_pixmap
        anno_icon = QLabel()
        pix = get_annotation_icon_pixmap(28)
        if not pix.isNull():
            anno_icon.setPixmap(pix)
        anno_icon.setFixedSize(28, 28)
        anno_icon.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(anno_icon)
        from ui.annotation_panel import _rounded_text_pixmap
        num_icon = QLabel()
        num_icon.setPixmap(_rounded_text_pixmap(str(self._display_number), size=32))
        num_icon.setFixedSize(32, 32)
        header_layout.addWidget(num_icon)
        title_label = QLabel(f"{self.label} {self._display_number}")
        title_font = make_font(size=13, bold=True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {default_theme.text_title};")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Reader mode badge
        reader_badge = QLabel("📖 View Only")
        reader_badge.setStyleSheet(f"""
            QLabel {{
                background-color: #DBEAFE;
                color: #1E40AF;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        header_layout.addWidget(reader_badge)
        
        main_layout.addLayout(header_layout)
        
        # Date (where coordinates were shown)
        from ui.annotation_panel import _format_annotation_date
        date_text = _format_annotation_date(self.created_at, include_time=True) if self.created_at and hasattr(self.created_at, 'month') else str(self.annotation_id)
        date_label = QLabel(f"📅 {date_text}")
        date_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 14px;")
        main_layout.addWidget(date_label)
        
        # Comment section
        if self.text:
            comment_label = QLabel("Comment:")
            comment_label.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 11px; font-weight: bold;")
            main_layout.addWidget(comment_label)
            
            # Read-only text display
            text_display = QTextEdit()
            text_display.setPlainText(self.text)
            text_display.setReadOnly(True)
            text_display.setMinimumHeight(60)
            text_display.setMaximumHeight(100)
            text_display.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {default_theme.row_bg_standard};
                    border: 1px solid {default_theme.border_light};
                    border-radius: 6px;
                    padding: 8px;
                    font-size: 11px;
                    color: {default_theme.text_primary};
                }}
            """)
            main_layout.addWidget(text_display)
        else:
            no_comment = QLabel("No comment provided")
            no_comment.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 11px; font-style: italic;")
            main_layout.addWidget(no_comment)
        
        # Photos section
        if self.image_paths:
            photos_label = QLabel(f"Photos ({len(self.image_paths)}) - Click to view:")
            photos_label.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 11px; font-weight: bold;")
            main_layout.addWidget(photos_label)
            
            # Photo thumbnails container
            photos_scroll = QScrollArea()
            photos_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            photos_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            photos_scroll.setWidgetResizable(True)
            photos_scroll.setFixedHeight(100)
            photos_scroll.setFrameShape(QFrame.NoFrame)
            photos_scroll.setStyleSheet("background: transparent;")
            
            photos_container = QWidget()
            photos_layout = QHBoxLayout(photos_container)
            photos_layout.setContentsMargins(0, 0, 0, 0)
            photos_layout.setSpacing(8)
            photos_layout.setAlignment(Qt.AlignLeft)
            
            for path in self.image_paths:
                thumb = ImageViewThumbnail(path)
                photos_layout.addWidget(thumb)
            
            photos_scroll.setWidget(photos_container)
            main_layout.addWidget(photos_scroll)
        
        main_layout.addStretch()
        
        # Close button only (no edit/delete in reader mode)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(36)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 12px;
                color: {default_theme.text_primary};
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        main_layout.addLayout(btn_layout)
