"""
ProjectBriefWidget — assembles the 7 section cards into a scrollable page.
All data and edit-mode logic is delegated to the individual section cards.
"""
import logging
from datetime import date
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QScrollArea,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from ui.styles import make_font
from .shared import _BG, _BORDER, _BORDER_L, _TEXT, _MUTED, _ACCENT
from i18n import t
from .section_overview    import ProductOverviewCard
from .section_techniques  import TechniquesCard
from .section_targets     import TargetPointsCard
from .section_dates       import TargetDatesCard
from .section_inspiration import InspirationCard
from .section_components  import ComponentsCard
from .section_notes       import NotesCard

logger = logging.getLogger(__name__)


class ProjectBriefWidget(QWidget):
    """Full Project Brief screen."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Sections are always editable now — the old Edit/Save Brief toggle
        # was removed since Save Project / Save Project As already persists
        # brief data, making a second in-page save gate redundant.
        self._edit_mode = True
        self._last_auto_title = ''
        self._last_auto_number = ''
        self._last_auto_photo = ''
        self.setStyleSheet(f'background-color: {_BG};')
        self._build_ui()
        self._set_edit_mode(True)

    # ── construction ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_top_bar())
        root.addWidget(self._build_scroll_body())

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f'background-color: {_BG}; border-bottom: 1px solid {_BORDER};')
        bar.setFixedHeight(52)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 24, 0)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        page_title = QLabel(t('project.brief.title'))
        page_title.setFont(make_font(size=20, bold=True))
        page_title.setStyleSheet(f'color: {_TEXT}; background: transparent; border: none;')
        subtitle = QLabel(t('project.brief.subtitle'))
        subtitle.setStyleSheet(f'color: {_MUTED}; font-size: 12px; background: transparent; border: none;')
        title_col.addWidget(page_title)
        title_col.addWidget(subtitle)
        layout.addLayout(title_col)
        layout.addStretch()
        return bar

    def _build_scroll_body(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background-color: {_BG}; border: none; }}
            QScrollBar:vertical {{ background: {_BG}; width: 12px; border-radius: 6px; }}
            QScrollBar::handle:vertical {{ background: {_ACCENT}; border-radius: 6px; min-height: 30px; }}
        """)

        body = QWidget()
        body.setStyleSheet(f'background-color: {_BG};')
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        # Instantiate all section cards
        self._s_overview    = ProductOverviewCard()
        self._s_techniques  = TechniquesCard()
        self._s_targets     = TargetPointsCard()
        self._s_dates       = TargetDatesCard()
        self._s_inspiration = InspirationCard()
        self._s_components  = ComponentsCard()
        self._s_notes       = NotesCard()

        # Row 1: Overview + Techniques
        row1 = QHBoxLayout(); row1.setSpacing(16)
        row1.addWidget(self._s_overview, 3)
        row1.addWidget(self._s_techniques, 2)
        layout.addLayout(row1)

        # Row 2: Targets + Dates + Inspiration
        row2 = QHBoxLayout(); row2.setSpacing(16)
        row2.addWidget(self._s_targets, 2)
        row2.addWidget(self._s_dates, 2)
        row2.addWidget(self._s_inspiration, 3)
        layout.addLayout(row2)

        # Row 3: Components + Notes
        self._s_components.setMinimumHeight(380)
        row3 = QHBoxLayout(); row3.setSpacing(16)
        row3.addWidget(self._s_components, 3)
        row3.addWidget(self._s_notes, 2)
        layout.addLayout(row3)

        layout.addWidget(self._build_footer())
        layout.addStretch()

        scroll.setWidget(body)
        return scroll

    def _build_footer(self) -> QWidget:
        w = QWidget(); w.setStyleSheet('background: transparent;')
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 8, 0, 0)
        today = date.today().strftime('%d %B %Y')
        for text, align in [(t('project.brief.generated_on').format(today=today), Qt.AlignLeft),
                             ('ECTOFORM v1.2.0', Qt.AlignRight)]:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f'color: {_MUTED}; font-size: 9px; background: transparent; border: none;'
            )
            layout.addWidget(lbl)
            if align == Qt.AlignLeft:
                layout.addStretch()
        return w

    # ── edit mode ─────────────────────────────────────────────────────────────

    def _set_edit_mode(self, enabled: bool):
        self._edit_mode = enabled
        for section in self._all_sections():
            section.set_edit_mode(enabled)

    def _all_sections(self):
        return (
            self._s_overview, self._s_techniques, self._s_targets,
            self._s_dates, self._s_inspiration, self._s_components, self._s_notes,
        )

    # ── serialisation ─────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        data = {}
        for section in self._all_sections():
            data.update(section.get_data())
        return data

    def set_data(self, data: dict):
        for section in self._all_sections():
            section.set_data(data)

    def update_project_info(self, info: dict):
        """Auto-fill overview fields from the sidebar project info.
        Keeps syncing while the field hasn't been manually edited.
        Also clears the field when the sidebar is cleared, if it was auto-filled.
        """
        title  = (info.get('title')  or '').strip()
        number = (info.get('number') or '').strip()

        current_name = self._s_overview._f_product_name.text().strip()
        if title:
            if not current_name or current_name == self._last_auto_title:
                self._s_overview._f_product_name.setText(title)
                self._last_auto_title = title
        elif current_name and current_name == self._last_auto_title:
            self._s_overview._f_product_name.setText('')
            self._last_auto_title = ''

        current_ref = self._s_overview._f_reference.text().strip()
        if number:
            if not current_ref or current_ref == self._last_auto_number:
                self._s_overview._f_reference.setText(number)
                self._last_auto_number = number
        elif current_ref and current_ref == self._last_auto_number:
            self._s_overview._f_reference.setText('')
            self._last_auto_number = ''

        photo = (info.get('photo_path') or '').strip()
        has_image = bool(self._s_overview._image_b64)
        if photo and photo != self._last_auto_photo:
            if not has_image or self._last_auto_photo:
                self._s_overview.set_image_from_path(photo)
                self._last_auto_photo = photo
        elif not photo and self._last_auto_photo:
            self._s_overview.clear_image()
            self._last_auto_photo = ''
