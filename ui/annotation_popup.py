"""
Annotation Popup Dialog — the PM's editable view of one annotation: a
single conversation thread (the original comment plus every reply, see
AnnotationPopup._all_entries) and one composer to post to it.
"""
import logging
from typing import List, Optional
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QFileDialog, QScrollArea, QFrame, QWidget, QLineEdit
)
from PyQt5.QtCore import Qt, pyqtSignal
from ui.styles import make_font
from i18n import t

logger = logging.getLogger(__name__)

# Light dialog theme (white) — independent of the app’s dark sidebar / theme.
_POPUP_BG = "#ffffff"
_POPUP_BORDER = "#d1d5db"
_POPUP_TEXT = "#111827"
_POPUP_TEXT_MUTED = "#6b7280"
_POPUP_SECTION = "#374151"
_POPUP_INPUT_BG = "#ffffff"
_POPUP_INPUT_BORDER = "#d1d5db"
_POPUP_SHADE = "#f3f4f6"
_POPUP_FOCUS = "#2596BE"


class AnnotationPopup(QDialog):
    """Popup dialog for editing an annotation."""
    
    # Signals
    annotation_validated = pyqtSignal(int, str, list, str)  # annotation_id, text, image_paths, label
    annotation_deleted = pyqtSignal(int)  # annotation_id
    note_added = pyqtSignal(int, dict)  # annotation_id, note — the PM posted a follow-up comment

    def __init__(self, annotation_id: int, point: tuple, text: str = "",
                 image_paths: Optional[List[str]] = None, label: str = "Point",
                 created_at=None, display_number: int = None,
                 supplier_notes: Optional[List[dict]] = None,
                 pm_notes: Optional[List[dict]] = None,
                 added_by: Optional[str] = None, parent=None):
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
        # were placed by a supplier in LYNS Lite rather than the PM here in
        # 360 (see ui/annotation_panel.py's Annotation.added_by) — decides
        # how that first conversation entry gets attributed in
        # _all_entries. None for every annotation the PM created themselves.
        self.added_by = added_by
        # Everything anyone has added on top of the original comment/photos
        # via the Supplier Review Workflow (core/annotation_merge.py):
        # supplier_notes from the supplier's LYNS Lite session, pm_notes from
        # this PM replying in 360. Both, plus the original text/image_paths
        # above, are shown as one conversation — see _all_entries — instead
        # of the original being a separate, fixed "starting comment".
        self.supplier_notes = list(supplier_notes or [])
        self.pm_notes = list(pm_notes or [])
        self._staged_photo_paths: List[str] = []

        self.setWindowTitle(t('annotation.popup_title').format(label=label, number=self._display_number))
        self.setModal(False)  # Non-modal so user can still interact with 3D view
        self.setMinimumSize(460, 420)
        from ui.annotation_icon import get_app_window_icon
        icon = get_app_window_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.setMaximumSize(620, 780)
        self.resize(500, 560)

        self.init_ui()

    def _all_entries(self) -> list:
        """This annotation's full conversation, oldest first: the original
        comment/photos (if any) as entry zero, then supplier_notes/pm_notes
        interleaved by added_at. The original entry is prepended rather than
        sorted in by timestamp so it's always first regardless of clock
        skew between this machine and wherever a supplier's notes were
        added. No author name is attached to the synthesized original entry
        — nothing in the data model records who actually wrote it, so
        _build_note_card's generic 'PM'/'Supplier' fallback is used instead
        of guessing (guessing would show whoever has the popup open now,
        which is wrong for anyone re-opening someone else's old comment)."""
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

    def init_ui(self):
        """Initialize the popup UI: fixed chrome (scroll area + Delete/Done
        buttons) built once here; the scrollable body itself is built by
        _build_content() so nothing (a long conversation, a tall photo) can
        ever get clipped by the dialog's max size — everything scrolls
        inside instead."""
        self.setObjectName("annotationPopup")
        self.setAttribute(Qt.WA_StyledBackground, True)
        # Scoped rules override global app QLabel styles (which can paint dark strips behind text/icons).
        self.setStyleSheet(f"""
            QDialog#annotationPopup {{
                background-color: {_POPUP_BG};
                border: 1px solid {_POPUP_BORDER};
                border-radius: 10px;
            }}
            QDialog#annotationPopup QLabel {{
                background-color: transparent;
                border: none;
                color: {_POPUP_TEXT};
            }}
            QDialog#annotationPopup QLabel#annotationDateBadge {{
                color: {_POPUP_TEXT_MUTED};
                font-size: 13px;
                background-color: {_POPUP_SHADE};
                border: 1px solid {_POPUP_BORDER};
                border-radius: 6px;
                padding: 6px 10px;
            }}
            QDialog#annotationPopup QScrollArea > QWidget > QWidget {{
                background-color: {_POPUP_BG};
            }}
        """)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 16, 0, 16)
        outer_layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"background: {_POPUP_BG};")
        self._scroll.setWidget(self._build_content())
        outer_layout.addWidget(self._scroll, 1)

        # Action buttons — fixed at the bottom, outside the scroll area, so
        # they're always reachable regardless of how much content is above.
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(16, 12, 16, 0)
        btn_layout.setSpacing(10)

        delete_btn = QPushButton(f"🗑 {t('annotation.delete')}")
        delete_btn.setFixedHeight(36)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #fef2f2;
                border: 1px solid #fecaca;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
                color: #dc2626;
            }}
            QPushButton:hover {{
                background-color: #fee2e2;
            }}
        """)
        delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()

        done_btn = QPushButton(f"✓ {t('annotation.done')}")
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

        outer_layout.addLayout(btn_layout)

    def _build_content(self) -> QWidget:
        """Build the scrollable body: header + the unified conversation
        section (see _all_entries — the original comment/photos plus every
        reply, one thread, no separate 'Comment:'/'Photos:' block). Called
        once from init_ui() and again from _on_submit_comment() after a new
        reply is posted, so the popup never needs to be closed and reopened."""
        content = QWidget()
        content.setStyleSheet(f"background-color: {_POPUP_BG};")
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(16, 0, 16, 0)
        main_layout.setSpacing(12)
        self._main_layout = main_layout

        # Header: annotation icon + rounded number + editable label
        header_layout = QHBoxLayout()
        from ui.annotation_icon import get_annotation_icon_pixmap
        anno_icon = QLabel()
        anno_icon.setObjectName("annotationIconLabel")
        anno_icon.setAutoFillBackground(False)
        pix = get_annotation_icon_pixmap(28)
        if not pix.isNull():
            anno_icon.setPixmap(pix)
        anno_icon.setFixedSize(28, 28)
        anno_icon.setAlignment(Qt.AlignCenter)
        anno_icon.setAttribute(Qt.WA_StyledBackground, True)
        header_layout.addWidget(anno_icon)
        from ui.annotation_panel import _rounded_text_pixmap
        num_icon = QLabel()
        num_icon.setObjectName("annotationNumBadge")
        num_icon.setAutoFillBackground(False)
        num_icon.setPixmap(_rounded_text_pixmap(str(self._display_number), size=32))
        num_icon.setFixedSize(32, 32)
        num_icon.setAttribute(Qt.WA_StyledBackground, True)
        header_layout.addWidget(num_icon)
        self.label_edit = QLineEdit()
        self.label_edit.setText(self.label)
        self.label_edit.setPlaceholderText(t('annotation.label_placeholder'))
        title_font = make_font(size=13, bold=True)
        self.label_edit.setFont(title_font)
        self.label_edit.setStyleSheet(f"""
            QLineEdit {{
                color: {_POPUP_TEXT};
                background: transparent;
                border: none;
                border-bottom: 1px solid transparent;
            }}
            QLineEdit:focus {{
                border-bottom: 1px solid {_POPUP_FOCUS};
            }}
        """)
        self.label_edit.setFixedHeight(28)
        header_layout.addWidget(self.label_edit)
        
        header_layout.addStretch()
        
        # Date (where coordinates were shown)
        from ui.annotation_panel import _format_annotation_date
        date_text = _format_annotation_date(self.created_at, include_time=True) if self.created_at and hasattr(self.created_at, 'month') else str(self.annotation_id)
        date_label = QLabel(date_text)
        date_label.setObjectName("annotationDateBadge")
        date_label.setAutoFillBackground(False)
        date_label.setAttribute(Qt.WA_StyledBackground, True)
        header_layout.addWidget(date_label)
        
        main_layout.addLayout(header_layout)

        # Conversation — the original comment/photos plus every reply, one
        # thread (see _all_entries), each in its own attributed card with
        # its own photos, plus a single composer at the bottom for posting
        # the next one — whether that's the very first comment on a brand
        # new annotation or a follow-up on one that already has a thread.
        self._conversation_widget = self._build_conversation_section()
        main_layout.addWidget(self._conversation_widget)
        main_layout.addStretch()
        return content

    def _build_conversation_section(self) -> QFrame:
        """The full thread on this annotation — see _all_entries — each
        entry in its own attributed card, plus a composer so the PM can
        keep posting to it instead of this being a single overwritable
        comment box. Mirrors the read-only half of this same thread shown
        to the supplier in ui/annotation_viewer_popup.py's
        AnnotationViewerPopup, so both sides see the identical conversation."""
        section = QFrame()
        section.setStyleSheet("background: transparent; border: none;")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 4, 0, 0)
        section_layout.setSpacing(8)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {_POPUP_BORDER}; background-color: {_POPUP_BORDER}; max-height: 1px; border: none;")
        section_layout.addWidget(sep)

        entries = self._all_entries()

        title = QLabel(t('annotation.conversation_label').format(count=len(entries)))
        title.setStyleSheet(f"color: {_POPUP_SECTION}; font-size: 12px; font-weight: bold; background: transparent;")
        section_layout.addWidget(title)

        # No inner scroll area here — the whole popup already scrolls (see
        # init_ui's self._scroll), so a long conversation just makes the
        # dialog scroll further instead of being squeezed into a fixed-
        # height box inside a fixed-height dialog (the old "modal is cut
        # off" bug: a tall photo or a few replies would overflow both the
        # inner and outer bounds at once).
        for side, note in entries:
            section_layout.addWidget(self._build_note_card(side, note))

        section_layout.addWidget(self._build_composer())
        return section

    def _build_note_card(self, side: str, note: dict) -> QFrame:
        """One conversation entry — attribution + text + its own photos.
        Renders both the synthesized original entry (see _all_entries) and
        real supplier_notes/pm_notes entries identically. side: 'supplier'
        or 'pm', just controls the accent color/name. On the 'pm' side this
        is the PM's own 360 session, so it can show the actual signed-in
        name (get_display_name()) rather than a generic "PM" label —
        unlike ui/annotation_viewer_popup.py's Lite-side rendering of this
        same thread, which deliberately hides individual PM names from
        the supplier behind "Managing Team"."""
        from core.identity import get_display_name
        accent = _POPUP_FOCUS if side == 'supplier' else '#10B981'
        who = (note.get('supplier_name') if side == 'supplier' else note.get('author_name')) or \
              ('Supplier' if side == 'supplier' else (get_display_name() or 'PM'))
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

        when = (note.get('added_at') or '')[:10]
        header = QLabel(f"👤 {who}" + (f"  ·  {when}" if when else ''))
        header.setStyleSheet(f"color: {accent}; font-size: 10px; font-weight: bold; background: transparent;")
        lay.addWidget(header)

        if note.get('text'):
            text_lbl = QLabel(note['text'])
            text_lbl.setWordWrap(True)
            text_lbl.setStyleSheet(f"color: {_POPUP_TEXT}; font-size: 11px; background: transparent;")
            lay.addWidget(text_lbl)

        note_images = note.get('image_paths') or []
        if note_images:
            from ui.annotation_viewer_popup import ImageViewThumbnail
            photos_row = QHBoxLayout()
            photos_row.setSpacing(6)
            photos_row.setAlignment(Qt.AlignLeft)
            for path in note_images:
                photos_row.addWidget(ImageViewThumbnail(path))
            lay.addLayout(photos_row)

        return card

    def _build_composer(self) -> QFrame:
        """Box for the PM to post into this annotation's conversation — see
        _on_submit_comment for whether that becomes the original
        text/image_paths or a pm_notes follow-up."""
        box = QFrame()
        box.setStyleSheet(f"""
            QFrame {{
                background-color: {_POPUP_SHADE};
                border: 1px dashed {_POPUP_INPUT_BORDER};
                border-radius: 6px;
            }}
        """)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self._composer_text = QTextEdit()
        self._composer_text.setPlaceholderText(t('annotation.comment_placeholder'))
        self._composer_text.setMinimumHeight(50)
        self._composer_text.setMaximumHeight(80)
        self._composer_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {_POPUP_INPUT_BG};
                border: 1px solid {_POPUP_INPUT_BORDER};
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
        add_photo_btn = QPushButton(f"📎 {t('annotation.add_photo')}")
        add_photo_btn.setCursor(Qt.PointingHandCursor)
        add_photo_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: {_POPUP_TEXT_MUTED};
                border: 1px solid {_POPUP_INPUT_BORDER}; border-radius: 6px;
                padding: 6px 12px; font-size: 11px;
            }}
            QPushButton:hover {{ background-color: #e5e7eb; }}
        """)
        add_photo_btn.clicked.connect(self._on_add_composer_photo)
        btn_row.addWidget(add_photo_btn)
        btn_row.addStretch()

        submit_btn = QPushButton(t('annotation.post_reply'))
        submit_btn.setCursor(Qt.PointingHandCursor)
        submit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_POPUP_FOCUS}; color: white; border: none;
                border-radius: 6px; padding: 6px 16px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #1f7ea3; }}
        """)
        submit_btn.clicked.connect(self._on_submit_comment)
        btn_row.addWidget(submit_btn)
        lay.addLayout(btn_row)

        return box

    def _on_add_composer_photo(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, t('annotation.select_photos_title'), "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.heic *.heif);;All Files (*)"
        )
        from core.image_utils import ensure_image_readable
        from ui.annotation_viewer_popup import ImageViewThumbnail
        for path in file_paths:
            if not path:
                continue
            usable_path = ensure_image_readable(path)
            if usable_path and usable_path not in self._staged_photo_paths:
                self._staged_photo_paths.append(usable_path)
                self._composer_photos_row.addWidget(ImageViewThumbnail(usable_path))

    def _on_submit_comment(self):
        """Post the composer's text/photos, then rebuild the conversation
        section in place so it appears immediately, without closing/
        reopening the dialog (mirrors AnnotationViewerPopup's
        _on_submit_feedback).

        If this annotation has no comment at all yet (a brand new pin),
        the composer's first submission becomes the canonical
        text/image_paths — the same fields PDF export, the sidebar card,
        and everything else in the app already reads — instead of a
        pm_notes entry; only once that "first message" exists does a
        further submission become a genuine follow-up in pm_notes. Either
        way this is the one input the PM ever posts through."""
        text = self._composer_text.toPlainText().strip()
        if not text and not self._staged_photo_paths:
            return

        if not self._all_entries():
            self.text = text
            self.image_paths = list(self._staged_photo_paths)
        else:
            import uuid
            from datetime import datetime, timezone
            from core.identity import get_display_name
            note = {
                'id': uuid.uuid4().hex,
                'author_name': get_display_name() or 'PM',
                'text': text,
                'image_paths': list(self._staged_photo_paths),
                'added_at': datetime.now(timezone.utc).isoformat(),
            }
            self.pm_notes.append(note)
            self.note_added.emit(self.annotation_id, note)
        logger.info(f"AnnotationPopup: comment added to annotation {self.annotation_id}")

        self._staged_photo_paths = []
        old_widget = self._conversation_widget
        idx = self._main_layout.indexOf(old_widget)
        self._main_layout.removeWidget(old_widget)
        old_widget.deleteLater()
        self._conversation_widget = self._build_conversation_section()
        self._main_layout.insertWidget(idx, self._conversation_widget)

    def _on_done(self):
        """Handle Done button - validate the annotation. self.text/
        image_paths are already current — set either at construction or by
        _on_submit_comment's "first message" path above, never edited
        directly in this popup any more."""
        self.label = self.label_edit.text().strip() or "Point"
        self.annotation_validated.emit(self.annotation_id, self.text, self.image_paths, self.label)
        self.accept()
    
    def _on_delete(self):
        """Handle Delete button."""
        self.annotation_deleted.emit(self.annotation_id)
        self.reject()
