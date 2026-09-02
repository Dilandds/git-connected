"""
Annotation Panel UI for displaying and managing 3D model annotations.
Workflow: Gray dots (pending) → Click to open popup → Add text/photos → Done → Black dot (validated)
"""
from i18n import t, on_language_changed
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Callable, Tuple
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QTextEdit, QLineEdit, QSizePolicy, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor, QPixmap, QPainter, QBrush, QPen, QFontMetrics
from ui.styles import default_theme, make_font, TOOLTIP_STYLE
from ui.color_palette import PALETTE
from ui.traceability.shared import _MarqueeLabel

logger = logging.getLogger(__name__)

# Colors for annotation states
PENDING_COLOR = '#909d92'   # Light grey - unvalidated
VALIDATED_COLOR = '#4ade80'  # Light green - validated
READER_UNREAD_COLOR = '#36cd2e'  # Green - unread in reader mode
READER_READ_COLOR = '#1821b4'    # Blue - read in reader mode

# Annotation mode top banner — blue/indigo gradient (matches screenshot/texture card style)
_ANNO_LEATHER_TOP = '#64B5F6'
_ANNO_LEATHER_UPPER = '#42A5F5'
_ANNO_LEATHER_MID = '#1976D2'
_ANNO_LEATHER_DEEP = '#1565C0'
_ANNO_LEATHER_BOTTOM = '#0D47A1'

# Dark annotation list cards — glassy teal slate (gradient + light rim on all sides)
_ANNO_CARD_BORDER = """
                border-top: 1px solid rgba(255, 255, 255, 0.42);
                border-left: 1px solid rgba(255, 255, 255, 0.36);
                border-right: 1px solid rgba(255, 255, 255, 0.26);
                border-bottom: 1px solid rgba(255, 255, 255, 0.20);
                border-radius: 10px;
"""
_ANNO_CARD_PENDING = (
    "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
    "stop:0 #2d4149, stop:0.5 #1f3238, stop:1 #162225)"
)
_ANNO_CARD_VALIDATED = (
    "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
    "stop:0 #2a3848, stop:0.5 #1e2a35, stop:1 #151a22)"
)
_ANNO_CARD_READER_UNREAD = (
    "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
    "stop:0 #2a4538, stop:0.5 #1f322c, stop:1 #16221c)"
)
_ANNO_CARD_HOVER = (
    "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
    "stop:0 #5a7a8c, stop:0.45 #426070, stop:1 #2d4a58)"
)
_ANNO_CARD_BORDER_HOVER = """
                border-top: 1px solid rgba(255, 255, 255, 0.55);
                border-left: 1px solid rgba(255, 255, 255, 0.48);
                border-right: 1px solid rgba(255, 255, 255, 0.34);
                border-bottom: 1px solid rgba(255, 255, 255, 0.28);
                border-radius: 10px;
"""


