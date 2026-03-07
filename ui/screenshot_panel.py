"""
Screenshot panel — displays captured screenshots with Delete / Save actions.
"""
import logging
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QMessageBox, QFileDialog, QSizePolicy,
    QDialog, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QFont
from ui.styles import default_theme, FONTS

logger = logging.getLogger(__name__)


class ScreenshotCard(QFrame):
    """A card displaying a screenshot thumbnail with Delete / Save buttons."""

    delete_requested = pyqtSignal(int)  # card index
    save_requested = pyqtSignal(int)    # card index

    def __init__(self, index: int, pixmap: QPixmap, timestamp: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.pixmap = pixmap
        self._expanded = False
        self.setObjectName("screenshotCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame#screenshotCard {{
                background-color: {default_theme.row_bg_standard};
                border-radius: 8px;
                border: 1px solid {default_theme.border_standard};
            }}
            QFrame#screenshotCard:hover {{
                border: 1px solid {default_theme.border_medium};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header row: number + timestamp
        header = QHBoxLayout()
        header.setSpacing(6)
        num_label = QLabel(f"📷  Screenshot {index + 1}")
        num_label.setStyleSheet(f"color: {default_theme.text_primary}; font-weight: bold; font-size: 12px; background: transparent;")
        header.addWidget(num_label)
        header.addStretch()
        ts_label = QLabel(timestamp)
        ts_label.setStyleSheet(f"color: {default_theme.text_subtext}; font-size: 10px; background: transparent;")
        header.addWidget(ts_label)
        layout.addLayout(header)

        # Thumbnail
        self.thumb_label = QLabel()
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet("background: transparent;")
        self._update_thumbnail()
        layout.addWidget(self.thumb_label)

        # Action buttons (hidden by default, shown on click)
        self.actions_widget = QWidget()
        self.actions_widget.setStyleSheet("background: transparent;")
        actions_layout = QHBoxLayout(self.actions_widget)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(8)

        self.delete_btn = QPushButton("🗑  Delete")
        self.delete_btn.setObjectName("screenshotDeleteBtn")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setStyleSheet(f"""
            QPushButton#screenshotDeleteBtn {{
                background-color: #FEE2E2;
                color: #DC2626;
                border: 1px solid #FECACA;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton#screenshotDeleteBtn:hover {{
                background-color: #FCA5A5;
            }}
        """)
        self.delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.index))
        actions_layout.addWidget(self.delete_btn)

        self.save_btn = QPushButton("💾  Save")
        self.save_btn.setObjectName("screenshotSaveBtn")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(f"""
            QPushButton#screenshotSaveBtn {{
                background-color: #D1FAE5;
                color: #059669;
                border: 1px solid #A7F3D0;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton#screenshotSaveBtn:hover {{
                background-color: #6EE7B7;
            }}
        """)
        self.save_btn.clicked.connect(lambda: self.save_requested.emit(self.index))
        actions_layout.addWidget(self.save_btn)

        actions_layout.addStretch()
        self.actions_widget.hide()
        layout.addWidget(self.actions_widget)

    def _update_thumbnail(self):
        scaled = self.pixmap.scaled(240, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.thumb_label.setPixmap(scaled)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._expanded = not self._expanded
            self.actions_widget.setVisible(self._expanded)
        super().mousePressEvent(event)

    def update_index(self, new_index: int):
        self.index = new_index


class ScreenshotPanel(QWidget):
    """Right-side panel listing captured screenshots."""

    exit_screenshot_mode = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.screenshots = []  # list of (QPixmap, timestamp_str)
        self.cards = []        # list of ScreenshotCard widgets
        self.setMinimumWidth(280)
        self.setMaximumWidth(350)  # Match annotation panel width
        self.setStyleSheet(f"background-color: {default_theme.card_background};")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("📷  Screenshots")
        title.setStyleSheet(f"color: {default_theme.text_title}; font-weight: bold; font-size: 14px; background: transparent;")
        header.addWidget(title)
        header.addStretch()

        exit_btn = QPushButton("✕")
        exit_btn.setObjectName("exitScreenshotBtn")
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setFixedSize(24, 24)
        exit_btn.setStyleSheet(f"""
            QPushButton#exitScreenshotBtn {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_secondary};
                border: none;
                border-radius: 12px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton#exitScreenshotBtn:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """)
        exit_btn.clicked.connect(self.exit_screenshot_mode.emit)
        header.addWidget(exit_btn)
        layout.addLayout(header)

        # Instruction
        self.instruction = QLabel(
            "Draw a rectangle to capture. Use the zoom buttons to zoom."
        )
        self.instruction.setWordWrap(True)
        self.instruction.setStyleSheet(f"color: {default_theme.text_subtext}; font-size: 11px; background: transparent;")
        layout.addWidget(self.instruction)

        # Scroll area for cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()

        scroll.setWidget(self.cards_container)
        layout.addWidget(scroll, 1)

        # Clear all button
        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.setObjectName("clearScreenshotsBtn")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setStyleSheet(f"""
            QPushButton#clearScreenshotsBtn {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_secondary};
                border: 1px solid {default_theme.button_default_border};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
            }}
            QPushButton#clearScreenshotsBtn:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """)
        self.clear_btn.clicked.connect(self._on_clear_all)
        self.clear_btn.hide()
        layout.addWidget(self.clear_btn)

    # ---- public API ----

    def add_screenshot(self, pixmap: QPixmap):
        """Add a captured screenshot to the panel."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.screenshots.append((pixmap, ts))
        idx = len(self.screenshots) - 1

        card = ScreenshotCard(idx, pixmap, ts)
        card.delete_requested.connect(self._on_delete)
        card.save_requested.connect(self._on_save)
        self.cards.append(card)

        # Insert before the stretch
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
        self.clear_btn.setVisible(len(self.screenshots) > 0)
        self.instruction.setVisible(len(self.screenshots) == 0)

    def clear_all(self):
        """Remove all screenshots."""
        for card in self.cards:
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        self.screenshots.clear()
        self.clear_btn.hide()
        self.instruction.show()

    # ---- private slots ----

    def _on_delete(self, index: int):
        reply = QMessageBox.question(
            self,
            "Delete Screenshot",
            "Are you sure to delete the photo?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        if 0 <= index < len(self.cards):
            card = self.cards.pop(index)
            self.screenshots.pop(index)
            self.cards_layout.removeWidget(card)
            card.deleteLater()
            # Re-index remaining cards
            for i, c in enumerate(self.cards):
                c.update_index(i)
            self.clear_btn.setVisible(len(self.screenshots) > 0)
            self.instruction.setVisible(len(self.screenshots) == 0)
            logger.info(f"Screenshot {index} deleted")

    def _on_save(self, index: int):
        if index < 0 or index >= len(self.screenshots):
            return
        pixmap, _ = self.screenshots[index]
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Screenshot",
            f"screenshot_{index + 1}.png",
            "PNG (*.png);;JPEG (*.jpg);;All Files (*)"
        )
        if path:
            pixmap.save(path)
            logger.info(f"Screenshot saved to {path}")

    def _on_clear_all(self):
        reply = QMessageBox.question(
            self,
            "Clear All Screenshots",
            "Are you sure you want to delete all screenshots?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.clear_all()
