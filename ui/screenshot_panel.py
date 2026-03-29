"""
Screenshot panel — displays captured screenshots in a 2-column grid with Delete / Save actions.
"""
import logging
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QFileDialog, QSizePolicy,
    QDialog, QApplication, QLineEdit, QGridLayout
)
from ui.components import confirm_dialog
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QFont
from ui.styles import default_theme, FONTS

logger = logging.getLogger(__name__)

GRID_COLUMNS = 2


class ScreenshotCard(QFrame):
    """A compact card displaying a screenshot thumbnail with Delete / Save buttons."""

    delete_requested = pyqtSignal(int)
    save_requested = pyqtSignal(int)

    def __init__(self, index: int, pixmap: QPixmap, timestamp: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.pixmap = pixmap
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
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Header row: camera icon + name + timestamp + close
        header = QHBoxLayout()
        header.setSpacing(2)
        cam_label = QLabel("📷")
        cam_label.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 10px; background: transparent;")
        header.addWidget(cam_label)
        self.name_edit = QLineEdit(f"Screenshot {index + 1}")
        self.name_edit.setStyleSheet(f"""
            QLineEdit {{
                color: {default_theme.text_primary};
                font-weight: bold;
                font-size: 10px;
                background: transparent;
                border: none;
                padding: 1px 2px;
            }}
            QLineEdit:focus {{
                border: 1px solid {default_theme.border_medium};
                border-radius: 3px;
                background: white;
            }}
        """)
        self.name_edit.setPlaceholderText("Name")
        self.name_edit.setCursor(Qt.IBeamCursor)
        self.name_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header.addWidget(self.name_edit)

        ts_label = QLabel(timestamp)
        ts_label.setStyleSheet(f"color: {default_theme.text_subtext}; font-size: 8px; background: transparent;")
        header.addWidget(ts_label)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("Remove screenshot")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {default_theme.text_secondary};
                border: none;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
                padding: 0; min-width: 20px; min-height: 20px;
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
                color: {default_theme.text_primary};
            }}
        """)
        close_btn.clicked.connect(lambda: self.delete_requested.emit(self.index))
        header.addWidget(close_btn)
        layout.addLayout(header)

        # Square thumbnail — compact
        self.thumb_label = QLabel()
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet("background: transparent;")
        self.thumb_label.setCursor(Qt.PointingHandCursor)
        self.thumb_label.setFixedHeight(90)
        self.thumb_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._update_thumbnail()
        layout.addWidget(self.thumb_label)

        # Action buttons
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 2, 0, 0)
        actions.setSpacing(4)

        self.delete_btn = QPushButton("🗑 Delete")
        self.delete_btn.setObjectName("screenshotDeleteBtn")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setStyleSheet(f"""
            QPushButton#screenshotDeleteBtn {{
                background-color: #FEE2E2;
                color: #DC2626;
                border: 1px solid #FECACA;
                border-radius: 5px;
                padding: 3px 6px;
                font-size: 9px;
                font-weight: bold;
            }}
            QPushButton#screenshotDeleteBtn:hover {{
                background-color: #FCA5A5;
            }}
        """)
        self.delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.index))
        actions.addWidget(self.delete_btn)

        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setObjectName("screenshotSaveBtn")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(f"""
            QPushButton#screenshotSaveBtn {{
                background-color: #D1FAE5;
                color: #059669;
                border: 1px solid #A7F3D0;
                border-radius: 5px;
                padding: 3px 6px;
                font-size: 9px;
                font-weight: bold;
            }}
            QPushButton#screenshotSaveBtn:hover {{
                background-color: #6EE7B7;
            }}
        """)
        self.save_btn.clicked.connect(lambda: self.save_requested.emit(self.index))
        actions.addWidget(self.save_btn)

        layout.addLayout(actions)

    def _update_thumbnail(self):
        card_w = max(self.width() - 16, 80)
        scaled = self.pixmap.scaled(card_w, card_w, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.thumb_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_thumbnail()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            thumb_pos = self.thumb_label.mapFrom(self, event.pos())
            if self.thumb_label.rect().contains(thumb_pos):
                self._show_preview()
        super().mousePressEvent(event)

    def _show_preview(self):
        """Show a full-size preview dialog of the screenshot."""
        dialog = QDialog(self.window())
        dialog.setWindowTitle(self.name_edit.text().strip() or f"Screenshot {self.index + 1}")
        dialog.setStyleSheet(f"background-color: {default_theme.card_background};")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)

        img_label = QLabel()
        img_label.setAlignment(Qt.AlignCenter)

        screen = QApplication.primaryScreen()
        if screen:
            screen_size = screen.availableGeometry()
            max_w = int(screen_size.width() * 0.8)
            max_h = int(screen_size.height() * 0.8)
        else:
            max_w, max_h = 1200, 800

        scaled = self.pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        img_label.setPixmap(scaled)
        layout.addWidget(img_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        save_btn = QPushButton("💾  Save")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #D1FAE5; color: #059669;
                border: 1px solid #A7F3D0; border-radius: 6px;
                padding: 8px 20px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #6EE7B7; }}
        """)
        save_btn.clicked.connect(lambda: (self.save_requested.emit(self.index), dialog.accept()))
        btn_row.addWidget(save_btn)

        delete_btn = QPushButton("🗑  Delete")
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #FEE2E2; color: #DC2626;
                border: 1px solid #FECACA; border-radius: 6px;
                padding: 8px 20px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #FCA5A5; }}
        """)
        delete_btn.clicked.connect(lambda: (dialog.accept(), self.delete_requested.emit(self.index)))
        btn_row.addWidget(delete_btn)

        close_btn = QPushButton("✕  Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.button_default_bg}; color: {default_theme.text_secondary};
                border: 1px solid {default_theme.button_default_border}; border-radius: 6px;
                padding: 8px 20px; font-size: 12px;
            }}
            QPushButton:hover {{ background-color: {default_theme.row_bg_hover}; }}
        """)
        close_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(close_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        dialog.resize(scaled.width() + 20, scaled.height() + 60)
        dialog.exec_()

    def update_index(self, new_index: int):
        self.index = new_index


class ScreenshotPanel(QWidget):
    """Right-side panel listing captured screenshots in a 2-column grid."""

    exit_screenshot_mode = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.screenshots = []  # list of (QPixmap, timestamp_str)
        self.cards = []        # list of ScreenshotCard widgets
        self.setMinimumWidth(280)
        self.setMaximumWidth(350)
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
        exit_btn.setFixedSize(28, 28)
        exit_btn.setStyleSheet(f"""
            QPushButton#exitScreenshotBtn {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_secondary};
                border: none;
                border-radius: 14px;
                font-size: 16px;
                font-weight: bold;
                padding: 0; min-width: 28px; min-height: 28px;
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
            "Draw a square on the model to capture a screenshot."
        )
        self.instruction.setWordWrap(True)
        self.instruction.setStyleSheet(f"color: {default_theme.text_subtext}; font-size: 11px; background: transparent;")
        layout.addWidget(self.instruction)

        # Scroll area with grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.grid_layout = QGridLayout(self.cards_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(6)

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

    def _rebuild_grid(self):
        """Rebuild the grid layout from the cards list."""
        # Remove all items from grid (without deleting widgets)
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
        # Re-add cards in 2-column grid
        for i, card in enumerate(self.cards):
            row = i // GRID_COLUMNS
            col = i % GRID_COLUMNS
            self.grid_layout.addWidget(card, row, col)

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

        # Add to grid
        row = idx // GRID_COLUMNS
        col = idx % GRID_COLUMNS
        self.grid_layout.addWidget(card, row, col)

        self.clear_btn.setVisible(len(self.screenshots) > 0)
        self.instruction.setVisible(len(self.screenshots) == 0)

    def clear_all(self):
        """Remove all screenshots."""
        for card in self.cards:
            self.grid_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        self.screenshots.clear()
        self.clear_btn.hide()
        self.instruction.show()

    # ---- private slots ----

    def _on_delete(self, index: int):
        if not confirm_dialog(self, "Delete Screenshot", "Are you sure to delete the photo?"):
            return

        if 0 <= index < len(self.cards):
            card = self.cards.pop(index)
            self.screenshots.pop(index)
            self.grid_layout.removeWidget(card)
            card.deleteLater()
            # Re-index remaining cards
            for i, c in enumerate(self.cards):
                c.update_index(i)
            self._rebuild_grid()
            self.clear_btn.setVisible(len(self.screenshots) > 0)
            self.instruction.setVisible(len(self.screenshots) == 0)
            logger.info(f"Screenshot {index} deleted")

    def _on_save(self, index: int):
        if index < 0 or index >= len(self.screenshots):
            return
        pixmap, _ = self.screenshots[index]
        if index < len(self.cards):
            raw = self.cards[index].name_edit.text().strip()
            suggested = "".join(c for c in raw if c not in r'\/:*?"<>|') if raw else f"Screenshot {index + 1}"
        else:
            suggested = f"Screenshot {index + 1}"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Screenshot",
            f"{suggested}.png",
            "PNG (*.png);;JPEG (*.jpg);;All Files (*)"
        )
        if path:
            pixmap.save(path)
            logger.info(f"Screenshot saved to {path}")

    def _on_clear_all(self):
        if confirm_dialog(self, "Clear All Screenshots", "Are you sure you want to delete all screenshots?"):
            self.clear_all()
