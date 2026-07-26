"""
Help Panel — Interactive Q&A panel with questions on the left and
illustrations / detailed answers on the right.
"""
import logging
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy, QStackedWidget,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap
from ui.styles import default_theme, make_font
from i18n import t, on_language_changed, raw

logger = logging.getLogger(__name__)


def _load_help_topics() -> list:
    """FAQ content lives in i18n/en.json + fr.json under "help.topics" so it
    translates with the rest of the app. Falls back to an empty list (the
    panel simply shows nothing) if the translation files are ever missing
    the key, rather than crashing."""
    topics = raw('help.topics')
    return topics if isinstance(topics, list) else []


# ── Question Card ──────────────────────────────────────────────────

class _QuestionCard(QPushButton):
    """A clickable question item in the left list."""

    def __init__(self, text: str, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.setText(f"  {text}")
        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setFont(make_font(size=11))
        self._apply_style(False)

    def _apply_style(self, selected: bool):
        if selected:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {default_theme.button_primary};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    text-align: left;
                    padding: 6px 12px;
                    font-weight: bold;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {default_theme.card_background};
                    color: {default_theme.text_primary};
                    border: 1px solid {default_theme.border_light};
                    border-radius: 6px;
                    text-align: left;
                    padding: 6px 12px;
                }}
                QPushButton:hover {{
                    background: {default_theme.row_bg_hover};
                    border-color: {default_theme.border_medium};
                }}
            """)

    def set_selected(self, selected: bool):
        self.setChecked(selected)
        self._apply_style(selected)

    def set_text(self, text: str):
        self.setText(f"  {text}")


# ── Answer Panel ───────────────────────────────────────────────────

class _AnswerPanel(QWidget):
    """Displays the answer text and optional illustration for a selected question."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self._question_label = QLabel()
        self._question_label.setObjectName("helpAnswerTitle")
        self._question_label.setFont(make_font(size=14, bold=True))
        self._question_label.setWordWrap(True)
        self._question_label.setStyleSheet(
            f"color: {default_theme.text_on_light}; background: transparent; border: none;"
        )
        layout.addWidget(self._question_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {default_theme.separator_on_light}; border: none;")
        layout.addWidget(sep)

        self._answer_label = QLabel()
        self._answer_label.setObjectName("helpAnswerBody")
        self._answer_label.setFont(make_font(size=11))
        self._answer_label.setWordWrap(True)
        self._answer_label.setStyleSheet(
            f"color: {default_theme.text_on_light_muted}; line-height: 1.5; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._answer_label)

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.hide()
        layout.addWidget(self._image_label)

        layout.addStretch()

    def show_topic(self, topic: dict):
        self._question_label.setText(topic["question"])
        self._answer_label.setText(topic["answer"])

        img_path = topic.get("image")
        if img_path:
            pixmap = QPixmap(img_path)
            if not pixmap.isNull():
                scaled = pixmap.scaledToWidth(
                    min(600, pixmap.width()), Qt.SmoothTransformation
                )
                self._image_label.setPixmap(scaled)
                self._image_label.show()
            else:
                self._image_label.hide()
        else:
            self._image_label.hide()


# ── Main Help Widget ──────────────────────────────────────────────

class HelpWidget(QWidget):
    """Full help workspace: question list (left) + answer/illustration (right)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_index = 0
        self._topics = _load_help_topics()
        self._init_ui()
        on_language_changed(self._retranslate)

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Left: question list ──
        left_frame = QFrame()
        left_frame.setFixedWidth(320)
        left_frame.setStyleSheet(f"""
            QFrame {{
                background: {default_theme.background};
                border-right: 1px solid {default_theme.border_light};
            }}
        """)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(12, 16, 12, 16)
        left_layout.setSpacing(6)

        self._header_lbl = QLabel(t('help.title'))
        self._header_lbl.setFont(make_font(size=14, bold=True))
        self._header_lbl.setStyleSheet(f"color: {default_theme.text_title}; border: none;")
        left_layout.addWidget(self._header_lbl)

        self._subtitle_lbl = QLabel(t('help.subtitle'))
        self._subtitle_lbl.setFont(make_font(size=9))
        self._subtitle_lbl.setStyleSheet(f"color: {default_theme.text_subtext}; border: none; margin-bottom: 8px;")
        left_layout.addWidget(self._subtitle_lbl)

        # Scrollable question list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(4)

        self._question_cards: list[_QuestionCard] = []
        for i, topic in enumerate(self._topics):
            card = _QuestionCard(topic.get("question", ""), i)
            card.clicked.connect(lambda checked, idx=i: self._on_question_clicked(idx))
            self._question_cards.append(card)
            scroll_layout.addWidget(card)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        left_layout.addWidget(scroll, 1)

        layout.addWidget(left_frame)

        # ── Right: answer area ──
        right_frame = QFrame()
        right_frame.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: none;
            }}
        """)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setStyleSheet("QScrollArea { border: none; background: white; }")

        self._answer_panel = _AnswerPanel()
        self._answer_panel.setStyleSheet("background: white;")
        right_scroll.setWidget(self._answer_panel)

        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(right_scroll)

        layout.addWidget(right_frame, 1)

        # Select first question
        if self._topics:
            self._select_question(0)

    def _on_question_clicked(self, index: int):
        self._select_question(index)

    def _select_question(self, index: int):
        self._selected_index = index
        for card in self._question_cards:
            card.set_selected(card.index == index)
        if 0 <= index < len(self._topics):
            self._answer_panel.show_topic(self._topics[index])

    def _retranslate(self):
        """Reload the FAQ content in the new language and refresh everything
        currently on screen: header/subtitle, each question card's label,
        and whichever answer is currently displayed."""
        self._topics = _load_help_topics()
        self._header_lbl.setText(t('help.title'))
        self._subtitle_lbl.setText(t('help.subtitle'))
        for card in self._question_cards:
            if card.index < len(self._topics):
                card.set_text(self._topics[card.index].get("question", ""))
        if self._topics:
            idx = self._selected_index if self._selected_index < len(self._topics) else 0
            self._answer_panel.show_topic(self._topics[idx])
