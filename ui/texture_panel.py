"""
Texture panel — displays uploaded texture images and predefined material
presets in a 2-column grid.  Textures / materials can be dragged onto
3D model parts to apply as surface textures or material finishes.
"""
import os
import json
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QFileDialog, QSizePolicy,
    QGridLayout, QApplication, QSlider,
)
from PyQt5.QtCore import Qt, pyqtSignal, QMimeData, QPoint
from PyQt5.QtGui import QPixmap, QDrag, QPainter, QColor, QRadialGradient, QPen
from ui.styles import default_theme, make_font
from ui.annotation_panel import (
    _ANNO_CARD_BORDER,
    _ANNO_CARD_BORDER_HOVER,
    _ANNO_CARD_HOVER,
    _ANNO_CARD_PENDING,
)

logger = logging.getLogger(__name__)

GRID_COLUMNS = 2

# Teal/cyan banner palette for texture mode
_TEX_TEAL_TOP = "#4DD0E1"
_TEX_TEAL_UPPER = "#26C6DA"
_TEX_TEAL_MID = "#00ACC1"
_TEX_TEAL_DEEP = "#00838F"
_TEX_TEAL_BOTTOM = "#006064"

# ---------------------------------------------------------------------------
# Material preset definitions
# ---------------------------------------------------------------------------
MATERIAL_PRESETS = [
    {
        "name": "Gold",
        "category": "metal",
        "color": "#D4A843",          # real 24K polished gold — warm amber, NOT bright yellow
        "highlight": "#F5E6B8",
        "specular": "#D4A843",
        "shininess": 350,
        "emissive": "#5C3D10",       # deep warm brown for shadow warmth
        "metalness": 1.0,
        "roughness": 0.15,           # slightly rough = satin gold finish (0.05 = chrome-like)
    },
    {
        "name": "Silver",
        "category": "metal",
        "color": "#C0C0C0",          # true neutral silver — pure mid-gray, no warmth
        "highlight": "#FFFFFF",
        "specular": "#FFFFFF",
        "shininess": 500,
        "emissive": "#060810",       # very dark blue-black for cold shadows
        "metalness": 1.0,
        "roughness": 0.05,           # near-mirror chrome finish
        "env_tone": "neutral",       # use neutral env map, not warm
    },
    {
        "name": "Leather Brown",
        "category": "fabric",
        "color": "#8B4513",
        "highlight": "#C4956A",
        "specular": "#3D2B1F",
        "shininess": 10,
        "metalness": 0.0,
        "roughness": 1.0,            # base roughness multiplied by roughness map
        "emissive": "#1A0A02",       # very dark warm shadow for depth
        "env_tone": "warm",
        "use_texture_maps": True,    # triggers procedural leather texture generation
        "albedo_map": "procedural_leather",
        "normal_map": "procedural_leather",
        "roughness_map": "procedural_leather",
    },
    {
        "name": "Glass",
        "category": "glass",
        "color": "#D4E8F0",          # very pale blue tint
        "highlight": "#FFFFFF",
        "specular": "#FFFFFF",
        "shininess": 500,
        "metalness": 0.0,
        "roughness": 0.02,           # near-perfect smooth surface
        "emissive": None,
        "env_tone": "neutral",
        "opacity": 0.3,              # transparent by default
    },
    {
        "name": "Lapis Lazuli",
        "category": "fabric",        # reuse Grain/Softness/Wear sliders
        "color": "#1A3A8F",          # deep royal blue base
        "highlight": "#4A6FCF",
        "specular": "#2B4DA0",
        "shininess": 80,
        "metalness": 0.0,
        "roughness": 0.7,
        "emissive": "#0A1540",       # deep blue shadow
        "env_tone": "neutral",
        "use_texture_maps": True,
        "albedo_map": "image_file",
        "albedo_map_path": "assets/textures/lapis_lazuli.png",
        "normal_map": None,
        "roughness_map": None,
        "swatch_image": "assets/textures/lapis_lazuli.png",
        "image_file": True,
        "tile_repeat": 1,
    },
    {
        "name": "Leather Orange",
        "category": "fabric",
        "color": "#B5541A",
        "highlight": "#D4763A",
        "specular": "#C06020",
        "shininess": 80,
        "metalness": 0.0,
        "roughness": 0.7,
        "emissive": "#5A2A0D",
        "env_tone": "neutral",
        "use_texture_maps": True,
        "albedo_map": "image_file",
        "albedo_map_path": "assets/leather_orange.png",
        "normal_map": None,
        "roughness_map": None,
        "swatch_image": "assets/leather_orange.png",
        "image_file": True,
        "tile_repeat": 1,
    },
    {
        "name": "Leather Black",
        "category": "fabric",
        "color": "#1A1A1A",
        "highlight": "#3A3A3A",
        "specular": "#2A2A2A",
        "shininess": 80,
        "metalness": 0.0,
        "roughness": 0.7,
        "emissive": "#0A0A0A",
        "env_tone": "neutral",
        "use_texture_maps": True,
        "albedo_map": "image_file",
        "albedo_map_path": "assets/leather_black_smooth.png",
        "normal_map": None,
        "roughness_map": None,
        "swatch_image": "assets/leather_black_smooth.png",
        "image_file": True,
        "tile_repeat": 1,
    },
    {
        "name": "Leather Black Grain",
        "category": "fabric",
        "color": "#151515",
        "highlight": "#353535",
        "specular": "#252525",
        "shininess": 80,
        "metalness": 0.0,
        "roughness": 0.7,
        "emissive": "#080808",
        "env_tone": "neutral",
        "use_texture_maps": True,
        "albedo_map": "image_file",
        "albedo_map_path": "assets/leather_black_grain.png",
        "normal_map": None,
        "roughness_map": None,
        "swatch_image": "assets/leather_black_grain.png",
        "image_file": True,
        "tile_repeat": 1,
    },
    {
        "name": "Turquoise Marble",
        "category": "fabric",
        "color": "#5CC8D4",
        "highlight": "#8DE0E8",
        "specular": "#6CD0DA",
        "shininess": 80,
        "metalness": 0.0,
        "roughness": 0.7,
        "emissive": "#2A646A",
        "env_tone": "neutral",
        "use_texture_maps": True,
        "albedo_map": "image_file",
        "albedo_map_path": "assets/turquoise_marble.png",
        "normal_map": None,
        "roughness_map": None,
        "swatch_image": "assets/turquoise_marble.png",
        "image_file": True,
        "tile_repeat": 1,
    },
    {
        "name": "Brushed Metal",
        "category": "fabric",
        "color": "#888888",
        "highlight": "#BBBBBB",
        "specular": "#999999",
        "shininess": 80,
        "metalness": 0.0,
        "roughness": 0.7,
        "emissive": "#444444",
        "env_tone": "neutral",
        "use_texture_maps": True,
        "albedo_map": "image_file",
        "albedo_map_path": "assets/brushed_metal.jpg",
        "normal_map": None,
        "roughness_map": None,
        "swatch_image": "assets/brushed_metal.jpg",
        "image_file": True,
        "tile_repeat": 1,
    },
    {
        "name": "Dark Wood",
        "category": "fabric",
        "color": "#3A1F0E",
        "highlight": "#5A3018",
        "specular": "#4A2814",
        "shininess": 80,
        "metalness": 0.0,
        "roughness": 0.7,
        "emissive": "#1A0F06",
        "env_tone": "neutral",
        "use_texture_maps": True,
        "albedo_map": "image_file",
        "albedo_map_path": "assets/dark_wood.jpg",
        "normal_map": None,
        "roughness_map": None,
        "swatch_image": "assets/dark_wood.jpg",
        "image_file": True,
        "tile_repeat": 1,
    },
]


