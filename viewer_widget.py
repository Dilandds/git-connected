"""
3D Viewer Widget using PyVista for STL file visualization.
"""
import sys
import os
import logging
import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QStackedLayout, QGridLayout, QFrame
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from ui.drop_zone_overlay import DropZoneOverlay
from ui.orientation_gizmo import OrientationGizmoWidget

# Set PyVista environment variables for macOS compatibility
os.environ.setdefault('PYVISTA_OFF_SCREEN', 'false')
os.environ.setdefault('PYVISTA_USE_PANEL', 'false')

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


def _pyvista_to_trimesh(pv_mesh):
    """Convert PyVista PolyData to trimesh.Trimesh for component splitting."""
    import trimesh
    try:
        pv_mesh = pv_mesh.triangulate()
    except Exception:
        pass
    verts = np.asarray(pv_mesh.points, dtype=np.float64)
    faces_arr = pv_mesh.faces
    if len(faces_arr) >= 4 and len(faces_arr) % 4 == 0:
        faces = faces_arr.reshape(-1, 4)[:, 1:4]
    else:
        idx = 0
        faces_list = []
        while idx < len(faces_arr):
            n = int(faces_arr[idx])
            idx += 1
            if n == 3 and idx + 3 <= len(faces_arr):
                faces_list.append([faces_arr[idx], faces_arr[idx + 1], faces_arr[idx + 2]])
            idx += n
        faces = np.array(faces_list, dtype=np.int32) if faces_list else np.empty((0, 3), dtype=np.int32)
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


def _trimesh_to_pyvista(tm):
    """Convert trimesh.Trimesh to PyVista PolyData."""
    import trimesh
    vertices = np.asarray(tm.vertices, dtype=np.float64)
    faces = np.asarray(tm.faces, dtype=np.int32)
    cells = np.column_stack([np.full(len(faces), 3), faces]).ravel().astype(np.int32)
    return pv.PolyData(vertices, cells)


def _split_reasonable_components(source_mesh):
    """Split mesh into connected components, with guardrails against triangle-explosion meshes."""
    import trimesh
    try:
        components = list(source_mesh.split(only_watertight=False))
    except Exception as e:
        logger.info(f"parts_debug: _split_reasonable_components split() failed: {e}, returning single mesh")
        return [source_mesh]
    components = [
        c for c in components
        if isinstance(c, trimesh.Trimesh) and len(c.vertices) > 0 and len(c.faces) > 0
    ]
    logger.info(f"parts_debug: trimesh.split returned {len(components)} components")
    if len(components) <= 1:
        logger.info(f"parts_debug: <=1 components, returning as-is")
        return components if components else [source_mesh]
    face_counts = [len(c.faces) for c in components]
    median_faces = float(np.median(face_counts))
    logger.info(f"parts_debug: median_faces={median_faces:.1f}, max_components={max(200, int(len(source_mesh.faces) * 0.25))}")
    if median_faces < 10:
        logger.info(f"parts_debug: median_faces<10 (triangle explosion), returning single mesh")
        return [source_mesh]
    if len(components) > 2000:
        logger.info(f"parts_debug: >2000 components, returning single mesh")
        return [source_mesh]
    if len(components) > max(200, int(len(source_mesh.faces) * 0.25)):
        logger.info(f"parts_debug: exceeds guardrail limit, returning single mesh")
        return [source_mesh]
    logger.info(f"parts_debug: keeping {len(components)} components")
    return components


