"""
Screenshot panel — displays captured screenshots in a 2-column grid with Delete / Save actions.
"""
import logging
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QFileDialog, QSizePolicy,
    QDialog, QApplication, QLineEdit, QGridLayout,
)
from ui.components import confirm_dialog
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from ui.styles import default_theme, make_font
from i18n import t, on_language_changed
from ui.annotation_panel import (
    _ANNO_CARD_BORDER,
    _ANNO_CARD_BORDER_HOVER,
    _ANNO_CARD_HOVER,
    _ANNO_CARD_PENDING,
)
from ui.screenshot_editor import ScreenshotEditorDialog

logger = logging.getLogger(__name__)

GRID_COLUMNS = 2

# Orange banner — same structure as annotation mode leather card (gradient + light rim)
_SS_ORANGE_TOP = "#FFB74D"
_SS_ORANGE_UPPER = "#FF9800"
_SS_ORANGE_MID = "#F57C00"
_SS_ORANGE_DEEP = "#E65100"
_SS_ORANGE_BOTTOM = "#BF360C"


class ScreenshotCard(QFrame):
    """A compact card displaying a screenshot thumbnail with Delete / Save buttons."""

    delete_requested = pyqtSignal(int)
    save_requested = pyqtSignal(int)

    def __init__(self, index: int, pixmap: QPixmap, timestamp: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.pixmap = pixmap
        self.setObjectName("screenshotCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # Same glassy gradient + light rim + hover as annotation list cards
        self.setStyleSheet(f"""
            QFrame#screenshotCard {{
                background: {_ANNO_CARD_PENDING};
                {_ANNO_CARD_BORDER}
            }}
            QFrame#screenshotCard:hover {{
                background: {_ANNO_CARD_HOVER};
                {_ANNO_CARD_BORDER_HOVER}
            }}
            QFrame#screenshotCard QLabel {{
                background-color: transparent;
            }}
            QFrame#screenshotCard QLineEdit {{
                background-color: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Header row: camera icon + name + timestamp + close
        header = QHBoxLayout()
        header.setSpacing(2)
        cam_label = QLabel("📷")
        cam_label.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 10px; background: transparent;")
        header.addWidget(cam_label)
        self.name_edit = QLineEdit(f"Image {index + 1}")
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
                background-color: rgba(255, 255, 255, 0.12);
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
        """Open the screenshot editor dialog for annotation."""
        title = self.name_edit.text().strip() or f"Image {self.index + 1}"
        editor = ScreenshotEditorDialog(self.pixmap, title=title, parent=self.window())
        editor.pixmap_updated.connect(self._on_pixmap_updated)
        editor.exec_()

    def _on_pixmap_updated(self, new_pixmap: QPixmap):
        """Update the card's pixmap after editing."""
        self.pixmap = new_pixmap
        self._update_thumbnail()

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

        # Header — same card pattern as annotation mode banner (gradient + rim + dashed rule), orange palette
        banner = QFrame()
        banner.setObjectName("screenshotModeBanner")
        banner.setAttribute(Qt.WA_StyledBackground, True)
        banner.setStyleSheet(f"""
            QFrame#screenshotModeBanner {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {_SS_ORANGE_TOP},
                    stop:0.12 {_SS_ORANGE_UPPER},
                    stop:0.38 {_SS_ORANGE_MID},
                    stop:0.72 {_SS_ORANGE_DEEP},
                    stop:1 {_SS_ORANGE_BOTTOM});
                border-top: 1px solid rgba(255, 255, 255, 0.52);
                border-left: 1px solid rgba(255, 255, 255, 0.42);
                border-right: 1px solid rgba(255, 255, 255, 0.38);
                border-bottom: 1px solid rgba(255, 255, 255, 0.32);
                border-radius: 14px;
            }}
        """)
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(16, 10, 16, 10)
        banner_layout.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(2, 0, 0, 0)
        title_row.setSpacing(10)
        cam_icon = QLabel("📷")
        cam_icon.setFixedSize(22, 22)
        cam_icon.setAlignment(Qt.AlignCenter)
        cam_icon.setStyleSheet("background: transparent; border: none; font-size: 16px;")
        title_row.addWidget(cam_icon)
        title = QLabel("Screenshots")
        title.setFont(make_font(size=12, bold=True))
        title.setStyleSheet("color: #FFFFFF; background: transparent; border: none;")
        title_row.addWidget(title)
        title_row.addStretch()

        exit_btn = QPushButton("✕")
        exit_btn.setObjectName("exitScreenshotBtn")
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setFixedSize(28, 28)
        exit_btn.setStyleSheet("""
            QPushButton#exitScreenshotBtn {
                background-color: transparent;
                border: none;
                color: rgba(255, 255, 255, 0.92);
                font-size: 16px;
                font-weight: bold;
                padding: 0; min-width: 28px; min-height: 28px;
            }
            QPushButton#exitScreenshotBtn:hover {
                color: #FFFFFF;
                background-color: rgba(0, 0, 0, 0.18);
                border-radius: 14px;
            }
        """)
        exit_btn.clicked.connect(self.exit_screenshot_mode.emit)
        title_row.addWidget(exit_btn)
        banner_layout.addLayout(title_row)

        divider = QFrame()
        divider.setObjectName("screenshotModeDivider")
        divider.setFrameShape(QFrame.NoFrame)
        divider.setMinimumHeight(3)
        divider.setMaximumHeight(3)
        divider.setStyleSheet("""
            QFrame#screenshotModeDivider {
                border: none;
                border-top: 1px dashed rgba(255, 255, 255, 0.55);
                margin-top: 8px;
                margin-bottom: 8px;
                margin-left: 0px;
                margin-right: 0px;
                background: transparent;
            }
        """)
        banner_layout.addWidget(divider)
        self._screenshot_banner_divider = divider

        self.instruction = QLabel(
            "Draw a square on the model to capture a screenshot."
        )
        self.instruction.setWordWrap(True)
        self.instruction.setStyleSheet(
            "color: rgba(255, 255, 255, 0.95); font-size: 11px; background: transparent; border: none;"
        )
        banner_layout.addWidget(self.instruction)

        layout.addWidget(banner)

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
        self.grid_layout.setAlignment(Qt.AlignTop)
        self.grid_layout.setColumnStretch(0, 1)
        self.grid_layout.setColumnStretch(1, 1)

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
        _show_hint = len(self.screenshots) == 0
        self.instruction.setVisible(_show_hint)
        self._screenshot_banner_divider.setVisible(_show_hint)

    def clear_all(self):
        """Remove all screenshots."""
        for card in self.cards:
            self.grid_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        self.screenshots.clear()
        self.clear_btn.hide()
        self.instruction.show()
        self._screenshot_banner_divider.show()

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
            _show_hint = len(self.screenshots) == 0
            self.instruction.setVisible(_show_hint)
            self._screenshot_banner_divider.setVisible(_show_hint)
            logger.info(f"Screenshot {index} deleted")

    def _on_save(self, index: int):
        if index < 0 or index >= len(self.screenshots):
            return
        pixmap, _ = self.screenshots[index]
        # Open editor so user can annotate before saving
        title = f"Image {index + 1}"
        if index < len(self.cards):
            raw = self.cards[index].name_edit.text().strip()
            if raw:
                title = raw
        editor = ScreenshotEditorDialog(pixmap, title=f"Edit & Save — {title}", parent=self.window())

        def _do_save(result_pixmap):
            # Update the card with the annotated version
            if index < len(self.cards):
                self.cards[index].pixmap = result_pixmap
                self.cards[index]._update_thumbnail()
            if index < len(self.screenshots):
                ts = self.screenshots[index][1]
                self.screenshots[index] = (result_pixmap, ts)

        editor.pixmap_updated.connect(_do_save)
        editor.exec_()

    def _on_clear_all(self):
        if confirm_dialog(self, "Clear All Screenshots", "Are you sure you want to delete all screenshots?"):
            self.clear_all()
