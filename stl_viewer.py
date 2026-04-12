"""
Main ECTOFORM Window with minimalistic UI and multi-tab support.
"""
import os
import sys
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Any
from pathlib import Path
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFileDialog,
    QMessageBox, QSplitter, QFrame, QApplication, QStackedWidget, QTabBar,
    QPushButton
)
from PyQt5.QtCore import Qt, QEvent, QTimer

# Force PyInstaller to bundle pygfx and deps (imported lazily in viewer_widget_pygfx._init_pygfx)
try:
    import pygfx  # noqa: F401
    import wgpu  # noqa: F401
    import trimesh  # noqa: F401
    import rendercanvas  # noqa: F401
except ImportError:
    pass

# Always use pygfx (WebGPU) - no env vars. Fixes Windows black screen, works in exe.
# Fall back to PyVista only if pygfx import fails (e.g. missing wgpu/rendercanvas).
USE_PYGFX = False
USE_OFFSCREEN = False
try:
    from viewer_widget_pygfx import STLViewerWidget
    USE_PYGFX = True
except Exception as e:
    print(f"Warning: Could not import pygfx viewer: {e}, falling back to PyVista", file=sys.stderr)
    try:
        from viewer_widget import STLViewerWidget
    except Exception as e2:
        print(f"Warning: Could not import QtInteractor viewer, using offscreen fallback: {e2}", file=sys.stderr)
        from viewer_widget_offscreen import STLViewerWidgetOffscreen as STLViewerWidget
        USE_OFFSCREEN = True

from ui.sidebar_panel import SidebarPanel
from ui.toolbar import ViewControlsToolbar
from ui.ruler_toolbar import RulerToolbar
from ui.annotation_panel import AnnotationPanel
from ui.arrow_panel import ArrowPanel
from ui.parts_panel import PartsPanel
from ui.styles import get_global_stylesheet, default_theme
from core.mesh_calculator import MeshCalculator
from ui.screenshot_panel import ScreenshotPanel
from ui.texture_panel import TexturePanel
from ui.components import confirm_dialog
from ui.technical_overview import TechnicalOverviewWidget
from ui.technical_sidebar import TechnicalSidebar
from ui.scale_canvas import ScaleCanvas
from ui.scale_sidebar import ScaleSidebar
from ui.help_panel import HelpWidget

logger = logging.getLogger(__name__)

# QTabBar + QSS can still clip the first glyph on macOS; leading en spaces reserve real width.
_TAB_CAPTION_LEAD = "\u2002\u2002\u2002"


def _ecto_tab_caption(visible_name: str) -> str:
    """Tab strip label with left inset so the first character is not clipped."""
    if not visible_name or visible_name == "+":
        return visible_name
    return _TAB_CAPTION_LEAD + visible_name


def safe_flush(stream):
    """Safely flush a stream, handling None (common in PyInstaller Windows builds)."""
    if stream is not None:
        try:
            stream.flush()
        except (AttributeError, OSError):
            pass  # Stream may not support flush or may be closed


# Print to stderr for immediate visibility
def debug_print(msg):
    print(f"[DEBUG] {msg}", file=sys.stderr)
    safe_flush(sys.stderr)


# ======================== Tab State ========================

@dataclass
class TabState:
    """Holds all per-tab state: viewer, annotations, arrows, sidebar cache, mode flags."""
    file_path: Optional[str] = None
    viewer_widget: Any = None  # STLViewerWidget instance
    annotation_panel: Any = None  # AnnotationPanel instance
    arrow_panel: Any = None  # ArrowPanel instance
    parts_panel: Any = None  # PartsPanel instance
    sidebar_data: Optional[dict] = None  # cached mesh_data dict for sidebar
    mesh: Any = None  # current_mesh reference
    ruler_active: bool = False
    annotation_mode_active: bool = False
    arrow_mode_active: bool = False
    parts_mode_active: bool = False
    screenshot_mode_active: bool = False
    texture_mode_active: bool = False
    draw_mode_active: bool = False
    annotations_exported: bool = False
    ecto_temp_dir: Optional[str] = None
    filename: Optional[str] = None  # display name for tab
    loaded_via_conversion: bool = False  # True when file was loaded via Convert File flow


# ======================== Main Window ========================

