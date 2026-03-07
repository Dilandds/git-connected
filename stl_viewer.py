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
    QMessageBox, QSplitter, QFrame, QApplication, QStackedWidget, QTabBar
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
from ui.styles import get_global_stylesheet, default_theme
from core.mesh_calculator import MeshCalculator
from ui.screenshot_panel import ScreenshotPanel

logger = logging.getLogger(__name__)


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
    """Holds all per-tab state: viewer, annotations, sidebar cache, mode flags."""
    file_path: Optional[str] = None
    viewer_widget: Any = None  # STLViewerWidget instance
    annotation_panel: Any = None  # AnnotationPanel instance
    sidebar_data: Optional[dict] = None  # cached mesh_data dict for sidebar
    mesh: Any = None  # current_mesh reference
    ruler_active: bool = False
    annotation_mode_active: bool = False
    annotations_exported: bool = False
    ecto_temp_dir: Optional[str] = None
    filename: Optional[str] = None  # display name for tab


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
        
        # Center window on screen
        screen = QApplication.primaryScreen().geometry()
        window_geometry = self.frameGeometry()
        window_geometry.moveCenter(screen.center())
        self.move(window_geometry.topLeft())
        
        logger.info("init_ui: Creating central widget...")
        central_widget = QWidget()
        central_widget.setStyleSheet(f"background-color: {default_theme.background};")
        self.setCentralWidget(central_widget)
        
        logger.info("init_ui: Creating main layout...")
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
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
        
        # ---- Tab Bar ----
        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("ectoTabBar")
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setMovable(False)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.tabCloseRequested.connect(self._on_tab_close_requested)
        # Add "+" button as the last tab (before connecting currentChanged so signal doesn't fire before _plus_tab_index exists)
        self._plus_tab_index = self.tab_bar.addTab("+")
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.tab_bar.setTabButton(self._plus_tab_index, QTabBar.RightSide, None)
        self.tab_bar.setTabButton(self._plus_tab_index, QTabBar.LeftSide, None)
        self.right_layout.addWidget(self.tab_bar)
        
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
        
        # ---- Stacked widgets for viewers and annotation panels ----
        self.viewer_stack = QStackedWidget()
        self.annotation_stack = QStackedWidget()
        
        viewer_h_layout = QHBoxLayout()
        viewer_h_layout.setContentsMargins(0, 0, 0, 0)
        viewer_h_layout.setSpacing(0)
        viewer_h_layout.addWidget(self.viewer_stack, 1)
        viewer_h_layout.addWidget(self.annotation_stack)
        
        viewer_container = QWidget()
        viewer_container.setLayout(viewer_h_layout)
        self.right_layout.addWidget(viewer_container, 1)
        
        # Add right container to splitter
        splitter.addWidget(right_container)
        
        logger.info("init_ui: Configuring splitter...")
        splitter.setSizes([200, 1000])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        
        logger.info("init_ui: Applying styling...")
        self.apply_styling()
        
        # Create initial empty tab
        self._create_new_tab()
        
        logger.info("init_ui: UI initialization complete")
    
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
        
        # Add to stacks
        self.viewer_stack.addWidget(tab.viewer_widget)
        self.annotation_stack.addWidget(tab.annotation_panel)
        
        # Add to tabs list
        self.tabs.append(tab)
        tab_index = len(self.tabs) - 1
        
        # Insert tab in tab bar (before the "+" tab)
        display_name = "Untitled"
        if file_path:
            display_name = Path(file_path).name
            tab.file_path = file_path
            tab.filename = display_name
        tab_bar_index = self.tab_bar.insertTab(self._plus_tab_index, display_name)
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
        
        # Show correct viewer and annotation panel
        self.viewer_stack.setCurrentWidget(tab.viewer_widget)
        self.annotation_stack.setCurrentWidget(tab.annotation_panel)
        
        # Update annotation panel visibility
        if tab.annotation_mode_active:
            tab.annotation_panel.show()
            self.annotation_stack.show()
        else:
            tab.annotation_panel.hide()
            # Only hide stack if no annotations visible
            if not tab.annotation_panel.isVisible():
                pass  # annotation_stack stays but panel is hidden
        
        # Update sidebar with this tab's data
        if tab.sidebar_data and tab.file_path:
            self.sidebar_panel.update_dimensions(tab.sidebar_data, tab.file_path)
            count = len(tab.annotation_panel.get_annotations())
            self.sidebar_panel.update_annotation_count(count)
        else:
            self.sidebar_panel.reset_all_data()
        
        # Update toolbar state
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
        
        logger.info(f"_on_tab_changed: Switched to tab {index} ({tab.filename or 'Untitled'})")
    
    def _save_current_tab_state(self):
        """Save mode flags from the current tab before switching."""
        tab = self._current_tab
        if tab is None:
            return
        tab.ruler_active = self.toolbar.ruler_mode_enabled
        tab.annotation_mode_active = self.toolbar.annotation_mode_enabled
    
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
        
        # Destroy widgets
        tab.viewer_widget.deleteLater()
        tab.annotation_panel.deleteLater()
        
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
        self.toolbar.toggle_annotation.connect(self._toggle_annotation_mode)
        self.toolbar.load_file.connect(self.upload_stl_file)
        self.toolbar.clear_model.connect(self._clear_current_model)
    
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
            self.tab_bar.setTabText(self.current_tab_index, "Untitled")
        
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
        
        self._load_file_into_current_tab(file_path)
    
    def _load_file_into_current_tab(self, file_path: str):
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
            
            # Update tab bar text
            self.tab_bar.setTabText(self.current_tab_index, filename)
            
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
        """Reset view to default isometric rotation."""
        vw = self.viewer_widget
        if vw is None:
            return
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
                    self.annotation_panel.show()
                    if self.toolbar.ruler_mode_enabled:
                        self._exit_ruler_mode()
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
        if vw and hasattr(vw, 'reframe_for_viewport'):
            QTimer.singleShot(50, vw.reframe_for_viewport)
        self.toolbar.reset_annotation_state()
        logger.info("_exit_annotation_mode: Annotation mode disabled, annotations kept")
    
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
            "All Supported (*.stl *.step *.stp *.3dm *.obj *.iges *.igs *.ecto);;ECTOFORM Bundle (*.ecto);;3D Files (*.stl *.step *.stp *.3dm *.obj *.iges *.igs);;STL Files (*.stl);;STEP Files (*.step *.stp);;3DM Files (*.3dm);;OBJ Files (*.obj);;IGES Files (*.iges *.igs);;All Files (*)"
        )
        
        if file_path:
            logger.info(f"upload_stl_file: File selected: {file_path}")
            
            if file_path.lower().endswith('.ecto'):
                self._load_ecto_file(file_path)
                return
            
            file_ext = file_path.lower()
            if not (file_ext.endswith('.stl') or file_ext.endswith('.step') or file_ext.endswith('.stp') or file_ext.endswith('.3dm') or file_ext.endswith('.obj') or file_ext.endswith('.iges') or file_ext.endswith('.igs')):
                logger.warning(f"upload_stl_file: Invalid file extension: {file_path}")
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
            
            logger.info("upload_stl_file: Loading 3D file into viewer...")
            self._load_file_into_current_tab(file_path)
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
            
            model_path, annotations, reader_mode, temp_dir = EctoFormat.import_ecto(ecto_path)
            
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
                self.tab_bar.setTabText(self.current_tab_index, display_name)
            
            self.setWindowTitle(f"ECTOFORM - {display_name}")
            self.toolbar.set_loaded_filename(display_name)
            self.toolbar.set_stl_loaded(True)
            
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
            
            logger.info(f"_load_ecto_file: Successfully loaded .ecto file")
            
        except Exception as e:
            logger.error(f"_load_ecto_file: Error loading .ecto file: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open .ecto file:\n{str(e)}"
            )
    
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
        
        # Cleanup all ecto temp directories
        for tab in self.tabs:
            if tab.ecto_temp_dir:
                try:
                    from core.ecto_format import EctoFormat
                    EctoFormat.cleanup_temp_dir(tab.ecto_temp_dir)
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
