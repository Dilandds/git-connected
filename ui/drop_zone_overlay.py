"""
Drag & Drop Overlay for the 3D Viewer.
Appears when no STL model is loaded.
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QPainter, QColor, QPen


class DropZoneOverlay(QWidget):
    """
    A passive drag-and-drop overlay inside the 3D viewer area.
    Entire area acts as drop target and click-to-upload surface.
    """
    
    # Signal emitted when a valid STL file is dropped
    file_dropped = pyqtSignal(str)
    # Signal emitted when user clicks to upload
    click_to_upload = pyqtSignal()
    # Signal emitted when an error occurs (invalid file, etc.)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._is_dragging = False
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the overlay UI."""
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet("""
            DropZoneOverlay {
                background-color: #ffffff;
            }
        """)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignCenter)
        
        # Primary text
        self.primary_label = QLabel("Drag & drop your 3D file here")
        self.primary_label.setAlignment(Qt.AlignCenter)
        self.primary_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: 600;
                color: #1a1a2e;
                background: transparent;
            }
        """)
        
        # Secondary text
        self.secondary_label = QLabel("or click anywhere in this area to upload")
        self.secondary_label.setAlignment(Qt.AlignCenter)
        self.secondary_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: 400;
                color: #4a5568;
                background: transparent;
            }
        """)
        
        # Helper text
        self.helper_label = QLabel("STL, STEP, 3DM, OBJ, IGES, DXF & ECTO files")
        self.helper_label.setAlignment(Qt.AlignCenter)
        self.helper_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                font-weight: 400;
                color: #a0aec0;
                background: transparent;
                margin-top: 8px;
            }
        """)
        
        layout.addStretch()
        layout.addWidget(self.primary_label)
        layout.addWidget(self.secondary_label)
        layout.addWidget(self.helper_label)
        layout.addStretch()
    
    def paintEvent(self, event):
        """Custom paint for border and background."""
        super().paintEvent(event)
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw dashed border when dragging
        if self._is_dragging:
            # Light blue tint background
            painter.fillRect(self.rect(), QColor(66, 153, 225, 30))  # Light blue with alpha
            
            # Dashed border
            pen = QPen(QColor(66, 153, 225), 2, Qt.DashLine)
            pen.setDashPattern([8, 4])
            painter.setPen(pen)
            margin = 10
            painter.drawRoundedRect(
                margin, margin,
                self.width() - 2 * margin,
                self.height() - 2 * margin,
                8, 8
            )
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter - validate file type."""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and len(urls) == 1:
                file_path = urls[0].toLocalFile()
                file_ext = file_path.lower()
                if file_ext.endswith('.stl') or file_ext.endswith('.step') or file_ext.endswith('.stp') or file_ext.endswith('.3dm') or file_ext.endswith('.obj') or file_ext.endswith('.iges') or file_ext.endswith('.igs') or file_ext.endswith('.ecto'):
                    event.acceptProposedAction()
                    self._is_dragging = True
                    self._update_dragging_state(True)
                    self.update()
                    return
        event.ignore()
    
    def dragLeaveEvent(self, event):
        """Handle drag leave."""
        self._is_dragging = False
        self._update_dragging_state(False)
        self.update()
    
    def dropEvent(self, event: QDropEvent):
        """Handle file drop."""
        self._is_dragging = False
        self._update_dragging_state(False)
        self.update()
        
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and len(urls) == 1:
                file_path = urls[0].toLocalFile()
                
                # Validate file extension
                file_ext = file_path.lower()
                if not (file_ext.endswith('.stl') or file_ext.endswith('.step') or file_ext.endswith('.stp') or file_ext.endswith('.3dm') or file_ext.endswith('.obj') or file_ext.endswith('.iges') or file_ext.endswith('.igs') or file_ext.endswith('.ecto')):
                    self.error_occurred.emit("Invalid file type. Please use .STL, .STEP, .STP, .3DM, .OBJ, .IGES, .IGS, or .ECTO files only.")
                    return
                
                event.acceptProposedAction()
                self.file_dropped.emit(file_path)
    
    def mousePressEvent(self, event):
        """Handle click to trigger upload."""
        if event.button() == Qt.LeftButton:
            self.click_to_upload.emit()
    
    def _update_dragging_state(self, is_dragging: bool):
        """Update the text labels based on drag state."""
        if is_dragging:
            self.primary_label.setText("Release to load your file")
            self.primary_label.setStyleSheet("""
                QLabel {
                    font-size: 18px;
                    font-weight: 600;
                    color: #4299e1;
                    background: transparent;
                }
            """)
        else:
            self.primary_label.setText("Drag & drop your 3D file here")
            self.primary_label.setStyleSheet("""
                QLabel {
                    font-size: 18px;
                    font-weight: 600;
                    color: #1a1a2e;
                    background: transparent;
                }
            """)
    
    def setCursor(self, cursor):
        """Override to always show pointer cursor."""
        super().setCursor(Qt.PointingHandCursor)
    
    def showEvent(self, event):
        """Set pointer cursor when shown."""
        super().showEvent(event)
        super().setCursor(Qt.PointingHandCursor)