def _is_dark_color(hex_color: str) -> bool:
    """Return True if color is dark (use white text for contrast)."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return False
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return luminance < 0.5


def _checkmark_pixmap(size: int = 12, color: str = "#64748B") -> QPixmap:
    """Draw a crisp checkmark (avoids poor Unicode rendering on Windows at small sizes)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    pen = QPen(QColor(color), max(1, size // 5))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    # Checkmark: two lines - bottom-left to center, center to top-right
    margin = 2
    painter.drawLine(margin, int(size * 0.55), int(size * 0.35), size - margin)
    painter.drawLine(int(size * 0.35), size - margin, size - margin, margin)
    painter.end()
    return pixmap


def _rounded_text_pixmap(text: str, size: int = 28, fill_color: str = "#DBEAFE") -> QPixmap:
    """Create a rounded circle with text inside. fill_color matches the annotation dot color."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    fill = QColor(fill_color)
    painter.setBrush(QBrush(fill))
    painter.setPen(QPen(fill.darker(120), 2))
    margin = 2
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    # Bold text centered - white on dark, black on light
    n = len(str(text))
    font = make_font(size=8 if n > 10 else (9 if n > 3 else 10), bold=True)
    painter.setFont(font)
    text_color = QColor("#FFFFFF") if _is_dark_color(fill_color) else QColor("#000000")
    painter.setPen(text_color)
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


def _format_annotation_time(dt: datetime) -> str:
    """Format time for display (e.g., '14:32')."""
    if not hasattr(dt, 'hour'):
        return ""
    return f"{dt.hour}:{dt.minute:02d}"


def get_first_comment(annotation) -> Optional[Tuple[str, str]]:
    """The earliest comment in an annotation's conversation — its own
    original text if it has one, otherwise whichever of supplier_notes/
    pm_notes came first by added_at (e.g. a supplier's own new pin, which
    has no original text but does have their first note). Duck-typed so
    it works for both ui.annotation_panel.Annotation (3D viewer) and
    ui.technical_overview.ArrowAnnotation (Technical Overview) — both
    share the same text/supplier_notes/pm_notes/added_by shape.

    Returns (text, author_label) so the card face can show it without
    opening the popup (see AnnotationCard's comment-preview row and
    ui/technical_overview.py's _create_card), or None if the annotation
    has no comment content at all yet.
    """
    if annotation.text:
        # Attribute to whoever actually created this annotation — a
        # supplier's own new pin in Lite (added_by == 'supplier'), or the
        # PM otherwise.
        author = t('annotation.first_comment_supplier') if annotation.added_by == 'supplier' \
            else t('annotation.first_comment_pm')
        return annotation.text, author

    entries = [('supplier', n) for n in getattr(annotation, 'supplier_notes', [])] + \
              [('pm', n) for n in getattr(annotation, 'pm_notes', [])]
    entries = [(side, n) for side, n in entries if n.get('text')]
    if not entries:
        return None
    entries.sort(key=lambda e: e[1].get('added_at') or '')
    side, note = entries[0]
    if side == 'supplier':
        author = note.get('supplier_name') or t('annotation.first_comment_supplier')
    else:
        author = note.get('author_name') or t('annotation.first_comment_pm')
    return note['text'], author


@dataclass
class Annotation:
    """Data class for a 3D annotation."""
    id: int
    point: tuple  # (x, y, z) in world coordinates
    text: str = ""
    image_paths: List[str] = field(default_factory=list)
    is_expanded: bool = True
    is_read: bool = False  # For reader mode: Green (unread) vs Blue (read)
    label: str = "Point"  # Editable display name (default "Point")
    created_at: datetime = field(default_factory=datetime.now)
    color: Optional[str] = None  # Optional hex color for this annotation
    # Set to 'supplier' for pins added in LYNS Lite on an otherwise
    # reader-mode bundle (see AnnotationPanel.add_annotation) — lets a later
    # merge-back (Supplier Review Workflow, Milestone 4) tell which pins are
    # the PM's originals vs. new ones the supplier contributed. None for
    # every annotation added normally in LYNS360 itself.
    added_by: Optional[str] = None
    # Feedback a supplier attached to this (usually the PM's own, pre-
    # existing) annotation in LYNS Lite, without touching the original
    # text/image_paths above — those stay the PM's, locked. Each entry:
    # {'id', 'supplier_id', 'supplier_name', 'text', 'image_paths', 'added_at'}.
    # Displayed stacked ("mounted one after another") in
    # ui/annotation_viewer_popup.py; merged in from a returned .lyns.review
    # via AnnotationPanel.add_supplier_notes (see core/annotation_merge.py).
    supplier_notes: List[dict] = field(default_factory=list)
    # The PM's own follow-up comments in LYNS360, added the same way after
    # the original text/image_paths above — a genuine back-and-forth
    # conversation instead of a single overwritable comment box. Each
    # entry: {'id', 'author_name', 'text', 'image_paths', 'added_at'}.
    # Interleaved with supplier_notes by added_at in both ui/annotation_popup.py
    # (360) and ui/annotation_viewer_popup.py (Lite) so both sides read the
    # same conversation; round-trips through a .lyns.review export/import
    # like supplier_notes does (see core/ecto_format.py).
    pm_notes: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'point': list(self.point),
            'text': self.text,
            'image_paths': self.image_paths,
            'label': self.label,
            'color': self.color,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'added_by': self.added_by,
            'supplier_notes': self.supplier_notes,
            'pm_notes': self.pm_notes,
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
            image_paths=data.get('image_paths', []),
            label=data.get('label', 'Point'),
            color=data.get('color'),
            created_at=created,
            added_by=data.get('added_by'),
            supplier_notes=data.get('supplier_notes', []),
            pm_notes=data.get('pm_notes', []),
        )


class AnnotationCard(QFrame):
    """A compact card for a single annotation in the sidebar list."""
    
    # Signals
    clicked = pyqtSignal(int)  # annotation_id - opens popup
    delete_requested = pyqtSignal(int)   # annotation_id
    focus_requested = pyqtSignal(int)    # annotation_id
    label_edited = pyqtSignal(int, str)  # annotation_id, new_label
    hover_changed = pyqtSignal(int, bool)  # annotation_id, is_hovered
    color_changed = pyqtSignal(int, str)  # annotation_id, hex color
    
    def __init__(self, annotation: Annotation, reader_mode: bool = False, display_number: int = None, parent=None):
        super().__init__(parent)
        self.annotation = annotation
        self._reader_mode = reader_mode
        self._display_number = display_number if display_number is not None else annotation.id
        self._label_locked = self._compute_label_locked()
        self.setObjectName("annotationCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.init_ui()
        self._update_style()
        self._update_tooltip()
        self._update_comment_preview()

    def init_ui(self):
        """Initialize the card UI."""
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        
        # Point indicator (colored dot) - clickable to change color
        dot_size = 22 if sys.platform == 'win32' else 16
        self.point_indicator = QPushButton()
        self.point_indicator.setFixedSize(dot_size, dot_size)
        self.point_indicator.setCursor(Qt.PointingHandCursor)
        self.point_indicator.setToolTip(t("annotation.change_color_tooltip"))
        self.point_indicator.clicked.connect(self._open_color_picker)
        layout.addWidget(self.point_indicator)
        
        # Rounded number badge (display number: 1, 2, 3...) - color matches dot
        self.date_icon = QLabel()
        self.date_icon.setPixmap(_rounded_text_pixmap(str(self._display_number), fill_color=self._get_indicator_color()))
        self.date_icon.setFixedSize(28, 28)
        self.date_icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.date_icon)
        
        # Editable label (replaces "Point 1")
        self.label_edit = QLineEdit()
        self.label_edit.setText(self.annotation.label)
        self.label_edit.setPlaceholderText(t("annotation.point"))
        title_font = make_font(size=14, bold=True)
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
        self.label_edit.setReadOnly(self._label_locked)
        self.label_edit.editingFinished.connect(self._on_label_editing_finished)

        # Status row: checkmark icon (drawn, not Unicode) + text (avoids poor rendering on Windows)
        status_row = QWidget()
        status_row.setStyleSheet("background-color: transparent;")
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(4)
        self.status_icon = QLabel()
        self.status_icon.setFixedSize(14, 14)
        self.status_icon.setStyleSheet("background-color: transparent;")
        status_layout.addWidget(self.status_icon)
        self.status_label = QLabel()
        self.status_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 13px; background-color: transparent;")
        status_layout.addWidget(self.status_label, 1)

        # First comment preview — the earliest message in this annotation's
        # conversation (its own text, or whoever's note came first if it
        # has none — see get_first_comment), shown right on the card face
        # so seeing what a point is about doesn't require opening it.
        # Marquee-scrolls on its own (see _MarqueeLabel) when the wording
        # is too long to fit the card's width instead of just clipping it.
        self.comment_preview = _MarqueeLabel('')
        self.comment_preview.setStyleSheet(f"background-color: transparent;")
        self.comment_preview.setColor(default_theme.text_secondary)
        preview_font = make_font(size=12)
        preview_font.setItalic(True)
        self.comment_preview.setFont(preview_font)
        self.comment_preview.setFixedHeight(QFontMetrics(preview_font).height() + 4)
        self.comment_preview.hide()

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)
        info_layout.addWidget(self.label_edit)
        info_layout.addWidget(status_row)
        info_layout.addWidget(self.comment_preview)

        layout.addLayout(info_layout, 1)  # stretch
        layout.addStretch()
        
        # Date and time (date on first line, time on second)
        if self.annotation.created_at:
            date_text = _format_annotation_date(self.annotation.created_at, include_time=False)
            time_text = _format_annotation_time(self.annotation.created_at)
            date_time_text = f"{date_text}\n{time_text}"
        else:
            date_time_text = str(self.annotation.id)
        self.coord_label = QLabel(date_time_text)
        self.coord_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.coord_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 15px; background-color: transparent;")
        layout.addWidget(self.coord_label)
        
        # Delete button (cross)
        self.delete_btn = QPushButton("✕")
        self.delete_btn.setFixedSize(28, 28)
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setToolTip(t("annotation.remove_tooltip"))
        self.delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                font-size: 15px;
                font-weight: bold;
                color: {default_theme.text_secondary};
                padding: 0; min-width: 28px; min-height: 28px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.12);
                color: #F87171;
                border-radius: 14px;
            }}
        """ + TOOLTIP_STYLE)
        self.delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.annotation.id))
        layout.addWidget(self.delete_btn)
    
    def _compute_label_locked(self) -> bool:
        """A supplier in LYNS Lite can rename their own pins but must not be
        able to relabel a point the PM already placed (added_by != 'supplier')
        — mirrors the existing-content-locked/new-content-editable split used
        for the popup conversation and for Quality Control control points."""
        from core.edition import is_lite
        return is_lite() and self.annotation.added_by != 'supplier'

    def _on_label_editing_finished(self):
        """Handle label edit - emit to panel."""
        new_label = self.label_edit.text().strip() or "Point"
        if new_label != self.annotation.label:
            self.annotation.label = new_label
            self.label_edited.emit(self.annotation.id, new_label)
        self.label_edit.setText(self.annotation.label)

    def _open_color_picker(self):
        """Open the shared DrawColorPicker and emit color changes."""
        try:
            from ui.draw_color_picker import DrawColorPicker
        except Exception:
            return
        picker = DrawColorPicker(self)
        picker.color_selected.connect(self._on_color_selected)
        global_pos = self.point_indicator.mapToGlobal(self.point_indicator.rect().bottomLeft())
        picker.move(global_pos)
        picker.show()

    def _on_color_selected(self, color: str):
        # Store color on the annotation and update visuals
        self.annotation.color = color
        # Update badge and dot appearance
        self.date_icon.setPixmap(_rounded_text_pixmap(str(self._display_number), fill_color=color))
        self.point_indicator.setStyleSheet(f"background-color: {color}; border-radius: 8px; border: 1px solid {default_theme.border_standard};")
        self.color_changed.emit(self.annotation.id, color)
    
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
    
    def _get_indicator_color(self) -> str:
        """Return the dot/badge color based on annotation state."""
        # If annotation has an explicit color, use it
        if getattr(self.annotation, 'color', None):
            return self.annotation.color
        if self._reader_mode:
            return READER_READ_COLOR if self.annotation.is_read else READER_UNREAD_COLOR
        return PENDING_COLOR

    def _update_style(self):
        """Update the card style based on reader mode's read/unread state.
        There's no separate "validated" state any more — outside reader
        mode every card just uses the same default look."""
        indicator_color = self._get_indicator_color()
        status_color = default_theme.text_secondary
        if self._reader_mode:
            if self.annotation.is_read:
                base_grad = _ANNO_CARD_VALIDATED
                self.status_icon.setPixmap(_checkmark_pixmap(12, status_color))
                self.status_icon.setVisible(True)
                self.status_label.setText(t("annotation.read"))
                self.status_label.setStyleSheet('color: %s; background: transparent;' % status_color)
            else:
                base_grad = _ANNO_CARD_READER_UNREAD
                self.status_icon.setPixmap(QPixmap())
                self.status_icon.setVisible(False)
                self.status_label.setText(t("annotation.unread"))
                self.status_label.setStyleSheet('color: %s; background: transparent;' % status_color)
        else:
            base_grad = _ANNO_CARD_PENDING
            self.status_icon.setPixmap(QPixmap())
            self.status_icon.setVisible(False)
            self.status_label.setText(t("annotation.click_to_edit"))
            self.status_label.setStyleSheet('color: %s; background: transparent;' % status_color)

        # Style the clickable dot as a colored round button
        self.point_indicator.setStyleSheet(f"""
            QPushButton {{
                background-color: {indicator_color};
                border-radius: 8px;
                border: 1px solid {default_theme.border_standard};
            }}
            QPushButton:hover {{
                border: 2px solid {default_theme.button_primary};
            }}
        """ + TOOLTIP_STYLE)
        self.date_icon.setPixmap(_rounded_text_pixmap(str(self._display_number), fill_color=indicator_color))
        self.setStyleSheet(f"""
            QFrame#annotationCard {{
                background: {base_grad};
                {_ANNO_CARD_BORDER}
            }}
            QFrame#annotationCard:hover {{
                background: {_ANNO_CARD_HOVER};
                {_ANNO_CARD_BORDER_HOVER}
            }}
            QFrame#annotationCard QLabel {{
                background-color: transparent;
            }}
            QFrame#annotationCard QLineEdit {{
                background-color: transparent;
            }}
        """ + TOOLTIP_STYLE)
    
    def update_annotation(self, annotation: Annotation, display_number: int = None):
        """Update the card with new annotation data and optional display number (1, 2, 3...)."""
        self.annotation = annotation
        if display_number is not None:
            self._display_number = display_number
        if annotation.created_at:
            date_text = _format_annotation_date(annotation.created_at, include_time=False)
            time_text = _format_annotation_time(annotation.created_at)
            self.coord_label.setText(f"{date_text}\n{time_text}")
        else:
            self.coord_label.setText(str(self._display_number))
        self._label_locked = self._compute_label_locked()
        self.label_edit.setReadOnly(self._label_locked)
        self.label_edit.blockSignals(True)
        self.label_edit.setText(annotation.label)
        self.label_edit.blockSignals(False)
        self._update_style()
        self._update_tooltip()
        self._update_comment_preview()

    def retranslate(self):
        """Refresh every translated string on this already-built card —
        the placeholder, both tooltips, the status label (via _update_style)
        and the hover tooltip (via _update_tooltip). Needed because a card
        is built once and lives for the rest of the session; unlike a
        dialog that gets reconstructed on each open (e.g. DrawColorPicker),
        nothing here refreshes on a language switch unless explicitly told
        to — see AnnotationPanel._update_texts, which calls this for every
        card on the on_language_changed hook."""
        self.label_edit.setPlaceholderText(t("annotation.point"))
        self.point_indicator.setToolTip(t("annotation.change_color_tooltip"))
        self.delete_btn.setToolTip(t("annotation.remove_tooltip"))
        self._update_style()
        self._update_tooltip()
        self._update_comment_preview()

    def _update_comment_preview(self):
        """Show the conversation's first comment (see get_first_comment)
        right on the card face, attributed to whoever wrote it — hidden
        entirely if there's no comment yet. Uses _MarqueeLabel so long
        wording scrolls into view instead of just getting clipped."""
        first = get_first_comment(self.annotation)
        if first is None:
            self.comment_preview.hide()
            return
        text, author = first
        self.comment_preview.setText(f"{author}: {text}")
        self.comment_preview.show()

    def _update_tooltip(self):
        """Update the hover tooltip with annotation details."""
        date_str = _format_annotation_date(self.annotation.created_at, include_time=True) if self.annotation.created_at else f"#{self.annotation.id}"

        tooltip_parts = [
            f"<b>{self.annotation.label}</b> #{self._display_number}",
        ]
        # Only reader mode still has a status worth calling out — read/unread.
        if self._reader_mode:
            status = t("annotation.read") if self.annotation.is_read else t("annotation.unread")
            tooltip_parts.append(f"<br><b>{t('annotation.tooltip_status')}</b> {status}")
        tooltip_parts.append(f"<br><b>{t('annotation.tooltip_date')}</b> {date_str}")

        if self.annotation.text:
            # Truncate long text
            text_preview = self.annotation.text[:100] + "..." if len(self.annotation.text) > 100 else self.annotation.text
            tooltip_parts.append(f"<br><b>{t('annotation.tooltip_note')}</b> {text_preview}")

        if self.annotation.image_paths:
            photos_count = t('annotation.tooltip_photos_count').format(count=len(self.annotation.image_paths))
            tooltip_parts.append(f"<br><b>{t('annotation.tooltip_photos')}</b> {photos_count}")
        
        self.setToolTip("".join(tooltip_parts))


