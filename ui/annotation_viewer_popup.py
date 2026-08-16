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
from ui.styles import default_theme, make_font, TOOLTIP_STYLE

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
        """ + TOOLTIP_STYLE)
        
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


# White popup theme — matches ui/annotation_popup.py's _POPUP_* constants
# so the Lite and 360 annotation modals read as one consistent UI instead
# of Lite inheriting the app's dark sidebar theme.
_POPUP_BG = "#ffffff"
_POPUP_BORDER = "#d1d5db"
_POPUP_TEXT = "#111827"
_POPUP_TEXT_MUTED = "#6b7280"
_POPUP_SECTION = "#374151"
_POPUP_SHADE = "#f3f4f6"


class AnnotationViewerPopup(QDialog):
    """Popup dialog for viewing an annotation from the supplier's side
    (LYNS Lite) or read-only from 360.

    The PM's original comment/photos and every supplier_notes/pm_notes
    reply are shown as one conversation (see _all_entries) — nothing here
    is directly editable. In LYNS Lite only, a single composer at the
    bottom lets the supplier post the next entry in that thread (a reply,
    or — for a pin the supplier just placed themselves, which starts out
    with no comment at all — the pin's first one)."""

    # (annotation_id, note_dict) — a supplier just added feedback in Lite.
    # note_dict: {'id','supplier_id','supplier_name','text','image_paths','added_at'}
    note_added = pyqtSignal(int, dict)

    def __init__(self, annotation_id: int, point: tuple, text: str = "",
                 image_paths: Optional[List[str]] = None, label: str = "Point",
                 created_at=None, display_number: int = None,
                 supplier_notes: Optional[List[dict]] = None,
                 pm_notes: Optional[List[dict]] = None,
                 added_by: Optional[str] = None,
                 current_supplier: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # Remove ? help button on Windows
        self.annotation_id = annotation_id
        self.point = point
        self.text = text
        self.image_paths = image_paths or []
        self.label = label
        self.created_at = created_at
        self._display_number = display_number if display_number is not None else annotation_id
        # 'supplier' if this annotation's own original comment/photos above
        # were placed by a supplier in LYNS Lite rather than the PM in 360
        # (see ui/annotation_panel.py's Annotation.added_by) — decides how
        # that first conversation entry gets attributed in _all_entries.
        self.added_by = added_by
        self.supplier_notes = list(supplier_notes or [])
        # The PM's own follow-up comments from LYNS360 (see
        # ui/annotation_panel.py's Annotation.pm_notes and
        # ui/annotation_popup.py's composer) — interleaved with
        # supplier_notes by added_at in _all_entries so the supplier sees
        # the same back-and-forth conversation the PM sees on their side.
        self.pm_notes = list(pm_notes or [])
        # None outside Lite (no composer shown at all); the supplier this
        # Lite session is reviewing for, once inside Lite — see
        # stl_viewer.py's _on_open_viewer_popup_requested for where this
        # comes from (the loaded .lyns.review envelope's own 'supplier').
        self._current_supplier = current_supplier
        self._staged_photo_paths: List[str] = []

        self.setWindowTitle(f"View Annotation {label} {self._display_number}")
        self.setModal(False)
        self.setMinimumSize(340, 320)
        from ui.annotation_icon import get_app_window_icon
        icon = get_app_window_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.setMaximumSize(440, 620)
        self.resize(400, 500 if self._current_supplier else 420)

        self.init_ui()

    def init_ui(self):
        """Initialize the popup UI: fixed chrome (scroll area + Close
        button) built once here; the scrollable body itself is built by
        _build_content() and reassigned in place by _on_submit_feedback
        whenever a supplier's note changes what needs to be shown."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {_POPUP_BG};
                border: 1px solid {_POPUP_BORDER};
                border-radius: 10px;
            }}
        """)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 16, 0, 16)
        outer_layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background: transparent;")
        self._scroll.setWidget(self._build_content())
        outer_layout.addWidget(self._scroll, 1)

        # Close button — fixed at the bottom, outside the scroll area, so
        # it's always reachable regardless of how much content is above it.
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(16, 12, 16, 0)
        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(36)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_POPUP_SHADE};
                border: 1px solid {_POPUP_BORDER};
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 12px;
                color: {_POPUP_TEXT};
            }}
            QPushButton:hover {{
                background-color: #e5e7eb;
            }}
        """)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        outer_layout.addLayout(btn_layout)

    def _build_content(self) -> QWidget:
        """Build the scrollable body from current state (self.text,
        self.image_paths, self.supplier_notes, ...). Called once from
        init_ui() and again from _on_submit_feedback() after a new note is
        added, so the popup never needs to be closed and reopened."""
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(16, 0, 16, 0)
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
        title_label.setStyleSheet(f"color: {_POPUP_TEXT};")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()

        # Reader mode badge — only for the PM's own annotations, where the
        # original comment/photos really are locked. A point the reviewer
        # placed themselves (added_by == 'supplier') has nothing of theirs
        # locked here — they authored it and can keep adding to it — so
        # labeling it "View Only" would just be wrong.
        if self.added_by != 'supplier':
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
        date_label.setStyleSheet(f"color: {_POPUP_TEXT_MUTED}; font-size: 14px;")
        main_layout.addWidget(date_label)
        
        # Conversation — the PM's original comment/photos (if any) as the
        # first entry, then every supplier_notes/pm_notes reply, oldest
        # first ("mounted one after another"), each attributed to whoever
        # added it. See _all_entries. Mirrors the identical thread shown to
        # the PM in ui/annotation_popup.py, so both sides read the same
        # conversation — there's no separate read-only "Comment:"/"Photos:"
        # block any more, just this one thread.
        entries = self._all_entries()
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {_POPUP_BORDER}; background-color: {_POPUP_BORDER}; max-height: 1px; border: none;")
        main_layout.addWidget(sep)
        notes_title = QLabel(f"Conversation ({len(entries)})")
        notes_title.setStyleSheet(f"color: {_POPUP_SECTION}; font-size: 11px; font-weight: bold;")
        main_layout.addWidget(notes_title)
        for side, note in entries:
            main_layout.addWidget(self._build_note_widget(side, note))

        # LYNS Lite only: let the supplier post the next entry in the
        # thread above — a reply, or the very first comment if this is a
        # pin the supplier just placed themselves. current_supplier is only
        # set when opened from Lite (stl_viewer.py's
        # _on_open_viewer_popup_requested).
        if self._current_supplier is not None:
            main_layout.addWidget(self._build_composer())

        main_layout.addStretch()
        return content

    def _all_entries(self) -> list:
        """This annotation's full conversation, oldest first: the original
        comment/photos (if any) as entry zero, then supplier_notes/pm_notes
        interleaved by added_at. The original entry is prepended rather
        than sorted in by timestamp so it's always first regardless of
        clock skew between this machine and wherever the PM's comment was
        made. Mirrors ui/annotation_popup.py's identical helper."""
        entries = []
        if self.text or self.image_paths:
            original_side = 'supplier' if self.added_by == 'supplier' else 'pm'
            entries.append((original_side, {
                'text': self.text,
                'image_paths': self.image_paths,
                'added_at': self.created_at.isoformat() if hasattr(self.created_at, 'isoformat') else '',
            }))
        followups = [('supplier', n) for n in self.supplier_notes] + [('pm', n) for n in self.pm_notes]
        followups.sort(key=lambda e: e[1].get('added_at') or '')
        entries.extend(followups)
        return entries

    def _build_photo_row(self, image_paths: List[str]) -> QScrollArea:
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

        for path in image_paths:
            thumb = ImageViewThumbnail(path)
            photos_layout.addWidget(thumb)

        photos_scroll.setWidget(photos_container)
        return photos_scroll

    def _build_note_widget(self, side: str, note: dict) -> QFrame:
        """One conversation entry: attribution + text + photos, styled as a
        distinct sub-card so it reads as "added on top of", not part of,
        the PM's original comment above. side: 'supplier' or 'pm', just
        controls the accent color/name. Unlike ui/annotation_popup.py's
        _build_note_card (which renders this same thread on the PM's side
        and shows the actual signed-in PM name), every 'pm' entry here is
        shown as "Managing Team" — the supplier doesn't need to know which
        individual PM wrote which reply."""
        accent = '#5294E2' if side == 'supplier' else '#10B981'
        who = (note.get('supplier_name') or 'Supplier') if side == 'supplier' else 'Managing Team'
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {_POPUP_SHADE};
                border-left: 3px solid {accent};
                border-radius: 4px;
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        when = note.get('added_at', '')[:10]
        header = QLabel(f"👤 {who}" + (f"  ·  {when}" if when else ''))
        header.setStyleSheet(f"color: {accent}; font-size: 10px; font-weight: bold;")
        lay.addWidget(header)

        if note.get('text'):
            text_lbl = QLabel(note['text'])
            text_lbl.setWordWrap(True)
            text_lbl.setStyleSheet(f"color: {_POPUP_TEXT}; font-size: 11px;")
            lay.addWidget(text_lbl)

        if note.get('image_paths'):
            lay.addWidget(self._build_photo_row(note['image_paths']))

        return card

    def _build_composer(self) -> QFrame:
        """LYNS Lite's reply box — the one input the supplier ever posts
        through, appended to the conversation above (self.supplier_notes)
        via note_added. Same shape/wording as ui/annotation_popup.py's
        composer on the PM's side, so both apps read as one conversation
        UI rather than two different ones."""
        box = QFrame()
        box.setStyleSheet(f"""
            QFrame {{
                background-color: {_POPUP_SHADE};
                border: 1px dashed {_POPUP_BORDER};
                border-radius: 6px;
            }}
        """)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self._composer_text = QTextEdit()
        self._composer_text.setPlaceholderText("Add a comment…")
        self._composer_text.setMinimumHeight(50)
        self._composer_text.setMaximumHeight(80)
        self._composer_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {_POPUP_BG};
                border: 1px solid {_POPUP_BORDER};
                border-radius: 6px;
                padding: 6px;
                font-size: 11px;
                color: {_POPUP_TEXT};
            }}
        """)
        lay.addWidget(self._composer_text)

        self._composer_photos_row = QHBoxLayout()
        self._composer_photos_row.setSpacing(6)
        lay.addLayout(self._composer_photos_row)

        btn_row = QHBoxLayout()
        add_photo_btn = QPushButton("📎 Add Photo")
        add_photo_btn.setCursor(Qt.PointingHandCursor)
        add_photo_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: {_POPUP_TEXT_MUTED};
                border: 1px solid {_POPUP_BORDER}; border-radius: 6px;
                padding: 6px 12px; font-size: 11px;
            }}
            QPushButton:hover {{ background-color: #e5e7eb; }}
        """)
        add_photo_btn.clicked.connect(self._on_add_composer_photo)
        btn_row.addWidget(add_photo_btn)
        btn_row.addStretch()

        submit_btn = QPushButton("Post Comment")
        submit_btn.setCursor(Qt.PointingHandCursor)
        submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #5294E2; color: white; border: none;
                border-radius: 6px; padding: 6px 16px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background-color: #4A84D2; }
        """)
        submit_btn.clicked.connect(self._on_submit_feedback)
        btn_row.addWidget(submit_btn)
        lay.addLayout(btn_row)

        return box

    def _on_add_composer_photo(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Attach Photo(s)", "", "Images (*.png *.jpg *.jpeg *.gif *.bmp *.heic)"
        )
        for p in paths:
            if p not in self._staged_photo_paths:
                self._staged_photo_paths.append(p)
                thumb = ImageViewThumbnail(p)
                self._composer_photos_row.addWidget(thumb)

    def _on_submit_feedback(self):
        text = self._composer_text.toPlainText().strip()
        if not text and not self._staged_photo_paths:
            return
        import uuid
        from datetime import datetime, timezone
        note = {
            'id': uuid.uuid4().hex,
            'supplier_id': self._current_supplier.get('id', ''),
            'supplier_name': self._current_supplier.get('name') or self._current_supplier.get('company') or 'Supplier',
            'text': text,
            'image_paths': list(self._staged_photo_paths),
            'added_at': datetime.now(timezone.utc).isoformat(),
        }
        self.supplier_notes.append(note)
        self.note_added.emit(self.annotation_id, note)
        logger.info(f"AnnotationViewerPopup: feedback added to annotation {self.annotation_id}")

        # Reflect it immediately in this open popup too — rebuild just the
        # scrollable body (self._scroll, set up once in init_ui) so the new
        # note appears in the stacked thread above a freshly-cleared composer.
        self._staged_photo_paths = []
        old_content = self._scroll.takeWidget()
        old_content.deleteLater()
        self._scroll.setWidget(self._build_content())