class STLViewerWidget(QWidget):
    """PyVista-based 3D viewer widget for displaying STL files."""
    
    # Signals for drag-and-drop functionality
    file_dropped = pyqtSignal(str)
    click_to_upload = pyqtSignal()
    drop_error = pyqtSignal(str)
    
    def __init__(self, parent=None):
        debug_print("STLViewerWidget: Initializing...")
        logger.info("STLViewerWidget: Initializing...")
        super().__init__(parent)
        debug_print("STLViewerWidget: Parent initialized")
        logger.info("STLViewerWidget: Parent initialized")
        
        # Set up stacked layout for overlay
        self.layout = QStackedLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setStackingMode(QStackedLayout.StackAll)
        
        # Container for the 3D viewer
        self.viewer_container = QWidget()
        self.viewer_layout = QGridLayout(self.viewer_container)
        self.viewer_layout.setContentsMargins(0, 0, 0, 0)
        
        # No placeholder - drop overlay handles empty state
        
        self.layout.addWidget(self.viewer_container)
        
        # Create drop zone overlay (shown when no model loaded)
        self.drop_overlay = DropZoneOverlay()
        self.drop_overlay.file_dropped.connect(self._on_file_dropped)
        self.drop_overlay.click_to_upload.connect(self._on_click_upload)
        self.drop_overlay.error_occurred.connect(self._on_drop_error)
        self.layout.addWidget(self.drop_overlay)
        
        # Object control overlay (gizmo + label, shown in annotation mode)
        self._object_control_overlay = QFrame()
        self._object_control_overlay.setObjectName("ObjectControlOverlay")
        self._object_control_overlay.setStyleSheet("""
            QFrame#ObjectControlOverlay {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #050B1A, stop:0.45 #0A1838, stop:1 #1B4FA0);
                border-radius: 14px;
                border: 2px solid #0B1A33;
            }
            QLabel#ObjectControlTitle {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1A2A45, stop:1 #0E1A30);
                color: #FFFFFF;
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #2A3F60;
                border-radius: 10px;
                padding: 5px 10px;
                letter-spacing: 0.5px;
            }
        """)
        overlay_layout = QVBoxLayout(self._object_control_overlay)
        overlay_layout.setContentsMargins(8, 8, 8, 10)
        overlay_layout.setSpacing(6)
        self._object_control_title = QLabel("3D Control")
        self._object_control_title.setObjectName("ObjectControlTitle")
        self._object_control_title.setAlignment(Qt.AlignCenter)
        overlay_layout.addWidget(self._object_control_title)
        self._orientation_gizmo = OrientationGizmoWidget(self._object_control_overlay)
        overlay_layout.addWidget(self._orientation_gizmo, 0, Qt.AlignCenter)
        self._object_control_overlay.setFixedSize(
            OrientationGizmoWidget.SIZE + 30,
            OrientationGizmoWidget.SIZE + 60
        )
        self._orientation_gizmo.rotation_delta.connect(self._on_gizmo_rotate)
        self._object_control_overlay.hide()
        
        # Show overlay on top initially
        self.layout.setCurrentWidget(self.drop_overlay)
        
        # Plotter will be initialized later
        self.plotter = None
        self.current_mesh = None
        self.current_actor = None  # Track the mesh actor to remove it specifically
        self._mesh_parts = []  # list of {'id', 'name', 'actor', 'visible', 'face_count'} for Parts panel
        self._orientation_widget = None  # Bottom-right rotation gizmo (annotation mode only)
        self._initialized = False
        self._model_loaded = False
        
        # Ruler/measurement mode state
        self.ruler_mode = False
        self.measurement_points = []
        self.measurement_actors = []  # Track measurement visualization actors
        self._ruler_unit = "mm"  # Current measurement unit

        # Ruler picking internals (VTK observer-based; more reliable than PyVista helpers in QtInteractor)
        self._ruler_click_observer_id = None
        self._ruler_picker = None
        self._ruler_mouse_move_observer_id = None
        self._preview_line_actor = None
        
        # Annotation mode state
        self.annotation_mode = False
        self.annotations = []  # List of annotation data: {'id': int, 'point': tuple, 'actor': vtk_actor}
        self.annotation_actors = []  # Track annotation marker actors
        self._annotation_click_observer_id = None
        self._annotation_picker = None
        self._annotation_callback = None  # Callback when point is picked for annotation
        self._annotation_visibility_timer = QTimer(self)
        self._annotation_visibility_timer.setInterval(250)  # Throttled to avoid slowdown during rotation
        self._annotation_visibility_timer.timeout.connect(self._update_annotation_label_visibility)
        self._last_visibility_cam_hash = None  # Skip update if camera unchanged

        debug_print("STLViewerWidget: Basic initialization complete, QtInteractor will be created after window is shown")
        logger.info("STLViewerWidget: Basic initialization complete, QtInteractor will be created after window is shown")
    
    def showEvent(self, event):
        """Initialize QtInteractor when widget is first shown."""
        super().showEvent(event)
        
        if not self._initialized:
            debug_print("STLViewerWidget: showEvent triggered, scheduling QtInteractor initialization...")
            logger.info("STLViewerWidget: showEvent triggered, scheduling QtInteractor initialization...")
            # Use QTimer with longer delay to ensure window is fully rendered
            # Process events multiple times to ensure everything is ready
            QTimer.singleShot(500, self._initialize_plotter)
    
    def resizeEvent(self, event):
        """Handle resize - force VTK refresh on Windows (fixes black screen)."""
        if sys.platform == 'win32' and self.plotter is not None:
            try:
                # vtkPropPicker.Pick forces display update and eliminates black frame (known workaround)
                import vtk
                picker = vtk.vtkPropPicker()
                picker.Pick(0, 0, 0, self.plotter.renderer)
            except Exception as e:
                logger.debug(f"resize pick: {e}")
            try:
                # Re-apply background color and render
                bg = getattr(self.plotter, 'background_color', 'white')
                self.plotter.background_color = bg
                ren = getattr(self.plotter, 'renderer', None)
                if ren is not None and hasattr(ren, 'ResetCameraClippingRange'):
                    ren.ResetCameraClippingRange()
                self._sync_overlay_viewport()
                self.plotter.render()
            except Exception as e:
                logger.debug(f"resize render: {e}")
        super().resizeEvent(event)
    
    def _initialize_plotter(self):
        """Initialize the PyVista plotter (called after window is shown)."""
        if self._initialized:
            return
        
        # Process events before starting initialization
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()
        
        # Ensure widget is visible and has a window
        if not self.isVisible():
            debug_print("STLViewerWidget: Widget not visible yet, retrying in 200ms...")
            logger.warning("STLViewerWidget: Widget not visible yet, retrying...")
            QTimer.singleShot(200, self._initialize_plotter)
            return
        
        # Check if widget has a valid window handle
        if not self.window().isVisible():
            debug_print("STLViewerWidget: Parent window not visible yet, retrying in 200ms...")
            logger.warning("STLViewerWidget: Parent window not visible yet, retrying...")
            QTimer.singleShot(200, self._initialize_plotter)
            return
            
        try:
            debug_print("STLViewerWidget: Starting plotter initialization...")
            logger.info("STLViewerWidget: Starting plotter initialization...")
            logger.info(f"STLViewerWidget: PyVista version: {pv.__version__}")
            debug_print(f"STLViewerWidget: PyVista version: {pv.__version__}")
            debug_print(f"STLViewerWidget: Widget visible: {self.isVisible()}, Window visible: {self.window().isVisible()}")
            logger.info(f"STLViewerWidget: Widget visible: {self.isVisible()}, Window visible: {self.window().isVisible()}")
            safe_flush(sys.stderr)
            
            debug_print("STLViewerWidget: Creating QtInteractor (this may take a moment)...")
            logger.info("STLViewerWidget: Creating QtInteractor (this may take a moment)...")
            safe_flush(sys.stderr)
            
            # Process events multiple times before creating QtInteractor
            for _ in range(3):
                QApplication.processEvents()
            
            # Initialize PyVista plotter with Qt backend
            # This might block, but we've processed events first
            self.plotter = QtInteractor(self.viewer_container)
            
            debug_print("STLViewerWidget: QtInteractor created successfully")
            logger.info("STLViewerWidget: QtInteractor created successfully")
            safe_flush(sys.stderr)
            
            # Process events after QtInteractor creation
            QApplication.processEvents()
            
            # Add plotter to viewer container layout
            self.viewer_layout.addWidget(self.plotter.interactor, 0, 0)
            # Add 3D control overlay in bottom-right (on top of plotter)
            self.viewer_layout.addWidget(
                self._object_control_overlay, 0, 0, 1, 1,
                Qt.AlignRight | Qt.AlignBottom
            )
            QApplication.processEvents()
            
            # Windows: WA_PaintOnScreen=False can reduce black screen during resize/maximize
            if sys.platform == 'win32':
                try:
                    self.plotter.interactor.setAttribute(Qt.WA_PaintOnScreen, False)
                except Exception:
                    pass
            
            debug_print("STLViewerWidget: Configuring plotter settings...")
            logger.info("STLViewerWidget: Configuring plotter settings...")
            safe_flush(sys.stderr)
            
            # Configure plotter for smooth interaction with large models
            # Windows: FXAA for reliable edge smoothing; Mac/Linux: SSAA for best quality
            try:
                aa_type = 'fxaa' if sys.platform == 'win32' else 'ssaa'
                self.plotter.enable_anti_aliasing(aa_type)
                debug_print(f"STLViewerWidget: Anti-aliasing enabled ({aa_type})")
                logger.info(f"STLViewerWidget: Anti-aliasing enabled ({aa_type})")
            except Exception as e:
                debug_print(f"STLViewerWidget: Could not enable anti-aliasing: {e}")
                logger.warning(f"STLViewerWidget: Could not enable anti-aliasing: {e}")
            
            # Shadows disabled to reduce excessive shadowing while preserving 3D look
            # try:
            #     self.plotter.enable_shadows()
            #     debug_print("STLViewerWidget: Shadows enabled")
            #     logger.info("STLViewerWidget: Shadows enabled")
            # except Exception as e:
            #     debug_print(f"STLViewerWidget: Could not enable shadows: {e}")
            #     logger.warning(f"STLViewerWidget: Could not enable shadows: {e}")
            
            debug_print("STLViewerWidget: Initializing empty scene...")
            logger.info("STLViewerWidget: Initializing empty scene...")
            safe_flush(sys.stderr)
            
            # Initialize with empty scene - do this carefully to avoid hangs
            try:
                self.plotter.background_color = 'white'
                QApplication.processEvents()
                debug_print("STLViewerWidget: Background color set")
                logger.info("STLViewerWidget: Background color set")
            except Exception as e:
                debug_print(f"STLViewerWidget: Could not set background color: {e}")
                logger.warning(f"STLViewerWidget: Could not set background color: {e}")
            
            QApplication.processEvents()
            
            # Add axes - this can sometimes hang, so do it carefully
            try:
                debug_print("STLViewerWidget: Adding axes...")
                logger.info("STLViewerWidget: Adding axes...")
                safe_flush(sys.stderr)
                self.plotter.add_axes()
                QApplication.processEvents()
                debug_print("STLViewerWidget: Axes added")
                logger.info("STLViewerWidget: Axes added")
            except Exception as e:
                debug_print(f"STLViewerWidget: Could not add axes: {e}")
                logger.warning(f"STLViewerWidget: Could not add axes: {e}")
                # Continue anyway - axes are optional
            
            QApplication.processEvents()
            
            # Don't force render immediately - let it render naturally
            # The render() call can block on macOS
            debug_print("STLViewerWidget: Scene configured, will render on next event loop")
            logger.info("STLViewerWidget: Scene configured, will render on next event loop")
            
            debug_print("STLViewerWidget: Empty scene initialized")
            logger.info("STLViewerWidget: Empty scene initialized")
            
            self._initialized = True
            debug_print("STLViewerWidget: QtInteractor initialization complete")
            logger.info("STLViewerWidget: QtInteractor initialization complete")
            safe_flush(sys.stderr)
            
            # Final event processing - multiple times to ensure UI updates
            for _ in range(5):
                QApplication.processEvents()
            
            # Update the widget to ensure it's visible
            self.update()
            self.repaint()
            QApplication.processEvents()
            
            debug_print("STLViewerWidget: All initialization complete, widget should be functional")
            logger.info("STLViewerWidget: All initialization complete, widget should be functional")
            safe_flush(sys.stderr)
            
        except Exception as e:
            debug_print(f"STLViewerWidget: ERROR during plotter initialization: {e}")
            logger.error(f"STLViewerWidget: Error during plotter initialization: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            # Don't raise - allow the app to continue
    
    def load_stl(self, file_path):
        """
        Load and display an STL or STEP file.
        
        Args:
            file_path (str): Path to the STL or STEP file
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"load_stl: Starting to load file: {file_path}")
        
        # Wait for plotter to be initialized if not ready
        if not self._initialized or self.plotter is None:
            logger.warning("load_stl: Plotter not initialized yet, waiting...")
            # Wait a bit for initialization
            from PyQt5.QtWidgets import QApplication
            for _ in range(50):  # Wait up to 5 seconds
                QApplication.processEvents()
                if self._initialized and self.plotter is not None:
                    break
                import time
                time.sleep(0.1)
            
            if not self._initialized or self.plotter is None:
                logger.error("load_stl: Plotter failed to initialize")
                return False
        
        try:
            # Remove previous mesh actor(s) if they exist
            def _remove_previous_mesh():
                if self._mesh_parts:
                    for p in self._mesh_parts:
                        try:
                            self.plotter.remove_actor(p['actor'])
                        except Exception:
                            pass
                    self._mesh_parts = []
                elif self.current_actor is not None:
                    try:
                        self.plotter.remove_actor(self.current_actor)
                    except Exception as e:
                        logger.warning(f"load_stl: Could not remove actor, using clear: {e}")
                        self.plotter.clear()
                        self.plotter.add_axes()
                        self._restore_renderer_settings()
                        return
                elif self.current_mesh is not None:
                    self.plotter.clear()
                    self.plotter.add_axes()
                self.current_actor = None
                self._restore_renderer_settings()

            if self.current_actor is not None or self._mesh_parts or self.current_mesh is not None:
                logger.info("load_stl: Removing previous mesh...")
                _remove_previous_mesh()
            
            # Detect file format and load accordingly
            file_ext = file_path.lower()
            if file_ext.endswith('.step') or file_ext.endswith('.stp'):
                logger.info("load_stl: Detected STEP file, loading with StepLoader...")
                from core.step_loader import StepLoader
                try:
                    mesh = StepLoader.load_step(file_path)
                    logger.info(f"load_stl: STEP file loaded successfully. Mesh info: {mesh}")
                except Exception as e:
                    logger.error(f"load_stl: Failed to load STEP file: {e}", exc_info=True)
                    raise
            elif file_ext.endswith('.3dm'):
                logger.info("load_stl: Detected 3DM file, loading with Rhino3dmLoader...")
                from core.rhino3dm_loader import Rhino3dmLoader
                try:
                    mesh = Rhino3dmLoader.load_3dm(file_path)
                    logger.info(f"load_stl: 3DM file loaded successfully. Mesh info: {mesh}")
                except Exception as e:
                    logger.error(f"load_stl: Failed to load 3DM file: {e}", exc_info=True)
                    raise
            elif file_ext.endswith('.obj'):
                logger.info("load_stl: Detected OBJ file, attempting to load...")
                mesh = None
                load_error = None
                
                # Try PyVista first (fastest)
                try:
                    logger.info("load_stl: Trying PyVista OBJ reader...")
                    mesh = pv.read(file_path)
                    logger.info(f"load_stl: PyVista read completed. Mesh info: {mesh}")
                    
                    # Check if mesh is valid
                    if mesh is not None and mesh.n_points > 0:
                        logger.info("load_stl: PyVista successfully loaded OBJ file")
                    else:
                        logger.warning("load_stl: PyVista loaded empty mesh, trying meshio fallback...")
                        mesh = None  # Will trigger fallback
                except Exception as e:
                    logger.warning(f"load_stl: PyVista failed to load OBJ: {e}, trying meshio fallback...")
                    load_error = str(e)
                    mesh = None
                
                # Fallback to meshio if PyVista failed or produced empty mesh
                meshio_error = None
                if mesh is None or mesh.n_points == 0:
                    try:
                        logger.info("load_stl: Trying meshio OBJ reader...")
                        import meshio
                        meshio_mesh = meshio.read(file_path)
                        logger.info(f"load_stl: meshio read completed. Points: {len(meshio_mesh.points)}, Cells: {len(meshio_mesh.cells)}")
                        
                        # Convert meshio mesh to PyVista
                        if len(meshio_mesh.points) == 0:
                            raise ValueError("meshio loaded OBJ but found no points")
                        
                        points = meshio_mesh.points
                        
                        # Find triangle cells (most common for OBJ)
                        cells = None
                        cell_type = None
                        for cell_block in meshio_mesh.cells:
                            if cell_block.type == "triangle":
                                cells = cell_block.data
                                cell_type = "triangle"
                                break
                        
                        # If no triangles, try other cell types
                        if cells is None:
                            if len(meshio_mesh.cells) > 0:
                                cell_block = meshio_mesh.cells[0]
                                cells = cell_block.data
                                cell_type = cell_block.type
                                logger.warning(f"load_stl: Using cell type {cell_type} (not triangles)")
                            else:
                                raise ValueError("meshio loaded OBJ but found no cells")
                        
                        # Create PyVista mesh
                        if cell_type == "triangle":
                            mesh = pv.PolyData(points, cells)
                        else:
                            # For other cell types, create UnstructuredGrid and extract surface
                            unstructured = pv.UnstructuredGrid(cells, cell_type, points)
                            mesh = unstructured.extract_surface()
                        
                        logger.info(f"load_stl: Converted meshio mesh to PyVista. Points: {mesh.n_points}, Cells: {mesh.n_cells}")
                    except ImportError:
                        meshio_error = "meshio is not available"
                        logger.warning(f"load_stl: {meshio_error}, will try custom parser...")
                    except ValueError as e:
                        error_str = str(e)
                        # Check if this is a texture coordinate mismatch error
                        if "len(points)" in error_str and "point_data" in error_str:
                            meshio_error = f"meshio texture coordinate mismatch: {error_str}"
                            logger.warning(f"load_stl: {meshio_error}, will try custom parser...")
                        else:
                            # Other ValueError from meshio - re-raise
                            meshio_error = error_str
                            raise
                    except Exception as e:
                        meshio_error = str(e)
                        logger.warning(f"load_stl: meshio failed: {meshio_error}, will try custom parser...")
                
                # Third fallback: custom OBJ parser for files with texture coordinate mismatches
                if (mesh is None or mesh.n_points == 0) and meshio_error:
                    try:
                        logger.info("load_stl: Trying custom OBJ parser (handles texture coordinate mismatches)...")
                        from core.obj_loader import ObjLoader
                        mesh = ObjLoader.load_obj(file_path)
                        logger.info(f"load_stl: Custom OBJ parser successfully loaded file. Points: {mesh.n_points}, Cells: {mesh.n_cells}")
                    except ImportError:
                        error_msg = "OBJ file could not be loaded. All loaders failed (PyVista, meshio, and custom parser unavailable)."
                        if load_error:
                            error_msg += f" PyVista error: {load_error}."
                        if meshio_error:
                            error_msg += f" meshio error: {meshio_error}."
                        logger.error(f"load_stl: {error_msg}")
                        raise ValueError(error_msg)
                    except Exception as e:
                        error_msg = "OBJ file could not be loaded with any available method (PyVista, meshio, or custom parser)."
                        if load_error:
                            error_msg += f" PyVista error: {load_error}."
                        if meshio_error:
                            error_msg += f" meshio error: {meshio_error}."
                        error_msg += f" Custom parser error: {str(e)}"
                        logger.error(f"load_stl: {error_msg}")
                        raise ValueError(error_msg)
                
                # Final validation
                if mesh is None or mesh.n_points == 0:
                    error_msg = "OBJ file loaded but contains no geometry (zero points). The file may be corrupted or in an unsupported format."
                    if load_error:
                        error_msg += f" Reader error: {load_error}"
                    logger.error(f"load_stl: {error_msg}")
                    raise ValueError(error_msg)
            elif file_ext.endswith('.iges') or file_ext.endswith('.igs'):
                logger.info("load_stl: Detected IGES file, loading with IgesLoader...")
                from core.iges_loader import IgesLoader
                try:
                    mesh = IgesLoader.load_iges(file_path)
                    logger.info(f"load_stl: IGES file loaded successfully. Mesh info: {mesh}")
                except Exception as e:
                    logger.error(f"load_stl: Failed to load IGES file: {e}", exc_info=True)
                    raise
            elif file_ext.endswith('.dxf'):
                logger.info("load_stl: Detected DXF file, loading with DxfLoader...")
                from core.dxf_loader import DxfLoader
                try:
                    mesh = DxfLoader.load_dxf(file_path)
                    logger.info(f"load_stl: DXF file loaded successfully. Mesh info: {mesh}")
                except Exception as e:
                    logger.error(f"load_stl: Failed to load DXF file: {e}", exc_info=True)
                    raise
            else:
                logger.info("load_stl: Reading STL file with PyVista...")
                # Read STL file using PyVista
                mesh = pv.read(file_path)
                logger.info(f"load_stl: STL file read successfully. Mesh info: {mesh}")
            
            # Check if this is the first mesh load (before we update current_mesh)
            is_first_load = (self.current_mesh is None)
            
            # Validate mesh is not empty before proceeding
            if mesh is None:
                error_msg = "Failed to load mesh: file returned None. The file may be corrupted or in an unsupported format."
                logger.error(f"load_stl: {error_msg}")
                raise ValueError(error_msg)
            
            if mesh.n_points == 0:
                error_msg = f"Loaded mesh contains no geometry (zero points). The file may be corrupted, empty, or in an unsupported format."
                logger.error(f"load_stl: {error_msg}")
                raise ValueError(error_msg)
            
            logger.info(f"load_stl: Mesh validated - {mesh.n_points} points, {mesh.n_cells} cells")
            
            # Store the original mesh for volume/dimensions (before splitting)
            self.current_mesh = mesh.copy()
            
            # Split into connected components for Parts panel (multi-part support)
            from pathlib import Path
            sub_meshes = []
            try:
                logger.info(f"parts_debug: Converting PyVista mesh to trimesh (points={mesh.n_points}, cells={mesh.n_cells})")
                mesh_tri = _pyvista_to_trimesh(mesh)
                logger.info(f"parts_debug: trimesh has {len(mesh_tri.vertices)} verts, {len(mesh_tri.faces)} faces")
                components = _split_reasonable_components(mesh_tri)
                fname = Path(file_path).stem if file_path else "Part"
                if len(components) > 1:
                    sub_meshes = [(f"{fname} #{i + 1}", c) for i, c in enumerate(components)]
                    logger.info(f"parts_debug: Using {len(sub_meshes)} components from split")
                else:
                    sub_meshes = [(fname, mesh_tri)]
                    logger.info(f"parts_debug: Single component, using whole mesh as part '{fname}'")
            except Exception as e:
                logger.warning(f"load_stl: Could not split components: {e}, using single part")
                try:
                    mesh_tri = _pyvista_to_trimesh(mesh)
                    sub_meshes = [(Path(file_path).stem if file_path else "Part", mesh_tri)]
                except Exception:
                    sub_meshes = [(Path(file_path).stem if file_path else "Part", _pyvista_to_trimesh(mesh))]

            logger.info(f"load_stl: Built {len(sub_meshes)} part(s) for panel: {[(n, len(t.faces)) for n, t in sub_meshes]}")

            self._restore_renderer_settings()
            self._mesh_parts = []
            mesh_params = dict(
                show_edges=False,
                smooth_shading=False,
                ambient=0.7,
                diffuse=0.4,
                specular=0.2,
                specular_power=20
            )
            for part_idx, (part_name, part_tri) in enumerate(sub_meshes):
                part_pv = _trimesh_to_pyvista(part_tri)
                try:
                    if not part_pv.is_all_triangles():
                        part_pv = part_pv.triangulate()
                except Exception:
                    pass
                try:
                    part_pv.compute_normals(inplace=True, point_normals=False, cell_normals=True)
                except Exception:
                    pass
                actor = self.plotter.add_mesh(part_pv, color='lightblue', **mesh_params)
                self._mesh_parts.append({
                    'id': part_idx,
                    'name': part_name,
                    'actor': actor,
                    'visible': True,
                    'face_count': len(part_tri.faces),
                })
            self.current_actor = self._mesh_parts[0]['actor'] if self._mesh_parts else None
            logger.info(f"load_stl: Mesh parts added to plotter, _mesh_parts={len(self._mesh_parts)}")
            # Ensure renderer settings are still active after adding mesh
            # This preserves visual quality when uploading files multiple times
            self._restore_renderer_settings()
            
            # Ensure axes are present (only add on first load)
            if is_first_load:
                self.plotter.add_axes()
            
            logger.info("load_stl: Resetting camera...")
            # Fit view to show entire model
            self.plotter.reset_camera()
            
            # Force renderer update to ensure consistent appearance
            # Explicitly render on Windows to ensure detail is visible
            from PyQt5.QtWidgets import QApplication
            import sys
            try:
                # Force render update, especially important on Windows
                self.plotter.render()
                logger.info("load_stl: Renderer updated explicitly")
            except Exception as e:
                logger.warning(f"load_stl: Could not force render: {e}, continuing anyway")
            
            QApplication.processEvents()
            logger.info("load_stl: STL file loaded successfully")
            
            # Hide overlay when model is loaded
            self._model_loaded = True
            self._show_overlay(False)

            return True
            
        except Exception as e:
            logger.error(f"load_stl: Error loading STL file: {e}", exc_info=True)
            return False
    
    def clear_viewer(self):
        """Clear the 3D viewer."""
        if self.plotter is None:
            return
        logger.info("clear_viewer: Clearing viewer...")
        # Remove orientation gizmo if present
        self._remove_orientation_gizmo()
        # Remove mesh actor(s)
        if self._mesh_parts:
            for p in self._mesh_parts:
                try:
                    self.plotter.remove_actor(p['actor'])
                except Exception:
                    pass
            self._mesh_parts = []
        elif self.current_actor is not None:
            try:
                self.plotter.remove_actor(self.current_actor)
            except Exception:
                pass
        self.plotter.clear()
        self.plotter.add_axes()
        self._orientation_widget = None  # Cleared with plotter
        
        # Restore renderer settings after clearing
        self._restore_renderer_settings()
        
        self.current_mesh = None
        self.current_actor = None
        self._model_loaded = False
        # Show overlay again when cleared
        self._show_overlay(True)
        logger.info("clear_viewer: Viewer cleared")
    
    def _restore_renderer_settings(self):
        """Restore renderer settings after clearing to maintain visual quality."""
        if self.plotter is None:
            return
        
        try:
            # Re-enable anti-aliasing for sharpness
            # Windows: FXAA for reliable edge smoothing; Mac/Linux: SSAA for best quality
            aa_type = 'fxaa' if sys.platform == 'win32' else 'ssaa'
            self.plotter.enable_anti_aliasing(aa_type)
            logger.info(f"_restore_renderer_settings: Anti-aliasing restored ({aa_type})")
        except Exception as e:
            logger.warning(f"_restore_renderer_settings: Could not restore anti-aliasing: {e}")
        
        # Restore lighting settings for consistent visual quality
        try:
            # Remove existing lights and add fresh default lighting
            self.plotter.remove_all_lights()
            # Add a light kit for balanced illumination (like initial state)
            light = pv.Light(position=(1, 1, 1), light_type='scene light')
            light.intensity = 1.0
            self.plotter.add_light(light)
            
            # Add fill light from opposite side for softer shadows
            fill_light = pv.Light(position=(-1, -0.5, 0.5), light_type='scene light')
            fill_light.intensity = 0.4
            self.plotter.add_light(fill_light)
            
            logger.info("_restore_renderer_settings: Lighting restored")
        except Exception as e:
            logger.warning(f"_restore_renderer_settings: Could not restore lighting: {e}")
        
        # Preserve background color
        try:
            self.plotter.background_color = 'white'
            logger.debug("_restore_renderer_settings: Background color restored")
        except Exception as e:
            logger.debug(f"_restore_renderer_settings: Could not restore background color: {e}")
        
        # Force renderer update to ensure settings take effect
        try:
            self.plotter.render()
            logger.debug("_restore_renderer_settings: Renderer updated")
        except Exception as e:
            logger.debug(f"_restore_renderer_settings: Could not force render: {e}")
    
    def _on_file_dropped(self, file_path: str):
        """Handle file dropped on overlay."""
        self.file_dropped.emit(file_path)
    
    def _on_click_upload(self):
        """Handle click on overlay to upload."""
        self.click_to_upload.emit()
    
    def _on_drop_error(self, error_msg: str):
        """Handle drop error."""
        self.drop_error.emit(error_msg)
    
    def _show_overlay(self, show: bool):
        """Show or hide the drop zone overlay."""
        if show:
            self.drop_overlay.show()
            self.drop_overlay.raise_()
        else:
            self.drop_overlay.hide()
    
    # ========== Ruler/Measurement Mode Methods ==========

    def _get_vtk_interactor(self):
        """Safely get the underlying VTK render window interactor from pyvistaqt.
        
        pyvistaqt wraps the VTK interactor in a RenderWindowInteractor class.
        We need the actual vtkRenderWindowInteractor for AddObserver calls.
        """
        if self.plotter is None:
            return None

        # Method 1: Get from render window directly (most reliable)
        try:
            ren_win = self.plotter.ren_win
            if ren_win is not None:
                vtk_iren = ren_win.GetInteractor()
                if vtk_iren is not None and hasattr(vtk_iren, 'AddObserver'):
                    return vtk_iren
        except Exception:
            pass

        # Method 2: pyvistaqt stores underlying interactor
        iren = getattr(self.plotter, 'iren', None)
        if iren is not None:
            # Check if it's the wrapper or the actual VTK object
            if hasattr(iren, 'AddObserver'):
                return iren
            # Try to get underlying VTK interactor from wrapper
            if hasattr(iren, 'GetRenderWindow'):
                try:
                    rw = iren.GetRenderWindow()
                    if rw is not None:
                        vtk_iren = rw.GetInteractor()
                        if vtk_iren is not None and hasattr(vtk_iren, 'AddObserver'):
                            return vtk_iren
                except Exception:
                    pass

        # Method 3: Fallback via interactor attribute
        interactor_widget = getattr(self.plotter, 'interactor', None)
        if interactor_widget is not None:
            try:
                rw = interactor_widget.GetRenderWindow()
                if rw is not None:
                    vtk_iren = rw.GetInteractor()
                    if vtk_iren is not None and hasattr(vtk_iren, 'AddObserver'):
                        return vtk_iren
            except Exception:
                pass

        logger.warning("_get_vtk_interactor: Could not find VTK interactor with AddObserver")
        return None

    def _install_ruler_click_picking(self) -> bool:
        """Install a VTK observer for click-based picking (most reliable in QtInteractor)."""
        try:
            import vtk  # type: ignore
        except Exception as e:
            logger.warning(f"_install_ruler_click_picking: vtk import failed: {e}")
            return False

        iren = self._get_vtk_interactor()
        if iren is None:
            logger.warning("_install_ruler_click_picking: Could not get VTK interactor")
            return False

        # Remove any previous observer first (important: do this before creating a new picker)
        self._uninstall_ruler_click_picking()

        # Create picker (cell picker is robust; we snap to nearest vertex ourselves)
        self._ruler_picker = vtk.vtkCellPicker()
        try:
            # A slightly larger tolerance improves hit-testing reliability on high-DPI displays.
            # We still snap to the nearest vertex, so accuracy remains high.
            self._ruler_picker.SetTolerance(0.01)
        except Exception:
            pass

        # Try to restrict picking to just the model actor (avoid axes/background)
        if self.current_actor is not None:
            try:
                self.current_actor.SetPickable(True)
            except Exception:
                pass
            try:
                self._ruler_picker.PickFromListOn()
                self._ruler_picker.AddPickList(self.current_actor)
            except Exception as e:
                logger.debug(f"_install_ruler_click_picking: Could not restrict pick list: {e}")
                # Avoid the "empty pick list" situation, which would prevent ALL picking.
                try:
                    self._ruler_picker.PickFromListOff()
                except Exception:
                    pass

        try:
            self._ruler_click_observer_id = iren.AddObserver(
                "LeftButtonPressEvent",
                self._on_ruler_left_click,
                1.0,  # high priority
            )
            self._ruler_mouse_move_observer_id = iren.AddObserver(
                "MouseMoveEvent",
                self._on_ruler_mouse_move,
                0.0,  # normal priority
            )
            logger.info("_install_ruler_click_picking: VTK click and mouse-move observers installed")
            return True
        except Exception as e:
            logger.error(f"_install_ruler_click_picking: Failed to add observer: {e}", exc_info=True)
            self._ruler_click_observer_id = None
            self._ruler_mouse_move_observer_id = None
            self._ruler_picker = None
            return False

    def _uninstall_ruler_click_picking(self):
        """Remove VTK observers used for ruler picking and preview."""
        iren = self._get_vtk_interactor()
        try:
            if iren is not None:
                if self._ruler_click_observer_id is not None:
                    iren.RemoveObserver(self._ruler_click_observer_id)
                if self._ruler_mouse_move_observer_id is not None:
                    iren.RemoveObserver(self._ruler_mouse_move_observer_id)
                logger.info("_uninstall_ruler_click_picking: VTK observers removed")
        except Exception as e:
            logger.debug(f"_uninstall_ruler_click_picking: Could not remove observer: {e}")
        finally:
            self._ruler_click_observer_id = None
            self._ruler_mouse_move_observer_id = None
            self._ruler_picker = None
            self._clear_preview_line()

    def _screen_to_world_focal_plane(self, x, y):
        """Convert screen (x, y) to world coordinates on the camera's focal plane.
        
        Used for ruler mode so clicks and mouse position map to the view plane.
        Returns (x, y, z) world tuple or None on failure.
        """
        renderer = getattr(self.plotter, 'renderer', None)
        if renderer is None:
            try:
                renderer = self.plotter.ren_win.GetRenderers().GetFirstRenderer()
            except Exception:
                return None
        if renderer is None:
            return None
        try:
            import vtk
            import numpy as np
            camera = renderer.GetActiveCamera()
            focal_pt = np.array(camera.GetFocalPoint())
            coord = vtk.vtkCoordinate()
            coord.SetCoordinateSystemToDisplay()
            coord.SetValue(float(x), float(y), 0.0)
            world_near = np.array(coord.GetComputedWorldValue(renderer))
            cam_dir = np.array(camera.GetDirectionOfProjection())
            offset = np.dot(focal_pt - world_near, cam_dir)
            world_pos = world_near + cam_dir * offset
            return tuple(world_pos)
        except Exception:
            return None

    def _clear_preview_line(self):
        """Remove the preview line actor from the overlay."""
        overlay = getattr(self, '_overlay_renderer', None)
        actor = getattr(self, '_preview_line_actor', None)
        if actor is not None and overlay is not None:
            try:
                overlay.RemoveActor(actor)
            except Exception:
                pass
        self._preview_line_actor = None

    def _update_preview_line(self, point1, point2):
        """Draw or update the preview line from point1 to point2 (follows mouse)."""
        if point1 is None or point2 is None:
            self._clear_preview_line()
            return
        try:
            self._clear_preview_line()
            line = pv.Line(point1, point2)
            tube_radius = self._get_line_tube_radius()
            tube = line.tube(radius=tube_radius, n_sides=12)
            actor = self._add_mesh_to_overlay(tube, color='black', smooth_shading=False)
            if actor is not None:
                self._preview_line_actor = actor
            try:
                self.plotter.render()
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"_update_preview_line: {e}")

    def _get_nearest_mesh_point(self, world_pos, max_distance_ratio=0.02):
        """Return the nearest mesh vertex to world_pos if within threshold, else world_pos.
        
        Helps snap to corners/edges of the 3D model. max_distance_ratio is relative to model size.
        """
        if self.current_mesh is None:
            return world_pos
        try:
            import numpy as np
            pts = self.current_mesh.points
            if pts is None or len(pts) == 0:
                return world_pos
            p = np.array(world_pos)
            bounds = self.current_mesh.bounds
            max_dim = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4])
            threshold = max_dim * max_distance_ratio
            dists = np.linalg.norm(pts - p, axis=1)
            idx = np.argmin(dists)
            if dists[idx] <= threshold:
                return tuple(pts[idx])
            return world_pos
        except Exception:
            return world_pos

    def _on_ruler_left_click(self, obj, event):
        """VTK callback for left-click picking while ruler mode is enabled.
        
        In ruler mode we use orthographic views, so we project the screen click
        directly onto the view plane (at the model's focal depth) instead of
        ray-casting to the mesh surface.  This avoids vertex-snapping sensitivity
        issues and lets the user place measurement dots exactly where they click.
        """
        if not self.ruler_mode or self.plotter is None:
            return

        iren = self._get_vtk_interactor()
        if iren is None:
            return

        try:
            x, y = iren.GetEventPosition()
        except Exception:
            return

        logger.info(f"_on_ruler_left_click: click screen=({x},{y})")

        world_pos = self._screen_to_world_focal_plane(x, y)
        if world_pos is None:
            logger.info("_on_ruler_left_click: No renderer available")
            return

        logger.info(f"_on_ruler_left_click: screen=({x},{y}) world={world_pos}")
        self._on_point_picked(world_pos)

    def _on_ruler_mouse_move(self, obj, event):
        """Update preview line from first point to mouse position (with perpendicular + corner snapping)."""
        if not self.ruler_mode or self.plotter is None or len(self.measurement_points) != 1:
            self._clear_preview_line()
            return

        iren = self._get_vtk_interactor()
        if iren is None:
            return
        try:
            x, y = iren.GetEventPosition()
        except Exception:
            return

        world_pos = self._screen_to_world_focal_plane(x, y)
        if world_pos is None:
            return

        # Snap to nearest mesh vertex when close (helps connect corners); else maybe snap to H/V if close
        nearest = self._get_nearest_mesh_point(world_pos)
        if nearest != world_pos:
            snapped = nearest  # Use corner/vertex when close
        else:
            snapped = self._maybe_snap_to_axis(self.measurement_points[0], world_pos)

        self._update_preview_line(self.measurement_points[0], snapped)

    def enable_ruler_mode(self):
        """Enable point-to-point measurement mode with orthographic projection."""
        if self.plotter is None:
            logger.warning("enable_ruler_mode: Plotter not initialized")
            return False

        if self.current_mesh is None:
            logger.warning("enable_ruler_mode: No mesh loaded")
            return False

        logger.info("enable_ruler_mode: Enabling ruler mode...")
        self.ruler_mode = True
        self.measurement_points = []

        # Ensure we don't have leftover picking/observers from a previous session
        self._uninstall_ruler_click_picking()
        try:
            self.plotter.disable_picking()
        except Exception:
            pass

        # Prefer VTK observer-based picking (more reliable than PyVista helpers under QtInteractor)
        if self._install_ruler_click_picking():
            try:
                self.plotter.enable_parallel_projection()
                self.plotter.view_yz()  # Start with Front view
                logger.info("enable_ruler_mode: Orthographic projection enabled")
            except Exception as e:
                logger.warning(f"enable_ruler_mode: Could not enable orthographic projection: {e}")
            
            # Disable rotation but keep zoom - use zoom-only interaction style
            self._enable_zoom_only_interaction()
            return True

        # Fallback to PyVista picking helpers (if VTK interactor not available)
        try:
            self.plotter.enable_surface_point_picking(
                callback=self._on_point_picked,
                show_message=False,
                show_point=False,
                picker='cell',
            )
            logger.info("enable_ruler_mode: Surface point picking enabled (fallback)")
            self.plotter.enable_parallel_projection()
            self.plotter.view_yz()  # Start with Front view
            logger.info("enable_ruler_mode: Orthographic projection enabled")
            return True
        except AttributeError:
            logger.info("enable_ruler_mode: Falling back to enable_point_picking...")
            try:
                self.plotter.enable_point_picking(
                    callback=self._on_point_picked,
                    show_message=False,
                    show_point=False,
                    use_mesh=True,
                )
                self.plotter.enable_parallel_projection()
                return True
            except Exception as e2:
                logger.error(f"enable_ruler_mode: Fallback also failed: {e2}", exc_info=True)
                self.ruler_mode = False
                return False
        except Exception as e:
            logger.error(f"enable_ruler_mode: Failed to enable ruler mode: {e}", exc_info=True)
            self.ruler_mode = False
            return False

    def disable_ruler_mode(self):
        """Disable measurement mode and restore perspective projection."""
        if self.plotter is None:
            return

        logger.info("disable_ruler_mode: Disabling ruler mode...")
        self.ruler_mode = False
        self.measurement_points = []

        # Remove our observer (if installed)
        self._uninstall_ruler_click_picking()

        try:
            self.plotter.disable_picking()
            logger.info("disable_ruler_mode: Picking disabled")
        except Exception as e:
            logger.warning(f"disable_ruler_mode: Could not disable picking: {e}")

        # Clear all measurement visualizations
        self.clear_measurements()

        try:
            self.plotter.disable_parallel_projection()
            logger.info("disable_ruler_mode: Perspective projection restored")
        except Exception as e:
            logger.warning(f"disable_ruler_mode: Could not restore projection: {e}")
        
        # Restore full interaction (rotation, pan, zoom)
        self._restore_full_interaction()

    def _snap_to_axis(self, point1, point2):
        """Snap point2 so the measurement is strictly horizontal or vertical on screen.
        
        Uses the camera's right and up vectors to determine screen-space axes,
        then constrains point2 to move only along the dominant screen direction.
        """
        import numpy as np
        try:
            camera = self.plotter.renderer.GetActiveCamera()
            # Get camera basis vectors
            view_up = np.array(camera.GetViewUp())
            cam_dir = np.array(camera.GetDirectionOfProjection())
            view_right = np.cross(cam_dir, view_up)
            # Normalize
            view_right = view_right / (np.linalg.norm(view_right) + 1e-12)
            view_up = view_up / (np.linalg.norm(view_up) + 1e-12)
            
            p1 = np.array(point1)
            p2 = np.array(point2)
            delta = p2 - p1
            
            # Project delta onto screen axes
            dx_screen = np.dot(delta, view_right)
            dy_screen = np.dot(delta, view_up)
            
            # Snap to the dominant axis
            if abs(dx_screen) >= abs(dy_screen):
                # Horizontal measurement
                snapped = p1 + view_right * dx_screen
            else:
                # Vertical measurement
                snapped = p1 + view_up * dy_screen
            
            logger.info(f"_snap_to_axis: Snapped from {point2} to {snapped} (dx={dx_screen:.4f}, dy={dy_screen:.4f})")
            return tuple(snapped)
        except Exception as e:
            logger.warning(f"_snap_to_axis: Could not snap, using original point: {e}")
            return point2

    def _maybe_snap_to_axis(self, point1, point2, threshold_deg=15):
        """Snap to horizontal or vertical only when the line is close to that axis.
        
        If the angle from first to second point is within threshold_deg of horizontal
        or vertical (in screen space), snap to that axis. Otherwise return point2
        unchanged for free diagonal placement.
        """
        import math
        import numpy as np
        try:
            camera = self.plotter.renderer.GetActiveCamera()
            view_up = np.array(camera.GetViewUp())
            cam_dir = np.array(camera.GetDirectionOfProjection())
            view_right = np.cross(cam_dir, view_up)
            view_right = view_right / (np.linalg.norm(view_right) + 1e-12)
            view_up = view_up / (np.linalg.norm(view_up) + 1e-12)

            p1 = np.array(point1)
            p2 = np.array(point2)
            delta = p2 - p1

            dx_screen = np.dot(delta, view_right)
            dy_screen = np.dot(delta, view_up)

            # Same point or negligible movement
            if abs(dx_screen) < 1e-12 and abs(dy_screen) < 1e-12:
                return point2

            # Angle from horizontal: 0 = horizontal, 90 = vertical
            angle_deg = math.degrees(math.atan2(abs(dy_screen), abs(dx_screen)))

            if angle_deg < threshold_deg:
                # Close to horizontal
                return self._snap_to_axis(point1, point2)
            if angle_deg > (90 - threshold_deg):
                # Close to vertical
                return self._snap_to_axis(point1, point2)
            # Free diagonal
            return point2
        except Exception as e:
            logger.warning(f"_maybe_snap_to_axis: Could not check angle, using original point: {e}")
            return point2

    def _on_point_picked(self, point):
        """Handle point picked for measurement."""
        if not self.ruler_mode or point is None:
            return
        
        logger.info(f"_on_point_picked: Point picked at {point}")
        
        # If this is the second point, maybe snap to H/V when close to axis
        if len(self.measurement_points) == 1:
            point = self._maybe_snap_to_axis(self.measurement_points[0], point)
        
        self.measurement_points.append(point)
        
        # Calculate adaptive sphere size based on mesh bounds
        sphere_radius = self._get_measurement_marker_size()
        
        # Add sphere marker directly to overlay (never to main) so it always renders on top
        try:
            sphere = pv.Sphere(radius=sphere_radius, center=point)
            actor = self._add_mesh_to_overlay(sphere, color='#FF69B4')
            if actor is not None:
                self.measurement_actors.append(actor)
            logger.info(f"_on_point_picked: Marker added at {point}")
        except Exception as e:
            logger.warning(f"_on_point_picked: Could not add marker: {e}")
        
        # If we have two points, calculate and display the measurement
        if len(self.measurement_points) == 2:
            self._clear_preview_line()
            distance = self._calculate_distance(
                self.measurement_points[0], 
                self.measurement_points[1]
            )
            self._draw_measurement_line(
                self.measurement_points[0],
                self.measurement_points[1],
                distance
            )
            # Reset for next measurement
            self.measurement_points = []
    
    def _get_measurement_marker_size(self):
        """Calculate appropriate marker size based on mesh bounds."""
        if self.current_mesh is None:
            return 1.0
        
        try:
            bounds = self.current_mesh.bounds
            max_dimension = max(
                bounds[1] - bounds[0],  # x range
                bounds[3] - bounds[2],  # y range
                bounds[5] - bounds[4],  # z range
            )
            # Marker size is ~0.25% of the largest dimension for precision
            return max(max_dimension * 0.0025, 0.03)
        except Exception as e:
            logger.warning(f"_get_measurement_marker_size: Could not calculate size: {e}")
            return 1.0
    
    def _get_arrow_size(self):
        """Calculate arrowhead size based on model dimensions (same approach as dots).
        
        Returns (arrow_tip_length, arrow_tip_radius) so arrows stay consistent
        across all measurements regardless of line length.
        """
        if self.current_mesh is None:
            return (0.2, 0.08)
        try:
            bounds = self.current_mesh.bounds
            max_dimension = max(
                bounds[1] - bounds[0],
                bounds[3] - bounds[2],
                bounds[5] - bounds[4],
            )
            # Arrow tip length ~2% of model max dimension (visible, consistent with dots)
            arrow_tip_length = max(max_dimension * 0.02, 0.1)
            # Tip radius for cone shape (~40% of height)
            arrow_tip_radius = arrow_tip_length * 0.4
            return (arrow_tip_length, arrow_tip_radius)
        except Exception as e:
            logger.warning(f"_get_arrow_size: Could not calculate size: {e}")
            return (0.2, 0.08)
    
    def _get_line_tube_radius(self):
        """Calculate line tube radius based on model dimensions (same approach as dots/arrows).
        
        Returns consistent tube radius across all measurements regardless of line length.
        """
        if self.current_mesh is None:
            return 0.02
        try:
            bounds = self.current_mesh.bounds
            max_dimension = max(
                bounds[1] - bounds[0],
                bounds[3] - bounds[2],
                bounds[5] - bounds[4],
            )
            # Tube radius ~0.15% of model max dimension (visible, consistent)
            return max(max_dimension * 0.0015, 0.02)
        except Exception as e:
            logger.warning(f"_get_line_tube_radius: Could not calculate size: {e}")
            return 0.02
    
    def _calculate_distance(self, point1, point2):
        """Calculate Euclidean distance between two 3D points."""
        import numpy as np
        p1 = np.array(point1)
        p2 = np.array(point2)
        distance = np.linalg.norm(p2 - p1)
        logger.info(f"_calculate_distance: Distance = {distance:.4f}")
        return distance
    
    def _draw_measurement_line(self, point1, point2, distance):
        """Draw measurement line with arrowheads and distance label between two points."""
        import numpy as np
        
        try:
            p1 = np.array(point1)
            p2 = np.array(point2)
            direction = p2 - p1
            length = np.linalg.norm(direction)
            
            if length == 0:
                return
            
            dir_unit = direction / length
            
            # Arrow size from model dimensions (consistent across all measurements, like dots)
            arrow_tip_length, arrow_tip_radius = self._get_arrow_size()
            
            # Create the main line as a tube; add directly to overlay so it always renders on top
            # Tube radius from model dimensions (consistent across all measurements, flat black)
            tube_radius = self._get_line_tube_radius()
            line = pv.Line(point1, point2)
            tube = line.tube(radius=tube_radius, n_sides=16)
            line_actor = self._add_mesh_to_overlay(tube, color='black', smooth_shading=False)
            if line_actor is not None:
                self.measurement_actors.append(line_actor)
            
            # Arrowhead at point1 (pointing from p2 toward p1); add directly to overlay
            try:
                cone1 = pv.Cone(
                    center=p1 + dir_unit * (arrow_tip_length / 2),
                    direction=-dir_unit,
                    height=arrow_tip_length,
                    radius=arrow_tip_radius,
                    resolution=20,
                )
                cone1_actor = self._add_mesh_to_overlay(cone1, color='black')
                if cone1_actor is not None:
                    self.measurement_actors.append(cone1_actor)
            except Exception as e:
                logger.warning(f"_draw_measurement_line: Could not add arrowhead 1: {e}")
            
            # Arrowhead at point2 (pointing from p1 toward p2); add directly to overlay
            try:
                cone2 = pv.Cone(
                    center=p2 - dir_unit * (arrow_tip_length / 2),
                    direction=dir_unit,
                    height=arrow_tip_length,
                    radius=arrow_tip_radius,
                    resolution=20,
                )
                cone2_actor = self._add_mesh_to_overlay(cone2, color='black')
                if cone2_actor is not None:
                    self.measurement_actors.append(cone2_actor)
            except Exception as e:
                logger.warning(f"_draw_measurement_line: Could not add arrowhead 2: {e}")
            
            # Calculate midpoint for label
            midpoint = [
                (point1[0] + point2[0]) / 2,
                (point1[1] + point2[1]) / 2,
                (point1[2] + point2[2]) / 2,
            ]
            
            # Add distance label at midpoint
            # Convert distance based on selected unit
            unit = getattr(self, '_ruler_unit', 'mm')
            conversion = {"mm": 1.0, "cm": 0.1, "m": 0.001, "inch": 1.0 / 25.4, "ft": 1.0 / 304.8}
            unit_labels = {"mm": "mm", "cm": "cm", "m": "m", "inch": "in", "ft": "ft"}
            converted = distance * conversion.get(unit, 1.0)
            suffix = unit_labels.get(unit, "mm")
            
            if converted < 1:
                label_text = f"{converted:.4f} {suffix}"
            elif converted < 100:
                label_text = f"{converted:.2f} {suffix}"
            else:
                label_text = f"{converted:.1f} {suffix}"
            
            # Add the label using point labels
            label_points = pv.PolyData([midpoint])
            label_actor = self.plotter.add_point_labels(
                label_points,
                [label_text],
                font_size=12,
                text_color='black',
                font_family='arial',
                bold=True,
                show_points=False,
                always_visible=True,
                name=f'measure_label_{id(point1)}'
            )
            if label_actor:
                # Move label to overlay renderer so it renders in front of the object
                self._set_actor_always_on_top(label_actor)
                self.measurement_actors.append(label_actor)
            
            logger.info(f"_draw_measurement_line: Line and label drawn, distance = {label_text}")
            
            # Force render to show the measurement
            self.plotter.render()
            
        except Exception as e:
            logger.error(f"_draw_measurement_line: Failed to draw measurement: {e}", exc_info=True)
    
    def clear_measurements(self):
        """Clear all measurement visualizations from the viewer."""
        if self.plotter is None:
            return
        
        logger.info("clear_measurements: Clearing all measurements...")
        self._clear_preview_line()

        # Remove all measurement actors from both main and overlay renderers
        overlay = getattr(self, '_overlay_renderer', None)
        for actor in self.measurement_actors:
            try:
                self.plotter.remove_actor(actor)
            except Exception:
                pass
            try:
                if overlay is not None:
                    overlay.RemoveActor(actor)
            except Exception:
                pass
        
        self.measurement_actors = []
        self.measurement_points = []
        
        try:
            self.plotter.render()
        except Exception as e:
            logger.debug(f"clear_measurements: Could not render: {e}")
        
        logger.info("clear_measurements: Measurements cleared")
    
    # ========== Ruler Mode Interaction Control ==========
    
    def _enable_zoom_only_interaction(self):
        """Restrict interaction to zoom only (disable rotation and pan) for ruler mode."""
        try:
            import vtk
            iren = self._get_vtk_interactor()
            if iren is None:
                logger.warning("_enable_zoom_only_interaction: No interactor available")
                return
            
            # Store the original interactor style if not already stored
            if not hasattr(self, '_original_interactor_style'):
                self._original_interactor_style = iren.GetInteractorStyle()
            
            # Create a custom interactor style that only allows zoom (dolly)
            # vtkInteractorStyleRubberBandZoom allows only zoom
            zoom_style = vtk.vtkInteractorStyleRubberBandZoom()
            
            # Actually, we want scroll-wheel zoom which is better handled by
            # a custom style. Let's use TrackballCamera but intercept rotation.
            # Simpler approach: use vtkInteractorStyleImage which allows pan + zoom but no rotation
            # For static views, we want zoom only, so let's create minimal style
            
            # Use vtkInteractorStyleTrackballCamera but we'll filter events
            # Better: use vtkInteractorStyleImage which is 2D-like (pan + zoom, no rotate)
            image_style = vtk.vtkInteractorStyleImage()
            iren.SetInteractorStyle(image_style)
            
            logger.info("_enable_zoom_only_interaction: Zoom-only interaction enabled")
        except Exception as e:
            logger.warning(f"_enable_zoom_only_interaction: Failed: {e}")
    
    def _restore_full_interaction(self):
        """Restore full 3D interaction (rotation, pan, zoom)."""
        try:
            import vtk
            iren = self._get_vtk_interactor()
            if iren is None:
                return
            
            if hasattr(self, '_original_interactor_style') and self._original_interactor_style is not None:
                iren.SetInteractorStyle(self._original_interactor_style)
                logger.info("_restore_full_interaction: Original interaction style restored")
            else:
                # Fallback: set a standard trackball camera style
                trackball_style = vtk.vtkInteractorStyleTrackballCamera()
                iren.SetInteractorStyle(trackball_style)
                logger.info("_restore_full_interaction: Trackball camera style set")
        except Exception as e:
            logger.warning(f"_restore_full_interaction: Failed: {e}")
    
    def _get_overlay_renderer(self):
        """Get or create an overlay renderer that always renders on top of the main scene."""
        if getattr(self, '_overlay_renderer', None) is not None:
            return self._overlay_renderer
        
        try:
            import vtk
            render_window = self.plotter.render_window
            
            # Create overlay renderer on layer 1 (main scene is layer 0)
            self._overlay_renderer = vtk.vtkRenderer()
            self._overlay_renderer.SetLayer(1)
            self._overlay_renderer.InteractiveOff()
            
            # Do NOT preserve depth buffer - overlay clears depth so measurements always render on top
            self._overlay_renderer.SetPreserveDepthBuffer(0)
            
            # Transparent background so main scene shows through
            self._overlay_renderer.SetBackground(0, 0, 0)
            render_window.SetAlphaBitPlanes(True)
            self._overlay_renderer.SetBackgroundAlpha(0.0)
            
            # Enable multiple layers
            render_window.SetNumberOfLayers(2)
            render_window.AddRenderer(self._overlay_renderer)
            
            # Share the same camera so views stay in sync across all 6 orthographic views
            self._overlay_renderer.SetActiveCamera(
                self.plotter.renderer.GetActiveCamera()
            )
            
            # Sync viewport with main renderer so overlay covers the same area
            self._sync_overlay_viewport()
            
            logger.debug("_get_overlay_renderer: Overlay renderer created")
        except Exception as e:
            logger.warning(f"_get_overlay_renderer: Failed to create overlay renderer: {e}")
            self._overlay_renderer = None
        
        return self._overlay_renderer

    def _add_mesh_to_overlay(self, mesh, color='black', smooth_shading=False):
        """Add a mesh directly to the overlay renderer (never to main) so it always renders on top.
        
        Bypasses the main renderer entirely to avoid measurement components being hidden behind the 3D object.
        Returns the vtkActor for tracking.
        """
        import vtk
        overlay = self._get_overlay_renderer()
        if overlay is None:
            return None
        try:
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputData(mesh)
            mapper.ScalarVisibilityOff()  # Use solid color, not mesh scalars (avoids red-blue gradient)
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            rgb = pv.Color(color).float_rgb
            actor.GetProperty().SetColor(rgb[0], rgb[1], rgb[2])
            if smooth_shading:
                actor.GetProperty().SetInterpolationToPhong()
            actor.GetProperty().LightingOff()
            actor.GetProperty().SetOpacity(1.0)
            overlay.AddActor(actor)
            return actor
        except Exception as e:
            logger.warning(f"_add_mesh_to_overlay: Failed: {e}")
            return None

    def _set_actor_always_on_top(self, actor):
        """Move an actor to the overlay renderer so it always renders in front.
        
        Also disables depth testing on the actor so it is never occluded.
        """
        if actor is None:
            return
        try:
            overlay = self._get_overlay_renderer()
            if overlay is not None:
                # Remove from main renderer and add to overlay
                self.plotter.renderer.RemoveActor(actor)
                overlay.AddActor(actor)
                logger.debug("_set_actor_always_on_top: Actor moved to overlay renderer")
            else:
                # Fallback: use polygon offset if overlay renderer unavailable
                mapper = actor.GetMapper()
                if mapper is not None:
                    mapper.SetResolveCoincidentTopologyToPolygonOffset()
                    mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-2, -2)
                logger.debug("_set_actor_always_on_top: Fallback polygon offset applied")
            
            # Disable depth testing so actor is never hidden behind geometry
            try:
                prop = actor.GetProperty()
                if prop is not None:
                    prop.SetOpacity(1.0)
                    # Render on top by disabling depth comparison
                    prop.LightingOff()
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"_set_actor_always_on_top: Failed: {e}")
    
    def _sync_overlay_viewport(self):
        """Sync overlay renderer viewport with main renderer so measurements render in the correct area."""
        overlay = getattr(self, '_overlay_renderer', None)
        if overlay is None or self.plotter is None:
            return
        try:
            vp = self.plotter.renderer.GetViewport()
            overlay.SetViewport(vp[0], vp[1], vp[2], vp[3])
        except Exception as e:
            logger.debug(f"_sync_overlay_viewport: {e}")
    
    # ========== Orthographic View Methods for Ruler Mode ==========
    
    def view_front_ortho(self):
        """Set camera to front view with orthographic projection."""
        if self.plotter is None:
            return
        try:
            self.plotter.view_yz()
            self.plotter.enable_parallel_projection()
            self._sync_overlay_viewport()
            logger.info("view_front_ortho: Front orthographic view set")
        except Exception as e:
            logger.warning(f"view_front_ortho: Could not set view: {e}")
    
    def view_right_ortho(self):
        """Set camera to right view with orthographic projection."""
        if self.plotter is None:
            return
        try:
            self.plotter.view_xz()
            self.plotter.enable_parallel_projection()
            self._sync_overlay_viewport()
            logger.info("view_right_ortho: Right orthographic view set")
        except Exception as e:
            logger.warning(f"view_right_ortho: Could not set view: {e}")
    
    def view_left_ortho(self):
        """Set camera to left view with orthographic projection."""
        if self.plotter is None:
            return
        try:
            # Left view: looking down the -Y axis
            self.plotter.view_xz(negative=True)
            self.plotter.enable_parallel_projection()
            self._sync_overlay_viewport()
            logger.info("view_left_ortho: Left orthographic view set")
        except Exception as e:
            logger.warning(f"view_left_ortho: Could not set view: {e}")
    
    def view_top_ortho(self):
        """Set camera to top view with orthographic projection."""
        if self.plotter is None:
            return
        try:
            self.plotter.view_xy()
            self.plotter.enable_parallel_projection()
            self._sync_overlay_viewport()
            logger.info("view_top_ortho: Top orthographic view set")
        except Exception as e:
            logger.warning(f"view_top_ortho: Could not set view: {e}")
    
    def view_bottom_ortho(self):
        """Set camera to bottom view with orthographic projection."""
        if self.plotter is None:
            return
        try:
            # Bottom view: looking down the -Z axis
            self.plotter.view_xy(negative=True)
            self.plotter.enable_parallel_projection()
            self._sync_overlay_viewport()
            logger.info("view_bottom_ortho: Bottom orthographic view set")
        except Exception as e:
            logger.warning(f"view_bottom_ortho: Could not set view: {e}")
    
    def view_rear_ortho(self):
        """Set camera to rear view with orthographic projection."""
        if self.plotter is None:
            return
        try:
            # Rear view: looking down the -X axis
            self.plotter.view_yz(negative=True)
            self.plotter.enable_parallel_projection()
            self._sync_overlay_viewport()
            logger.info("view_rear_ortho: Rear orthographic view set")
        except Exception as e:
            logger.warning(f"view_rear_ortho: Could not set view: {e}")
    
    # ========== Annotation Mode Methods ==========
    
    def enable_annotation_mode(self, callback=None):
        """Enable annotation mode for adding 3D point annotations.
        
        Args:
            callback: Function to call when a point is picked. Receives (point_tuple,).
        """
        if self.plotter is None:
            logger.warning("enable_annotation_mode: Plotter not initialized")
            return False
        
        if self.current_mesh is None:
            logger.warning("enable_annotation_mode: No mesh loaded")
            return False
        
        logger.info("enable_annotation_mode: Enabling annotation mode...")
        self.annotation_mode = True
        self._annotation_callback = callback
        
        # Disable ruler mode if active
        if self.ruler_mode:
            self.disable_ruler_mode()
        
        # Install click picking for annotations
        if self._install_annotation_click_picking():
            # Hide bottom-left XYZ axes (we show camera orientation gizmo in bottom right instead)
            try:
                self.plotter.hide_axes()
            except Exception:
                pass
            # Add interactive orientation cube in bottom right for rotating when zoomed in
            # (clicking on model adds annotations, so use this to rotate view instead)
            self._add_orientation_gizmo()
            if self._object_control_overlay is not None:
                self._object_control_overlay.show()
                self._object_control_overlay.raise_()
            logger.info("enable_annotation_mode: Annotation mode enabled")
            return True
        
        logger.warning("enable_annotation_mode: Failed to install picking")
        self.annotation_mode = False
        return False
    
    def disable_annotation_mode(self):
        """Disable annotation mode."""
        if self.plotter is None:
            return
        
        logger.info("disable_annotation_mode: Disabling annotation mode...")
        self.annotation_mode = False
        self._annotation_callback = None
        
        # Remove our observer
        self._uninstall_annotation_click_picking()
        
        try:
            self.plotter.disable_picking()
        except Exception:
            pass
        
        self._remove_orientation_gizmo()
        if self._object_control_overlay is not None:
            self._object_control_overlay.hide()
        # Restore bottom-left XYZ axes
        try:
            self.plotter.show_axes()
        except Exception:
            pass
        logger.info("disable_annotation_mode: Annotation mode disabled")
    
    def _add_orientation_gizmo(self):
        """Show custom orientation gizmo overlay (no-op; overlay shown in enable_annotation_mode)."""
        pass

    def _on_gizmo_rotate(self, dx: float, dy: float):
        """Handle drag on orientation gizmo - rotate the camera (matches main canvas drag direction)."""
        if self.plotter is None:
            return
        try:
            scale = 0.5  # degrees per pixel
            cam = self.plotter.renderer.GetActiveCamera()
            cam.Azimuth(dx * scale)
            cam.Elevation(-dy * scale)
            self.plotter.render()
        except Exception as e:
            logger.debug(f"_on_gizmo_rotate: {e}")

    def _remove_orientation_gizmo(self):
        """Hide the orientation gizmo overlay (no-op; overlay hidden in disable_annotation_mode)."""
        pass

    def _install_annotation_click_picking(self) -> bool:
        """Install VTK observer for annotation point picking."""
        try:
            import vtk
        except ImportError as e:
            logger.warning(f"_install_annotation_click_picking: vtk import failed: {e}")
            return False
        
        iren = self._get_vtk_interactor()
        if iren is None:
            logger.warning("_install_annotation_click_picking: Could not get VTK interactor")
            return False
        
        # Remove any previous observer
        self._uninstall_annotation_click_picking()
        
        # Create picker
        self._annotation_picker = vtk.vtkCellPicker()
        try:
            # Smaller tolerance = must click directly on model (reduces accidental picks in empty space)
            self._annotation_picker.SetTolerance(0.01)
        except Exception:
            pass
        
        # Restrict to model actor only - must not pick empty space or other actors
        if self.current_actor is None:
            logger.warning("_install_annotation_click_picking: No mesh actor to restrict picking")
            self._annotation_picker = None
            return False
        try:
            self.current_actor.SetPickable(True)
            self._annotation_picker.PickFromListOn()
            self._annotation_picker.AddPickList(self.current_actor)
            logger.debug("_install_annotation_click_picking: Picking restricted to model mesh")
        except Exception as e:
            logger.warning(f"_install_annotation_click_picking: Could not restrict pick list: {e}")
            self._annotation_picker = None
            return False
        
        try:
            self._annotation_click_observer_id = iren.AddObserver(
                "LeftButtonPressEvent",
                self._on_annotation_left_click,
                1.0,
            )
            logger.info("_install_annotation_click_picking: VTK click observer installed")
            return True
        except Exception as e:
            logger.error(f"_install_annotation_click_picking: Failed to add observer: {e}", exc_info=True)
            self._annotation_click_observer_id = None
            self._annotation_picker = None
            return False
    
    def _uninstall_annotation_click_picking(self):
        """Remove VTK observer for annotation picking."""
        if self._annotation_click_observer_id is None:
            self._annotation_picker = None
            return
        
        iren = self._get_vtk_interactor()
        try:
            if iren is not None:
                iren.RemoveObserver(self._annotation_click_observer_id)
                logger.info("_uninstall_annotation_click_picking: Observer removed")
        except Exception as e:
            logger.debug(f"_uninstall_annotation_click_picking: Could not remove observer: {e}")
        finally:
            self._annotation_click_observer_id = None
            self._annotation_picker = None
    
    def _on_annotation_left_click(self, obj, event):
        """VTK callback for annotation point picking."""
        if not self.annotation_mode or self.plotter is None or self._annotation_picker is None:
            return
        
        iren = self._get_vtk_interactor()
        if iren is None:
            return
        
        try:
            x, y = iren.GetEventPosition()
        except Exception:
            return
        
        logger.info(f"_on_annotation_left_click: click screen=({x},{y})")
        
        renderer = getattr(self.plotter, 'renderer', None)
        if renderer is None:
            try:
                renderer = self.plotter.ren_win.GetRenderers().GetFirstRenderer()
            except Exception:
                renderer = None
        
        # Reject clicks outside the 3D view viewport
        try:
            if renderer is not None and self.plotter.ren_win is not None:
                vp = renderer.GetViewport()
                size = self.plotter.ren_win.GetSize()
                vp_x_min = int(vp[0] * size[0])
                vp_x_max = int(vp[2] * size[0])
                vp_y_min = int(vp[1] * size[1])
                vp_y_max = int(vp[3] * size[1])
                if x < vp_x_min or x > vp_x_max or y < vp_y_min or y > vp_y_max:
                    logger.info(f"_on_annotation_left_click: Click ({x},{y}) outside viewport, ignored")
                    return
        except Exception:
            pass
        
        if renderer is None:
            logger.info("_on_annotation_left_click: No renderer available")
            return
        
        try:
            self._annotation_picker.Pick(x, y, 0, renderer)
            cell_id = self._annotation_picker.GetCellId()
            if cell_id == -1:
                logger.info(f"_on_annotation_left_click: No hit at ({x}, {y})")
                return
            
            # Must have picked the mesh actor, not overlay or other geometry
            picked_actor = self._annotation_picker.GetActor()
            if picked_actor is None or picked_actor != self.current_actor:
                logger.info(f"_on_annotation_left_click: Pick hit wrong actor (not mesh), ignored")
                return
            
            # Use exact pick position on surface - do NOT snap to vertices, which pulls
            # annotations to triangle corners/edges and prevents placing on plain surfaces
            picked_world = self._annotation_picker.GetPickPosition()
            point_tuple = tuple(float(c) for c in picked_world)
            
            # Validate: point must be within mesh bounds (reject picks outside model)
            if self.current_mesh is not None:
                bounds = self.current_mesh.bounds
                max_dim = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4], 0.01)
                margin = max_dim * 0.001
                if (point_tuple[0] < bounds[0] - margin or point_tuple[0] > bounds[1] + margin or
                    point_tuple[1] < bounds[2] - margin or point_tuple[1] > bounds[3] + margin or
                    point_tuple[2] < bounds[4] - margin or point_tuple[2] > bounds[5] + margin):
                    logger.info(f"_on_annotation_left_click: Point {point_tuple} outside mesh bounds, ignored")
                    return
                
                # Validate: point must be ON the mesh surface (reject picks in empty space)
                # Use distance from picked point to closest mesh point - must be within model
                try:
                    closest_idx = self.current_mesh.find_closest_point(point_tuple)
                    closest_pt = self.current_mesh.points[closest_idx]
                    dist = np.linalg.norm(np.array(point_tuple) - np.array(closest_pt))
                    # Reject if point is far from mesh (clearly in empty space)
                    # 10% of model size - on-surface picks are typically much closer to a vertex
                    surface_tolerance = max(max_dim * 0.10, 1.0)
                    if dist > surface_tolerance:
                        logger.info(f"_on_annotation_left_click: Point not on mesh surface (dist={dist:.2f}mm > {surface_tolerance:.2f}mm), ignored")
                        return
                except Exception as e:
                    logger.debug(f"_on_annotation_left_click: Surface validation failed: {e}")
            
            logger.info(f"_on_annotation_left_click: hit at {point_tuple}")
            
            # Call the callback if set
            if self._annotation_callback is not None:
                self._annotation_callback(point_tuple)
            
        except Exception as e:
            logger.error(f"_on_annotation_left_click: Picking failed: {e}", exc_info=True)
    
    def add_annotation_marker(self, annotation_id: int, point: tuple, color: str = '#909d92',
                              display_date: str = None) -> object:
        """Add a visible marker for an annotation point with date label.
        
        Args:
            annotation_id: Unique ID for the annotation
            point: (x, y, z) world coordinates
            color: Marker color (hex string) - default gray for pending
            display_date: Label to show at the point (e.g. annotation number '1', '2', '3')
            
        Returns:
            The actor for the marker, or None if failed
        """
        if self.plotter is None or self.current_mesh is None:
            return None
        
        display_date = display_date or str(annotation_id)
        
        try:
            # Flat 1.5% of max dimension — consistent across all model sizes
            try:
                bounds = self.current_mesh.bounds
                dim_x = bounds[1] - bounds[0]
                dim_y = bounds[3] - bounds[2]
                dim_z = bounds[5] - bounds[4]
                max_dim = max(dim_x, dim_y, dim_z)
                sphere_radius = max_dim * 0.012
                logger.info(
                    f"add_annotation_marker: dims=({dim_x:.2f}, {dim_y:.2f}, {dim_z:.2f}) "
                    f"max_dim={max_dim:.2f} → radius={sphere_radius:.4f} "
                    f"({sphere_radius/max_dim*100:.1f}% of model)"
                )
            except Exception:
                sphere_radius = 0.5
            
            sphere = pv.Sphere(radius=sphere_radius, center=point)
            actor = self.plotter.add_mesh(
                sphere,
                color=color,
                specular=1.0,
                specular_power=50,
                diffuse=0.7,
                ambient=0.2,
                smooth_shading=True,
                name=f'annotation_marker_{annotation_id}',
                reset_camera=False  # Preserve user's zoom/pan when adding annotation
            )
            try:
                actor.SetPickable(False)  # Don't pick annotation markers - only the model
            except Exception:
                pass
            
            # Add date label slightly above the sphere - badge color matches dot
            label_actor = None
            try:
                offset = sphere_radius * 1.5
                label_pos = (point[0], point[1] + offset, point[2])
                label_points = pv.PolyData([list(label_pos)])
                # Text green for validated (blue), white on other dark backgrounds, black on light
                text_color = '#22C55E' if (color and color.lower().lstrip('#') == '1821b4') else ('#FFFFFF' if self._is_dark_hex_color(color) else '#000000')
                label_actor = self.plotter.add_point_labels(
                    label_points,
                    [display_date],
                    font_size=18,
                    text_color=text_color,
                    shape_color=color,  # Badge background matches dot color
                    font_family='arial',
                    bold=True,
                    show_points=False,
                    always_visible=True,  # On top when visible; we hide via SetVisibility when dot occluded
                    name=f'annotation_label_{annotation_id}',
                    reset_camera=False  # Preserve user's zoom/pan
                )
                if label_actor:
                    try:
                        label_actor.SetPickable(False)  # Don't pick labels
                    except Exception:
                        pass
                    self._set_actor_always_on_top(label_actor)
            except Exception as e:
                logger.debug(f"add_annotation_marker: Could not add date label: {e}")
            
            self.annotations.append({
                'id': annotation_id,
                'point': point,
                'actor': actor,
                'label_actor': label_actor,
                'base_color': color,  # For restoring when deselected
                'display_date': display_date,
            })
            self.annotation_actors.append(actor)
            if label_actor:
                self.annotation_actors.append(label_actor)
            
            if not self._annotation_visibility_timer.isActive():
                self._annotation_visibility_timer.start()
            
            self.plotter.render()
            logger.info(f"add_annotation_marker: Added marker id={annotation_id} at {point} with color {color}, date={display_date}")
            return actor
            
        except Exception as e:
            logger.error(f"add_annotation_marker: Failed: {e}", exc_info=True)
            return None
    
    def update_annotation_marker_color(self, annotation_id: int, color: str):
        """Update the color of an annotation marker and its label badge.
        
        Args:
            annotation_id: The annotation ID
            color: New color (hex string)
        """
        for ann in self.annotations:
            if ann['id'] == annotation_id:
                try:
                    ann['base_color'] = color
                    # Only update actor if not currently selected (yellow)
                    if not ann.get('selected', False):
                        ann['actor'].GetProperty().SetColor(
                            *self._hex_to_rgb_normalized(color)
                        )
                    # Update label badge to match dot color
                    self._replace_annotation_label(ann, color)
                    self.plotter.render()
                    logger.info(f"update_annotation_marker_color: Updated id={annotation_id} to {color}")
                except Exception as e:
                    logger.warning(f"update_annotation_marker_color: Failed: {e}")
                break
    
    def set_annotation_selected(self, annotation_id: int, selected: bool):
        """Set annotation marker to yellow when selected, restore base color when deselected."""
        if selected:
            # Deselect any previously selected
            for ann in self.annotations:
                if ann.get('selected', False):
                    ann['selected'] = False
                    try:
                        ann['actor'].GetProperty().SetColor(
                            *self._hex_to_rgb_normalized(ann.get('base_color', '#909d92'))
                        )
                        self._replace_annotation_label(ann, ann.get('base_color', '#909d92'))
                    except Exception:
                        pass
        for ann in self.annotations:
            if ann['id'] == annotation_id:
                try:
                    ann['selected'] = selected
                    color = '#FACC15' if selected else ann.get('base_color', '#909d92')  # Yellow when selected
                    ann['actor'].GetProperty().SetColor(
                        *self._hex_to_rgb_normalized(color)
                    )
                    self._replace_annotation_label(ann, color)
                    self.plotter.render()
                except Exception as e:
                    logger.warning(f"set_annotation_selected: Failed: {e}")
                break
    
    def remove_annotation_marker(self, annotation_id: int):
        """Remove an annotation marker by ID."""
        if self.plotter is None:
            return
        
        for i, ann in enumerate(self.annotations):
            if ann['id'] == annotation_id:
                try:
                    self.plotter.remove_actor(ann['actor'])
                    if ann['actor'] in self.annotation_actors:
                        self.annotation_actors.remove(ann['actor'])
                    label_actor = ann.get('label_actor')
                    if label_actor is not None:
                        try:
                            self.plotter.remove_actor(label_actor)
                        except Exception:
                            pass
                        overlay = getattr(self, '_overlay_renderer', None)
                        if overlay is not None:
                            try:
                                overlay.RemoveActor(label_actor)
                            except Exception:
                                pass
                        if label_actor in self.annotation_actors:
                            self.annotation_actors.remove(label_actor)
                except Exception as e:
                    logger.debug(f"remove_annotation_marker: Could not remove actor: {e}")
                self.annotations.pop(i)
                if not self.annotations:
                    self._annotation_visibility_timer.stop()
                self.plotter.render()
                logger.info(f"remove_annotation_marker: Removed id={annotation_id}")
                break
    
    def update_annotation_labels_from_list(self, annotations_with_display):
        """Update only labels whose display number changed (incremental renumber after delete).
        
        Args:
            annotations_with_display: List of (annotation_id, display_number, color) tuples.
        """
        if self.plotter is None:
            return
        updated = 0
        lookup = {aid: (dnum, color) for aid, dnum, color in annotations_with_display}
        for ann in self.annotations:
            aid = ann['id']
            if aid not in lookup:
                continue
            display_number, color = lookup[aid]
            new_display = str(display_number)
            if ann.get('display_date') != new_display:
                ann['display_date'] = new_display
                self._replace_annotation_label(ann, color)
                updated += 1
        if updated > 0:
            try:
                self.plotter.render()
            except Exception:
                pass
        logger.debug(f"update_annotation_labels_from_list: Updated {updated} labels")
    
    def clear_all_annotation_markers(self):
        """Remove all annotation markers and their date labels."""
        if self.plotter is None:
            return
        
        logger.info("clear_all_annotation_markers: Clearing all annotations...")
        overlay = getattr(self, '_overlay_renderer', None)
        for ann in list(self.annotations):
            try:
                self.plotter.remove_actor(ann['actor'])
                label_actor = ann.get('label_actor')
                if label_actor is not None:
                    # Labels are in overlay renderer (always-on-top) - must remove from both
                    try:
                        self.plotter.remove_actor(label_actor)
                    except Exception:
                        pass
                    if overlay is not None:
                        try:
                            overlay.RemoveActor(label_actor)
                        except Exception:
                            pass
            except Exception:
                pass
        
        self.annotations = []
        self.annotation_actors = []
        self._annotation_visibility_timer.stop()
        
        # Keep gizmo visible - user is still in annotation mode and may add more
        try:
            self.plotter.render()
        except Exception:
            pass
        
        logger.info("clear_all_annotation_markers: All annotations cleared")
    
    def focus_on_annotation(self, annotation_id: int):
        """Focus the camera on a specific annotation point."""
        for ann in self.annotations:
            if ann['id'] == annotation_id:
                point = ann['point']
                try:
                    # Set camera to look at this point
                    self.plotter.camera.focal_point = point
                    self.plotter.reset_camera()
                    self.plotter.render()
                    logger.info(f"focus_on_annotation: Focused on id={annotation_id}")
                except Exception as e:
                    logger.warning(f"focus_on_annotation: Failed: {e}")
                break
    
    def _is_dot_visible_pyvista(self, point) -> bool:
        """Return True if the annotation point is not occluded by the mesh."""
        if self.current_mesh is None or self.plotter is None:
            return True
        try:
            cam_pos = np.array(self.plotter.camera.position)
            pt = np.array(point, dtype=np.float64)
            direction = pt - cam_pos
            dist_to_dot = np.linalg.norm(direction)
            if dist_to_dot < 1e-9:
                return True
            direction = direction / dist_to_dot
            max_dist = dist_to_dot * 1.1
            end_pt = cam_pos + direction * max_dist
            try:
                points, _ = self.current_mesh.ray_trace(cam_pos, end_pt)
            except Exception:
                return True
            if points is None or points.n_points == 0:
                return True
            dists = np.linalg.norm(np.asarray(points.points) - cam_pos, axis=1)
            closest = float(np.min(dists))
            if closest < dist_to_dot - 1e-6:
                return False
            return True
        except Exception:
            return True

    def _update_annotation_label_visibility(self):
        """Update each annotation label visibility: hide when dot is occluded by mesh."""
        if not self.annotations or self.plotter is None:
            return
        try:
            cam = self.plotter.camera
            cam_hash = (tuple(cam.position), tuple(cam.focal_point))
            if cam_hash == self._last_visibility_cam_hash:
                return
            self._last_visibility_cam_hash = cam_hash
        except Exception:
            pass
        changed = False
        for ann in self.annotations:
            try:
                label_actor = ann.get('label_actor')
                if label_actor is None:
                    continue
                visible = self._is_dot_visible_pyvista(ann['point'])
                new_vis = 1 if visible else 0
                if label_actor.GetVisibility() != new_vis:
                    label_actor.SetVisibility(new_vis)
                    changed = True
            except Exception:
                pass
        if changed:
            try:
                self.plotter.render()
            except Exception:
                pass

    def _replace_annotation_label(self, ann: dict, color: str):
        """Replace the annotation label with one using the given badge color."""
        label_actor = ann.get('label_actor')
        display_date = ann.get('display_date', str(ann['id']))
        point = ann['point']
        if label_actor is None:
            return
        try:
            # Remove old label
            self.plotter.remove_actor(label_actor)
            if label_actor in self.annotation_actors:
                self.annotation_actors.remove(label_actor)
            overlay = getattr(self, '_overlay_renderer', None)
            if overlay is not None:
                try:
                    overlay.RemoveActor(label_actor)
                except Exception:
                    pass
            # Compute sphere radius for offset (same as add_annotation_marker)
            try:
                bounds = self.current_mesh.bounds
                dim_x = bounds[1] - bounds[0]
                dim_y = bounds[3] - bounds[2]
                dim_z = bounds[5] - bounds[4]
                max_dim = max(dim_x, dim_y, dim_z)
                sphere_radius = max_dim * 0.012
            except Exception:
                sphere_radius = 0.5
            offset = sphere_radius * 1.5
            label_pos = (point[0], point[1] + offset, point[2])
            label_points = pv.PolyData([list(label_pos)])
            text_color = '#22C55E' if (color and color.lower().lstrip('#') == '1821b4') else ('#FFFFFF' if self._is_dark_hex_color(color) else '#000000')
            new_label = self.plotter.add_point_labels(
                label_points,
                [display_date],
                font_size=18,
                text_color=text_color,
                shape_color=color,
                font_family='arial',
                bold=True,
                show_points=False,
                always_visible=True,  # On top when visible; we hide via SetVisibility when dot occluded
                name=f"annotation_label_{ann['id']}",
                reset_camera=False
            )
            if new_label:
                new_label.SetPickable(False)
                self._set_actor_always_on_top(new_label)
            ann['label_actor'] = new_label
            if new_label and new_label not in self.annotation_actors:
                self.annotation_actors.append(new_label)
        except Exception as e:
            logger.debug(f"_replace_annotation_label: {e}")
    
    def _hex_to_rgb_normalized(self, hex_color: str) -> tuple:
        """Convert hex color to normalized RGB tuple."""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0
        return (r, g, b)
    
    def _is_dark_hex_color(self, hex_color: str) -> bool:
        """Return True if color is dark (use white text for contrast)."""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            return False
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        return luminance < 0.5

    # ========== Part Visibility Methods (Parts panel) ==========

    def get_parts_list(self):
        """Return list of part metadata for the PartsPanel."""
        parts = [
            {
                'id': p['id'],
                'name': p['name'],
                'face_count': p.get('face_count', 0),
                'visible': p.get('visible', True),
            }
            for p in self._mesh_parts
        ]
        logger.info(f"parts_debug: get_parts_list returning {len(parts)} parts, _mesh_parts len={len(self._mesh_parts)}: {[(x['name'], x['face_count']) for x in parts]}")
        return parts

    def set_part_visible(self, part_id, visible):
        """Show or hide a specific part by ID."""
        for p in self._mesh_parts:
            if p['id'] == part_id:
                p['visible'] = visible
                p['actor'].SetVisibility(1 if visible else 0)
                break
        try:
            self.plotter.render()
        except Exception:
            pass

    def show_all_parts(self):
        """Make all parts visible."""
        for p in self._mesh_parts:
            p['visible'] = True
            p['actor'].SetVisibility(1)
        try:
            self.plotter.render()
        except Exception:
            pass

    def hide_all_parts(self):
        """Hide all parts."""
        for p in self._mesh_parts:
            p['visible'] = False
            p['actor'].SetVisibility(0)
        try:
            self.plotter.render()
        except Exception:
            pass

    def invert_parts_visibility(self):
        """Invert visibility of all parts."""
        for p in self._mesh_parts:
            p['visible'] = not p['visible']
            p['actor'].SetVisibility(1 if p['visible'] else 0)
        try:
            self.plotter.render()
        except Exception:
            pass

    def isolate_part(self, part_id):
        """Show only the specified part, hide all others."""
        for p in self._mesh_parts:
            vis = (p['id'] == part_id)
            p['visible'] = vis
            p['actor'].SetVisibility(1 if vis else 0)
        try:
            self.plotter.render()
        except Exception:
            pass

    def highlight_part(self, part_id):
        """Briefly highlight a selected part (make others semi-transparent)."""
        for p in self._mesh_parts:
            if not p['visible']:
                continue
            prop = p['actor'].GetProperty()
            if p['id'] == part_id:
                prop.SetOpacity(1.0)
            else:
                prop.SetOpacity(0.25)
        try:
            self.plotter.render()
        except Exception:
            pass

    def unhighlight_parts(self):
        """Restore normal opacity on all parts."""
        for p in self._mesh_parts:
            prop = p['actor'].GetProperty()
            prop.SetOpacity(1.0)
        try:
            self.plotter.render()
        except Exception:
            pass