class AnnotationPanel(QWidget):
    """Panel for managing all annotations with popup editing."""
    
    # Signals
    annotation_added = pyqtSignal(object)  # Annotation
    annotation_deleted = pyqtSignal(int)   # annotation_id
    annotation_validated = pyqtSignal(int, str, list, str)  # annotation_id, text, image_paths, label
    annotation_color_changed = pyqtSignal(int, str)  # annotation_id, hex color
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

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Header — warm leather-style banner (gradient + bevel + dashed section rule)
        header = QFrame()
        header.setObjectName("annotationModeBanner")
        header.setAttribute(Qt.WA_StyledBackground, True)
        header.setStyleSheet(f"""
            QFrame#annotationModeBanner {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {_ANNO_LEATHER_TOP},
                    stop:0.12 {_ANNO_LEATHER_UPPER},
                    stop:0.38 {_ANNO_LEATHER_MID},
                    stop:0.72 {_ANNO_LEATHER_DEEP},
                    stop:1 {_ANNO_LEATHER_BOTTOM});
                border-top: 1px solid rgba(255, 255, 255, 0.52);
                border-left: 1px solid rgba(255, 255, 255, 0.42);
                border-right: 1px solid rgba(255, 255, 255, 0.38);
                border-bottom: 1px solid rgba(255, 255, 255, 0.32);
                border-radius: 14px;
            }}
        """)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(0)
        
        # Title row
        title_row = QHBoxLayout()
        title_row.setContentsMargins(2, 0, 0, 0)
        title_row.setSpacing(10)
        from ui.annotation_icon import get_annotation_icon_pixmap
        anno_icon = QLabel()
        pix = get_annotation_icon_pixmap(22)
        if not pix.isNull():
            anno_icon.setPixmap(pix)
        else:
            anno_icon.setText("📝")
        anno_icon.setFixedSize(22, 22)
        anno_icon.setAlignment(Qt.AlignCenter)
        anno_icon.setStyleSheet("background: transparent; border: none;")
        title_row.addWidget(anno_icon)
        self.title_label = QLabel()
        title_font = make_font(size=15, bold=True)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet("color: #FFFFFF; background: transparent; border: none;")
        title_row.addWidget(self.title_label)
        title_row.addStretch()
        
        # Close button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: rgba(255, 255, 255, 0.92);
                font-size: 16px;
                font-weight: bold;
                padding: 0; min-width: 28px; min-height: 28px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                background-color: rgba(0, 0, 0, 0.18);
                border-radius: 14px;
            }
        """)
        close_btn.clicked.connect(self.exit_annotation_mode.emit)
        title_row.addWidget(close_btn)
        
        header_layout.addLayout(title_row)
        
        divider = QFrame()
        divider.setObjectName("annotationModeDivider")
        divider.setFrameShape(QFrame.NoFrame)
        divider.setMinimumHeight(3)
        divider.setMaximumHeight(3)
        divider.setStyleSheet("""
            QFrame#annotationModeDivider {
                border: none;
                border-top: 1px dashed rgba(255, 255, 255, 0.55);
                margin-top: 8px;
                margin-bottom: 8px;
                margin-left: 0px;
                margin-right: 0px;
                background: transparent;
            }
        """)
        header_layout.addWidget(divider)
        
        # Instructions / Reader Mode indicator
        self.instructions_label = QLabel("Please add the first annotation by clicking on the 3D object")
        self.instructions_label.setWordWrap(True)
        self.instructions_label.setStyleSheet(
            "color: rgba(255, 255, 255, 0.95); font-size: 15px; background: transparent; border: none;"
        )
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
        reader_label.setStyleSheet("color: #1E40AF; font-size: 15px; font-weight: bold;")
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
        self.empty_label = QLabel(t("annotation.no_annotations_short"))
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 15px; padding: 20px;")
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
                font-size: 15px;
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

        on_language_changed(self._update_texts)
        self._update_texts()
    
    def set_reader_mode(self, enabled: bool):
        """Enable or disable reader mode (view-only).

        In LYNS Lite, `enabled` is still True for the whole bundle (it
        locks the PM's own annotations — see AnnotationCard and
        AnnotationPanel.add_annotation's is_lite() bypass) but the
        "Reader Mode - View Only" banner doesn't apply there: the supplier
        can add new pins and post comments, so telling them the panel is
        view-only is simply wrong. Lite shows the same header 360 shows
        outside reader mode instead — just the instructions text, no banner."""
        self._reader_mode = enabled
        from core.edition import is_lite
        show_banner = enabled and not is_lite()

        if show_banner:
            # Show reader mode banner, hide instructions
            self.reader_mode_banner.show()
            self.instructions_label.hide()
        else:
            # Show instructions, hide banner
            self.reader_mode_banner.hide()
            self.instructions_label.show()
        # Clear button stays hidden for any reader-mode bundle, Lite
        # included — there's still nothing a supplier should be clearing.
        self.clear_btn.setVisible(not enabled)

        # Update all cards: badge and dot must follow color in both reader and editor modes
        for card in self.annotation_cards.values():
            card._reader_mode = enabled
            card._update_style()
    
    def is_reader_mode(self) -> bool:
        """Check if panel is in reader mode."""
        return self._reader_mode
    
    def add_annotation(self, point: tuple) -> Annotation:
        """Add a new annotation at the given point. Each new point automatically
        picks up the next color in the shared palette (cycling), so consecutive
        points are easy to tell apart at a glance instead of all starting out
        the same gray."""
        from core.edition import is_lite
        color = PALETTE[len(self.annotations) % len(PALETTE)]
        annotation = Annotation(
            id=self._next_id,
            point=point,
            text="",
            image_paths=[],
            color=color,
            added_by='supplier' if is_lite() else None,
        )
        self._next_id += 1
        self.annotations.append(annotation)

        # Create card (display_number = position in list, 1-based)
        display_number = len(self.annotations)  # we just appended
        # A pin just placed by the supplier is always editable, even when the
        # rest of this bundle (the PM's own annotations) is reader-mode —
        # see ui/toolbar.py's set_reader_mode for the matching "can still add"
        # bypass on the toolbar button.
        card_reader_mode = False if is_lite() else self._reader_mode
        card = AnnotationCard(annotation, reader_mode=card_reader_mode, display_number=display_number)
        card.clicked.connect(self._on_card_clicked)
        card.delete_requested.connect(self._on_delete_requested)
        card.focus_requested.connect(self._on_focus_requested)
        card.label_edited.connect(self._on_label_edited)
        card.color_changed.connect(self._on_card_color_changed)
        card.hover_changed.connect(self.annotation_hovered.emit)
        
        self.annotation_cards[annotation.id] = card
        self.content_layout.addWidget(card)
        
        # Update UI state
        self.empty_label.hide()
        self.clear_btn.setEnabled(True)
        
        self.annotation_added.emit(annotation)
        logger.info(f"Annotation added: id={annotation.id}, point={point}")

        return annotation

    def import_annotation(self, data: dict) -> Annotation:
        """Append one annotation from external data (a supplier's returned
        .lyns.review, via the merge-import flow in ui/project_widget.py /
        core/annotation_merge.py) — appends, unlike load_annotations which
        replaces the whole list.

        Renumbers the id if it collides with one already present: the
        supplier's id sequence started from the same base as this tab's did
        at export time, so if the PM added new annotations locally after
        exporting, a genuinely new id on each side can coincide."""
        annotation = Annotation.from_dict(data)
        existing_ids = {a.id for a in self.annotations}
        if annotation.id in existing_ids:
            new_id = (max(existing_ids) + 1) if existing_ids else 1
            logger.info(f"import_annotation: id {annotation.id} collides with an "
                        f"existing annotation, renumbering to {new_id}")
            annotation.id = new_id
        if annotation.id >= self._next_id:
            self._next_id = annotation.id + 1
        self.annotations.append(annotation)

        display_number = len(self.annotations)
        card = AnnotationCard(annotation, reader_mode=False, display_number=display_number)
        card.clicked.connect(self._on_card_clicked)
        card.delete_requested.connect(self._on_delete_requested)
        card.focus_requested.connect(self._on_focus_requested)
        card.label_edited.connect(self._on_label_edited)
        card.color_changed.connect(self._on_card_color_changed)
        card.hover_changed.connect(self.annotation_hovered.emit)

        self.annotation_cards[annotation.id] = card
        self.content_layout.addWidget(card)
        self.empty_label.hide()
        self.clear_btn.setEnabled(True)

        self.annotation_added.emit(annotation)
        logger.info(f"import_annotation: merged in annotation id={annotation.id}")
        return annotation

    def add_supplier_notes(self, annotation_id: int, notes: list) -> bool:
        """Append supplier feedback note(s) to an EXISTING annotation's
        thread (see Annotation.supplier_notes) — used by the merge-import
        flow when a supplier commented on one of the PM's own annotations
        rather than adding a new one. Returns False if the annotation no
        longer exists locally (e.g. the PM deleted it after exporting)."""
        annotation = self.get_annotation_by_id(annotation_id)
        if annotation is None:
            return False
        annotation.supplier_notes.extend(notes)
        card = self.annotation_cards.get(annotation_id)
        if card is not None:
            card.update_annotation(annotation)
        return True

    def add_pm_notes(self, annotation_id: int, notes: list) -> bool:
        """Append the PM's own follow-up comment(s) to an annotation's
        thread (see Annotation.pm_notes) — used by ui/annotation_popup.py's
        conversation composer so the PM can keep replying without
        overwriting the original text/image_paths. Mirrors
        add_supplier_notes above; returns False if the annotation no
        longer exists."""
        annotation = self.get_annotation_by_id(annotation_id)
        if annotation is None:
            return False
        annotation.pm_notes.extend(notes)
        card = self.annotation_cards.get(annotation_id)
        if card is not None:
            card.update_annotation(annotation)
        return True

    def remove_annotation(self, annotation_id: int, skip_emit: bool = False):
        """Remove an annotation by ID and renumber remaining (1, 2, 3...).
        
        Args:
            annotation_id: ID of annotation to remove
            skip_emit: If True, do not emit annotation_deleted (used during bulk clear)
        """
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
        
        if not skip_emit:
            self.annotation_deleted.emit(annotation_id)
        logger.info(f"Annotation removed: id={annotation_id}, renumbered to {[i+1 for i in range(len(self.annotations))]}")
    
    def clear_all(self):
        """Remove all annotations."""
        for annotation_id in list(self.annotation_cards.keys()):
            self.remove_annotation(annotation_id, skip_emit=True)
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

    def _update_texts(self):
        """Refresh translated labels — the panel's own chrome, plus every
        already-built card (see AnnotationCard.retranslate's docstring for
        why cards need this explicit push instead of picking it up on
        their own)."""
        self.title_label.setText(t("annotation.panel_title"))
        self.instructions_label.setText(t("annotation.subtitle"))
        self.clear_btn.setText(t("annotation.clear_all"))
        self.empty_label.setText(t("annotation.no_annotations_short"))
        for card in self.annotation_cards.values():
            card.retranslate()
    
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
            card.color_changed.connect(self._on_card_color_changed)
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

    def _on_card_color_changed(self, annotation_id: int, color: str):
        """Handle color change from a card: update model, UI and emit panel signal."""
        annotation = self.get_annotation_by_id(annotation_id)
        if not annotation:
            return
        annotation.color = color
        # Update the card display
        card = self.annotation_cards.get(annotation_id)
        if card:
            card.update_annotation(annotation)
        # Emit panel-level signal for external listeners (viewer)
        self.annotation_color_changed.emit(annotation_id, color)
        logger.info(f"Annotation color changed: id={annotation_id}, color={color}")
    
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
        """Commit the popup's Done button: save text/images/label onto the
        live annotation (there's no separate validated/pending state any
        more — every annotation looks the same once it has this)."""
        annotation = self.get_annotation_by_id(annotation_id)
        if annotation:
            annotation.text = text
            annotation.image_paths = image_paths
            annotation.label = label or "Point"

            # Update card display
            if annotation_id in self.annotation_cards:
                self.annotation_cards[annotation_id].update_annotation(annotation)

            self.annotation_validated.emit(annotation_id, text, image_paths, label or "Point")
            logger.info(f"Annotation updated: id={annotation_id}")