class STLViewerWindow(QMainWindow):
    """Main window for STL file viewer application with multi-tab support."""
    
    def __init__(self):
        debug_print("STLViewerWindow: Initializing...")
        logger.info("STLViewerWindow: Initializing...")
        super().__init__()
        debug_print("STLViewerWindow: Parent initialized")
        logger.info("STLViewerWindow: Parent initialized")
        
        # Tab management
        self.tabs: List[TabState] = []
        self.current_tab_index: int = -1
        
        self.init_ui()
        debug_print("STLViewerWindow: Initialization complete")
        logger.info("STLViewerWindow: Initialization complete")
    
    # ---- helpers to access current tab ----
    
    @property
    def _current_tab(self) -> Optional[TabState]:
        if 0 <= self.current_tab_index < len(self.tabs):
            return self.tabs[self.current_tab_index]
        return None

    @property
    def viewer_widget(self):
        tab = self._current_tab
        return tab.viewer_widget if tab else None

    @property
    def annotation_panel(self):
        tab = self._current_tab
        return tab.annotation_panel if tab else None

    @property
    def _annotations_exported(self):
        tab = self._current_tab
        return tab.annotations_exported if tab else False

    @_annotations_exported.setter
    def _annotations_exported(self, value):
        tab = self._current_tab
        if tab:
            tab.annotations_exported = value

    def init_ui(self):
        """Initialize the user interface."""
        logger.info("init_ui: Starting UI initialization...")
        
        logger.info("init_ui: Setting window title and size...")
        self.setWindowTitle("ECTOFORM")
        if sys.platform == 'win32':
            min_w, min_h = 1600, 1000
        else:
            min_w, min_h = 1400, 900
        self.setMinimumSize(min_w, min_h)
        from ui.annotation_icon import get_app_window_icon
        icon = get_app_window_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.resize(min_w, min_h)
        
        # Position window on left side of screen (align with toolbar/content)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.left(), screen.top() + max(0, (screen.height() - min_h) // 2))
        
        logger.info("init_ui: Creating central widget...")
        central_widget = QWidget()
        central_widget.setStyleSheet(f"background-color: {default_theme.background};")
        self.setCentralWidget(central_widget)
        
        logger.info("init_ui: Creating main layout...")
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        
        # ---- Mode Switcher Bar ----
        mode_bar = QWidget()
        mode_bar.setFixedHeight(36)
        mode_bar.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {default_theme.gradient_start},
                    stop:0.5 {default_theme.gradient_mid},
                    stop:1 {default_theme.gradient_end});
                border-bottom: 1px solid {default_theme.border_standard};
            }}
        """)
        mode_bar_layout = QHBoxLayout(mode_bar)
        mode_bar_layout.setContentsMargins(12, 4, 12, 4)
        mode_bar_layout.setSpacing(4)
        
        self._mode_3d_btn = QPushButton("🔲 3D Viewer")
        self._mode_tech_btn = QPushButton("📋 Technical Overview")
        self._mode_scale_btn = QPushButton("📐 Drawing Scale")
        self._mode_help_btn = QPushButton("❓ Help")
        for btn in (self._mode_3d_btn, self._mode_tech_btn, self._mode_scale_btn, self._mode_help_btn):
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setAttribute(Qt.WA_StyledBackground, True)
        self._mode_3d_btn.setChecked(True)
        self._current_mode = "3d"
        
        self._update_mode_btn_styles()
        self._mode_3d_btn.clicked.connect(lambda: self._switch_mode("3d"))
        self._mode_tech_btn.clicked.connect(lambda: self._switch_mode("technical"))
        self._mode_scale_btn.clicked.connect(lambda: self._switch_mode("scale"))
        self._mode_help_btn.clicked.connect(lambda: self._switch_mode("help"))
        
        mode_bar_layout.addWidget(self._mode_3d_btn)
        mode_bar_layout.addWidget(self._mode_tech_btn)
        mode_bar_layout.addWidget(self._mode_scale_btn)
        mode_bar_layout.addStretch()
        mode_bar_layout.addWidget(self._mode_help_btn)
        root_layout.addWidget(mode_bar)
        
        # ---- Workspace stack (3D vs Technical) ----
        self._workspace_stack = QStackedWidget()
        root_layout.addWidget(self._workspace_stack, 1)
        
        # ==== 3D Viewer Workspace ====
        viewer_workspace = QWidget()
        main_layout = QHBoxLayout(viewer_workspace)
        main_layout.setContentsMargins(0, 10, 10, 10)
        main_layout.setSpacing(10)
        
        logger.info("init_ui: Creating splitter...")
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(f"background-color: {default_theme.background};")
        splitter.setOpaqueResize(False)
        main_layout.addWidget(splitter)
        
        logger.info("init_ui: Creating sidebar panel...")
        self.sidebar_panel = SidebarPanel()
        self.sidebar_panel.upload_btn.clicked.connect(self.upload_stl_file)
        self.sidebar_panel.export_scaled_stl.connect(self.export_scaled_stl)
        self.sidebar_panel.annotations_exported.connect(self._on_annotations_exported)
        
        splitter.addWidget(self.sidebar_panel)
        logger.info("init_ui: Sidebar panel created")
        
        # Create right panel container (tab bar + toolbar + viewer stack)
        right_container = QWidget()
        self.right_layout = QVBoxLayout(right_container)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(0)
        
        # ---- Tab Bar (left-aligned so "Untitled" starts at left edge) ----
        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("ectoTabBar")
        self.tab_bar.setAttribute(Qt.WA_StyledBackground, True)
        self.tab_bar.setMinimumHeight(30)
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setMovable(False)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setElideMode(Qt.ElideNone)
        self.tab_bar.tabCloseRequested.connect(self._on_tab_close_requested)
        # Add "+" button as the last tab (before connecting currentChanged so signal doesn't fire before _plus_tab_index exists)
        self._plus_tab_index = self.tab_bar.addTab("+")
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.tab_bar.setTabButton(self._plus_tab_index, QTabBar.RightSide, None)
        self.tab_bar.setTabButton(self._plus_tab_index, QTabBar.LeftSide, None)
        tab_bar_container = QWidget()
        tab_bar_layout = QHBoxLayout(tab_bar_container)
        # Left inset so first tab label (bold) is not flush against the splitter edge / clipped
        tab_bar_layout.setContentsMargins(14, 0, 0, 0)
        tab_bar_layout.setSpacing(0)
        tab_bar_layout.addWidget(self.tab_bar, 0, Qt.AlignLeft)
        tab_bar_layout.addStretch(1)
        self.right_layout.addWidget(tab_bar_container)
        
        # Create toolbar
        logger.info("init_ui: Creating toolbar...")
        self.toolbar = ViewControlsToolbar()
        self._connect_toolbar_signals()
        self.right_layout.addWidget(self.toolbar)
        logger.info("init_ui: Toolbar created")
        
        # Create ruler toolbar (hidden by default)
        logger.info("init_ui: Creating ruler toolbar...")
        self.ruler_toolbar = RulerToolbar()
        self.ruler_toolbar.hide()
        self._connect_ruler_toolbar_signals()
        self.right_layout.addWidget(self.ruler_toolbar)
        logger.info("init_ui: Ruler toolbar created")
        
        # ---- Stacked widgets for viewers and annotation/screenshot/arrow/texture panels ----
        self.viewer_stack = QStackedWidget()
        self.annotation_stack = QStackedWidget()
        self.screenshot_stack = QStackedWidget()
        self.arrow_stack = QStackedWidget()
        self.parts_stack = QStackedWidget()
        self.texture_stack = QStackedWidget()
        
        # Shared screenshot panel (one per window, not per tab)
        self.screenshot_panel = ScreenshotPanel()
        self.screenshot_panel.exit_screenshot_mode.connect(self._exit_screenshot_mode)
        self.screenshot_stack.addWidget(self.screenshot_panel)
        
        # Shared texture panel (one per window, not per tab)
        self.texture_panel = TexturePanel()
        self.texture_panel.exit_texture_mode.connect(self._exit_texture_mode_from_panel)
        self.texture_panel.texture_settings_changed.connect(self._on_texture_settings_changed)
        self.texture_stack.addWidget(self.texture_panel)
        
        # Single right panel: only annotation OR screenshot OR arrow OR parts OR texture visible at a time
        self.right_panel_stack = QStackedWidget()
        self._right_panel_placeholder = QWidget()
        self._right_panel_placeholder.setFixedWidth(0)  # No space when neither mode active
        self.right_panel_stack.addWidget(self._right_panel_placeholder)
        self.right_panel_stack.addWidget(self.annotation_stack)
        self.right_panel_stack.addWidget(self.screenshot_stack)
        self.right_panel_stack.addWidget(self.arrow_stack)
        self.right_panel_stack.addWidget(self.parts_stack)
        self.right_panel_stack.addWidget(self.texture_stack)
        self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
        self.right_panel_stack.hide()  # No blank space when neither mode active
        
        viewer_h_layout = QHBoxLayout()
        viewer_h_layout.setContentsMargins(0, 0, 0, 0)
        viewer_h_layout.setSpacing(0)
        viewer_h_layout.addWidget(self.viewer_stack, 1)
        viewer_h_layout.addWidget(self.right_panel_stack)
        
        viewer_container = QWidget()
        viewer_container.setLayout(viewer_h_layout)
        self.right_layout.addWidget(viewer_container, 1)
        
        # Add right container to splitter
        splitter.addWidget(right_container)
        
        logger.info("init_ui: Configuring splitter...")
        splitter.setSizes([200, 1000])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        
        self._workspace_stack.addWidget(viewer_workspace)
        
        # ==== Technical Overview Workspace ====
        tech_workspace = QWidget()
        tech_layout = QHBoxLayout(tech_workspace)
        tech_layout.setContentsMargins(0, 10, 10, 10)
        tech_layout.setSpacing(10)
        
        self.technical_sidebar = TechnicalSidebar()
        self.technical_sidebar.upload_requested.connect(self._tech_upload_image)
        self.technical_sidebar.annotate_toggled.connect(self._tech_toggle_annotation)
        self.technical_sidebar.export_requested.connect(self._tech_export_ecto)
        self.technical_sidebar.export_pdf_requested.connect(self._tech_export_pdf)
        self.technical_sidebar.reset_requested.connect(self._tech_reset)
        self._tech_ecto_exported = False
        tech_layout.addWidget(self.technical_sidebar)
        
        self.technical_overview = TechnicalOverviewWidget()
        tech_layout.addWidget(self.technical_overview, 1)
        
        self._workspace_stack.addWidget(tech_workspace)
        
        # ==== Drawing Scale Workspace ====
        scale_workspace = QWidget()
        scale_layout = QHBoxLayout(scale_workspace)
        scale_layout.setContentsMargins(0, 10, 10, 10)
        scale_layout.setSpacing(10)
        
        self.scale_sidebar = ScaleSidebar()
        self.scale_sidebar.upload_requested.connect(self._scale_upload)
        self.scale_sidebar.unit_changed.connect(self._scale_unit_changed)
        self.scale_sidebar.scale_changed.connect(self._scale_ratio_changed)
        self.scale_sidebar.ruler_toggled.connect(self._scale_ruler_toggled)
        self.scale_sidebar.export_requested.connect(self._scale_export)
        self.scale_sidebar.add_ref_requested.connect(self._scale_add_ref)
        self.scale_sidebar.reset_requested.connect(self._scale_reset)
        scale_layout.addWidget(self.scale_sidebar)
        
        self.scale_canvas = ScaleCanvas()
        self.scale_canvas.click_to_upload.connect(self._scale_upload)
        scale_layout.addWidget(self.scale_canvas, 1)
        
        self._workspace_stack.addWidget(scale_workspace)
        
        # ==== Help Workspace ====
        self.help_widget = HelpWidget()
        self._workspace_stack.addWidget(self.help_widget)
        self._workspace_stack.setCurrentIndex(0)  # Start with 3D Viewer
        
        logger.info("init_ui: Applying styling...")
        self.apply_styling()
        
        # Create initial empty tab
        self._create_new_tab()
        
        logger.info("init_ui: UI initialization complete")
    
    # ======================== Mode Switching ========================
    
    def _update_mode_btn_styles(self):
        """Update mode switcher button styles based on current mode."""
        # Selected: glossy / skeuomorphic — top shine + vertical depth + beveled edges (Qt has no inset shadow)
        active_style = f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #9aa3b8,
                    stop:0.1 #7d8598,
                    stop:0.28 #636877,
                    stop:0.55 #565c6e,
                    stop:1 #3e424f);
                color: {default_theme.text_white};
                border-top: 1px solid #b8c0d4;
                border-left: 1px solid #9aa2b4;
                border-right: 1px solid #3a3f4c;
                border-bottom: 1px solid #252830;
                border-radius: 5px;
                padding: 5px 14px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #a8b0c4,
                    stop:0.1 #8a92a6,
                    stop:0.28 #6f7688,
                    stop:0.55 #5f6576,
                    stop:1 #484c59);
                border-top: 1px solid #c8d0e0;
                border-left: 1px solid #a8b0c0;
                border-right: 1px solid #424650;
                border-bottom: 1px solid #2a2e38;
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5a6172,
                    stop:0.45 #4d5362,
                    stop:1 #3a3e4a);
                border-top: 1px solid #3a3f4c;
                border-left: 1px solid #353942;
                border-right: 1px solid #5a5f6e;
                border-bottom: 1px solid #6a7080;
            }}
        """
        inactive_style = f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2e323c,
                    stop:1 #1e2128);
                border: 1px solid {default_theme.border_light};
                border-top: 1px solid #454a58;
                border-radius: 5px;
                padding: 5px 14px;
                font-size: 11px;
                color: {default_theme.text_secondary};
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3a3e4a,
                    stop:1 #2a2e36);
                color: {default_theme.text_white};
                border: 1px solid {default_theme.border_medium};
            }}
        """
        self._mode_3d_btn.setStyleSheet(active_style if self._current_mode == "3d" else inactive_style)
        self._mode_tech_btn.setStyleSheet(active_style if self._current_mode == "technical" else inactive_style)
        self._mode_scale_btn.setStyleSheet(active_style if self._current_mode == "scale" else inactive_style)
        self._mode_help_btn.setStyleSheet(active_style if self._current_mode == "help" else inactive_style)
    
    def _switch_mode(self, mode: str):
        """Switch between '3d', 'technical', 'scale', and 'help' workspace modes."""
        if mode == self._current_mode:
            return
        self._current_mode = mode
        self._mode_3d_btn.setChecked(mode == "3d")
        self._mode_tech_btn.setChecked(mode == "technical")
        self._mode_scale_btn.setChecked(mode == "scale")
        self._mode_help_btn.setChecked(mode == "help")
        self._update_mode_btn_styles()
        
        if mode == "3d":
            self._workspace_stack.setCurrentIndex(0)
            self.setWindowTitle(f"ECTOFORM - {self._current_tab.filename}" if self._current_tab and self._current_tab.filename else "ECTOFORM")
        elif mode == "technical":
            self._workspace_stack.setCurrentIndex(1)
            self.setWindowTitle("ECTOFORM - Technical Overview")
        elif mode == "scale":
            self._workspace_stack.setCurrentIndex(2)
            self.setWindowTitle("ECTOFORM - Drawing Scale")
        elif mode == "help":
            self._workspace_stack.setCurrentIndex(3)
            self.setWindowTitle("ECTOFORM - Help")
        
        logger.info(f"_switch_mode: Switched to {mode} mode")
    
    def _tech_upload_image(self):
        """Handle upload request from technical sidebar — supports images, PDFs, and .ecto files."""
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image, PDF, or .ecto File", "",
            "Supported Files (*.png *.jpg *.jpeg *.bmp *.pdf *.ecto);;Images & PDFs (*.png *.jpg *.jpeg *.bmp *.pdf);;ECTO Files (*.ecto);;All Files (*)"
        )
        if not path:
            return
        if path.lower().endswith('.ecto'):
            self._load_technical_ecto(path)
        else:
            self.technical_overview.load_image_from_path(path)
    
    def _tech_toggle_annotation(self, enabled: bool):
        """Toggle annotation mode on the technical overview."""
        if enabled:
            self.technical_overview.enter_annotation_mode()
        else:
            self.technical_overview.exit_annotation_mode()

    def _tech_export_ecto(self):
        """Export technical overview as a passcode-protected .ecto file."""
        doc_path = self.technical_overview.get_document_path()
        if not doc_path:
            QMessageBox.warning(self, "No Document", "Please upload an image or PDF first.")
            return

        # Ask for passcode
        from ui.passcode_dialog import PasscodeDialog
        dlg = PasscodeDialog(mode='set', parent=self)
        if dlg.exec() != PasscodeDialog.Accepted:
            return
        passcode_hash = dlg.get_passcode_hash()

        # Pick save location
        default_name = Path(doc_path).stem + '.ecto'
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Export Technical Overview .ecto", default_name,
            "ECTO Files (*.ecto);;All Files (*)"
        )
        if not save_path:
            return

        from core.ecto_format import EctoFormat
        annotations = self.technical_overview.get_annotations_data()
        metadata = self.technical_sidebar.get_metadata()

        success, msg = EctoFormat.export_technical(
            document_path=doc_path,
            annotations=annotations,
            metadata=metadata,
            output_path=save_path,
            passcode_hash=passcode_hash,
        )
        if success:
            self._tech_ecto_exported = True
            QMessageBox.information(self, "Export Successful",
                                    f"Technical overview exported to:\n{msg}")
        else:
            QMessageBox.critical(self, "Export Failed", f"Error: {msg}")

    def _tech_export_pdf(self):
        """Export technical overview as a PDF report with annotated image and table."""
        pixmap = self.technical_overview.canvas._pixmap
        if pixmap is None or pixmap.isNull():
            QMessageBox.warning(self, "No Document", "Please upload an image or PDF first.")
            return

        metadata = self.technical_sidebar.get_metadata()
        default_name = "Technical_Overview_Report.pdf"
        doc_path = self.technical_overview.get_document_path()
        if doc_path:
            default_name = Path(doc_path).stem + "_report.pdf"

        save_path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Report", default_name,
            "PDF Files (*.pdf);;All Files (*)"
        )
        if not save_path:
            return

        from core.technical_pdf_exporter import TechnicalPDFExporter
        annotations = self.technical_overview.get_annotations()
        success, msg = TechnicalPDFExporter.export(
            document_pixmap=pixmap,
            annotations=annotations,
            metadata=metadata,
            output_path=save_path,
        )
        if success:
            QMessageBox.information(self, "PDF Exported", f"Report saved to:\n{msg}")
        else:
            QMessageBox.critical(self, "Export Failed", f"Error: {msg}")

    def _tech_reset(self):
        """Reset the technical overview workspace with unsaved-changes warning."""
        has_content = (
            self.technical_overview.get_annotations()
            or self.technical_overview.get_document_path()
        )

        if has_content and not self._tech_ecto_exported:
            reply = QMessageBox.warning(
                self, "Unsaved Changes",
                "You have not exported this workspace as an .ecto file.\n\n"
                "All annotations, metadata, and the loaded document will be lost.\n\n"
                "Do you want to reset anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # Reset everything
        self.technical_overview.clear_all()
        self.technical_overview.canvas.clear_image()
        self.technical_sidebar.reset()
        self._tech_ecto_exported = False

    # ======================== Drawing Scale Mode ========================

    def _scale_upload(self):
        """Upload a drawing file for scale calibration."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Drawing", "",
            "Drawings (*.png *.jpg *.jpeg *.bmp *.pdf);;All Files (*)"
        )
        if path:
            self.scale_canvas.load_file(path)

    def _scale_unit_changed(self, unit: str):
        self.scale_canvas.set_unit(unit)

    def _scale_ratio_changed(self, ratio: float):
        self.scale_canvas.set_scale_ratio(ratio)

    def _scale_ruler_toggled(self, enabled: bool):
        self.scale_canvas.set_ruler_mode(enabled)

    def _scale_reset(self):
        """Clear the drawing and reset all Drawing Scale controls (canvas + sidebar)."""
        self.scale_canvas.reset_workspace()
        self.scale_sidebar.reset()

    # ======================== Tab Management ========================
    
    def _create_new_tab(self, file_path: str = None) -> int:
        """Create a new tab with its own viewer and annotation panel. Returns tab index."""
        tab = TabState()
        
        # Create viewer widget
        try:
            if not USE_OFFSCREEN:
                tab.viewer_widget = STLViewerWidget()
            else:
                from viewer_widget_offscreen import STLViewerWidgetOffscreen
                tab.viewer_widget = STLViewerWidgetOffscreen()
        except Exception as e:
            logger.error(f"_create_new_tab: Failed to create viewer: {e}", exc_info=True)
            try:
                from viewer_widget_offscreen import STLViewerWidgetOffscreen
                tab.viewer_widget = STLViewerWidgetOffscreen()
            except Exception as e2:
                logger.error(f"_create_new_tab: Offscreen fallback failed: {e2}", exc_info=True)
                return -1
        
        # Connect viewer signals
        self._connect_viewer_signals_for(tab.viewer_widget)
        
        # Create annotation panel
        tab.annotation_panel = AnnotationPanel()
        tab.annotation_panel.hide()
        self._connect_annotation_panel_signals_for(tab)
        
        # Create arrow panel
        tab.arrow_panel = ArrowPanel()
        tab.arrow_panel.hide()
        self._connect_arrow_panel_signals_for(tab)
        
        # Create parts panel
        tab.parts_panel = PartsPanel()
        tab.parts_panel.hide()
        self._connect_parts_panel_signals_for(tab)
        
        # Add to stacks
        self.viewer_stack.addWidget(tab.viewer_widget)
        self.annotation_stack.addWidget(tab.annotation_panel)
        self.arrow_stack.addWidget(tab.arrow_panel)
        self.parts_stack.addWidget(tab.parts_panel)
        
        # Add to tabs list
        self.tabs.append(tab)
        tab_index = len(self.tabs) - 1
        
        # Insert tab in tab bar (before the "+" tab)
        display_name = "Untitled"
        if file_path:
            display_name = Path(file_path).name
            tab.file_path = file_path
            tab.filename = display_name
        tab_bar_index = self.tab_bar.insertTab(self._plus_tab_index, _ecto_tab_caption(display_name))
        self._plus_tab_index += 1  # "+" tab shifted right
        
        # Switch to the new tab
        self.tab_bar.setCurrentIndex(tab_bar_index)
        
        return tab_index
    
    def _on_tab_changed(self, index: int):
        """Handle tab bar selection change."""
        # If the "+" tab is clicked, create a new tab and upload
        if index == self._plus_tab_index:
            # Revert to previous tab first
            if self.current_tab_index >= 0:
                self.tab_bar.blockSignals(True)
                self.tab_bar.setCurrentIndex(self.current_tab_index)
                self.tab_bar.blockSignals(False)
            self.upload_stl_file()
            return
        
        if index < 0 or index >= len(self.tabs):
            return
        
        # Save current tab state
        self._save_current_tab_state()
        
        # Switch to new tab
        self.current_tab_index = index
        tab = self.tabs[index]
        
        # Show correct viewer, annotation panel, arrow panel, and parts panel
        self.viewer_stack.setCurrentWidget(tab.viewer_widget)
        self.annotation_stack.setCurrentWidget(tab.annotation_panel)
        self.arrow_stack.setCurrentWidget(tab.arrow_panel)
        self.parts_stack.setCurrentWidget(tab.parts_panel)
        
        # Determine which right panel to show
        if tab.parts_mode_active:
            tab.parts_panel.show()
            self.right_panel_stack.setCurrentWidget(self.parts_stack)
            self.right_panel_stack.show()
        elif tab.arrow_mode_active:
            tab.arrow_panel.show()
            self.right_panel_stack.setCurrentWidget(self.arrow_stack)
            self.right_panel_stack.show()
        elif tab.annotation_mode_active:
            tab.annotation_panel.show()
            self.right_panel_stack.setCurrentWidget(self.annotation_stack)
            self.right_panel_stack.show()
        elif tab.screenshot_mode_active:
            self.right_panel_stack.setCurrentWidget(self.screenshot_stack)
            self.right_panel_stack.show()
            self.screenshot_panel.show()
        elif tab.texture_mode_active:
            self.right_panel_stack.setCurrentWidget(self.texture_stack)
            self.right_panel_stack.show()
            self.texture_panel.show()
        else:
            tab.annotation_panel.hide()
            tab.arrow_panel.hide()
            tab.parts_panel.hide()
            self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
            self.right_panel_stack.hide()
        
        # Update sidebar with this tab's data
        if tab.sidebar_data and tab.file_path:
            self.sidebar_panel.update_dimensions(tab.sidebar_data, tab.file_path)
            count = len(tab.annotation_panel.get_annotations())
            self.sidebar_panel.update_annotation_count(count)
        else:
            self.sidebar_panel.reset_all_data()

        has_file = tab.file_path is not None
        self.toolbar.set_stl_loaded(has_file)
        if has_file:
            self.toolbar.set_loaded_filename(tab.filename)
            self.setWindowTitle(f"ECTOFORM - {tab.filename}")
        else:
            self.toolbar.set_loaded_filename(None)
            self.setWindowTitle("ECTOFORM")

        # Restore ruler mode
        if tab.ruler_active:
            self.toolbar.ruler_mode_enabled = True
            self.toolbar.ruler_btn.set_active(True)
            self.toolbar.ruler_btn.set_icon("📐")
            self.toolbar.ruler_btn.set_label("Ruler")
            self.ruler_toolbar.show()
        else:
            if self.toolbar.ruler_mode_enabled:
                self.toolbar.ruler_mode_enabled = False
                self.toolbar.ruler_btn.set_active(False)
                self.toolbar.ruler_btn.set_icon("📏")
                self.ruler_toolbar.hide()

        # Restore annotation mode
        if tab.annotation_mode_active:
            self.toolbar.annotation_mode_enabled = True
        else:
            if self.toolbar.annotation_mode_enabled:
                self.toolbar.reset_annotation_state()

        # Restore arrow mode
        if tab.arrow_mode_active:
            self.toolbar.arrow_mode_enabled = True
        else:
            if self.toolbar.arrow_mode_enabled:
                self.toolbar.reset_arrow_state()

        # Restore screenshot mode
        if tab.screenshot_mode_active:
            self.toolbar.screenshot_mode_enabled = True
            self.toolbar.screenshot_btn.set_active(True)
        else:
            if self.toolbar.screenshot_mode_enabled:
                self._exit_screenshot_mode()

        # Restore texture mode
        if tab.texture_mode_active:
            self.toolbar.texture_mode_enabled = True
            self.toolbar.texture_btn.set_active(True)
        else:
            if self.toolbar.texture_mode_enabled:
                self._exit_texture_mode()

        logger.info(f"_on_tab_changed: Switched to tab {index} ({tab.filename or 'Untitled'})")

    def _scale_export(self):
        """Export the scaled drawing with measurements."""
        if not self.scale_canvas.has_image():
            return
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Scaled Drawing", "",
            "PNG Image (*.png);;JPEG Image (*.jpg);;PDF Document (*.pdf)"
        )
        if path:
            success, result = self.scale_canvas.export_scaled(path)
            if success:
                logger.info(f"Scaled drawing exported to: {result}")
            else:
                logger.error(f"Export failed: {result}")

    def _scale_add_ref(self):
        """Add an extra draggable reference line to the scale canvas."""
        self.scale_canvas.add_extra_ref_line()

    def _save_current_tab_state(self):
        """Save mode flags from the current tab before switching."""
        tab = self._current_tab
        if tab is None:
            return
        tab.ruler_active = self.toolbar.ruler_mode_enabled
        tab.annotation_mode_active = self.toolbar.annotation_mode_enabled
        tab.arrow_mode_active = self.toolbar.arrow_mode_enabled
        tab.parts_mode_active = getattr(self.toolbar, 'parts_mode_enabled', False)
        tab.screenshot_mode_active = self.toolbar.screenshot_mode_enabled
        tab.texture_mode_active = getattr(self.toolbar, 'texture_mode_enabled', False)
        tab.draw_mode_active = self.toolbar.draw_mode_enabled
    
    def _on_tab_close_requested(self, index: int):
        """Handle tab close button click."""
        if index == self._plus_tab_index:
            return  # Can't close "+" tab
        if index < 0 or index >= len(self.tabs):
            return
        
        tab = self.tabs[index]
        
        # Check for unsaved annotations
        annotations = tab.annotation_panel.get_annotations()
        if annotations and not tab.annotations_exported:
            reply = QMessageBox.warning(
                self,
                "Unsaved Annotations",
                f"Tab '{tab.filename or 'Untitled'}' has {len(annotations)} annotation(s) that have not been exported.\n\n"
                "Would you like to export them as .ecto before closing?\n\n"
                "• Click 'Yes' to export first\n"
                "• Click 'No' to close without exporting\n"
                "• Click 'Cancel' to go back",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                # Switch to this tab first so sidebar export works
                self.tab_bar.setCurrentIndex(index)
                self.sidebar_panel.export_as_ecto()
                return
            elif reply == QMessageBox.Cancel:
                return
        
        self._close_tab(index)
    
    def _close_tab(self, index: int):
        """Close and destroy a tab at the given index."""
        tab = self.tabs[index]
        
        # Cleanup ecto temp dir
        if tab.ecto_temp_dir:
            try:
                from core.ecto_format import EctoFormat
                EctoFormat.cleanup_temp_dir(tab.ecto_temp_dir)
            except Exception:
                pass
        
        # Remove widgets from stacks
        self.viewer_stack.removeWidget(tab.viewer_widget)
        self.annotation_stack.removeWidget(tab.annotation_panel)
        self.arrow_stack.removeWidget(tab.arrow_panel)
        self.parts_stack.removeWidget(tab.parts_panel)
        
        # Destroy widgets
        tab.viewer_widget.deleteLater()
        tab.annotation_panel.deleteLater()
        tab.arrow_panel.deleteLater()
        tab.parts_panel.deleteLater()
        
        # Remove from lists
        self.tabs.pop(index)
        
        # Remove tab from tab bar
        self.tab_bar.blockSignals(True)
        self.tab_bar.removeTab(index)
        self._plus_tab_index -= 1
        self.tab_bar.blockSignals(False)
        
        # If no tabs left, create a new empty one
        if len(self.tabs) == 0:
            self.current_tab_index = -1
            self._create_new_tab()
        else:
            # Adjust current index
            if self.current_tab_index >= len(self.tabs):
                self.current_tab_index = len(self.tabs) - 1
            elif self.current_tab_index > index:
                self.current_tab_index -= 1
            elif self.current_tab_index == index:
                self.current_tab_index = min(index, len(self.tabs) - 1)
            
            self.tab_bar.blockSignals(True)
            self.tab_bar.setCurrentIndex(self.current_tab_index)
            self.tab_bar.blockSignals(False)
            self._on_tab_changed(self.current_tab_index)
        
        logger.info(f"_close_tab: Closed tab {index}")
    
    def _find_empty_tab(self) -> int:
        """Find an empty (no file loaded) tab. Returns index or -1."""
        for i, tab in enumerate(self.tabs):
            if tab.file_path is None:
                return i
        return -1
    
    # ======================== Viewer / Annotation Signal Wiring ========================
    
    def _connect_viewer_signals_for(self, viewer):
        """Connect viewer widget signals for drag-and-drop."""
        if hasattr(viewer, 'file_dropped'):
            viewer.file_dropped.connect(self._load_dropped_file)
        if hasattr(viewer, 'click_to_upload'):
            viewer.click_to_upload.connect(self.upload_stl_file)
        if hasattr(viewer, 'drop_error'):
            viewer.drop_error.connect(self._show_drop_error)
        if hasattr(viewer, 'material_preset_applied'):
            viewer.material_preset_applied.connect(self._on_material_preset_applied)
    
    def _connect_annotation_panel_signals_for(self, tab: TabState):
        """Connect annotation panel signals for a specific tab."""
        panel = tab.annotation_panel
        panel.annotation_added.connect(self._on_annotation_added)
        panel.annotation_deleted.connect(self._on_annotation_deleted)
        panel.annotation_validated.connect(self._on_annotation_validated)
        panel.open_popup_requested.connect(self._on_open_popup_requested)
        panel.open_viewer_popup_requested.connect(self._on_open_viewer_popup_requested)
        panel.focus_annotation.connect(self._on_focus_annotation)
        panel.annotation_hovered.connect(self._on_annotation_hovered)
        panel.exit_annotation_mode.connect(self._exit_annotation_mode)
        panel.clear_all_requested.connect(self._on_clear_all_requested)
    
    def apply_styling(self):
        """Apply minimalistic styling with floating card design."""
        self.setStyleSheet(get_global_stylesheet())
    
    def resizeEvent(self, event):
        """Trigger viewer render on resize (Windows black screen fix)."""
        super().resizeEvent(event)
        if sys.platform == 'win32' and self.viewer_widget and getattr(self.viewer_widget, 'plotter', None):
            QTimer.singleShot(100, self._trigger_viewer_render)
    
    def changeEvent(self, event):
        """Trigger viewer render on maximize (Windows black screen fix)."""
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and sys.platform == 'win32' and self.isMaximized():
            QTimer.singleShot(200, self._trigger_viewer_render)
    
    def _trigger_viewer_render(self):
        """Force VTK refresh on viewer (called after resize/maximize)."""
        vw = self.viewer_widget
        plotter = getattr(vw, 'plotter', None) if vw else None
        if plotter is not None:
            try:
                import vtk
                picker = vtk.vtkPropPicker()
                picker.Pick(0, 0, 0, plotter.renderer)
            except Exception as e:
                logger.debug(f"trigger pick: {e}")
            try:
                bg = getattr(plotter, 'background_color', 'white')
                plotter.background_color = bg
                ren = getattr(plotter, 'renderer', None)
                if ren is not None and hasattr(ren, 'ResetCameraClippingRange'):
                    ren.ResetCameraClippingRange()
                if hasattr(vw, '_sync_overlay_viewport'):
                    vw._sync_overlay_viewport()
                plotter.render()
            except Exception as e:
                logger.warning(f"maximize render: {e}")
    
    def _connect_toolbar_signals(self):
        """Connect toolbar signals to handler methods."""
        self.toolbar.toggle_grid.connect(self._toggle_grid)
        self.toolbar.toggle_theme.connect(self._toggle_theme)
        self.toolbar.render_mode_changed.connect(self._set_render_mode)
        self.toolbar.reset_rotation.connect(self._reset_rotation)
        self.toolbar.view_front.connect(self._view_front)
        self.toolbar.view_rear.connect(self._view_rear)
        self.toolbar.view_left.connect(self._view_left)
        self.toolbar.view_right.connect(self._view_right)
        self.toolbar.view_top.connect(self._view_top)
        self.toolbar.view_bottom.connect(self._view_bottom)
        self.toolbar.toggle_fullscreen.connect(self._toggle_fullscreen)
        self.toolbar.toggle_ruler.connect(self._toggle_ruler_mode)
        self.toolbar.toggle_screenshot.connect(self._toggle_screenshot_mode)
        self.toolbar.toggle_texture.connect(self._toggle_texture_mode)
        self.toolbar.toggle_annotation.connect(self._toggle_annotation_mode)
        self.toolbar.toggle_arrow.connect(self._toggle_arrow_mode)
        self.toolbar.toggle_draw.connect(self._toggle_draw_mode)
        self.toolbar.toggle_parts.connect(self._toggle_parts_mode)
        self.toolbar.draw_color_changed.connect(self._on_draw_color_changed)
        self.toolbar.draw_eraser_toggled.connect(self._on_draw_eraser_toggled)
        self.toolbar.draw_undo_requested.connect(self._on_draw_undo)
        self.toolbar.draw_clear_requested.connect(self._on_draw_clear)
        self.toolbar.load_file.connect(self.upload_stl_file)
        self.toolbar.clear_model.connect(self._clear_current_model)
        self.toolbar.open_converter.connect(self._open_converter_dialog)
    
    def _connect_ruler_toolbar_signals(self):
        """Connect ruler toolbar signals to handler methods."""
        self.ruler_toolbar.view_front.connect(self._ruler_view_front)
        self.ruler_toolbar.view_left.connect(self._ruler_view_left)
        self.ruler_toolbar.view_right.connect(self._ruler_view_right)
        self.ruler_toolbar.view_top.connect(self._ruler_view_top)
        self.ruler_toolbar.view_bottom.connect(self._ruler_view_bottom)
        self.ruler_toolbar.view_rear.connect(self._ruler_view_rear)
        self.ruler_toolbar.clear_measurements.connect(self._clear_measurements)
        self.ruler_toolbar.exit_ruler.connect(self._exit_ruler_mode)
        self.ruler_toolbar.unit_changed.connect(self._ruler_unit_changed)
    
    def _clear_current_model(self, skip_confirmation=False):
        """Clear the current model from the viewer."""
        logger.info("_clear_current_model: Clearing current model...")
        
        if self.annotation_panel is None or self.viewer_widget is None:
            return
        
        if not skip_confirmation:
            annotations = self.annotation_panel.get_annotations()
            if annotations:
                if not self._annotations_exported:
                    reply = QMessageBox.warning(
                        self,
                        "Unsaved Annotations",
                        f"You have {len(annotations)} annotation(s) that have not been exported.\n\n"
                        "Would you like to export them as .ecto before clearing?\n\n"
                        "• Click 'Yes' to export first\n"
                        "• Click 'No' to clear without exporting\n"
                        "• Click 'Cancel' to go back",
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                        QMessageBox.Yes
                    )
                    if reply == QMessageBox.Yes:
                        self.sidebar_panel.export_as_ecto()
                        return
                    elif reply == QMessageBox.Cancel:
                        return
                else:
                    reply = QMessageBox.question(
                        self,
                        "Clear Model",
                        f"You have {len(annotations)} annotation(s). Are you sure you want to clear everything?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if reply == QMessageBox.No:
                        return
        
        # Screenshot warning (second warning, after annotation)
        if not skip_confirmation and len(self.screenshot_panel.screenshots) > 0:
            n = len(self.screenshot_panel.screenshots)
            msg = f"You have {n} screenshot(s) that have not been saved. They will be removed. Continue?"
            if not confirm_dialog(self, "Unsaved Screenshots", msg):
                return
        
        # Clear the viewer
        if hasattr(self.viewer_widget, 'clear_viewer'):
            self.viewer_widget.clear_viewer()
        
        # Update toolbar state
        self.toolbar.set_stl_loaded(False)
        self.setWindowTitle("ECTOFORM")
        self.toolbar.set_loaded_filename(None)
        
        # Clear all annotations from panel and viewer
        self._clear_all_annotations()
        
        # Clear ruler measurements and exit ruler mode if active
        if hasattr(self.viewer_widget, 'clear_measurements'):
            self.viewer_widget.clear_measurements()
        if self.toolbar.ruler_mode_enabled:
            self._exit_ruler_mode()
        
        # Hide annotation panel if visible
        if self.annotation_panel.isVisible():
            self._exit_annotation_mode()
        
        # Exit parts mode and hide parts panel
        if self.toolbar.parts_mode_enabled:
            self.toolbar.parts_mode_enabled = False
            self._exit_parts_mode()
        
        # Exit screenshot mode if active and clear all screenshots
        if self.toolbar.screenshot_mode_enabled:
            self._exit_screenshot_mode()
        self.screenshot_panel.clear_all()
        
        # Reset sidebar panel dimensions and calculations
        self.sidebar_panel.reset_all_data()
        
        
        # Reset tab state
        tab = self._current_tab
        if tab:
            tab.file_path = None
            tab.filename = None
            tab.sidebar_data = None
            tab.mesh = None
            tab.annotations_exported = False
            # Update tab bar text
            self.tab_bar.setTabText(self.current_tab_index, _ecto_tab_caption("Untitled"))
        
        logger.info("_clear_current_model: Model and all data cleared")
    
    def _connect_viewer_signals(self):
        """Connect viewer widget signals for drag-and-drop (legacy, used by property)."""
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'file_dropped'):
            vw.file_dropped.connect(self._load_dropped_file)
        if hasattr(vw, 'click_to_upload'):
            vw.click_to_upload.connect(self.upload_stl_file)
        if hasattr(vw, 'drop_error'):
            vw.drop_error.connect(self._show_drop_error)
    
    def _load_dropped_file(self, file_path):
        """Load a file that was dropped on the viewer."""
        logger.info(f"_load_dropped_file: Loading dropped file: {file_path}")
        
        file_ext = file_path.lower()
        if file_ext.endswith('.ecto'):
            self._load_ecto_file(file_path)
            return
        
        if not (file_ext.endswith('.stl') or file_ext.endswith('.step') or file_ext.endswith('.stp') or file_ext.endswith('.3dm') or file_ext.endswith('.obj') or file_ext.endswith('.iges') or file_ext.endswith('.igs')):
            QMessageBox.warning(
                self,
                "Invalid File",
                "Please select a valid 3D file (.stl, .step, .stp, .3dm, .obj, .iges, .igs, or .ecto extension)."
            )
            return
        
        # If current tab has a file, create a new tab; otherwise reuse empty tab
        tab = self._current_tab
        if tab and tab.file_path is not None:
            self._create_new_tab()
        
        self._load_file_into_current_tab(file_path, from_conversion=False)
    
    def _open_converter_dialog(self):
        """Open the file converter dialog."""
        from ui.converter_dialog import ConverterDialog
        # Pre-populate with current file if it's a convertible format
        preset = None
        if self._current_tab and self._current_tab.file_path:
            ext = self._current_tab.file_path.lower()
            if ext.endswith('.3dm') or ext.endswith('.step') or ext.endswith('.stp'):
                preset = self._current_tab.file_path
        dlg = ConverterDialog(self, preset_file=preset)
        dlg.conversion_complete.connect(self._load_converted_file)
        dlg.exec_()

    def _load_converted_file(self, output_path: str):
        """Load a file that was created by the Convert File flow."""
        if self._current_mode != "3d":
            self._switch_mode("3d")
        if self._current_tab and self._current_tab.file_path is not None:
            self._create_new_tab()
        self._load_file_into_current_tab(output_path, from_conversion=True)
    
    def _load_file_into_current_tab(self, file_path: str, from_conversion: bool = False):
        """Load a 3D file into the current tab's viewer."""
        tab = self._current_tab
        if tab is None or tab.viewer_widget is None:
            return
        
        success = tab.viewer_widget.load_stl(file_path)
        
        if not success:
            file_ext = file_path.lower()
            if file_ext.endswith('.step') or file_ext.endswith('.stp'):
                file_type = "STEP"
            elif file_ext.endswith('.3dm'):
                file_type = "3DM"
            elif file_ext.endswith('.obj'):
                file_type = "OBJ"
            elif file_ext.endswith('.iges') or file_ext.endswith('.igs'):
                file_type = "IGES"
            else:
                file_type = "STL"
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load {file_type} file:\n{file_path}\n\nPlease ensure the file is a valid {file_type} format."
            )
        else:
            filename = Path(file_path).name
            tab.file_path = file_path
            tab.filename = filename
            tab.loaded_via_conversion = from_conversion
            
            
            # Update tab bar text
            self.tab_bar.setTabText(self.current_tab_index, _ecto_tab_caption(filename))
            
            self.setWindowTitle(f"ECTOFORM - {filename}")
            self.toolbar.set_loaded_filename(filename)
            self.toolbar.set_stl_loaded(True)
            
            # Update dimensions display and cache
            if hasattr(tab.viewer_widget, 'current_mesh'):
                mesh = tab.viewer_widget.current_mesh
                if mesh is not None:
                    mesh_data = MeshCalculator.get_mesh_data(mesh)
                    tab.sidebar_data = mesh_data
                    tab.mesh = mesh
                    self.sidebar_panel.update_dimensions(mesh_data, file_path)
            
            # Load any existing annotations for this file
            self._load_annotations_for_file(file_path)
            
            # Keep 3D view aligned with toolbar (default visual style is shaded)
            self._set_render_mode(self.toolbar.render_mode)
    
    def _show_drop_error(self, error_msg):
        """Show an error message from drag-and-drop."""
        QMessageBox.warning(self, "Upload Error", error_msg)
    
    def _toggle_grid(self):
        """Toggle the background grid."""
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'toggle_grid') and callable(getattr(vw, 'toggle_grid', None)):
            try:
                vw.toggle_grid()
            except Exception as e:
                logger.warning(f"Could not toggle grid (pygfx): {e}")
            return
        if hasattr(vw, 'plotter') and vw.plotter is not None:
            try:
                if self.toolbar.grid_enabled:
                    vw.plotter.show_grid()
                else:
                    vw.plotter.remove_bounds_axes()
            except Exception as e:
                logger.warning(f"Could not toggle grid: {e}")
    
    def _toggle_theme(self):
        """Toggle between light and dark viewer theme."""
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'set_background_color'):
            try:
                color = '#1a1a2e' if self.toolbar.dark_theme else '#ffffff'
                vw.set_background_color(color)
            except Exception as e:
                logger.warning(f"Could not toggle theme (pygfx): {e}")
            return
        if hasattr(vw, 'plotter') and vw.plotter is not None:
            try:
                if self.toolbar.dark_theme:
                    vw.plotter.background_color = '#1a1a2e'
                else:
                    vw.plotter.background_color = 'white'
            except Exception as e:
                logger.warning(f"Could not toggle theme: {e}")
    
    def _set_render_mode(self, mode):
        """Set render mode: solid, wireframe, or shaded."""
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'set_render_mode'):
            vw.set_render_mode(mode)
            return
        if hasattr(vw, 'current_actor') and vw.current_actor is not None:
            try:
                prop = vw.current_actor.GetProperty()
                if mode == 'wireframe':
                    prop.SetRepresentationToSurface()
                    prop.EdgeVisibilityOff()
                    prop.SetRepresentationToWireframe()
                elif mode == 'shaded':
                    prop.SetRepresentationToSurface()
                    prop.EdgeVisibilityOff()
                    prop.SetInterpolationToFlat()
                    prop.SetColor(0.72, 0.72, 0.76)
                    prop.SetAmbient(0.25)
                    prop.SetDiffuse(0.55)
                    prop.SetSpecular(0.65)
                    prop.SetSpecularPower(90)
                else:
                    prop.SetRepresentationToSurface()
                    prop.EdgeVisibilityOff()
                    prop.SetInterpolationToFlat()
                    prop.SetColor(0.68, 0.85, 0.90)
                    prop.SetAmbient(0.7)
                    prop.SetDiffuse(0.4)
                    prop.SetSpecular(0.2)
                    prop.SetSpecularPower(20)
                vw.plotter.render()
            except Exception as e:
                logger.warning(f"Could not set render mode: {e}")
    
    def _reset_rotation(self):
        """Reset view to default isometric rotation and clear drawings."""
        vw = self.viewer_widget
        if vw is None:
            return
        # Exit parts mode and hide the parts panel
        if self.toolbar.parts_mode_enabled:
            self.toolbar.parts_mode_enabled = False
            self._exit_parts_mode()
            self._save_current_tab_state()
        if hasattr(vw, 'clear_drawings'):
            try:
                vw.clear_drawings()
            except Exception as e:
                logger.warning(f"Could not clear drawings: {e}")
        if hasattr(vw, 'reset_view'):
            try:
                vw.reset_view()
            except Exception as e:
                logger.warning(f"Could not reset rotation (pygfx): {e}")
            return
        if hasattr(vw, 'plotter') and vw.plotter is not None:
            try:
                vw.plotter.reset_camera()
                vw.plotter.view_isometric()
            except Exception as e:
                logger.warning(f"Could not reset rotation: {e}")
    
    def _sync_ruler_toolbar_view(self, view_name):
        """Sync ruler toolbar active button when view changes from main toolbar."""
        if self.toolbar.ruler_mode_enabled and self.ruler_toolbar.isVisible():
            self.ruler_toolbar._update_view_buttons(view_name)

    def _ensure_ruler_mode_for_view(self):
        """If not in ruler mode, enable it so 6 views use orthographic projection."""
        vw = self.viewer_widget
        if vw is None:
            return
        if not self.toolbar.ruler_mode_enabled and hasattr(vw, 'enable_ruler_mode'):
            success = vw.enable_ruler_mode()
            if success:
                self.toolbar.ruler_mode_enabled = True
                self.toolbar.ruler_btn.set_active(True)
                self.toolbar.ruler_btn.set_icon("📐")
                self.toolbar.ruler_btn.set_label("Ruler")
                self.ruler_toolbar.show()

    def _view_front(self):
        """Set camera to front orthographic view."""
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'view_front_ortho'):
            self._ensure_ruler_mode_for_view()
            vw.view_front_ortho()
            self._sync_ruler_toolbar_view("front")
            return
        if hasattr(vw, 'plotter') and vw.plotter is not None:
            try:
                vw.plotter.view_yz()
            except Exception as e:
                logger.warning(f"Could not set front view: {e}")
    
    def _view_rear(self):
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'view_rear_ortho'):
            self._ensure_ruler_mode_for_view()
            vw.view_rear_ortho()
            self._sync_ruler_toolbar_view("rear")
    
    def _view_left(self):
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'view_left_ortho'):
            self._ensure_ruler_mode_for_view()
            vw.view_left_ortho()
            self._sync_ruler_toolbar_view("left")
    
    def _view_right(self):
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'view_right_ortho'):
            self._ensure_ruler_mode_for_view()
            vw.view_right_ortho()
            self._sync_ruler_toolbar_view("right")
    
    def _view_top(self):
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'view_top_ortho'):
            self._ensure_ruler_mode_for_view()
            vw.view_top_ortho()
            self._sync_ruler_toolbar_view("top")
            return
        if hasattr(vw, 'plotter') and vw.plotter is not None:
            try:
                vw.plotter.view_xy()
            except Exception as e:
                logger.warning(f"Could not set top view: {e}")
    
    def _view_bottom(self):
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'view_bottom_ortho'):
            self._ensure_ruler_mode_for_view()
            vw.view_bottom_ortho()
            self._sync_ruler_toolbar_view("bottom")
    
    # ========== Ruler Mode Methods ==========
    
    def _toggle_ruler_mode(self):
        """Toggle ruler/measurement mode."""
        vw = self.viewer_widget
        if vw is None:
            return
        if self.toolbar.ruler_mode_enabled:
            if hasattr(vw, 'enable_ruler_mode'):
                success = vw.enable_ruler_mode()
                if success:
                    logger.info("_toggle_ruler_mode: Showing ruler toolbar, setting front view")
                    self.ruler_toolbar.show()
                    self.ruler_toolbar.reset_to_front()
                    self._ruler_view_front()
                    QTimer.singleShot(100, self._ruler_view_front)
                    logger.info("_toggle_ruler_mode: Ruler mode enabled (front view set, deferred at 100ms)")
                else:
                    self.toolbar.ruler_mode_enabled = False
                    self.toolbar.ruler_btn.set_active(False)
                    logger.warning("_toggle_ruler_mode: Failed to enable ruler mode")
        else:
            self._exit_ruler_mode()
    
    def _exit_ruler_mode(self):
        """Exit ruler mode and restore normal view."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'disable_ruler_mode'):
            vw.disable_ruler_mode()
        self.ruler_toolbar.hide()
        self.toolbar.ruler_mode_enabled = False
        self.toolbar.ruler_btn.set_active(False)
        self.toolbar.ruler_btn.set_icon("📏")
        logger.info("_exit_ruler_mode: Ruler mode disabled")
    
    def _ruler_view_front(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'view_front_ortho'):
            vw.view_front_ortho()
    
    def _ruler_view_left(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'view_left_ortho'):
            vw.view_left_ortho()
    
    def _ruler_view_right(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'view_right_ortho'):
            vw.view_right_ortho()
    
    def _ruler_view_top(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'view_top_ortho'):
            vw.view_top_ortho()
    
    def _ruler_view_bottom(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'view_bottom_ortho'):
            vw.view_bottom_ortho()
    
    def _ruler_view_rear(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'view_rear_ortho'):
            vw.view_rear_ortho()
    
    def _clear_measurements(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'clear_measurements'):
            vw.clear_measurements()
    
    def _ruler_unit_changed(self, unit_key):
        vw = self.viewer_widget
        if vw and hasattr(vw, '_ruler_unit'):
            vw._ruler_unit = unit_key
            logger.info(f"_ruler_unit_changed: Unit set to {unit_key}")
    
    # ========== Annotation Mode Methods ==========
    
    def _connect_annotation_panel_signals(self):
        """Legacy: connect annotation panel signals (no longer used directly, see _connect_annotation_panel_signals_for)."""
        pass
    
    def _toggle_annotation_mode(self):
        """Toggle annotation mode."""
        vw = self.viewer_widget
        if vw is None:
            return
        if self.toolbar.annotation_mode_enabled:
            if hasattr(vw, 'enable_annotation_mode'):
                success = vw.enable_annotation_mode(
                    callback=self._on_annotation_point_picked
                )
                if success:
                    # Always exit screenshot mode - toolbar clears screenshot_mode_enabled before we run,
                    # so we must call _exit_screenshot_mode to hide zoom/overlay on the viewer
                    self._exit_screenshot_mode()
                    self.annotation_panel.show()
                    self.right_panel_stack.setCurrentWidget(self.annotation_stack)
                    self.right_panel_stack.show()
                    if self.toolbar.ruler_mode_enabled:
                        self._exit_ruler_mode()
                    if self.toolbar.draw_mode_enabled:
                        self._exit_draw_mode()
                    if hasattr(vw, 'reframe_for_viewport'):
                        QTimer.singleShot(50, vw.reframe_for_viewport)
                    logger.info("_toggle_annotation_mode: Annotation mode enabled")
                else:
                    self.toolbar.reset_annotation_state()
                    logger.warning("_toggle_annotation_mode: Failed to enable annotation mode")
        else:
            self._exit_annotation_mode()
    
    def _exit_annotation_mode(self):
        """Exit annotation mode; keep annotations saved and visible on the model."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'disable_annotation_mode'):
            vw.disable_annotation_mode()
        if self.annotation_panel:
            self.annotation_panel.hide()
        if self.toolbar.screenshot_mode_enabled:
            self.right_panel_stack.setCurrentWidget(self.screenshot_stack)
            self.right_panel_stack.show()
        else:
            self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
            self.right_panel_stack.hide()
        if vw and hasattr(vw, 'reframe_for_viewport'):
            QTimer.singleShot(50, vw.reframe_for_viewport)
        self.toolbar.reset_annotation_state()
        logger.info("_exit_annotation_mode: Annotation mode disabled, annotations kept")
    
    # ========== Arrow Mode Methods ==========

    def _toggle_arrow_mode(self):
        """Toggle 3D arrow placement mode with control panel."""
        vw = self.viewer_widget
        if vw is None:
            return
        tab = self._current_tab
        if tab is None:
            return
        if self.toolbar.arrow_mode_enabled:
            if hasattr(vw, 'enable_arrow_mode'):
                # Exit other modes FIRST
                if self.toolbar.annotation_mode_enabled:
                    self._exit_annotation_mode()
                if self.toolbar.ruler_mode_enabled:
                    self._exit_ruler_mode()
                if self.toolbar.screenshot_mode_enabled:
                    self._exit_screenshot_mode()
                if self.toolbar.draw_mode_enabled:
                    self._exit_draw_mode()
                # Set callback so viewer notifies us of new arrows
                vw._arrow_added_callback = lambda aid: self._on_arrow_placed(aid)
                success = vw.enable_arrow_mode()
                if success:
                    # Show arrow panel
                    tab.arrow_panel.show()
                    self.arrow_stack.setCurrentWidget(tab.arrow_panel)
                    self.right_panel_stack.setCurrentWidget(self.arrow_stack)
                    self.right_panel_stack.show()
                    if hasattr(vw, 'reframe_for_viewport'):
                        QTimer.singleShot(50, vw.reframe_for_viewport)
                    logger.info("_toggle_arrow_mode: Arrow mode enabled with panel")
                else:
                    self.toolbar.reset_arrow_state()
                    logger.warning("_toggle_arrow_mode: Failed to enable arrow mode")
        else:
            self._exit_arrow_mode()

    def _exit_arrow_mode(self):
        """Exit arrow mode; arrows remain visible."""
        vw = self.viewer_widget
        tab = self._current_tab
        if vw and hasattr(vw, 'disable_arrow_mode'):
            vw.disable_arrow_mode()
            vw._arrow_added_callback = None
        if tab and tab.arrow_panel:
            tab.arrow_panel.hide()
        # Restore right panel
        if self.toolbar.annotation_mode_enabled and tab:
            self.right_panel_stack.setCurrentWidget(self.annotation_stack)
            self.right_panel_stack.show()
        elif self.toolbar.screenshot_mode_enabled:
            self.right_panel_stack.setCurrentWidget(self.screenshot_stack)
            self.right_panel_stack.show()
        else:
            self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
            self.right_panel_stack.hide()
        if vw and hasattr(vw, 'reframe_for_viewport'):
            QTimer.singleShot(50, vw.reframe_for_viewport)
        self.toolbar.reset_arrow_state()
        logger.info("_exit_arrow_mode: Arrow mode disabled")

    def _on_arrow_placed(self, arrow_id: int):
        """Called when the viewer places a new arrow on the model."""
        tab = self._current_tab
        if tab and tab.arrow_panel:
            tab.arrow_panel.add_arrow(arrow_id)

    def _connect_arrow_panel_signals_for(self, tab: TabState):
        """Connect arrow panel signals for a specific tab."""
        panel = tab.arrow_panel
        panel.rotate_requested.connect(lambda aid, axis, angle: self._arrow_rotate(aid, axis, angle))
        panel.scale_requested.connect(lambda aid, factor: self._arrow_scale(aid, factor))
        panel.move_requested.connect(lambda aid, dx, dy, dz: self._arrow_move(aid, dx, dy, dz))
        panel.color_changed.connect(lambda aid, color: self._arrow_set_color(aid, color))
        panel.delete_requested.connect(lambda aid: self._arrow_delete(aid))
        panel.clear_all_requested.connect(self._arrow_clear_all)
        panel.undo_last_requested.connect(self._arrow_undo_last)
        panel.exit_arrow_mode.connect(self._exit_arrow_mode_from_panel)

    def _exit_arrow_mode_from_panel(self):
        """Exit arrow mode triggered from the panel close button."""
        if self.toolbar.arrow_mode_enabled:
            self.toolbar.arrow_mode_enabled = False
            self.toolbar.reset_arrow_state()
        self._exit_arrow_mode()

    def _arrow_rotate(self, arrow_id, axis, angle):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'rotate_arrow'):
            vw.rotate_arrow(arrow_id, axis, angle)

    def _arrow_scale(self, arrow_id, factor):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'scale_arrow'):
            vw.scale_arrow(arrow_id, factor)

    def _arrow_move(self, arrow_id, dx, dy, dz):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'move_arrow'):
            vw.move_arrow(arrow_id, dx, dy, dz)

    def _arrow_set_color(self, arrow_id, color):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_arrow_color'):
            vw.set_arrow_color(arrow_id, color)

    def _arrow_delete(self, arrow_id):
        vw = self.viewer_widget
        tab = self._current_tab
        if vw and hasattr(vw, 'remove_arrow'):
            vw.remove_arrow(arrow_id)
        if tab and tab.arrow_panel:
            tab.arrow_panel.remove_arrow(arrow_id)

    def _arrow_clear_all(self):
        vw = self.viewer_widget
        tab = self._current_tab
        if vw and hasattr(vw, 'clear_all_arrows'):
            vw.clear_all_arrows()
        if tab and tab.arrow_panel:
            tab.arrow_panel.clear_all()

    def _arrow_undo_last(self):
        vw = self.viewer_widget
        tab = self._current_tab
        if vw and hasattr(vw, '_arrow_objects') and vw._arrow_objects:
            last_id = vw._arrow_objects[-1]['id']
            vw.remove_arrow(last_id)
            if tab and tab.arrow_panel:
                tab.arrow_panel.remove_arrow(last_id)

    # ========== Parts Mode Methods ==========

    def _toggle_parts_mode(self):
        """Toggle parts visibility panel."""
        vw = self.viewer_widget
        if vw is None:
            return
        tab = self._current_tab
        if tab is None:
            return
        if self.toolbar.parts_mode_enabled:
            # Exit other modes
            if self.toolbar.annotation_mode_enabled:
                self._exit_annotation_mode()
            if self.toolbar.arrow_mode_enabled:
                self._exit_arrow_mode()
            if self.toolbar.ruler_mode_enabled:
                self._exit_ruler_mode()
            if self.toolbar.screenshot_mode_enabled:
                self._exit_screenshot_mode()
            if self.toolbar.draw_mode_enabled:
                self._exit_draw_mode()
            # Clear any previous cards — panel starts empty, populated on click
            tab.parts_panel.clear_all()
            tab.parts_panel.show()
            self.parts_stack.setCurrentWidget(tab.parts_panel)
            self.right_panel_stack.setCurrentWidget(self.parts_stack)
            self.right_panel_stack.show()
            # Cache hierarchy data for on-click lookup
            has_hierarchy = hasattr(vw, 'get_parts_hierarchy')
            has_flat = hasattr(vw, 'get_parts_list')
            if has_hierarchy:
                self._cached_parts_hierarchy = vw.get_parts_hierarchy()
            elif has_flat:
                self._cached_parts_hierarchy = vw.get_parts_list()
            else:
                self._cached_parts_hierarchy = []
            # Enable click-to-select in 3D viewport
            if hasattr(vw, 'enable_parts_pick_mode'):
                vw.enable_parts_pick_mode()
            if hasattr(vw, 'reframe_for_viewport'):
                QTimer.singleShot(50, vw.reframe_for_viewport)
            logger.info("_toggle_parts_mode: Parts mode enabled")
        else:
            self._exit_parts_mode()

    def _exit_parts_mode(self):
        """Exit parts mode."""
        tab = self._current_tab
        vw = self.viewer_widget
        if tab and tab.parts_panel:
            tab.parts_panel.hide()
        # Disable click-to-select in 3D viewport
        if vw and hasattr(vw, 'disable_parts_pick_mode'):
            vw.disable_parts_pick_mode()
        # Restore all parts visible
        if vw and hasattr(vw, 'show_all_parts'):
            vw.show_all_parts()
        if vw and hasattr(vw, 'unhighlight_parts'):
            vw.unhighlight_parts()
        self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
        self.right_panel_stack.hide()
        parent = self.right_panel_stack.parentWidget()
        if parent:
            parent.updateGeometry()
        if vw and hasattr(vw, 'reframe_for_viewport'):
            QTimer.singleShot(50, vw.reframe_for_viewport)
        self.toolbar.reset_parts_state()
        logger.info("_exit_parts_mode: Parts mode disabled")

    def _exit_parts_mode_from_panel(self):
        """Exit parts mode triggered from the panel close button."""
        if self.toolbar.parts_mode_enabled:
            self.toolbar.parts_mode_enabled = False
            self.toolbar.reset_parts_state()
        self._exit_parts_mode()

    def _connect_parts_panel_signals_for(self, tab: TabState):
        """Connect parts panel signals for a specific tab."""
        panel = tab.parts_panel
        panel.part_visibility_changed.connect(lambda pid, vis: self._part_set_visible(pid, vis))
        panel.part_selected.connect(lambda pid: self._part_select(pid))
        panel.group_selected.connect(lambda pids: self._group_select(pids))
        panel.show_all_requested.connect(self._parts_show_all)
        panel.hide_all_requested.connect(self._parts_hide_all)
        panel.invert_visibility_requested.connect(self._parts_invert)
        panel.isolate_selected_requested.connect(lambda pid: self._part_isolate(pid))
        panel.isolate_group_requested.connect(lambda pids: self._group_isolate(pids))
        panel.exit_parts_mode.connect(self._exit_parts_mode_from_panel)

        # Connect viewer part_clicked signal to panel selection
        vw = tab.viewer_widget
        if vw and hasattr(vw, 'part_clicked'):
            vw.part_clicked.connect(lambda pid, p=panel: self._on_viewer_part_clicked(pid, p))

    def _part_set_visible(self, part_id, visible):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_part_visible'):
            vw.set_part_visible(part_id, visible)

    def _part_select(self, part_id):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'highlight_part'):
            vw.highlight_part(part_id)

    def _group_select(self, part_ids):
        """Highlight all parts in a group."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'highlight_parts'):
            vw.highlight_parts(part_ids)

    def _on_viewer_part_clicked(self, part_id, panel):
        """Handle click on a part in the 3D viewer — add card if needed, then select."""
        # Find the hierarchy entry that owns this part_id
        item = self._find_hierarchy_entry_for(part_id)
        if item:
            panel.add_part(item)
            panel.select_part_by_id(part_id)

    def _find_hierarchy_entry_for(self, part_id):
        """Find the hierarchy entry (standalone or group) that contains part_id."""
        cached = getattr(self, '_cached_parts_hierarchy', [])
        for entry in cached:
            if entry['id'] == part_id:
                return entry
            if part_id in entry.get('child_ids', []):
                return entry
        return None

    def _parts_show_all(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'show_all_parts'):
            vw.show_all_parts()

    def _parts_hide_all(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'hide_all_parts'):
            vw.hide_all_parts()

    def _parts_invert(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'invert_parts_visibility'):
            vw.invert_parts_visibility()

    def _part_isolate(self, part_id):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'isolate_part'):
            vw.isolate_part(part_id)

    def _group_isolate(self, part_ids):
        """Isolate a group — show only its child parts."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'isolate_parts'):
            vw.isolate_parts(part_ids)
        elif vw:
            # Fallback: hide all, then show group parts
            if hasattr(vw, 'hide_all_parts'):
                vw.hide_all_parts()
            if hasattr(vw, 'set_part_visible'):
                for pid in part_ids:
                    vw.set_part_visible(pid, True)

    # ========== Screenshot Mode Methods ==========
    
    def _toggle_screenshot_mode(self):
        """Toggle screenshot capture mode."""
        vw = self.viewer_widget
        if vw is None:
            return
        if self.toolbar.screenshot_mode_enabled:
            if hasattr(vw, 'enable_screenshot_mode'):
                success = vw.enable_screenshot_mode()
                if success:
                    vw._screenshot_captured_callback = self._on_screenshot_captured
                    if self.toolbar.ruler_mode_enabled:
                        self._exit_ruler_mode()
                    if self.toolbar.annotation_mode_enabled:
                        self._exit_annotation_mode()
                    if self.toolbar.draw_mode_enabled:
                        self._exit_draw_mode()
                    self.right_panel_stack.setCurrentWidget(self.screenshot_stack)
                    self.right_panel_stack.show()
                    self.screenshot_panel.show()
                    if hasattr(vw, 'reframe_for_viewport'):
                        QTimer.singleShot(50, vw.reframe_for_viewport)
                    logger.info("_toggle_screenshot_mode: Screenshot mode enabled")
                else:
                    self.toolbar.reset_screenshot_state()
        else:
            self._exit_screenshot_mode()
    
    def _exit_screenshot_mode(self):
        """Exit screenshot mode."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'disable_screenshot_mode'):
            vw.disable_screenshot_mode()
            vw._screenshot_captured_callback = None
        self.screenshot_panel.hide()
        if self.toolbar.annotation_mode_enabled:
            self.right_panel_stack.setCurrentWidget(self.annotation_stack)
            self.right_panel_stack.show()
        else:
            self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
            self.right_panel_stack.hide()
        if vw and hasattr(vw, 'reframe_for_viewport'):
            QTimer.singleShot(50, vw.reframe_for_viewport)
        self.toolbar.reset_screenshot_state()
        logger.info("_exit_screenshot_mode: Screenshot mode disabled")

    # ========== Texture Mode Methods ==========

    def _toggle_texture_mode(self):
        """Toggle texture application mode."""
        vw = self.viewer_widget
        if vw is None:
            return
        if self.toolbar.texture_mode_enabled:
            # Exit other modes
            if self.toolbar.annotation_mode_enabled:
                self._exit_annotation_mode()
            if self.toolbar.arrow_mode_enabled:
                self._exit_arrow_mode()
            if self.toolbar.ruler_mode_enabled:
                self._exit_ruler_mode()
            if self.toolbar.screenshot_mode_enabled:
                self._exit_screenshot_mode()
            if self.toolbar.draw_mode_enabled:
                self._exit_draw_mode()
            if self.toolbar.parts_mode_enabled:
                self.toolbar.parts_mode_enabled = False
                self._exit_parts_mode()
            # Enable texture drop on viewer
            if hasattr(vw, 'enable_texture_drop_mode'):
                vw.enable_texture_drop_mode()
            self.texture_panel.show()
            self.right_panel_stack.setCurrentWidget(self.texture_stack)
            self.right_panel_stack.show()
            if hasattr(vw, 'reframe_for_viewport'):
                QTimer.singleShot(50, vw.reframe_for_viewport)
            logger.info("_toggle_texture_mode: Texture mode enabled")
        else:
            self._exit_texture_mode()

    def _exit_texture_mode(self):
        """Exit texture mode."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'disable_texture_drop_mode'):
            vw.disable_texture_drop_mode()
        self.texture_panel.hide()
        self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
        self.right_panel_stack.hide()
        if vw and hasattr(vw, 'reframe_for_viewport'):
            QTimer.singleShot(50, vw.reframe_for_viewport)
        self.toolbar.reset_texture_state()
        logger.info("_exit_texture_mode: Texture mode disabled")

    def _exit_texture_mode_from_panel(self):
        """Exit texture mode triggered from the panel close button."""
        if self.toolbar.texture_mode_enabled:
            self.toolbar.texture_mode_enabled = False
            self.toolbar.reset_texture_state()
        self._exit_texture_mode()

    def _on_texture_settings_changed(self, settings):
        """Forward texture slider settings to the active viewer widget."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'update_texture_settings'):
            vw.update_texture_settings(settings)

    def _on_material_preset_applied(self, preset_data):
        """Sync simplified material sliders when a preset is dropped onto the model."""
        if self.texture_panel and hasattr(self.texture_panel, 'sync_material_controls'):
            self.texture_panel.sync_material_controls(preset_data)

    # ========== Draw Mode Methods ==========
    
    def _toggle_draw_mode(self):
        """Toggle freehand draw mode."""
        vw = self.viewer_widget
        if vw is None:
            return
        if self.toolbar.draw_mode_enabled:
            if hasattr(vw, 'enable_draw_mode'):
                success = vw.enable_draw_mode()
                if success:
                    # Exit other modes
                    if self.toolbar.ruler_mode_enabled:
                        self._exit_ruler_mode()
                    if self.toolbar.annotation_mode_enabled:
                        self._exit_annotation_mode()
                    if self.toolbar.screenshot_mode_enabled or getattr(vw, "screenshot_mode", False):
                        self._exit_screenshot_mode()
                    # Show color picker on first enable
                    self.toolbar.show_draw_color_picker()
                    logger.info("_toggle_draw_mode: Draw mode enabled")
                else:
                    self.toolbar.reset_draw_state()
                    logger.warning("_toggle_draw_mode: Failed to enable draw mode")
        else:
            self._exit_draw_mode()
    
    def _exit_draw_mode(self):
        """Exit draw mode."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'disable_draw_mode'):
            vw.disable_draw_mode()
        self.toolbar.reset_draw_state()
        logger.info("_exit_draw_mode: Draw mode disabled")
    
    def _on_draw_color_changed(self, color: str):
        """Handle draw color change from toolbar."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_draw_color'):
            vw.set_draw_color(color)

    def _on_draw_eraser_toggled(self, enabled: bool):
        """Handle eraser mode toggle."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_eraser_mode'):
            vw.set_eraser_mode(enabled)

    def _on_draw_undo(self):
        """Undo last drawn stroke."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'undo_last_stroke'):
            vw.undo_last_stroke()

    def _on_draw_clear(self):
        """Clear all drawn strokes."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'clear_drawings'):
            vw.clear_drawings()

    
    def _on_screenshot_captured(self, pixmap):
        """Handle a captured screenshot from the viewer overlay."""
        self.screenshot_panel.add_screenshot(pixmap)
        logger.info("_on_screenshot_captured: Screenshot added to panel")

    def _on_annotation_point_picked(self, point: tuple):
        """Handle point picked for annotation - creates gray dot."""
        logger.info(f"_on_annotation_point_picked: Point picked at {point}")
        
        if self.annotation_panel is None:
            return
        
        annotation = self.annotation_panel.add_annotation(point)
        
        vw = self.viewer_widget
        if vw and hasattr(vw, 'add_annotation_marker'):
            display_num = self.annotation_panel.get_display_number(annotation.id)
            vw.add_annotation_marker(
                annotation.id, point, '#909d92',
                display_date=str(display_num or len(self.annotation_panel.annotations))
            )
    
    def _on_annotation_added(self, annotation):
        logger.info(f"_on_annotation_added: Annotation {annotation.id} added")
        self._update_sidebar_annotation_count()
    
    def _on_annotation_deleted(self, annotation_id: int):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'remove_annotation_marker'):
            vw.remove_annotation_marker(annotation_id)
        if self.annotation_panel is None:
            return
        annotations = self.annotation_panel.get_annotations()
        if annotations and vw and hasattr(vw, 'update_annotation_labels_from_list'):
            reader_mode = self.annotation_panel.is_reader_mode()
            annotations_with_display = []
            for i, ann in enumerate(annotations):
                display_number = i + 1
                if reader_mode:
                    color = '#1821b4' if ann.is_read else '#36cd2e'
                else:
                    color = '#1821b4' if ann.is_validated else '#909d92'
                annotations_with_display.append((ann.id, display_number, color))
            vw.update_annotation_labels_from_list(annotations_with_display)
        logger.info(f"_on_annotation_deleted: Annotation {annotation_id} removed, markers renumbered")
        self._update_sidebar_annotation_count()
    
    def _on_open_popup_requested(self, annotation_id: int):
        from ui.annotation_popup import AnnotationPopup
        
        if self.annotation_panel is None:
            return
        annotation = self.annotation_panel.get_annotation_by_id(annotation_id)
        if annotation is None:
            return
        
        display_num = self.annotation_panel.get_display_number(annotation.id)
        popup = AnnotationPopup(
            annotation_id=annotation.id,
            point=annotation.point,
            text=annotation.text,
            image_paths=annotation.image_paths,
            label=annotation.label,
            created_at=annotation.created_at,
            display_number=display_num,
            parent=self
        )
        
        popup.annotation_validated.connect(self._on_popup_validated)
        popup.annotation_deleted.connect(self._on_popup_deleted)
        popup.finished.connect(lambda: self._on_annotation_popup_closed(annotation_id))
        
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_annotation_selected'):
            vw.set_annotation_selected(annotation_id, True)
        
        popup.show()
        logger.info(f"_on_open_popup_requested: Opened popup for annotation {annotation_id}")
    
    def _on_open_viewer_popup_requested(self, annotation_id: int):
        from ui.annotation_viewer_popup import AnnotationViewerPopup
        
        if self.annotation_panel is None:
            return
        annotation = self.annotation_panel.get_annotation_by_id(annotation_id)
        if annotation is None:
            return
        
        display_num = self.annotation_panel.get_display_number(annotation.id)
        popup = AnnotationViewerPopup(
            annotation_id=annotation.id,
            point=annotation.point,
            text=annotation.text,
            image_paths=annotation.image_paths,
            label=annotation.label,
            created_at=annotation.created_at,
            display_number=display_num,
            parent=self
        )
        
        self.annotation_panel.mark_as_read(annotation_id)
        vw = self.viewer_widget
        if vw and hasattr(vw, 'update_annotation_marker_color'):
            vw.update_annotation_marker_color(annotation_id, '#1821b4')
        
        if vw and hasattr(vw, 'set_annotation_selected'):
            vw.set_annotation_selected(annotation_id, True)
        
        popup.finished.connect(lambda: self._on_annotation_popup_closed(annotation_id))
        popup.show()
        
        logger.info(f"_on_open_viewer_popup_requested: Opened viewer popup for annotation {annotation_id}")
    
    def _on_popup_validated(self, annotation_id: int, text: str, image_paths: list, label: str = "Point"):
        if self.annotation_panel:
            self.annotation_panel.validate_annotation(annotation_id, text, image_paths, label)
        vw = self.viewer_widget
        if vw and hasattr(vw, 'update_annotation_marker_color'):
            vw.update_annotation_marker_color(annotation_id, '#1821b4')
        logger.info(f"_on_popup_validated: Annotation {annotation_id} validated")
    
    def _on_popup_deleted(self, annotation_id: int):
        if self.annotation_panel:
            self.annotation_panel.remove_annotation(annotation_id)
        logger.info(f"_on_popup_deleted: Annotation {annotation_id} deleted from popup")
    
    def _on_annotation_popup_closed(self, annotation_id: int):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_annotation_selected'):
            vw.set_annotation_selected(annotation_id, False)
    
    def _on_annotation_validated(self, annotation_id: int, text: str, image_paths: list, label: str = "Point"):
        logger.info(f"_on_annotation_validated: Annotation {annotation_id} validated")
    
    def _on_focus_annotation(self, annotation_id: int):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'focus_on_annotation'):
            vw.focus_on_annotation(annotation_id)
    
    def _on_annotation_hovered(self, annotation_id: int, is_hovered: bool):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_annotation_selected'):
            vw.set_annotation_selected(annotation_id, is_hovered)
    
    def _refresh_annotation_markers(self):
        vw = self.viewer_widget
        if not vw or not hasattr(vw, 'clear_all_annotation_markers'):
            return
        vw.clear_all_annotation_markers()
        if self.annotation_panel is None:
            return
        annotations = self.annotation_panel.get_annotations()
        if not annotations:
            return
        reader_mode = self.annotation_panel.is_reader_mode()
        for i, ann in enumerate(annotations):
            display_number = i + 1
            if reader_mode:
                color = '#1821b4' if ann.is_read else '#36cd2e'
            else:
                color = '#1821b4' if ann.is_validated else '#909d92'
            if hasattr(vw, 'add_annotation_marker'):
                vw.add_annotation_marker(ann.id, ann.point, color, display_date=str(display_number))
    
    def _on_clear_all_requested(self):
        if self.annotation_panel is None:
            return
        annotations = self.annotation_panel.get_annotations()
        if annotations:
            if not self._annotations_exported:
                reply = QMessageBox.warning(
                    self,
                    "Unsaved Annotations",
                    f"You have {len(annotations)} annotation(s) that have not been exported.\n\n"
                    "Would you like to export them as .ecto before clearing?\n\n"
                    "• Click 'Yes' to export first\n"
                    "• Click 'No' to clear without exporting\n"
                    "• Click 'Cancel' to go back",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    self.sidebar_panel.export_as_ecto()
                    return
                elif reply == QMessageBox.Cancel:
                    return
            else:
                reply = QMessageBox.question(
                    self,
                    "Clear All",
                    f"You have {len(annotations)} annotation(s). Are you sure you want to clear everything?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
        # Screenshot warning (second, after annotation)
        if len(self.screenshot_panel.screenshots) > 0:
            n = len(self.screenshot_panel.screenshots)
            if not confirm_dialog(self, "Unsaved Screenshots", f"You have {n} screenshot(s) that have not been saved. They will be removed. Continue?"):
                return
        self._clear_current_model(skip_confirmation=True)

    def _clear_all_annotations(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'clear_all_annotation_markers'):
            vw.clear_all_annotation_markers()
        if self.annotation_panel:
            self.annotation_panel.clear_all()
        logger.info("_clear_all_annotations: All annotations cleared")
        self._update_sidebar_annotation_count()
    
    def _update_sidebar_annotation_count(self):
        if self.annotation_panel is None:
            return
        count = len(self.annotation_panel.annotations)
        self.sidebar_panel.update_annotation_count(count)
        if count > 0:
            self._annotations_exported = False
    
    def _on_annotations_exported(self):
        self._annotations_exported = True
        logger.info("_on_annotations_exported: Annotations have been exported")

    def _toggle_fullscreen(self):
        if self.toolbar.is_fullscreen:
            self.showFullScreen()
        else:
            self.showNormal()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.showNormal()
            self.toolbar.reset_fullscreen_state()
        else:
            super().keyPressEvent(event)

    
    def upload_stl_file(self):
        """Open file dialog and load selected 3D or .ecto file."""
        logger.info("upload_stl_file: Opening file dialog...")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select 3D File",
            "",
            "All Supported (*.stl *.step *.stp *.3dm *.obj *.iges *.igs *.dxf *.ecto);;ECTOFORM Bundle (*.ecto);;3D Files (*.stl *.step *.stp *.3dm *.obj *.iges *.igs *.dxf);;STL Files (*.stl);;STEP Files (*.step *.stp);;3DM Files (*.3dm);;OBJ Files (*.obj);;IGES Files (*.iges *.igs);;DXF Files (*.dxf);;All Files (*)"
        )
        
        if file_path:
            logger.info(f"upload_stl_file: File selected: {file_path}")
            
            if file_path.lower().endswith('.ecto'):
                self._load_ecto_file(file_path)
                return
            
            file_ext = file_path.lower()
            if not (file_ext.endswith('.stl') or file_ext.endswith('.step') or file_ext.endswith('.stp') or file_ext.endswith('.3dm') or file_ext.endswith('.obj') or file_ext.endswith('.iges') or file_ext.endswith('.igs') or file_ext.endswith('.dxf')):
                logger.warning(f"upload_stl_file: Invalid file extension: {file_path}")
                QMessageBox.warning(
                    self,
                    "Invalid File",
                    "Please select a valid 3D file (.stl, .step, .stp, .3dm, .obj, .iges, .igs, .dxf, or .ecto extension)."
                )
                return
            
            # If current tab has a file, create a new tab; otherwise reuse empty tab
            tab = self._current_tab
            if tab and tab.file_path is not None:
                self._create_new_tab()
            
            logger.info("upload_stl_file: Loading 3D file into viewer...")
            self._load_file_into_current_tab(file_path, from_conversion=False)
        else:
            logger.info("upload_stl_file: File selection cancelled")
    
    def export_scaled_stl(self, file_path, scale_factor):
        """Export the current mesh scaled by the given factor."""
        logger.info(f"export_scaled_stl: Exporting scaled STL to {file_path} with scale {scale_factor}")
        
        vw = self.viewer_widget
        if not vw or not hasattr(vw, 'current_mesh') or vw.current_mesh is None:
            logger.error("export_scaled_stl: No mesh loaded")
            QMessageBox.warning(
                self,
                "No Mesh Loaded",
                "Please load an STL file first before exporting."
            )
            return
        
        try:
            scaled_mesh = MeshCalculator.scale_mesh(vw.current_mesh, scale_factor)
            
            if scaled_mesh is None:
                logger.error("export_scaled_stl: Failed to scale mesh")
                QMessageBox.critical(
                    self,
                    "Export Error",
                    "Failed to scale the mesh. Please try again."
                )
                return
            
            success = MeshCalculator.export_stl(scaled_mesh, file_path)
            
            if success:
                annotations = self.annotation_panel.export_annotations() if self.annotation_panel else []
                if annotations:
                    from core.annotation_exporter import AnnotationExporter
                    AnnotationExporter.save_annotations(
                        annotations, file_path, 
                        reader_mode=True,
                        bundle_images=True
                    )
                    logger.info(f"export_scaled_stl: Saved {len(annotations)} annotations with reader_mode")
                
                logger.info(f"export_scaled_stl: Successfully exported to {file_path}")
                msg = f"Scaled STL file exported successfully to:\n{file_path}"
                if annotations:
                    msg += f"\n\n{len(annotations)} annotations saved."
                QMessageBox.information(self, "Export Successful", msg)
            else:
                logger.error(f"export_scaled_stl: Failed to export to {file_path}")
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to export STL file to:\n{file_path}"
                )
        except Exception as e:
            logger.error(f"export_scaled_stl: Error during export: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Export Error",
                f"Error during export:\n{str(e)}"
            )
    
    def _load_annotations_for_file(self, file_path: str):
        """Load annotations for a file if they exist and handle reader mode."""
        try:
            from core.annotation_exporter import AnnotationExporter
            
            self._clear_all_annotations()
            
            self.toolbar.set_reader_mode(False)
            if self.annotation_panel:
                self.annotation_panel.set_reader_mode(False)
            
            if not AnnotationExporter.annotations_exist(file_path):
                return
            
            annotations, msg, reader_mode = AnnotationExporter.load_annotations(file_path)
            if annotations and self.annotation_panel:
                self.annotation_panel.load_annotations(annotations)
                
                if reader_mode:
                    self.toolbar.set_reader_mode(True)
                    self.annotation_panel.set_reader_mode(True)
                    self.annotation_panel.show()
                    logger.info(f"Reader Mode enabled for {file_path}")
                
                vw = self.viewer_widget
                for i, ann_data in enumerate(annotations):
                    ann_id = ann_data['id']
                    point = tuple(ann_data['point'])
                    is_validated = ann_data.get('is_validated', False)
                    is_read = ann_data.get('is_read', False)
                    if reader_mode:
                        color = '#1821b4' if is_read else '#36cd2e'
                    else:
                        color = '#1821b4' if is_validated else '#909d92'
                    if vw and hasattr(vw, 'add_annotation_marker'):
                        vw.add_annotation_marker(ann_id, point, color, display_date=str(i + 1))
                
                logger.info(f"Loaded {len(annotations)} annotations for {file_path} (reader_mode={reader_mode})")
                self._update_sidebar_annotation_count()
                
        except Exception as e:
            logger.warning(f"Failed to load annotations: {e}")
    
    def save_current_annotations(self):
        title = self.windowTitle()
        if " - " not in title:
            return False
        logger.info("save_current_annotations: Annotations will be saved on export")
        return True
    
    def _load_ecto_file(self, ecto_path: str):
        """Load an .ecto bundle file."""
        logger.info(f"_load_ecto_file: Loading .ecto file: {ecto_path}")
        
        try:
            from core.ecto_format import EctoFormat

            # Check if this is a technical overview .ecto
            if EctoFormat.is_technical_ecto(ecto_path):
                self._load_technical_ecto(ecto_path)
                return
            
            model_path, annotations, reader_mode, temp_dir, drawings = EctoFormat.import_ecto(ecto_path)
            
            if model_path is None:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to open .ecto file:\n{temp_dir}"
                )
                return
            
            # If current tab has a file, create a new tab
            tab = self._current_tab
            if tab and tab.file_path is not None:
                self._create_new_tab()
                tab = self._current_tab
            
            # Cleanup previous ecto temp dir for this tab
            if tab and tab.ecto_temp_dir:
                EctoFormat.cleanup_temp_dir(tab.ecto_temp_dir)
            if tab:
                tab.ecto_temp_dir = temp_dir
            
            vw = self.viewer_widget
            if vw is None:
                return
            
            success = vw.load_stl(model_path)
            
            if not success:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to load model from .ecto bundle"
                )
                EctoFormat.cleanup_temp_dir(temp_dir)
                if tab:
                    tab.ecto_temp_dir = None
                return
            
            filename = Path(ecto_path).stem
            display_name = f"{filename}.ecto"
            if tab:
                tab.file_path = ecto_path
                tab.filename = display_name
                self.tab_bar.setTabText(self.current_tab_index, _ecto_tab_caption(display_name))
            
            self.setWindowTitle(f"ECTOFORM - {display_name}")
            self.toolbar.set_loaded_filename(display_name)
            self.toolbar.set_stl_loaded(True)
            
            self._set_render_mode(self.toolbar.render_mode)
            
            if hasattr(vw, 'current_mesh'):
                mesh = vw.current_mesh
                if mesh is not None:
                    mesh_data = MeshCalculator.get_mesh_data(mesh)
                    if tab:
                        tab.sidebar_data = mesh_data
                        tab.mesh = mesh
                    self.sidebar_panel.update_dimensions(mesh_data, ecto_path)
            
            self._clear_all_annotations()
            
            self.toolbar.set_reader_mode(reader_mode)
            if self.annotation_panel:
                self.annotation_panel.set_reader_mode(reader_mode)
                self.annotation_panel.show()
            
            if annotations and self.annotation_panel:
                self.annotation_panel.load_annotations(annotations)
                
                for i, ann_data in enumerate(annotations):
                    ann_id = ann_data['id']
                    point = tuple(ann_data['point'])
                    if reader_mode:
                        is_read = ann_data.get('is_read', False)
                        color = '#1821b4' if is_read else '#36cd2e'
                    else:
                        is_validated = ann_data.get('is_validated', False)
                        color = '#1821b4' if is_validated else '#909d92'
                    if vw and hasattr(vw, 'add_annotation_marker'):
                        vw.add_annotation_marker(ann_id, point, color, display_date=str(i + 1))
                
                logger.info(f"_load_ecto_file: Loaded {len(annotations)} annotations (reader_mode={reader_mode})")
                self._update_sidebar_annotation_count()
            
            # Restore drawings ( strokes on the 3D model surface)
            if drawings and vw and hasattr(vw, 'restore_draw_strokes'):
                vw.restore_draw_strokes(drawings)
                logger.info(f"_load_ecto_file: Restored {len(drawings)} drawing strokes")
            
            logger.info(f"_load_ecto_file: Successfully loaded .ecto file")
            
        except Exception as e:
            logger.error(f"_load_ecto_file: Error loading .ecto file: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open .ecto file:\n{str(e)}"
            )
    
    def _load_technical_ecto(self, ecto_path: str):
        """Load a technical-overview .ecto file into the Technical Overview workspace."""
        from core.ecto_format import EctoFormat

        doc_path, annotations, metadata, passcode_hash, temp_dir = EctoFormat.import_technical(ecto_path)
        if doc_path is None:
            QMessageBox.critical(self, "Error", f"Failed to open technical .ecto:\n{temp_dir}")
            return

        # Switch to technical mode
        self._switch_mode("technical")

        # Load document + annotations
        self.technical_overview.load_from_ecto(doc_path, annotations or [], passcode_hash)

        # Load metadata into sidebar
        if metadata:
            self.technical_sidebar.set_metadata(metadata)

        # If passcode protected, prompt for passcode to unlock editing
        if passcode_hash:
            from ui.passcode_dialog import PasscodeDialog
            dlg = PasscodeDialog(mode='enter', stored_hash=passcode_hash, parent=self)
            if dlg.exec() == PasscodeDialog.Accepted:
                logger.info("Technical .ecto: passcode verified, edit mode enabled")
            else:
                # Lock editing: disable sidebar fields and annotation mode
                self.technical_sidebar.setEnabled(False)
                QMessageBox.information(self, "View Only",
                                        "You can view this file but editing is locked.\n"
                                        "Enter the correct passcode to edit.")

        self.setWindowTitle(f"ECTOFORM - {Path(ecto_path).name}")
        # Store temp dir for cleanup
        self._tech_ecto_temp_dir = temp_dir
        logger.info(f"_load_technical_ecto: Loaded {ecto_path}")

    def closeEvent(self, event):
        """Handle window close - prompt for unsaved annotations across all tabs, then cleanup."""
        # Check all tabs for unsaved annotations
        for i, tab in enumerate(self.tabs):
            if tab.annotation_panel is None:
                continue
            annotations = tab.annotation_panel.get_annotations()
            if annotations and not tab.annotations_exported:
                tab_name = tab.filename or 'Untitled'
                reply = QMessageBox.warning(
                    self,
                    "Unsaved Annotations",
                    f"Tab '{tab_name}' has {len(annotations)} annotation(s) that have not been exported.\n\n"
                    "Would you like to export them as .ecto before closing?\n\n"
                    "• Click 'Yes' to export first\n"
                    "• Click 'No' to close without exporting\n"
                    "• Click 'Cancel' to stay",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    event.ignore()
                    # Switch to that tab and export
                    self.tab_bar.setCurrentIndex(i)
                    self.sidebar_panel.export_as_ecto()
                    return
                if reply == QMessageBox.Cancel:
                    event.ignore()
                    return
        
        # Screenshot warning (second warning, after annotations)
        if len(self.screenshot_panel.screenshots) > 0:
            n = len(self.screenshot_panel.screenshots)
            msg = f"You have {n} screenshot(s) that have not been saved. They will be lost. Continue?"
            if not confirm_dialog(self, "Unsaved Screenshots", msg):
                event.ignore()
                return
        
        # Cleanup all ecto temp directories
        for tab in self.tabs:
            if tab.ecto_temp_dir:
                try:
                    from core.ecto_format import EctoFormat
                    EctoFormat.cleanup_temp_dir(tab.ecto_temp_dir)
                except Exception:
                    pass
        # Cleanup technical overview temp dir
        if hasattr(self, '_tech_ecto_temp_dir') and self._tech_ecto_temp_dir:
            try:
                from core.ecto_format import EctoFormat
                EctoFormat.cleanup_temp_dir(self._tech_ecto_temp_dir)
            except Exception:
                pass
        super().closeEvent(event)


def main():
    """Main function to run the application."""
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    window = STLViewerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
