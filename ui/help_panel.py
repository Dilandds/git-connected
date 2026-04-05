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

logger = logging.getLogger(__name__)

# ── Help content data ──────────────────────────────────────────────
# Each entry: { "question": str, "answer": str, "image": str|None }
# image paths are relative to assets/ or absolute; None = no image.

HELP_TOPICS = [
    {
        "question": "How do I load a 3D file?",
        "answer": (
            "Click the Upload button in the sidebar or drag-and-drop a file "
            "onto the viewer area.\n\n"
            "Supported formats: STL, STEP, OBJ, IGES, DXF, 3DM.\n\n"
            "You can also open multiple files in separate tabs using the '+' button."
        ),
        "image": None,
    },
    {
        "question": "How do I measure dimensions?",
        "answer": (
            "1. Click the Ruler icon in the toolbar.\n"
            "2. Click two points on the model to create a measurement.\n"
            "3. The distance is shown in the current unit (mm by default).\n\n"
            "You can change units from the sidebar dropdown."
        ),
        "image": None,
    },
    {
        "question": "How do I annotate a model?",
        "answer": (
            "1. Click the Annotation mode button in the toolbar.\n"
            "2. Click on the 3D model to place an annotation marker.\n"
            "3. Type your note in the annotation panel that appears on the right.\n\n"
            "Annotations are saved when you export to .ecto format."
        ),
        "image": None,
    },
    {
        "question": "How do I use Technical Overview?",
        "answer": (
            "1. Switch to the Technical Overview tab in the mode bar.\n"
            "2. Upload a document image or PDF.\n"
            "3. Use the annotation tool to place numbered callout arrows.\n"
            "4. Fill in metadata (title, manufacturer, dates) in the sidebar.\n"
            "5. Export as .ecto or PDF."
        ),
        "image": None,
    },
    {
        "question": "How do I calibrate Drawing Scale?",
        "answer": (
            "1. Switch to the Drawing Scale tab.\n"
            "2. Upload a technical drawing (PDF, JPG, or PNG).\n"
            "3. Use the scroll wheel to resize the drawing proportionally.\n"
            "4. Align the drawing's known dimension with the ruler frame.\n"
            "5. Once calibrated, enable the Ruler Tool to take accurate measurements.\n\n"
            "Use 'Add Reference' to place extra reference markers anywhere on the drawing."
        ),
        "image": None,
    },
    {
        "question": "How do I apply textures?",
        "answer": (
            "1. Click the Texture mode button in the toolbar.\n"
            "2. Upload texture images in the texture panel.\n"
            "3. Drag a texture from the panel and drop it onto a part of the 3D model.\n\n"
            "The texture will be applied to the selected surface."
        ),
        "image": None,
    },
    {
        "question": "How do I take screenshots?",
        "answer": (
            "1. Click the Screenshot mode button in the toolbar.\n"
            "2. Adjust the view as desired.\n"
            "3. Use the screenshot panel controls to capture and save the image.\n\n"
            "Screenshots can be saved as PNG files."
        ),
        "image": None,
    },
    {
        "question": "How do I export my work?",
        "answer": (
            "ECTOFORM supports multiple export options:\n\n"
            "• Scaled STL — Export with a custom scale factor from the sidebar.\n"
            "• .ecto — Bundle the model, annotations, and metadata into a single file.\n"
            "• PDF — Export Technical Overview as a formatted PDF report.\n"
            "• Scaled Drawing — Export calibrated drawings from the Drawing Scale mode.\n"
            "• Screenshots — Save viewport captures as PNG images."
        ),
        "image": None,
    },
    {
        "question": "What file formats are supported?",
        "answer": (
            "Import formats:\n"
            "  • STL (binary & ASCII)\n"
            "  • STEP / STP (AP203, AP214)\n"
            "  • OBJ (with MTL materials)\n"
            "  • IGES / IGS\n"
            "  • DXF (3D entities)\n"
            "  • 3DM (Rhino)\n"
            "  • .ecto (ECTOFORM bundle)\n\n"
            "Export formats:\n"
            "  • STL (scaled)\n"
            "  • .ecto (annotated bundle)\n"
            "  • PDF (technical report)\n"
            "  • PNG (screenshots & scaled drawings)"
        ),
        "image": None,
    },
    {
        "question": "How do I use multi-part models?",
        "answer": (
            "When a multi-part model is loaded (e.g., STEP or OBJ with groups):\n\n"
            "1. Click the Parts mode button in the toolbar.\n"
            "2. The parts panel lists all detected components.\n"
            "3. Click a part to select/highlight it in the 3D view.\n"
            "4. Toggle visibility of individual parts."
        ),
        "image": None,
    },
]


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
        self._init_ui()

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

        header = QLabel("❓ Help & FAQ")
        header.setFont(make_font(size=14, bold=True))
        header.setStyleSheet(f"color: {default_theme.text_title}; border: none;")
        left_layout.addWidget(header)

        subtitle = QLabel("Click a question to see the answer")
        subtitle.setFont(make_font(size=9))
        subtitle.setStyleSheet(f"color: {default_theme.text_subtext}; border: none; margin-bottom: 8px;")
        left_layout.addWidget(subtitle)

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
        for i, topic in enumerate(HELP_TOPICS):
            card = _QuestionCard(topic["question"], i)
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
        if HELP_TOPICS:
            self._select_question(0)

    def _on_question_clicked(self, index: int):
        self._select_question(index)

    def _select_question(self, index: int):
        self._selected_index = index
        for card in self._question_cards:
            card.set_selected(card.index == index)
        self._answer_panel.show_topic(HELP_TOPICS[index])