def _generate_material_swatch(base_color: str, highlight_color: str, size: int = 80) -> QPixmap:
    """Create a photo-realistic metallic sphere swatch with specular highlight and shadow."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    base = QColor(base_color)
    highlight = QColor(highlight_color)

    cx, cy = size * 0.5, size * 0.52          # sphere centre (slightly low for shadow room)
    radius = size * 0.40

    # --- 1) Ambient-occlusion / ground shadow (soft dark ellipse below sphere) ---
    shadow_grad = QRadialGradient(cx, size * 0.88, size * 0.28)
    shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 80))
    shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setPen(QPen(Qt.NoPen))
    painter.setBrush(shadow_grad)
    painter.drawEllipse(int(cx - size * 0.28), int(size * 0.82), int(size * 0.56), int(size * 0.12))

    # --- 2) Base sphere body gradient (main gold/metal colour) ---
    body_grad = QRadialGradient(cx * 0.78, cy * 0.65, radius * 1.35)
    body_grad.setColorAt(0.00, highlight.lighter(160))        # bright hotspot
    body_grad.setColorAt(0.18, highlight.lighter(130))
    body_grad.setColorAt(0.35, base.lighter(125))
    body_grad.setColorAt(0.55, base)
    body_grad.setColorAt(0.72, base.darker(130))
    body_grad.setColorAt(0.88, base.darker(200))
    body_grad.setColorAt(1.00, base.darker(280))

    painter.setBrush(body_grad)
    painter.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))

    # --- 3) Warm reflection band (lower half, mimics environment reflection) ---
    refl_grad = QRadialGradient(cx, cy + radius * 0.45, radius * 0.7)
    warm = QColor(base.lighter(140))
    warm.setAlpha(90)
    refl_grad.setColorAt(0.0, warm)
    refl_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setBrush(refl_grad)
    painter.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))

    # --- 4) Specular highlight (small bright oval, upper-left) ---
    spec_cx = cx - radius * 0.22
    spec_cy = cy - radius * 0.32
    spec_r = radius * 0.38
    spec_grad = QRadialGradient(spec_cx, spec_cy, spec_r)
    spec_grad.setColorAt(0.0, QColor(255, 255, 255, 210))
    spec_grad.setColorAt(0.35, QColor(255, 255, 255, 90))
    spec_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.setBrush(spec_grad)
    painter.drawEllipse(int(spec_cx - spec_r), int(spec_cy - spec_r), int(spec_r * 2), int(spec_r * 2))

    # --- 5) Rim light (subtle bright edge on the right) ---
    rim_grad = QRadialGradient(cx + radius * 0.85, cy - radius * 0.1, radius * 0.35)
    rim_col = QColor(highlight.lighter(170))
    rim_col.setAlpha(55)
    rim_grad.setColorAt(0.0, rim_col)
    rim_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setBrush(rim_grad)
    painter.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))

    painter.end()
    return pixmap


# ---------------------------------------------------------------------------
# Material preset card (permanent, no delete)
# ---------------------------------------------------------------------------
class MaterialPresetCard(QFrame):
    """A compact card for a built-in material preset.  Supports drag so the
    material can be dropped onto the 3D viewer."""

    def __init__(self, preset: dict, parent=None):
        super().__init__(parent)
        self.preset = preset
        self.setObjectName("materialPresetCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.OpenHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(f"""
            QFrame#materialPresetCard {{
                background: {_ANNO_CARD_PENDING};
                {_ANNO_CARD_BORDER}
            }}
            QFrame#materialPresetCard:hover {{
                background: {_ANNO_CARD_HOVER};
                {_ANNO_CARD_BORDER_HOVER}
            }}
            QFrame#materialPresetCard QLabel {{
                background-color: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Sphere thumbnail or image-based swatch
        swatch_image_path = preset.get("swatch_image")
        if swatch_image_path:
            import sys as _sys
            if hasattr(_sys, '_MEIPASS'):
                _base = _sys._MEIPASS
            else:
                _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            full_swatch = os.path.join(_base, swatch_image_path)
            swatch = QPixmap(full_swatch)
            if swatch.isNull():
                swatch = _generate_material_swatch(preset["color"], preset["highlight"])
        else:
            swatch = _generate_material_swatch(preset["color"], preset["highlight"])
        self._swatch = swatch
        thumb = QLabel()
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setStyleSheet("background: transparent; border-radius: 6px;")
        thumb.setFixedHeight(70)
        thumb.setPixmap(swatch.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(thumb)

        # Name label
        name_lbl = QLabel(preset["name"])
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet(f"""
            color: {default_theme.text_primary};
            font-size: 10px;
            font-weight: bold;
            background: transparent;
        """)
        layout.addWidget(name_lbl)

    # --- Drag support ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if not hasattr(self, '_drag_start_pos'):
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return
        drag = QDrag(self)
        mime = QMimeData()
        payload_dict = {
            "color": self.preset["color"],
            "specular": self.preset["specular"],
            "shininess": self.preset["shininess"],
        }
        if "emissive" in self.preset:
            payload_dict["emissive"] = self.preset["emissive"]
        if "metalness" in self.preset:
            payload_dict["metalness"] = self.preset["metalness"]
        if "roughness" in self.preset:
            payload_dict["roughness"] = self.preset["roughness"]
        if "env_tone" in self.preset:
            payload_dict["env_tone"] = self.preset["env_tone"]
        # Texture map keys for PBR texture-mapped presets
        for map_key in ("use_texture_maps", "albedo_map", "albedo_map_path", "normal_map", "roughness_map", "category", "image_file", "tile_repeat"):
            if map_key in self.preset:
                payload_dict[map_key] = self.preset[map_key]
        payload = json.dumps(payload_dict)
        mime.setData("application/x-ectoform-material-preset", payload.encode('utf-8'))
        drag.setMimeData(mime)
        thumb = self._swatch.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        drag.setPixmap(thumb)
        drag.setHotSpot(QPoint(thumb.width() // 2, thumb.height() // 2))
        self.setCursor(Qt.ClosedHandCursor)
        drag.exec_(Qt.CopyAction)
        self.setCursor(Qt.OpenHandCursor)


# ---------------------------------------------------------------------------
# Texture card (user-uploaded, deletable)
# ---------------------------------------------------------------------------
class TextureCard(QFrame):
    """A compact card displaying a texture thumbnail with a delete button.
    Supports drag-start so the texture can be dropped onto the 3D viewer.
    """

    delete_requested = pyqtSignal(int)

    def __init__(self, index: int, pixmap: QPixmap, image_path: str, name: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.pixmap = pixmap
        self.image_path = image_path
        self.texture_name = name
        self.setObjectName("textureCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.OpenHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(f"""
            QFrame#textureCard {{
                background: {_ANNO_CARD_PENDING};
                {_ANNO_CARD_BORDER}
            }}
            QFrame#textureCard:hover {{
                background: {_ANNO_CARD_HOVER};
                {_ANNO_CARD_BORDER_HOVER}
            }}
            QFrame#textureCard QLabel {{
                background-color: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Header row: icon + name + close
        header = QHBoxLayout()
        header.setSpacing(2)
        icon_label = QLabel("🎨")
        icon_label.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 10px; background: transparent;")
        header.addWidget(icon_label)

        name_label = QLabel(name)
        name_label.setStyleSheet(f"""
            color: {default_theme.text_primary};
            font-weight: bold;
            font-size: 10px;
            background: transparent;
        """)
        name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header.addWidget(name_label)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("Remove texture")
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

        # Square thumbnail
        self.thumb_label = QLabel()
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet("background: transparent;")
        self.thumb_label.setFixedHeight(90)
        self.thumb_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._update_thumbnail()
        layout.addWidget(self.thumb_label)

    def _update_thumbnail(self):
        card_w = max(self.width() - 16, 80)
        scaled = self.pixmap.scaled(card_w, card_w, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.thumb_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_thumbnail()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if not hasattr(self, '_drag_start_pos'):
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self.image_path)
        mime.setData("application/x-ectoform-texture", self.image_path.encode('utf-8'))
        drag.setMimeData(mime)
        thumb = self.pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        drag.setPixmap(thumb)
        drag.setHotSpot(QPoint(thumb.width() // 2, thumb.height() // 2))
        self.setCursor(Qt.ClosedHandCursor)
        drag.exec_(Qt.CopyAction)
        self.setCursor(Qt.OpenHandCursor)

    def update_index(self, new_index: int):
        self.index = new_index


# ---------------------------------------------------------------------------
# Main texture panel
# ---------------------------------------------------------------------------
class TexturePanel(QWidget):
    """Right-side panel for uploading and managing textures for 3D model parts."""

    exit_texture_mode = pyqtSignal()
    texture_settings_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.textures = []  # list of {'path': str, 'name': str, 'pixmap': QPixmap}
        self.cards = []
        self.setMinimumWidth(280)
        self.setMaximumWidth(350)
        self.setStyleSheet(f"background-color: {default_theme.card_background};")
        self._init_ui()

    def _create_slider_row(self, label_text, min_val, max_val, default_val, suffix="", divisor=1):
        """Helper to create a labeled slider row. Returns (container, slider, value_label)."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        lbl = QLabel(label_text)
        lbl.setFixedWidth(65)
        lbl.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 10px; background: transparent;")
        h.addWidget(lbl)

        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(min_val)
        slider.setMaximum(max_val)
        slider.setValue(default_val)
        slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {default_theme.button_default_bg};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: #4DD0E1;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QSlider::sub-page:horizontal {{
                background: #00ACC1;
                border-radius: 2px;
            }}
        """)
        h.addWidget(slider, 1)

        if divisor > 1:
            display = f"{default_val / divisor:.1f}{suffix}"
        else:
            display = f"{default_val}{suffix}"
        val_lbl = QLabel(display)
        val_lbl.setFixedWidth(40)
        val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        val_lbl.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 10px; background: transparent;")
        h.addWidget(val_lbl)

        def _on_change(v):
            if divisor > 1:
                val_lbl.setText(f"{v / divisor:.1f}{suffix}")
            else:
                val_lbl.setText(f"{v}{suffix}")
            self._emit_settings()

        slider.valueChanged.connect(_on_change)
        return container, slider, val_lbl

    def sync_material_controls(self, preset_data: dict):
        """Sync the simple material sliders to match an applied preset.
        Switches between metal, fabric, and glass slider groups based on preset category."""
        category = preset_data.get("category", "metal")
        self._active_category = category

        # Show/hide slider groups
        is_metal = (category == "metal")
        is_glass = (category == "glass")
        is_fabric = (category == "fabric")
        is_image = preset_data.get("image_file", False)
        self._metal_sliders_container.setVisible(is_metal and not is_image)
        self._fabric_sliders_container.setVisible(is_fabric and not is_image)
        self._glass_sliders_container.setVisible(is_glass)
        self._image_sliders_container.setVisible(is_image)
        if is_image:
            self._active_category = "image"

        if is_metal:
            shine = int(preset_data.get("shine", self._slider_shine.value()))
            shadow_depth = int(preset_data.get("shadow_depth", self._slider_shadow.value()))

            self._slider_shine.blockSignals(True)
            self._slider_shadow.blockSignals(True)
            self._slider_shine.setValue(shine)
            self._slider_shadow.setValue(shadow_depth)
            self._slider_shine.blockSignals(False)
            self._slider_shadow.blockSignals(False)

            # Reset brightness to 50% (original) when a new preset is applied
            self._slider_brightness.blockSignals(True)
            self._slider_brightness.setValue(50)
            self._slider_brightness.blockSignals(False)
            if hasattr(self, '_lbl_brightness'):
                self._lbl_brightness.setText("50%")

            if hasattr(self, '_lbl_shine'):
                self._lbl_shine.setText(f"{shine}%")
            if hasattr(self, '_lbl_shadow'):
                self._lbl_shadow.setText(f"{shadow_depth}%")
        elif is_glass:
            # Glass: reset sliders to defaults
            self._slider_opacity.blockSignals(True)
            self._slider_clarity.blockSignals(True)
            self._slider_tint.blockSignals(True)
            self._slider_opacity.setValue(30)    # 30% opacity default
            self._slider_clarity.setValue(98)    # near-perfect clarity
            self._slider_tint.setValue(0)        # no tint
            self._slider_opacity.blockSignals(False)
            self._slider_clarity.blockSignals(False)
            self._slider_tint.blockSignals(False)
            if hasattr(self, '_lbl_opacity'):
                self._lbl_opacity.setText("30%")
            if hasattr(self, '_lbl_clarity'):
                self._lbl_clarity.setText("98%")
            if hasattr(self, '_lbl_tint'):
                self._lbl_tint.setText("0%")
        elif is_image:
            # Image preset: reset image-specific sliders
            self._slider_img_softness.blockSignals(True)
            self._slider_img_softness.setValue(50)
            self._slider_img_softness.blockSignals(False)
            if hasattr(self, '_lbl_img_softness'):
                self._lbl_img_softness.setText("50%")
            self._slider_img_brightness.blockSignals(True)
            self._slider_img_brightness.setValue(50)
            self._slider_img_brightness.blockSignals(False)
            if hasattr(self, '_lbl_img_brightness'):
                self._lbl_img_brightness.setText("50%")
            self._slider_img_contrast.blockSignals(True)
            self._slider_img_contrast.setValue(50)
            self._slider_img_contrast.blockSignals(False)
            if hasattr(self, '_lbl_img_contrast'):
                self._lbl_img_contrast.setText("50%")
        else:
            # Fabric: reset sliders to defaults
            self._slider_grain.blockSignals(True)
            self._slider_softness.blockSignals(True)
            self._slider_wear.blockSignals(True)
            self._slider_grain.setValue(50)
            self._slider_softness.setValue(50)
            self._slider_wear.setValue(0)
            self._slider_grain.blockSignals(False)
            self._slider_softness.blockSignals(False)
            self._slider_wear.blockSignals(False)
            if hasattr(self, '_lbl_grain'):
                self._lbl_grain.setText("50%")
            if hasattr(self, '_lbl_softness'):
                self._lbl_softness.setText("50%")
            if hasattr(self, '_lbl_wear'):
                self._lbl_wear.setText("0%")
            # Reset tile density
            if hasattr(self, '_slider_tile_density'):
                tile_default = int(preset_data.get("tile_repeat", 200))
                self._slider_tile_density.blockSignals(True)
                self._slider_tile_density.setValue(tile_default)
                self._slider_tile_density.blockSignals(False)
                if hasattr(self, '_lbl_tile_density'):
                    self._lbl_tile_density.setText(f"{tile_default}x")

    def _emit_settings(self):
        """Emit current slider values as a dict."""
        category = getattr(self, '_active_category', 'metal')
        settings = {"category": category}

        if category == "metal":
            settings["shine"] = self._slider_shine.value()
            settings["shadow_depth"] = self._slider_shadow.value()
            settings["brightness"] = self._slider_brightness.value() if hasattr(self, '_slider_brightness') else 50
        elif category == "glass":
            settings["opacity"] = self._slider_opacity.value()
            settings["clarity"] = self._slider_clarity.value()
            settings["tint"] = self._slider_tint.value()
        elif category == "image":
            settings["softness"] = self._slider_img_softness.value()
            settings["img_brightness"] = self._slider_img_brightness.value()
            settings["img_contrast"] = self._slider_img_contrast.value()
        else:
            settings["grain"] = self._slider_grain.value()
            settings["softness"] = self._slider_softness.value()
            settings["wear"] = self._slider_wear.value()
            if hasattr(self, '_slider_tile_density'):
                settings["tile_density"] = self._slider_tile_density.value()

        if hasattr(self, '_slider_smoothness'):
            settings["smoothness"] = self._slider_smoothness.value() / 100.0
        if hasattr(self, '_slider_crease_angle'):
            settings["crease_angle"] = self._slider_crease_angle.value()
        self.texture_settings_changed.emit(settings)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header banner (teal gradient)
        banner = QFrame()
        banner.setObjectName("textureModeBanner")
        banner.setAttribute(Qt.WA_StyledBackground, True)
        banner.setStyleSheet(f"""
            QFrame#textureModeBanner {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {_TEX_TEAL_TOP},
                    stop:0.12 {_TEX_TEAL_UPPER},
                    stop:0.38 {_TEX_TEAL_MID},
                    stop:0.72 {_TEX_TEAL_DEEP},
                    stop:1 {_TEX_TEAL_BOTTOM});
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
        tex_icon = QLabel("🎨")
        tex_icon.setFixedSize(22, 22)
        tex_icon.setAlignment(Qt.AlignCenter)
        tex_icon.setStyleSheet("background: transparent; border: none; font-size: 16px;")
        title_row.addWidget(tex_icon)
        title = QLabel("Textures")
        title.setFont(make_font(size=12, bold=True))
        title.setStyleSheet("color: #FFFFFF; background: transparent; border: none;")
        title_row.addWidget(title)
        title_row.addStretch()

        exit_btn = QPushButton("✕")
        exit_btn.setObjectName("exitTextureBtn")
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setFixedSize(28, 28)
        exit_btn.setStyleSheet("""
            QPushButton#exitTextureBtn {
                background-color: transparent;
                border: none;
                color: rgba(255, 255, 255, 0.92);
                font-size: 16px;
                font-weight: bold;
                padding: 0; min-width: 28px; min-height: 28px;
            }
            QPushButton#exitTextureBtn:hover {
                color: #FFFFFF;
                background-color: rgba(0, 0, 0, 0.18);
                border-radius: 14px;
            }
        """)
        exit_btn.clicked.connect(self.exit_texture_mode.emit)
        title_row.addWidget(exit_btn)
        banner_layout.addLayout(title_row)

        divider = QFrame()
        divider.setObjectName("textureModeDivider")
        divider.setFrameShape(QFrame.NoFrame)
        divider.setMinimumHeight(3)
        divider.setMaximumHeight(3)
        divider.setStyleSheet("""
            QFrame#textureModeDivider {
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

        self.instruction = QLabel(
            "Upload textures and drag them onto model parts to apply."
        )
        self.instruction.setWordWrap(True)
        self.instruction.setStyleSheet(
            "color: rgba(255, 255, 255, 0.95); font-size: 11px; background: transparent; border: none;"
        )
        banner_layout.addWidget(self.instruction)

        layout.addWidget(banner)

        # ---- Materials section ----
        mat_label = QLabel("Materials")
        mat_label.setFont(make_font(size=11, bold=True))
        mat_label.setStyleSheet(f"color: {default_theme.text_primary}; background: transparent;")
        layout.addWidget(mat_label)

        mat_grid = QGridLayout()
        mat_grid.setContentsMargins(0, 0, 0, 0)
        mat_grid.setSpacing(6)
        mat_grid.setColumnStretch(0, 1)
        mat_grid.setColumnStretch(1, 1)
        for i, preset in enumerate(MATERIAL_PRESETS):
            card = MaterialPresetCard(preset)
            mat_grid.addWidget(card, i // GRID_COLUMNS, i % GRID_COLUMNS)
        layout.addLayout(mat_grid)

        # ---- Upload button ----
        upload_label = QLabel("Custom Textures")
        upload_label.setFont(make_font(size=11, bold=True))
        upload_label.setStyleSheet(f"color: {default_theme.text_primary}; background: transparent;")
        layout.addWidget(upload_label)

        self.upload_btn = QPushButton("📁  Upload Texture")
        self.upload_btn.setObjectName("uploadTextureBtn")
        self.upload_btn.setCursor(Qt.PointingHandCursor)
        self.upload_btn.setStyleSheet(f"""
            QPushButton#uploadTextureBtn {{
                background-color: #D1FAE5;
                color: #059669;
                border: 1px solid #A7F3D0;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton#uploadTextureBtn:hover {{
                background-color: #6EE7B7;
            }}
        """)
        self.upload_btn.clicked.connect(self._on_upload)
        layout.addWidget(self.upload_btn)

        # Scroll area with grid for uploaded textures
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
        self.clear_btn.setObjectName("clearTexturesBtn")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setStyleSheet(f"""
            QPushButton#clearTexturesBtn {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_secondary};
                border: 1px solid {default_theme.button_default_border};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
            }}
            QPushButton#clearTexturesBtn:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """)
        self.clear_btn.clicked.connect(self._on_clear_all)
        self.clear_btn.hide()
        layout.addWidget(self.clear_btn)

        # ---- Texture Settings (sliders) ----
        settings_label = QLabel("Texture Settings")
        settings_label.setFont(make_font(size=11, bold=True))
        settings_label.setStyleSheet(f"color: {default_theme.text_primary}; background: transparent;")
        layout.addWidget(settings_label)

        # --- Metal sliders container ---
        self._metal_sliders_container = QWidget()
        self._metal_sliders_container.setStyleSheet("background: transparent;")
        metal_layout = QVBoxLayout(self._metal_sliders_container)
        metal_layout.setContentsMargins(0, 0, 0, 0)
        metal_layout.setSpacing(4)

        row, self._slider_shine, self._lbl_shine = self._create_slider_row("Shine", 0, 100, 70, "%")
        metal_layout.addWidget(row)
        row, self._slider_shadow, self._lbl_shadow = self._create_slider_row("Shadow", 0, 100, 50, "%")
        metal_layout.addWidget(row)
        row, self._slider_brightness, self._lbl_brightness = self._create_slider_row("Brightness", 0, 100, 50, "%")
        metal_layout.addWidget(row)

        layout.addWidget(self._metal_sliders_container)

        # --- Fabric sliders container ---
        self._fabric_sliders_container = QWidget()
        self._fabric_sliders_container.setStyleSheet("background: transparent;")
        fabric_layout = QVBoxLayout(self._fabric_sliders_container)
        fabric_layout.setContentsMargins(0, 0, 0, 0)
        fabric_layout.setSpacing(4)

        row, self._slider_grain, self._lbl_grain = self._create_slider_row("Grain", 0, 100, 50, "%")
        fabric_layout.addWidget(row)
        row, self._slider_softness, self._lbl_softness = self._create_slider_row("Softness", 0, 100, 50, "%")
        fabric_layout.addWidget(row)
        row, self._slider_wear, self._lbl_wear = self._create_slider_row("Wear", 0, 100, 0, "%")
        fabric_layout.addWidget(row)
        row, self._slider_tile_density, self._lbl_tile_density = self._create_slider_row("Tile Density", 1, 500, 200, "x")
        fabric_layout.addWidget(row)

        self._fabric_sliders_container.hide()  # Default to metal sliders
        layout.addWidget(self._fabric_sliders_container)

        # --- Image sliders container (for image-based presets) ---
        self._image_sliders_container = QWidget()
        self._image_sliders_container.setStyleSheet("background: transparent;")
        image_layout = QVBoxLayout(self._image_sliders_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(4)

        row, self._slider_img_softness, self._lbl_img_softness = self._create_slider_row("Softness", 0, 100, 50, "%")
        image_layout.addWidget(row)
        row, self._slider_img_brightness, self._lbl_img_brightness = self._create_slider_row("Brightness", 0, 100, 50, "%")
        image_layout.addWidget(row)
        row, self._slider_img_contrast, self._lbl_img_contrast = self._create_slider_row("Contrast", 0, 100, 50, "%")
        image_layout.addWidget(row)

        self._image_sliders_container.hide()
        layout.addWidget(self._image_sliders_container)

        # --- Glass sliders container ---
        self._glass_sliders_container = QWidget()
        self._glass_sliders_container.setStyleSheet("background: transparent;")
        glass_layout = QVBoxLayout(self._glass_sliders_container)
        glass_layout.setContentsMargins(0, 0, 0, 0)
        glass_layout.setSpacing(4)

        row, self._slider_opacity, self._lbl_opacity = self._create_slider_row("Opacity", 0, 100, 30, "%")
        glass_layout.addWidget(row)
        row, self._slider_clarity, self._lbl_clarity = self._create_slider_row("Clarity", 0, 100, 98, "%")
        glass_layout.addWidget(row)
        row, self._slider_tint, self._lbl_tint = self._create_slider_row("Tint", 0, 100, 0, "%")
        glass_layout.addWidget(row)

        self._glass_sliders_container.hide()  # Default hidden
        layout.addWidget(self._glass_sliders_container)

        self._active_category = "metal"

        # ---- Shading Settings ----
        shading_label = QLabel("Shading")
        shading_label.setFont(make_font(size=11, bold=True))
        shading_label.setStyleSheet(f"color: {default_theme.text_primary}; background: transparent;")
        layout.addWidget(shading_label)

        # Smoothness: 0% = flat shading, 100% = smooth shading
        row, self._slider_smoothness, _ = self._create_slider_row("Smoothness", 0, 100, 100, "%")
        layout.addWidget(row)

        # Crease Angle: 0-180 degrees (edges sharper than this stay hard)
        row, self._slider_crease_angle, _ = self._create_slider_row("Crease Angle", 0, 180, 30, u"\u00b0")
        layout.addWidget(row)

    def _rebuild_grid(self):
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)
        for i, card in enumerate(self.cards):
            row = i // GRID_COLUMNS
            col = i % GRID_COLUMNS
            self.grid_layout.addWidget(card, row, col)

    def _on_upload(self):
        """Open file dialog to add texture images."""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Texture Images",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tga *.tiff *.heic *.heif);;All Files (*)"
        )
        if not paths:
            return
        for path in paths:
            self.add_texture(path)

    def add_texture(self, image_path: str):
        """Add a texture image to the panel."""
        try:
            from core.image_utils import ensure_image_readable
            readable = ensure_image_readable(image_path)
            if readable is None:
                logger.warning(f"add_texture: Could not read {image_path}")
                return
            image_path = readable
        except ImportError:
            pass

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            logger.warning(f"add_texture: Could not load {image_path}")
            return

        name = os.path.basename(image_path)
        self.textures.append({'path': image_path, 'name': name, 'pixmap': pixmap})
        idx = len(self.textures) - 1

        card = TextureCard(idx, pixmap, image_path, name)
        card.delete_requested.connect(self._on_delete)
        self.cards.append(card)

        row = idx // GRID_COLUMNS
        col = idx % GRID_COLUMNS
        self.grid_layout.addWidget(card, row, col)

        self.clear_btn.setVisible(len(self.textures) > 0)

    def _on_delete(self, index: int):
        if 0 <= index < len(self.cards):
            card = self.cards[index]
            self.grid_layout.removeWidget(card)
            card.deleteLater()
            self.cards.pop(index)
            self.textures.pop(index)
            for i, c in enumerate(self.cards):
                c.update_index(i)
            self._rebuild_grid()
            self.clear_btn.setVisible(len(self.textures) > 0)

    def _on_clear_all(self):
        for card in self.cards:
            self.grid_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        self.textures.clear()
        self.clear_btn.hide()

    def clear_all(self):
        self._on_clear_all()
