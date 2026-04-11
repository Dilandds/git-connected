"""
Minimal 3D Viewer Widget using pygfx + wgpu for STL file visualization.
WebGPU-based (avoids OpenGL) - intended to fix Windows black screen.
Settings match PyVista viewer for consistent default view and rendering.
"""
import sys
import os
import logging
from pathlib import Path
import numpy as np
from PyQt5.QtWidgets import QWidget, QStackedLayout, QGridLayout, QVBoxLayout, QLabel, QFrame, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QEvent, QPoint, QPointF, QRectF, QSize
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QPixmap
from ui.drop_zone_overlay import DropZoneOverlay

logger = logging.getLogger(__name__)

# Rubber-band screenshot: render at this multiple of logical canvas size then crop.
SCREENSHOT_CAPTURE_SCALE = 8
_SCREENSHOT_MAX_EDGE_PX = 8192
_SCREENSHOT_MAX_PIXELS = 67_000_000  # ~8k × 8k — safe for most GPUs

from ui.orientation_gizmo import OrientationGizmoWidget


def _get_zoom_icon_path(filename: str) -> Path:
    """Return path to zoom icon (handles PyInstaller frozen bundle)."""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent
    return base / 'assets' / filename


def _trimesh_to_pyvista(tm):
    """Convert trimesh (Trimesh or Scene) to PyVista PolyData for MeshCalculator compatibility."""
    import trimesh
    import pyvista as pv

    if isinstance(tm, trimesh.Scene):
        all_meshes = [g for g in tm.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not all_meshes:
            return None
        tm = trimesh.util.concatenate(all_meshes) if len(all_meshes) > 1 else all_meshes[0]

    if not isinstance(tm, trimesh.Trimesh):
        return None

    vertices = np.asarray(tm.vertices, dtype=np.float64)
    faces = np.asarray(tm.faces, dtype=np.int32)
    cells = np.column_stack([np.full(len(faces), 3), faces]).ravel().astype(np.int32)
    return pv.PolyData(vertices, cells)


def _trimesh_to_flat_shaded(tm):
    """Convert trimesh to flat-shaded version (duplicated vertices, one per face).
    Each triangle gets 3 unique vertices with face normal, so edges render sharp.
    Returns a new trimesh suitable for geometry_from_trimesh.
    """
    import trimesh
    verts = np.asarray(tm.vertices, dtype=np.float64)
    faces = np.asarray(tm.faces, dtype=np.int32)
    tris = verts[faces]  # (N, 3, 3)
    # Explode: 3 vertices per face, no sharing
    flat_verts = tris.reshape(-1, 3)
    flat_faces = np.arange(len(tris) * 3, dtype=np.int32).reshape(-1, 3)
    flat_tm = trimesh.Trimesh(vertices=flat_verts, faces=flat_faces, process=False)
    flat_tm.fix_normals()  # With unique verts per face, this gives face normals
    return flat_tm


def _pyvista_to_trimesh(pv_mesh):
    """Convert PyVista PolyData to trimesh.Trimesh for pygfx rendering."""
    import trimesh
    import pyvista as pv

    try:
        pv_mesh = pv_mesh.triangulate()
    except Exception:
        pass
    verts = np.asarray(pv_mesh.points, dtype=np.float64)
    faces_arr = pv_mesh.faces
    # PyVista: [3, i0, i1, i2, 3, i3, i4, i5, ...] for triangles
    if len(faces_arr) >= 4 and len(faces_arr) % 4 == 0:
        faces = faces_arr.reshape(-1, 4)[:, 1:4]
    else:
        # Parse variable-length faces
        idx = 0
        faces_list = []
        while idx < len(faces_arr):
            n = int(faces_arr[idx])
            idx += 1
            if n == 3 and idx + 3 <= len(faces_arr):
                faces_list.append([faces_arr[idx], faces_arr[idx + 1], faces_arr[idx + 2]])
            idx += n
        faces = np.array(faces_list, dtype=np.int32) if faces_list else np.zeros((0, 3), dtype=np.int32)
    return trimesh.Trimesh(vertices=verts, faces=faces)




def _debug_print(msg):
    print(f"[DEBUG] {msg}", file=sys.stderr)
    if sys.stderr:
        try:
            sys.stderr.flush()
        except (AttributeError, OSError):
            pass


class STLViewerWidget(QWidget):
    """Minimal pygfx-based 3D viewer for STL files. File upload and display only."""

    file_dropped = pyqtSignal(str)
    click_to_upload = pyqtSignal()
    drop_error = pyqtSignal(str)
    part_clicked = pyqtSignal(int)  # emitted when user clicks a part in parts mode

    def __init__(self, parent=None):
        _debug_print("STLViewerWidget (pygfx): Initializing...")
        logger.info("STLViewerWidget (pygfx): Initializing...")
        super().__init__(parent)

        self.layout = QStackedLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setStackingMode(QStackedLayout.StackAll)

        self.viewer_container = QWidget()
        self.viewer_layout = QGridLayout(self.viewer_container)
        self.viewer_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.viewer_container)

        self.drop_overlay = DropZoneOverlay()
        self.drop_overlay.file_dropped.connect(self._on_file_dropped)
        self.drop_overlay.click_to_upload.connect(self._on_click_upload)
        self.drop_overlay.error_occurred.connect(self._on_drop_error)
        self.layout.addWidget(self.drop_overlay)

        self.layout.setCurrentWidget(self.drop_overlay)

        self._canvas = None
        self._renderer = None
        self._scene = None
        self._camera = None
        self._controller = None
        self._mesh_obj = None  # Single mesh or gfx.Group of parts
        self._mesh_parts = []  # list of {'id', 'name', 'mesh_obj', 'trimesh', 'visible', 'face_count'}
        self.current_mesh = None  # Trimesh object for compatibility
        self.current_actor = None  # Not used; kept for hasattr checks
        self.plotter = None  # Not used; kept for hasattr checks
        self._model_loaded = False
        self._initialized = False
        self._render_mode = 'shaded'  # Match toolbar default; Phong shading on load
        self._grid_visible = False
        self._grid_objects = []  # All pygfx objects making up the bounding box grid
        self._axes_labels = []  # X, Y, Z text labels on the corner axes

        # Ruler/measurement mode state (matches viewer_widget.py interface)
        self.ruler_mode = False
        self._ruler_current_view = "front"
        self.measurement_points = []
        self.measurement_actors = []  # pygfx objects for spheres, lines, arrows, labels
        self._ruler_unit = "mm"
        self._preview_line_obj = None
        self._ruler_event_filter_installed = False
        self._camera_before_ruler = None  # Store PerspectiveCamera to restore on exit
        self._controller_before_ruler = None  # Store controller state for zoom-only

        # Annotation mode state
        self.annotation_mode = False
        self.annotations = []  # List of {'id', 'point', 'marker', 'label', 'base_color', 'display_date', 'selected'}
        self.annotation_actors = []  # All pygfx objects for annotation markers/labels
        self._annotation_callback = None
        self._annotation_event_filter_installed = False
        self._annotation_trimesh = None  # trimesh.Trimesh for raycasting

        # Screenshot mode state
        self.screenshot_mode = False
        self._screenshot_overlay = None
        self.screenshot_taken = None  # will be set as pyqtSignal-like callback

        # Draw mode state
        self.draw_mode = False
        self._draw_color = '#FF0000'
        self._draw_strokes = []  # list of pygfx.Line objects in scene
        self._draw_strokes_data = []  # parallel list for export: [{'points': [...], 'color': '...'}]
        self._current_stroke_points = []  # points being drawn
        self._current_stroke_line = None  # live preview line
        self._draw_event_filter_installed = False
        self._drawing_active = False  # True while mouse button is held
        self._eraser_mode = False  # When True, clicks erase strokes instead of drawing

        # Parts pick mode state
        self.parts_pick_mode = False
        self._parts_pick_event_filter_installed = False

        # Arrow mode state
        self.arrow_mode = False
        self._arrow_objects = []  # list of {'id', 'group', 'point', 'direction', 'length_factor', 'color'}
        self._arrow_next_id = 1
        self._arrow_event_filter_installed = False
        self._arrow_dragging = None  # arrow id being manipulated
        self._arrow_drag_start = None  # (x, y) screen start
        self._arrow_added_callback = None  # called with arrow_id when a new arrow is placed

        # Zoom buttons overlay (shown in screenshot mode) - bottom-left
        from PyQt5.QtWidgets import QPushButton, QVBoxLayout, QLabel
        from PyQt5.QtGui import QIcon
        self._zoom_controls_overlay = QFrame(self.viewer_container)
        self._zoom_controls_overlay.setStyleSheet(
            "background-color: rgba(255,255,255,0.85); border-radius: 6px; border: 1px solid #ddd;"
        )
        zoom_layout = QVBoxLayout(self._zoom_controls_overlay)
        zoom_layout.setContentsMargins(6, 6, 6, 6)
        zoom_layout.setSpacing(4)
        zoom_label = QLabel("Zoom")
        zoom_label.setStyleSheet("color: #333; font-size: 10px; font-weight: 500; background: transparent;")
        zoom_layout.addWidget(zoom_label, 0, Qt.AlignCenter)
        zoom_plus_path = _get_zoom_icon_path("zoom_plus.png")
        zoom_minus_path = _get_zoom_icon_path("zoom_minus.png")
        self._zoom_in_btn = QPushButton()
        self._zoom_out_btn = QPushButton()
        if zoom_plus_path and zoom_plus_path.exists():
            self._zoom_in_btn.setIcon(QIcon(str(zoom_plus_path)))
        else:
            self._zoom_in_btn.setText("+")
        if zoom_minus_path and zoom_minus_path.exists():
            self._zoom_out_btn.setIcon(QIcon(str(zoom_minus_path)))
        else:
            self._zoom_out_btn.setText("−")
        for btn in (self._zoom_in_btn, self._zoom_out_btn):
            btn.setFixedSize(36, 28)
            btn.setIconSize(QSize(18, 18))
            btn.setStyleSheet(
                "QPushButton { background: #f0f0f0; border: 1px solid #ccc; border-radius: 4px; "
                "font-size: 16px; font-weight: bold; color: #333; }"
                "QPushButton:hover { background: #e0e0e0; }"
                "QPushButton:pressed { background: #d0d0d0; }"
            )
        zoom_layout.addWidget(self._zoom_in_btn)
        zoom_layout.addWidget(self._zoom_out_btn)
        self._zoom_controls_overlay.setFixedSize(52, 90)
        self._zoom_controls_overlay.hide()
        self._zoom_in_btn.clicked.connect(lambda: self._screenshot_zoom(1.15))
        self._zoom_out_btn.clicked.connect(lambda: self._screenshot_zoom(0.85))

        # Object control overlay (gizmo + label, shown in annotation mode)
        self._object_control_overlay = QFrame(self.viewer_container)
        self._object_control_overlay.setStyleSheet(
            "background-color: rgba(255,255,255,0.85); border-radius: 6px; border: 1px solid #ddd;"
        )
        overlay_layout = QVBoxLayout(self._object_control_overlay)
        overlay_layout.setContentsMargins(6, 6, 6, 6)
        overlay_layout.setSpacing(4)
        self._object_control_label = QLabel("3D control")
        self._object_control_label.setStyleSheet(
            "color: #000000; font-size: 10px; font-weight: 500; background: transparent;"
        )
        overlay_layout.addWidget(self._object_control_label, 0, Qt.AlignCenter)
        self._orientation_gizmo = OrientationGizmoWidget(self._object_control_overlay)
        overlay_layout.addWidget(self._orientation_gizmo, 0, Qt.AlignCenter)
        self._object_control_overlay.hide()
        self._object_control_overlay.setFixedSize(
            OrientationGizmoWidget.SIZE + 20,
            OrientationGizmoWidget.SIZE + 36
        )
        self._orientation_gizmo.rotation_delta.connect(self._on_gizmo_rotate)

        _debug_print("STLViewerWidget (pygfx): Basic init complete")

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initialized:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(100, self._init_pygfx)

    def resizeEvent(self, event):
        """Update camera aspect and reframe on resize (e.g. when annotation panel opens)."""
        super().resizeEvent(event)
        if self._initialized and self._camera is not None and self._canvas is not None and self._mesh_obj is not None:
            from PyQt5.QtCore import QTimer
            # Defer reframe so layout has settled (fixes object shrinking when viewport changes)
            QTimer.singleShot(50, self.reframe_for_viewport)
        # Keep screenshot overlay sized to viewer
        if self._screenshot_overlay is not None and self._screenshot_overlay.isVisible():
            self._screenshot_overlay.setGeometry(self.viewer_container.rect())

    def _init_pygfx(self):
        if self._initialized:
            return
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()

            if not self.isVisible() or not self.window().isVisible():
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(200, self._init_pygfx)
                return

            _debug_print("STLViewerWidget (pygfx): Creating pygfx canvas...")
            import pygfx as gfx
            from rendercanvas.qt import QRenderWidget

            self._canvas = QRenderWidget(parent=self.viewer_container)
            self.viewer_layout.addWidget(self._canvas)
            # Overlay for 3D control gizmo (annotation mode) - bottom-right corner
            self.viewer_layout.addWidget(
                self._object_control_overlay, 0, 0, 1, 1,
                Qt.AlignRight | Qt.AlignBottom
            )
            # Overlay for zoom controls (screenshot mode) - bottom-left corner
            self.viewer_layout.addWidget(
                self._zoom_controls_overlay, 0, 0, 1, 1,
                Qt.AlignLeft | Qt.AlignBottom
            )

            self._renderer = gfx.WgpuRenderer(self._canvas)
            # SSAA for sharp edges (PyVista uses FXAA/SSAA)
            try:
                self._renderer.pixel_scale = 2
            except Exception:
                pass

            self._scene = gfx.Scene()
            # White background (PyVista: background_color='white')
            self._background = gfx.Background.from_color("#ffffff")
            self._scene.add(self._background)

            # Lighting: balanced ambient + directional for general viewing
            # (metallic preset accent lights override when applied)
            self._scene.add(gfx.AmbientLight(intensity=0.6))
            light1 = gfx.DirectionalLight(color="white", intensity=1.5)
            light1.local.position = (5, 5, 5)
            light1.look_at((0, 0, 0))
            self._scene.add(light1)
            light2 = gfx.DirectionalLight(color="white", intensity=0.8)
            light2.local.position = (-3, 2, 3)
            light2.look_at((0, 0, 0))
            self._scene.add(light2)

            # Axes (positioned when mesh loads)
            try:
                self._axes = gfx.AxesHelper(1.0)
                self._axes.visible = False  # Show when mesh loaded
                self._scene.add(self._axes)
            except Exception:
                self._axes = None

            w, h = max(400, self.width()), max(300, self.height())
            self._camera = gfx.PerspectiveCamera(50, w / h)
            self._camera.local.position = (0, 0, 5)
            self._camera.local.up = (0, 1, 0)  # Y-up: drag left/right rotates around Y axis
            self._camera.show_pos((0, 0, 0))

            self._controller = gfx.TrackballController(
                self._camera, register_events=self._renderer
            )
            self._controller.auto_update = True

            def animate():
                if self._renderer and self._scene and self._camera:
                    self._update_annotation_label_visibility()
                    self._renderer.render(self._scene, self._camera)

            self._canvas.request_draw(animate)
            self._initialized = True
            _debug_print("STLViewerWidget (pygfx): pygfx initialized")
            logger.info("STLViewerWidget (pygfx): pygfx initialized")

        except Exception as e:
            _debug_print(f"STLViewerWidget (pygfx): ERROR: {e}")
            logger.error(f"STLViewerWidget (pygfx): Init failed: {e}", exc_info=True)

    def load_stl(self, file_path):
        """Load and display a 3D file (STL, STEP, 3DM, OBJ, IGES, PLY). Returns True if successful."""
        logger.info(f"load_stl (pygfx): Loading {file_path}")

        if not self._initialized or self._scene is None:
            logger.warning("load_stl (pygfx): Not initialized yet")
            from PyQt5.QtWidgets import QApplication
            for _ in range(50):
                QApplication.processEvents()
                if self._initialized and self._scene is not None:
                    break
                import time
                time.sleep(0.1)
            if not self._initialized or self._scene is None:
                logger.error("load_stl (pygfx): Init failed")
                return False

        file_ext = file_path.lower()
        supported = ('.stl', '.obj', '.ply', '.step', '.stp', '.3dm', '.iges', '.igs', '.dxf')
        if not any(file_ext.endswith(ext) for ext in supported):
            logger.warning(f"load_stl (pygfx): Unsupported format, got {file_ext}")
            return False

        try:
            import pygfx as gfx
            import trimesh
            import pyvista as pv

            if self._mesh_obj is not None:
                self._scene.remove(self._mesh_obj)
                self._mesh_obj = None

            mesh_tri = None
            pv_mesh = None

            def _scene_has_geometry(candidate):
                if not isinstance(candidate, trimesh.Scene):
                    return False
                for g in candidate.geometry.values():
                    if isinstance(g, trimesh.Trimesh) and len(g.vertices) > 0 and len(g.faces) > 0:
                        return True
                return False

            def _segment_by_angle(mesh_input, angle_threshold_deg=30):
                """Segment a connected mesh into regions separated by sharp dihedral edges."""
                import networkx as nx
                try:
                    adj = mesh_input.face_adjacency
                    angles = mesh_input.face_adjacency_angles
                except Exception as e:
                    logger.info(f"parts_debug (pygfx): face_adjacency failed: {e}")
                    return [mesh_input]

                n_faces = len(mesh_input.faces)
                if n_faces < 10:
                    return [mesh_input]

                threshold_rad = np.radians(angle_threshold_deg)
                smooth_mask = angles < threshold_rad
                smooth_edges = adj[smooth_mask]

                G = nx.Graph()
                G.add_nodes_from(range(n_faces))
                G.add_edges_from(smooth_edges.tolist())
                face_groups = list(nx.connected_components(G))

                if len(face_groups) <= 1:
                    return [mesh_input]

                # Safety: if too many segments, skip
                if len(face_groups) > 200:
                    logger.info(f"parts_debug (pygfx): angle segmentation produced {len(face_groups)} segments, skipping")
                    return [mesh_input]

                # Merge tiny segments (< 4 faces) into largest neighbor
                MIN_FACES = 4
                large_groups = []
                tiny_groups = []
                for grp in face_groups:
                    if len(grp) >= MIN_FACES:
                        large_groups.append(grp)
                    else:
                        tiny_groups.append(grp)

                if not large_groups:
                    return [mesh_input]

                # Assign tiny faces to the largest group overall (simple merge)
                if tiny_groups:
                    biggest = max(large_groups, key=len)
                    for tg in tiny_groups:
                        biggest.update(tg)

                # Extract sub-meshes
                segments = []
                for grp in sorted(large_groups, key=len, reverse=True):
                    face_indices = np.array(sorted(grp))
                    try:
                        sub = mesh_input.submesh([face_indices], append=True)
                        if isinstance(sub, trimesh.Trimesh) and len(sub.faces) > 0:
                            segments.append(sub)
                    except Exception:
                        pass

                if not segments:
                    return [mesh_input]

                logger.info(f"parts_debug (pygfx): angle segmentation produced {len(segments)} segments from {n_faces} faces")
                return segments

            def _split_reasonable_components(source_mesh):
                """Split mesh into connected components, then segment large ones by dihedral angle."""
                try:
                    components = list(source_mesh.split(only_watertight=False))
                except Exception as e:
                    logger.info(f"parts_debug (pygfx): split() failed: {e}, returning single mesh")
                    return [source_mesh]

                components = [
                    c for c in components
                    if isinstance(c, trimesh.Trimesh) and len(c.vertices) > 0 and len(c.faces) > 0
                ]
                logger.info(f"parts_debug (pygfx): trimesh.split returned {len(components)} components")
                if len(components) <= 1:
                    comp = components[0] if components else source_mesh
                    # Even a single connected component can be segmented by angle
                    if len(comp.faces) >= 50:
                        segmented = _segment_by_angle(comp)
                        if len(segmented) > 1:
                            logger.info(f"parts_debug (pygfx): single component segmented into {len(segmented)} parts by angle")
                            return segmented
                    return [comp]

                # Safety valve: cap at 5000 raw components
                if len(components) > 5000:
                    logger.info(f"parts_debug (pygfx): >5000 components, returning single mesh")
                    return [source_mesh]

                # Apply angle segmentation to large connected components
                result = []
                for comp in components:
                    if len(comp.faces) >= 50:
                        segmented = _segment_by_angle(comp)
                        result.extend(segmented)
                    else:
                        result.append(comp)

                logger.info(f"parts_debug (pygfx): final {len(result)} parts after connectivity + angle segmentation")
                return result

            # STEP
            if file_ext.endswith('.step') or file_ext.endswith('.stp'):
                logger.info("load_stl (pygfx): Loading STEP with StepLoader...")
                from core.step_loader import StepLoader
                pv_mesh = StepLoader.load_step(file_path)
                if pv_mesh is None or pv_mesh.n_points == 0:
                    raise ValueError("STEP loader returned empty mesh")
                mesh_tri = _pyvista_to_trimesh(pv_mesh)
            # 3DM
            elif file_ext.endswith('.3dm'):
                logger.info("load_stl (pygfx): Loading 3DM with Rhino3dmLoader...")
                from core.rhino3dm_loader import Rhino3dmLoader
                pv_mesh = Rhino3dmLoader.load_3dm(file_path)
                if pv_mesh is None or pv_mesh.n_points == 0:
                    raise ValueError("3DM loader returned empty mesh")
                mesh_tri = _pyvista_to_trimesh(pv_mesh)
            # IGES
            elif file_ext.endswith('.iges') or file_ext.endswith('.igs'):
                logger.info("load_stl (pygfx): Loading IGES with IgesLoader...")
                from core.iges_loader import IgesLoader
                pv_mesh = IgesLoader.load_iges(file_path)
                if pv_mesh is None or pv_mesh.n_points == 0:
                    raise ValueError("IGES loader returned empty mesh")
                mesh_tri = _pyvista_to_trimesh(pv_mesh)
            # DXF
            elif file_ext.endswith('.dxf'):
                logger.info("load_stl (pygfx): Loading DXF with DxfLoader...")
                from core.dxf_loader import DxfLoader
                pv_mesh = DxfLoader.load_dxf(file_path)
                if pv_mesh is None or pv_mesh.n_points == 0:
                    raise ValueError("DXF loader returned empty mesh")
                mesh_tri = _pyvista_to_trimesh(pv_mesh)
            # OBJ: prefer Scene (preserves object groups), then fallback chain
            elif file_ext.endswith('.obj'):
                mesh_tri = None
                try:
                    mesh_tri = trimesh.load(file_path, force='scene', process=False)
                except Exception:
                    try:
                        mesh_tri = trimesh.load(file_path, force='mesh', process=False)
                    except Exception:
                        mesh_tri = None

                if mesh_tri is None or (
                    isinstance(mesh_tri, trimesh.Trimesh) and len(mesh_tri.vertices) == 0
                ) or (
                    isinstance(mesh_tri, trimesh.Scene) and not _scene_has_geometry(mesh_tri)
                ):
                    try:
                        pv_mesh = pv.read(file_path)
                    except Exception:
                        try:
                            import meshio
                            meshio_mesh = meshio.read(file_path)
                            pts = meshio_mesh.points
                            cells = None
                            for cb in meshio_mesh.cells:
                                if cb.type == "triangle":
                                    cells = cb.data
                                    break
                            if cells is None and meshio_mesh.cells:
                                cells = meshio_mesh.cells[0].data
                            if cells is not None and len(pts) > 0:
                                n_verts = cells.shape[1] if cells.ndim == 2 else 3
                                cells_flat = np.column_stack([np.full(len(cells), n_verts), cells]).ravel().astype(np.int32)
                                pv_mesh = pv.PolyData(pts, cells_flat).triangulate()
                            else:
                                raise ValueError("No cells")
                        except Exception:
                            from core.obj_loader import ObjLoader
                            pv_mesh = ObjLoader.load_obj(file_path)
                    if pv_mesh is not None and pv_mesh.n_points > 0:
                        mesh_tri = _pyvista_to_trimesh(pv_mesh)

                if mesh_tri is None or (
                    isinstance(mesh_tri, trimesh.Trimesh) and len(mesh_tri.vertices) == 0
                ) or (
                    isinstance(mesh_tri, trimesh.Scene) and not _scene_has_geometry(mesh_tri)
                ):
                    raise ValueError("OBJ file could not be loaded")
            # STL, PLY: trimesh
            else:
                mesh_tri = trimesh.load(file_path, force='mesh')
                if mesh_tri is None:
                    raise ValueError("No mesh in file")
                pv_mesh = _trimesh_to_pyvista(mesh_tri)

            # Normalize mesh_tri: preserve sub-meshes as separate parts.
            # If we only have one mesh, split by disconnected components so assemblies
            # can still be isolated in the Parts panel.
            sub_meshes = []  # list of (name, trimesh.Trimesh)
            if isinstance(mesh_tri, trimesh.Scene):
                named_meshes = []

                # Prefer transformed meshes from scene graph dump
                try:
                    dumped = mesh_tri.dump(concatenate=False)
                    dumped_meshes = [
                        g for g in dumped
                        if isinstance(g, trimesh.Trimesh) and len(g.vertices) > 0 and len(g.faces) > 0
                    ]
                    if dumped_meshes:
                        named_meshes = [(f"Part {i + 1}", g) for i, g in enumerate(dumped_meshes)]
                except Exception:
                    named_meshes = []

                # Fallback: raw scene geometry map
                if not named_meshes:
                    named_meshes = [
                        (str(name), g) for name, g in mesh_tri.geometry.items()
                        if isinstance(g, trimesh.Trimesh) and len(g.vertices) > 0 and len(g.faces) > 0
                    ]

                if not named_meshes:
                    raise ValueError("No meshes in file")

                exploded_parts = []
                for part_name, source_mesh in named_meshes:
                    components = _split_reasonable_components(source_mesh)

                    if len(components) <= 1:
                        exploded_parts.append((part_name, source_mesh))
                    else:
                        for comp_idx, comp in enumerate(components, 1):
                            exploded_parts.append((f"{part_name} #{comp_idx}", comp))

                sub_meshes = exploded_parts

            elif isinstance(mesh_tri, trimesh.Trimesh) and len(mesh_tri.vertices) > 0:
                fname = Path(file_path).stem if file_path else "Part"
                logger.info(f"parts_debug (pygfx): Single Trimesh, verts={len(mesh_tri.vertices)}, faces={len(mesh_tri.faces)}")
                components = _split_reasonable_components(mesh_tri)

                if len(components) > 1:
                    sub_meshes = [(f"{fname} #{i + 1}", comp) for i, comp in enumerate(components)]
                    logger.info(f"parts_debug (pygfx): Using {len(sub_meshes)} components")
                else:
                    sub_meshes = [(fname, mesh_tri)]
                    logger.info(f"parts_debug (pygfx): Single component, part='{fname}'")
            else:
                raise ValueError("No mesh in file")

            if not sub_meshes:
                raise ValueError("No mesh in file")

            # Combined mesh for raycasting/MeshCalculator
            mesh_tri = trimesh.util.concatenate([g for _, g in sub_meshes]) if len(sub_meshes) > 1 else sub_meshes[0][1]
            logger.info(f"load_stl (pygfx): Built {len(sub_meshes)} part(s) for panel: {[(n, len(t.faces)) for n, t in sub_meshes]}")

            if not isinstance(mesh_tri, trimesh.Trimesh) or len(mesh_tri.vertices) == 0:
                raise ValueError("No mesh in file")

            # Ensure PyVista for MeshCalculator (before flat-shading)
            if pv_mesh is None:
                pv_mesh = _trimesh_to_pyvista(mesh_tri)
            if pv_mesh is None:
                raise ValueError("Could not convert mesh for dimensions/volume calculation")

            # Build separate gfx.Mesh per sub-mesh inside a Group
            from pygfx.geometries import geometry_from_trimesh
            mesh_group = gfx.Group()
            self._mesh_parts = []
            for part_idx, (part_name, part_tri) in enumerate(sub_meshes):
                flat_tri = _trimesh_to_flat_shaded(part_tri)
                material = gfx.MeshPhongMaterial(
                    color="#ADD9E6", specular="#333333", shininess=20,
                )
                geometry = geometry_from_trimesh(flat_tri)
                part_mesh = gfx.Mesh(geometry, material)
                mesh_group.add(part_mesh)
                self._mesh_parts.append({
                    'id': part_idx,
                    'name': part_name,
                    'mesh_obj': part_mesh,
                    'trimesh': part_tri,
                    'visible': True,
                    'face_count': len(part_tri.faces),
                })

            self._mesh_obj = mesh_group
            self._scene.add(self._mesh_obj)
            self.set_render_mode(self._render_mode)

            # Keep combined flat-shaded trimesh for annotation raycasting
            mesh_tri = _trimesh_to_flat_shaded(mesh_tri)

            self.current_mesh = pv_mesh
            self._annotation_trimesh = mesh_tri  # Keep trimesh for raycasting in annotation mode
            self._model_loaded = True
            self._show_overlay(False)

            # Ensure layout is complete and canvas has valid size before framing
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()

            # Pygfx-recommended: syncs camera + controller orbit center
            # Update camera aspect from current canvas size (critical for correct framing)
            try:
                cw, ch = self._canvas.get_logical_size() if hasattr(self._canvas, 'get_logical_size') else (self.width(), self.height())
            except Exception:
                cw, ch = max(1, self.width()), max(1, self.height())
            if hasattr(self._camera, 'aspect'):
                self._camera.aspect = cw / ch
            view_dir = (1.2, -0.8, -1.0)  # isometric-like, matches PyVista default
            self._camera.show_object(
                self._mesh_obj, view_dir=view_dir, scale=1.8, up=(0, 1, 0)
            )

            # No fixed orbit target — TrackballController rotates around viewport center

            # Position axes at mesh min corner (PyVista add_axes in corner)
            if getattr(self, '_axes', None) is not None:
                try:
                    b = np.asarray(mesh_tri.bounds)
                    if b.ndim == 2 and b.shape == (2, 3):
                        mins, maxs = b[0], b[1]
                    else:
                        mins = np.array([b[0], b[2], b[4]])
                        maxs = np.array([b[1], b[3], b[5]])
                    max_dim = max(
                        float(maxs[0] - mins[0]),
                        float(maxs[1] - mins[1]),
                        float(maxs[2] - mins[2]),
                        0.01,
                    ) * 0.15
                    self._axes.local.scale = (max_dim, max_dim, max_dim)
                    self._axes.local.position = (float(mins[0]), float(mins[1]), float(mins[2]))
                    self._axes.visible = True
                    # Add X, Y, Z labels at axis tips (match AxesHelper colors: X=red, Y=green, Z=blue)
                    offset = max_dim * 0.12
                    x0, y0, z0 = float(mins[0]), float(mins[1]), float(mins[2])
                    for lbl in self._axes_labels:
                        try:
                            self._scene.remove(lbl)
                        except Exception:
                            pass
                    self._axes_labels.clear()
                    ax_lbls = [
                        ("X", (x0 + max_dim + offset, y0, z0), "#CC3333"),
                        ("Y", (x0, y0 + max_dim + offset, z0), "#33AA33"),
                        ("Z", (x0, y0, z0 + max_dim + offset), "#3366CC"),
                    ]
                    for txt, pos, color in ax_lbls:
                        m = gfx.TextMaterial(color=color)
                        m.depth_test = False
                        m.depth_write = False
                        lbl = gfx.Text(text=txt, material=m, font_size=11, anchor="middle-center", screen_space=True)
                        lbl.local.position = pos
                        self._scene.add(lbl)
                        self._axes_labels.append(lbl)
                except Exception:
                    pass

            # Force immediate redraw so object appears without needing a click
            if self._canvas:
                self._canvas.request_draw()
            QApplication.processEvents()
            # Deferred redraws to ensure WebGPU pipeline is ready
            from PyQt5.QtCore import QTimer
            def _deferred_repaint():
                if self._canvas and getattr(self, '_model_loaded', False):
                    self._canvas.request_draw()
            QTimer.singleShot(50, _deferred_repaint)
            QTimer.singleShot(200, _deferred_repaint)

            logger.info("load_stl (pygfx): Loaded successfully")
            return True

        except Exception as e:
            logger.error(f"load_stl (pygfx): Error: {e}", exc_info=True)
            return False

    def set_render_mode(self, mode):
        """Set render mode: 'solid', 'wireframe', or 'shaded'."""
        if self._mesh_obj is None:
            return
        self._render_mode = mode
        import pygfx as gfx
        # Build material based on mode
        def _make_material():
            if mode == 'wireframe':
                return gfx.MeshBasicMaterial(wireframe=True, color="#333333", wireframe_thickness=1)
            elif mode == 'shaded':
                return gfx.MeshPhongMaterial(color="#b8b8c0", specular="#a0a0a0", shininess=90)
            else:
                return gfx.MeshPhongMaterial(color="#ADD9E6", specular="#333333", shininess=20)

        # Apply to all parts in the group
        if self._mesh_parts:
            for part in self._mesh_parts:
                part['mesh_obj'].material = _make_material()
        elif hasattr(self._mesh_obj, 'material'):
            self._mesh_obj.material = _make_material()
        if self._canvas:
            self._canvas.request_draw()

    def _get_view_center_and_distance(self):
        """Get mesh center and camera distance for view presets. Returns (cx, cy, cz), distance."""
        if self.current_mesh is None:
            return (0.0, 0.0, 0.0), 5.0
        b = self.current_mesh.bounds
        cx = (b[0] + b[1]) / 2
        cy = (b[2] + b[3]) / 2
        cz = (b[4] + b[5]) / 2
        w, h, d = b[1] - b[0], b[3] - b[2], b[5] - b[4]
        dist = max(w, h, d, 1.0) * 1.5
        return (float(cx), float(cy), float(cz)), float(dist)

    def reset_view(self):
        """Reset to default isometric view."""
        if not self._initialized or self._camera is None or self._mesh_obj is None:
            return
        self._safe_set_aspect()
        view_dir = (1.2, -0.8, -1.0)
        self._camera.show_object(self._mesh_obj, view_dir=view_dir, scale=1.8, up=(0, 1, 0))
        if self._canvas:
            self._canvas.request_draw()

    def _safe_set_aspect(self):
        """Set camera aspect ratio safely (PerspectiveCamera only)."""
        try:
            cw, ch = self._canvas.get_logical_size() if hasattr(self._canvas, 'get_logical_size') else (self.width(), self.height())
        except Exception:
            cw, ch = max(1, self.width()), max(1, self.height())
        if hasattr(self._camera, 'aspect'):
            self._camera.aspect = cw / ch

    def reframe_for_viewport(self):
        """Reframe the object for the current viewport size. Call when layout changes (e.g. annotation panel show/hide)."""
        if not self._initialized or self._camera is None or self._mesh_obj is None:
            return
        try:
            self._safe_set_aspect()
            # In ruler mode, preserve the current ortho view (front/top/left/etc.) instead of
            # recomputing from camera position, which can produce wrong view when toolbar shows.
            if getattr(self, 'ruler_mode', False):
                view_presets = {
                    "front": ((1, 0, 0), (0, 1, 0)),
                    "top": ((0, 0, 1), (0, 1, 0)),
                    "left": ((-1, 0, 0), (0, 1, 0)),
                    "right": ((1, 0, 0), (0, 1, 0)),
                    "bottom": ((0, 0, -1), (0, 1, 0)),
                    "rear": ((0, -1, 0), (0, 0, 1)),
                }
                preset = view_presets.get(getattr(self, '_ruler_current_view', 'front'), ((1, 0, 0), (0, 1, 0)))
                view_dir, up = preset
                logger.debug(f"reframe_for_viewport: ruler_mode=True, preserving view={getattr(self, '_ruler_current_view', 'front')}")
            else:
                center, _ = self._get_view_center_and_distance()
                cam_pos = np.array(self._camera.local.position)
                view_dir = np.array(center) - cam_pos
                n = np.linalg.norm(view_dir)
                if n > 1e-12:
                    view_dir = tuple(view_dir / n)
                else:
                    view_dir = (1.2, -0.8, -1.0)
                up = tuple(self._camera.local.up)
            self._camera.show_object(self._mesh_obj, view_dir=view_dir, scale=1.8, up=up)
            if self._canvas:
                self._canvas.request_draw()
        except Exception as e:
            logger.debug(f"reframe_for_viewport: {e}")

    def _set_view(self, view_dir, up=(0, 1, 0)):
        """Set camera to a specific view direction."""
        if not self._initialized or self._camera is None or self._mesh_obj is None:
            return
        self._safe_set_aspect()
        self._camera.show_object(self._mesh_obj, view_dir=view_dir, scale=1.8, up=up)
        if self._canvas:
            self._canvas.request_draw()

    def view_front(self):
        """Set camera to front view (looking along +X, Y up). PyVista view_yz equivalent."""
        self._set_view(view_dir=(1, 0, 0), up=(0, 1, 0))

    def view_side(self):
        """Set camera to side view (looking along +Y, Z up). PyVista view_xz equivalent."""
        self._set_view(view_dir=(0, 1, 0), up=(0, 0, 1))

    def view_top(self):
        """Set camera to top view (looking along +Z, Y up). PyVista view_xy equivalent."""
        self._set_view(view_dir=(0, 0, 1), up=(0, 1, 0))

    def view_front_ortho(self):
        """Front orthographic view (ruler mode)."""
        self._ruler_current_view = "front"
        logger.debug("view_front_ortho: Setting front view (view_dir +X)")
        self._set_view(view_dir=(1, 0, 0), up=(0, 1, 0))

    def view_top_ortho(self):
        """Top orthographic view (ruler mode)."""
        self._ruler_current_view = "top"
        self._set_view(view_dir=(0, 0, 1), up=(0, 1, 0))

    def view_left_ortho(self):
        """Left orthographic view (camera from -X)."""
        self._ruler_current_view = "left"
        self._set_view(view_dir=(-1, 0, 0), up=(0, 1, 0))

    def view_right_ortho(self):
        """Right orthographic view (camera from +X)."""
        self._ruler_current_view = "right"
        self._set_view(view_dir=(1, 0, 0), up=(0, 1, 0))

    def view_bottom_ortho(self):
        """Bottom orthographic view (camera from -Z)."""
        self._ruler_current_view = "bottom"
        self._set_view(view_dir=(0, 0, -1), up=(0, 1, 0))

    def view_rear_ortho(self):
        """Rear orthographic view (camera from -Y)."""
        self._ruler_current_view = "rear"
        self._set_view(view_dir=(0, -1, 0), up=(0, 0, 1))

    def set_background_color(self, color):
        """Set 3D viewer background color (e.g. '#ffffff' light, '#1a1a2e' dark)."""
        if not self._initialized or not hasattr(self, '_scene') or self._scene is None:
            return
        try:
            import pygfx as gfx
            if getattr(self, '_background', None) is not None:
                self._scene.remove(self._background)
            self._background = gfx.Background.from_color(color)
            self._scene.add(self._background)
            if self._canvas:
                self._canvas.request_draw()
            # Update drop overlay when visible (no model loaded)
            if not self._model_loaded and hasattr(self, 'drop_overlay'):
                self.drop_overlay.setStyleSheet(f"DropZoneOverlay {{ background-color: {color}; }}")
                is_dark = color.lower() == '#1a1a2e'
                primary = '#e2e8f0' if is_dark else '#1a1a2e'
                secondary = '#94a3b8' if is_dark else '#4a5568'
                helper = '#64748b' if is_dark else '#a0aec0'
                self.drop_overlay.primary_label.setStyleSheet(f"QLabel {{ font-size: 18px; font-weight: 600; color: {primary}; background: transparent; }}")
                self.drop_overlay.secondary_label.setStyleSheet(f"QLabel {{ font-size: 14px; font-weight: 400; color: {secondary}; background: transparent; }}")
                self.drop_overlay.helper_label.setStyleSheet(f"QLabel {{ font-size: 11px; font-weight: 400; color: {helper}; background: transparent; margin-top: 8px; }}")
        except Exception as e:
            logger.warning(f"set_background_color (pygfx): {e}")

    def clear_viewer(self):
        """Clear the 3D viewer."""
        self.remove_grid()
        if self._scene and self._mesh_obj:
            self._scene.remove(self._mesh_obj)
            self._mesh_obj = None
        self._mesh_parts = []
        self.clear_drawings()
        if getattr(self, '_axes', None) is not None:
            try:
                self._axes.visible = False
            except Exception:
                pass
        for lbl in getattr(self, '_axes_labels', []):
            try:
                if self._scene:
                    self._scene.remove(lbl)
            except Exception:
                pass
        self._axes_labels.clear()
        self.current_mesh = None
        self._annotation_trimesh = None
        self._model_loaded = False
        self._show_overlay(True)
        if self._canvas:
            self._canvas.request_draw()
        logger.info("clear_viewer (pygfx): Cleared")

    def _on_file_dropped(self, file_path):
        self.file_dropped.emit(file_path)

    def _on_click_upload(self):
        self.click_to_upload.emit()

    def _on_drop_error(self, error_msg):
        self.drop_error.emit(error_msg)

    # ── Bounding-box grid with axis labels & ticks ──────────────────────

    def show_grid(self):
        """Show a 3D bounding box with axis labels and tick marks around the loaded mesh."""
        if not self._initialized or self._scene is None or self.current_mesh is None:
            return
        self.remove_grid()
        self._grid_visible = True

        import pygfx as gfx

        bounds = self.current_mesh.bounds  # (xmin,xmax,ymin,ymax,zmin,zmax)
        xmin, xmax, ymin, ymax, zmin, zmax = [float(v) for v in bounds]

        # Dimensions in mm (mesh is in mm)
        width = xmax - xmin
        height = ymax - ymin
        depth = zmax - zmin

        # ── 12 edges of the bounding box ──
        corners = np.array([
            [xmin, ymin, zmin], [xmax, ymin, zmin],
            [xmax, ymax, zmin], [xmin, ymax, zmin],
            [xmin, ymin, zmax], [xmax, ymin, zmax],
            [xmax, ymax, zmax], [xmin, ymax, zmax],
        ], dtype=np.float32)
        edges = [
            (0,1),(1,2),(2,3),(3,0),  # bottom
            (4,5),(5,6),(6,7),(7,4),  # top
            (0,4),(1,5),(2,6),(3,7),  # verticals
        ]
        for a, b in edges:
            positions = np.array([corners[a], corners[b]], dtype=np.float32)
            geom = gfx.Geometry(positions=positions)
            line = gfx.Line(geom, gfx.LineMaterial(color="#888888", thickness=1.0))
            self._scene.add(line)
            self._grid_objects.append(line)

        # ── Helper: generate nice tick values ──
        def _nice_ticks(vmin, vmax, n=5):
            span = vmax - vmin
            if span <= 0:
                return [vmin]
            raw_step = span / n
            mag = 10 ** np.floor(np.log10(raw_step))
            residual = raw_step / mag
            if residual <= 1.5:
                nice = 1
            elif residual <= 3:
                nice = 2
            elif residual <= 7:
                nice = 5
            else:
                nice = 10
            step = nice * mag
            start = np.ceil(vmin / step) * step
            ticks = []
            v = start
            while v <= vmax + step * 0.01:
                ticks.append(round(float(v), 6))
                v += step
            return ticks

        # ── Helper: create a text label (pygfx Text API: text=, material=, no TextGeometry) ──
        def _make_text(text, pos, font_size=10, anchor="middle-center"):
            obj = gfx.Text(
                text=str(text),
                material=gfx.TextMaterial(color="#333333"),
                font_size=font_size,
                anchor=anchor,
                screen_space=True,
            )
            obj.local.position = tuple(float(p) for p in pos)
            return obj

        # ── Helper: small tick line ──
        def _make_tick_line(p1, p2):
            positions = np.array([p1, p2], dtype=np.float32)
            geom = gfx.Geometry(positions=positions)
            return gfx.Line(geom, gfx.LineMaterial(color="#888888", thickness=1.0))

        tick_len_x = (ymax - ymin) * 0.02 if (ymax - ymin) > 0 else 0.1
        tick_len_y = (xmax - xmin) * 0.02 if (xmax - xmin) > 0 else 0.1
        tick_len_z = (xmax - xmin) * 0.02 if (xmax - xmin) > 0 else 0.1
        label_offset = 0.08  # fraction of axis range for label placement

        # ── X axis ticks & labels (along bottom-front edge at ymin, zmin) ──
        x_ticks = _nice_ticks(xmin, xmax)
        for v in x_ticks:
            tick = _make_tick_line([v, ymin, zmin], [v, ymin - tick_len_x, zmin])
            self._scene.add(tick)
            self._grid_objects.append(tick)
            lbl = _make_text(f"{v:.1f}", [v, ymin - tick_len_x * 3, zmin], font_size=9)
            self._scene.add(lbl)
            self._grid_objects.append(lbl)
        # Axis title
        x_title = _make_text("X Axis", [(xmin + xmax) / 2, ymin - (ymax - ymin) * label_offset * 2, zmin], font_size=12)
        self._scene.add(x_title)
        self._grid_objects.append(x_title)

        # ── Y axis ticks & labels (along bottom-left edge at xmin, zmin) ──
        y_ticks = _nice_ticks(ymin, ymax)
        for v in y_ticks:
            tick = _make_tick_line([xmin, v, zmin], [xmin - tick_len_y, v, zmin])
            self._scene.add(tick)
            self._grid_objects.append(tick)
            lbl = _make_text(f"{v:.1f}", [xmin - tick_len_y * 3, v, zmin], font_size=9)
            self._scene.add(lbl)
            self._grid_objects.append(lbl)
        y_title = _make_text("Y Axis", [xmin - (xmax - xmin) * label_offset * 2, (ymin + ymax) / 2, zmin], font_size=12)
        self._scene.add(y_title)
        self._grid_objects.append(y_title)

        # ── Z axis ticks & labels (along left-front vertical edge at xmin, ymin) ──
        z_ticks = _nice_ticks(zmin, zmax)
        for v in z_ticks:
            tick = _make_tick_line([xmin, ymin, v], [xmin - tick_len_z, ymin, v])
            self._scene.add(tick)
            self._grid_objects.append(tick)
            lbl = _make_text(f"{v:.1f}", [xmin - tick_len_z * 3, ymin, v], font_size=9)
            self._scene.add(lbl)
            self._grid_objects.append(lbl)
        z_title = _make_text("Z Axis", [xmin - (xmax - xmin) * label_offset * 2, ymin, (zmin + zmax) / 2], font_size=12)
        self._scene.add(z_title)
        self._grid_objects.append(z_title)

        # ── Dimension length labels (width, height, depth in mm) ──
        def _fmt_dim(val):
            if val < 0.01:
                return f"{val * 1000:.2f} µm"
            if val < 1:
                return f"{val:.2f} mm"
            if val < 100:
                return f"{val:.1f} mm"
            return f"{val:.0f} mm"

        # Width (X): midpoint of bottom-front edge, slightly below
        width_lbl = _make_text(_fmt_dim(width), [(xmin + xmax) / 2, ymin - (ymax - ymin) * label_offset * 3.5, zmin], font_size=10)
        self._scene.add(width_lbl)
        self._grid_objects.append(width_lbl)

        # Height (Y): midpoint of left vertical edge, slightly left
        height_lbl = _make_text(_fmt_dim(height), [xmin - (xmax - xmin) * label_offset * 3.5, (ymin + ymax) / 2, zmin], font_size=10)
        self._scene.add(height_lbl)
        self._grid_objects.append(height_lbl)

        # Depth (Z): midpoint of left-front vertical edge, slightly left
        depth_lbl = _make_text(_fmt_dim(depth), [xmin - (xmax - xmin) * label_offset * 3.5, ymin, (zmin + zmax) / 2], font_size=10)
        self._scene.add(depth_lbl)
        self._grid_objects.append(depth_lbl)

        if self._canvas:
            self._canvas.request_draw()

    def remove_grid(self):
        """Remove the bounding box grid from the scene."""
        for obj in self._grid_objects:
            try:
                self._scene.remove(obj)
            except Exception:
                pass
        self._grid_objects.clear()
        self._grid_visible = False
        if self._canvas:
            self._canvas.request_draw()

    def toggle_grid(self):
        """Toggle the bounding box grid on/off."""
        if self._grid_visible:
            self.remove_grid()
        else:
            self.show_grid()

    # ========== Ruler Mode (point-to-point measurement) ==========

    def _screen_to_world_focal_plane(self, x, y):
        """Convert screen (x, y) to world coordinates on the camera's focal plane.
        Used for ruler mode so clicks map to the view plane. Returns (x,y,z) or None.
        """
        if self._camera is None or self._canvas is None:
            return None
        try:
            cw, ch = self._canvas.get_logical_size() if hasattr(self._canvas, 'get_logical_size') else (self.width(), self.height())
        except Exception:
            return None
        if cw <= 0 or ch <= 0:
            return None
        try:
            # Qt: (0,0) top-left. NDC: x in [-1,1] left-to-right, y in [-1,1] bottom-to-top
            ndc_x = 2.0 * float(x) / cw - 1.0
            ndc_y = 1.0 - 2.0 * float(y) / ch
            vm = np.array(self._camera.view_matrix)
            ipm = np.array(self._camera.projection_matrix_inverse)
            # Unproject near (z=0) and far (z=1) in NDC
            ndc_near = np.array([ndc_x, ndc_y, 0, 1])
            ndc_far = np.array([ndc_x, ndc_y, 1, 1])
            ivm = np.linalg.inv(vm)
            world_near = ivm @ ipm @ ndc_near
            world_far = ivm @ ipm @ ndc_far
            world_near = world_near[:3] / (world_near[3] + 1e-12)
            world_far = world_far[:3] / (world_far[3] + 1e-12)
            cam_dir = world_far - world_near
            cam_dir_norm = np.linalg.norm(cam_dir)
            if cam_dir_norm < 1e-12:
                return None
            cam_dir = cam_dir / cam_dir_norm
            # Focal plane through mesh center
            focal_pt = np.array(self._get_view_center_and_distance()[0])
            offset = np.dot(focal_pt - world_near, cam_dir)
            world_pos = world_near + cam_dir * offset
            return tuple(float(p) for p in world_pos)
        except Exception:
            return None

    def eventFilter(self, obj, event):
        """Qt event filter: handle ruler_mode, annotation_mode, draw_mode, and parts_pick_mode events."""
        if self._canvas is None:
            return super().eventFilter(obj, event)
        if not self.ruler_mode and not self.annotation_mode and not self.draw_mode and not self.arrow_mode and not self.parts_pick_mode:
            return super().eventFilter(obj, event)
        # Check if obj is canvas, self, viewer_container, or a descendant of any
        is_our_widget = obj in (self._canvas, self, self.viewer_container)
        if not is_our_widget and obj is not None:
            w = obj
            while w is not None:
                if w in (self._canvas, self, self.viewer_container):
                    is_our_widget = True
                    break
                w = w.parent() if hasattr(w, 'parent') and callable(w.parent) else None
        if is_our_widget:
            if self.ruler_mode:
                return self._ruler_event_filter_impl(obj, event)
            if self.annotation_mode:
                return self._annotation_event_filter_impl(obj, event)
            if self.arrow_mode:
                return self._arrow_event_filter_impl(obj, event)
            if self.draw_mode:
                return self._draw_event_filter_impl(obj, event)
            if self.parts_pick_mode:
                return self._parts_pick_event_filter_impl(obj, event)
        return super().eventFilter(obj, event)

    def _ruler_event_filter_impl(self, obj, event):
        """Handle ruler mode events. Return True to consume, False to pass through."""
        if not self.ruler_mode or self._canvas is None:
            return False
        t = event.type()
        if t == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                pos = event.pos()
                self._on_ruler_click(pos.x(), pos.y())
                return True
            if event.button() in (Qt.RightButton, Qt.MidButton):
                return True  # Block pan
        elif t == QEvent.MouseButtonRelease:
            if event.button() == Qt.LeftButton:
                return True
            if event.button() in (Qt.RightButton, Qt.MidButton):
                return True
        elif t == QEvent.MouseMove:
            pos = event.pos()
            self._on_ruler_mouse_move(pos.x(), pos.y())
            return True
        elif t == QEvent.Wheel:
            # Manually handle zoom for orthographic camera
            self._handle_ruler_wheel(event)
            return True
        return False

    def _handle_ruler_wheel(self, event):
        """Handle wheel zoom in ruler mode by directly scaling OrthographicCamera width/height."""
        if self._camera is None or self._canvas is None:
            return
        try:
            dy = event.angleDelta().y()
            if dy == 0:
                return
            # Zoom factor: scroll up = zoom in (smaller width), scroll down = zoom out
            factor = 0.9 if dy > 0 else 1.1
            import pygfx as gfx
            if isinstance(self._camera, gfx.OrthographicCamera):
                self._camera.width *= factor
                self._camera.height *= factor
            else:
                # Fallback for perspective camera
                delta = float(dy) / 120.0 * 0.02
                try:
                    w, h = self._canvas.get_logical_size() if hasattr(self._canvas, 'get_logical_size') else (self._canvas.width(), self._canvas.height())
                except Exception:
                    w, h = self._canvas.width(), self._canvas.height()
                rect = (0, 0, max(1, w), max(1, h))
                self._controller.zoom((delta, delta), rect)
            self._canvas.request_draw()
        except Exception as e:
            logger.warning(f"_handle_ruler_wheel: {e}")

    def _on_ruler_click(self, x, y):
        """Handle left click in ruler mode: unproject to focal plane (between user and object)."""
        if not self.ruler_mode:
            return
        world_pos = self._screen_to_world_focal_plane(x, y)
        if world_pos is None:
            return
        self._on_point_picked(world_pos)

    def _on_ruler_mouse_move(self, x, y):
        """Update preview line from first point to mouse position (with snapping)."""
        if not self.ruler_mode or len(self.measurement_points) != 1:
            self._clear_preview_line()
            return
        world_pos = self._screen_to_world_focal_plane(x, y)
        if world_pos is None:
            return
        snapped = self._maybe_snap_to_axis(self.measurement_points[0], world_pos)
        self._update_preview_line(self.measurement_points[0], snapped)

    def _get_nearest_mesh_point(self, world_pos, max_distance_ratio=0.02):
        """Disabled - no longer snap to mesh vertices. Always return the input point."""
        return world_pos

    def _get_camera_view_axes(self):
        """Return (view_right, view_up) in world space for screen-space snapping.
        Uses camera world matrix for reliable axes in Front/Left/Rear/Right ortho views.
        """
        cam = self._camera
        try:
            # Use world matrix: columns 0,1 = right, up in world space
            w = np.array(cam.world.matrix)
            if w.shape[0] >= 3 and w.shape[1] >= 2:
                view_right = w[:3, 0].copy()
                view_up = w[:3, 1].copy()
                rn = np.linalg.norm(view_right)
                un = np.linalg.norm(view_up)
                if rn > 1e-8 and un > 1e-8:
                    return view_right / rn, view_up / un
        except Exception:
            pass
        # Fallback: cross product
        view_up = np.array(cam.local.up)
        center = np.array(self._get_view_center_and_distance()[0])
        pos = np.array(cam.local.position)
        forward = center - pos
        forward_norm = np.linalg.norm(forward)
        if forward_norm < 1e-12:
            forward = np.array([0, 0, -1])
        else:
            forward = forward / forward_norm
        view_right = np.cross(forward, view_up)
        view_right = view_right / (np.linalg.norm(view_right) + 1e-12)
        view_up = view_up / (np.linalg.norm(view_up) + 1e-12)
        return view_right, view_up

    def _maybe_snap_to_axis(self, point1, point2, threshold_deg=3):
        """Snap to horizontal or vertical only when line is very close to perpendicular axes.
        Otherwise allow lines at any angle (diagonal). Threshold 3° = snap only when within
        3° of 0° (horizontal) or 90° (vertical); 3°–87° draws freely.
        """
        import math
        try:
            view_right, view_up = self._get_camera_view_axes()
            p1, p2 = np.array(point1), np.array(point2)
            delta = p2 - p1
            dx_screen = np.dot(delta, view_right)
            dy_screen = np.dot(delta, view_up)
            # Avoid snapping when delta is too small
            if abs(dx_screen) < 1e-12 and abs(dy_screen) < 1e-12:
                return point2
            angle_deg = math.degrees(math.atan2(abs(dy_screen), abs(dx_screen)))
            # Snap only when very close to 0° (horizontal) or 90° (vertical)
            if angle_deg < threshold_deg:
                snapped = p1 + view_right * dx_screen
                return tuple(snapped)
            elif angle_deg > (90 - threshold_deg):
                snapped = p1 + view_up * dy_screen
                return tuple(snapped)
            return point2
        except Exception:
            return point2

    def _snap_to_axis(self, point1, point2):
        """Snap point2 so measurement is strictly horizontal or vertical on screen."""
        try:
            view_right, view_up = self._get_camera_view_axes()
            p1, p2 = np.array(point1), np.array(point2)
            delta = p2 - p1
            dx_screen = np.dot(delta, view_right)
            dy_screen = np.dot(delta, view_up)
            if abs(dx_screen) >= abs(dy_screen):
                snapped = p1 + view_right * dx_screen
            else:
                snapped = p1 + view_up * dy_screen
            return tuple(snapped)
        except Exception:
            return point2

    def _on_point_picked(self, point):
        """Handle point picked for measurement."""
        if not self.ruler_mode or point is None:
            return
        if len(self.measurement_points) == 1:
            point = self._maybe_snap_to_axis(self.measurement_points[0], point)
        self.measurement_points.append(point)
        if len(self.measurement_points) == 2:
            self._clear_preview_line()
            distance = self._calculate_distance(self.measurement_points[0], self.measurement_points[1])
            self._draw_measurement_line(
                self.measurement_points[0], self.measurement_points[1], distance
            )
            self.measurement_points = []
        if self._canvas:
            self._canvas.request_draw()

    def _get_measurement_marker_size(self):
        if self.current_mesh is None:
            return 1.0
        try:
            b = self.current_mesh.bounds
            max_dim = max(b[1] - b[0], b[3] - b[2], b[5] - b[4])
            return max(max_dim * 0.0025, 0.03)
        except Exception:
            return 1.0

    def _get_arrow_size(self):
        if self.current_mesh is None:
            return (0.2, 0.08)
        try:
            b = self.current_mesh.bounds
            max_dim = max(b[1] - b[0], b[3] - b[2], b[5] - b[4])
            tip_len = max(max_dim * 0.02, 0.1)
            tip_rad = tip_len * 0.4
            return (tip_len, tip_rad)
        except Exception:
            return (0.2, 0.08)

    def _get_line_tube_radius(self):
        if self.current_mesh is None:
            return 0.02
        try:
            b = self.current_mesh.bounds
            max_dim = max(b[1] - b[0], b[3] - b[2], b[5] - b[4])
            return max(max_dim * 0.0015, 0.02)
        except Exception:
            return 0.02

    def _calculate_distance(self, point1, point2):
        p1, p2 = np.array(point1), np.array(point2)
        return float(np.linalg.norm(p2 - p1))

    def _draw_measurement_line(self, point1, point2, distance):
        """Draw measurement line with arrowheads and distance label."""
        import pygfx as gfx
        try:
            p1, p2 = np.array(point1), np.array(point2)
            direction = p2 - p1
            length = np.linalg.norm(direction)
            if length < 1e-12:
                return
            dir_unit = direction / length
            arrow_tip_length, arrow_tip_radius = self._get_arrow_size()
            # Scale arrows to line length so they don't overlap (max 15% of line each)
            arrow_tip_length = min(arrow_tip_length, length * 0.15)
            arrow_tip_radius = min(arrow_tip_radius, arrow_tip_length * 0.4)
            if arrow_tip_length < 1e-6:
                arrow_tip_length = length * 0.05
                arrow_tip_radius = arrow_tip_length * 0.4
            # Main line (slightly shortened to leave room for arrowheads)
            line_thickness = 2.5
            line_start = p1 + dir_unit * arrow_tip_length
            line_end = p2 - dir_unit * arrow_tip_length
            if np.linalg.norm(line_end - line_start) < 1e-6:
                line_start, line_end = p1, p2
            positions = np.array([line_start, line_end], dtype=np.float32)
            geom = gfx.Geometry(positions=positions)
            mat = gfx.LineMaterial(color="#000000", thickness=line_thickness, depth_test=False, depth_write=False)
            mat.render_queue = 3000  # Lines render behind labels
            line_obj = gfx.Line(geom, mat)
            self._scene.add(line_obj)
            self.measurement_actors.append(line_obj)
            # Create flat triangle arrowheads in the view plane
            try:
                view_right, view_up = self._get_camera_view_axes()
            except Exception:
                view_right = np.array([1, 0, 0])
                view_up = np.array([0, 1, 0])
            half_w = arrow_tip_radius
            def _make_arrow_triangle(tip_pos, direction):
                """Create a flat triangle mesh for an arrowhead pointing in `direction`."""
                base_center = tip_pos - direction * arrow_tip_length
                # Perpendicular in the view plane
                dx = np.dot(direction, view_right)
                dy = np.dot(direction, view_up)
                perp = -dy * view_right + dx * view_up
                perp_norm = np.linalg.norm(perp)
                if perp_norm > 1e-12:
                    perp = perp / perp_norm
                else:
                    perp = view_right
                v0 = np.array(tip_pos, dtype=np.float32)
                v1 = np.array(base_center + perp * half_w, dtype=np.float32)
                v2 = np.array(base_center - perp * half_w, dtype=np.float32)
                verts = np.array([v0, v1, v2], dtype=np.float32)
                faces = np.array([[0, 1, 2]], dtype=np.uint32)
                g = gfx.Geometry(positions=verts, indices=faces)
                m = gfx.MeshBasicMaterial(color="#000000", side="both")
                m.depth_test = False
                m.depth_write = False
                m.render_queue = 3000  # Arrows render behind labels
                return gfx.Mesh(g, m)
            # Arrow at p1 pointing outward (away from p2)
            arrow1 = _make_arrow_triangle(p1, -dir_unit)
            self._scene.add(arrow1)
            self.measurement_actors.append(arrow1)
            # Arrow at p2 pointing outward (away from p1)
            arrow2 = _make_arrow_triangle(p2, dir_unit)
            self._scene.add(arrow2)
            self.measurement_actors.append(arrow2)
            # Label at midpoint, offset in view plane to avoid overlapping other labels
            midpoint = np.array([(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, (p1[2] + p2[2]) / 2])
            measurement_index = len(self.measurement_actors) // 5  # 5 actors per measurement: line, 2 arrows, bg, lbl
            try:
                view_right, view_up = self._get_camera_view_axes()
                dx_screen = np.dot(dir_unit, view_right)
                dy_screen = np.dot(dir_unit, view_up)
                perp_screen = -dy_screen * view_right + dx_screen * view_up
                perp_screen = perp_screen / (np.linalg.norm(perp_screen) + 1e-12)
                # Gentle radial spread: small angle steps, modest distance to avoid overlap without jumping far
                angle_deg = (measurement_index % 4) * 90.0  # 4 positions: perp, along, opposite perp, opposite along
                angle_rad = np.deg2rad(angle_deg)
                cos_a, sin_a = np.cos(angle_rad), np.sin(angle_rad)
                along_screen = dx_screen * view_right + dy_screen * view_up
                along_norm = np.linalg.norm(along_screen)
                if along_norm < 1e-8:
                    along_screen = view_right
                else:
                    along_screen = along_screen / along_norm
                offset_dir = perp_screen * cos_a + along_screen * sin_a
                offset_dir = offset_dir / (np.linalg.norm(offset_dir) + 1e-12)
                b = self.current_mesh.bounds if self.current_mesh else None
                max_dim = max(b[1] - b[0], b[3] - b[2], b[5] - b[4]) if b else length
                # Compact distance: 5–10% of model, cycle so labels don't jump far
                offset_dist = max_dim * (0.048 + 0.015 * (measurement_index % 5))
                label_pos = tuple(midpoint + offset_dir * offset_dist)
            except Exception:
                label_pos = tuple(midpoint)
            unit = getattr(self, '_ruler_unit', 'mm')
            conversion = {"mm": 1.0, "cm": 0.1, "m": 0.001, "inch": 1.0 / 25.4, "ft": 1.0 / 304.8}
            unit_labels = {"mm": "mm", "cm": "cm", "m": "m", "inch": "in", "ft": "ft"}
            converted = distance * conversion.get(unit, 1.0)
            suffix = unit_labels.get(unit, "mm")
            label_text = f"{converted:.4f} {suffix}" if converted < 1 else (f"{converted:.2f} {suffix}" if converted < 100 else f"{converted:.1f} {suffix}")
            # Background plane behind label (grey #666666, rounded look via size)
            try:
                view_right, view_up = self._get_camera_view_axes()
            except Exception:
                view_right = np.array([1, 0, 0])
                view_up = np.array([0, 1, 0])
            b = self.current_mesh.bounds if self.current_mesh else None
            max_dim = max(b[1] - b[0], b[3] - b[2], b[5] - b[4]) if b else length
            # Scale background - compact size, still covers text
            char_count = len(label_text)
            bg_w = max_dim * (0.014 * char_count + 0.04)  # Reduced: compact grey box
            bg_h = max_dim * 0.032  # Reduced height
            normal = np.cross(view_right, view_up)
            n = np.linalg.norm(normal)
            if n > 1e-12:
                normal = normal / n
            else:
                normal = np.array([0, 0, 1])
            m = np.eye(4, dtype=np.float32)
            m[:3, 0] = view_right * bg_w
            m[:3, 1] = view_up * bg_h
            m[:3, 2] = normal
            m[:3, 3] = np.array(label_pos, dtype=np.float32)
            bg_geom = gfx.plane_geometry(1, 1)
            bg_mat = gfx.MeshBasicMaterial(color="#666666", side="both")
            bg_mat.depth_test = False
            bg_mat.depth_write = False
            bg_mat.render_queue = 4000  # Labels render on top of lines
            bg_plane = gfx.Mesh(bg_geom, bg_mat)
            bg_plane.local.matrix = m
            self._scene.add(bg_plane)
            self.measurement_actors.append(bg_plane)
            try:
                lbl_mat = gfx.TextMaterial(color="#000000", weight_offset=300)
            except TypeError:
                lbl_mat = gfx.TextMaterial(color="#000000")
            lbl_mat.depth_test = False
            lbl_mat.depth_write = False
            lbl_mat.render_queue = 4100  # Text renders on top of background and lines
            lbl = gfx.Text(text=label_text, material=lbl_mat, font_size=12, anchor="middle-center", screen_space=True)
            lbl.local.position = label_pos
            self._scene.add(lbl)
            self.measurement_actors.append(lbl)
        except Exception as e:
            logger.error(f"_draw_measurement_line: {e}", exc_info=True)
        if self._canvas:
            self._canvas.request_draw()

    def _clear_preview_line(self):
        """Remove the preview line from the scene."""
        if self._preview_line_obj is not None:
            try:
                self._scene.remove(self._preview_line_obj)
            except Exception:
                pass
            self._preview_line_obj = None
        if self._canvas:
            self._canvas.request_draw()

    def _update_preview_line(self, point1, point2):
        """Draw or update the preview line from point1 to point2."""
        if point1 is None or point2 is None:
            self._clear_preview_line()
            return
        self._clear_preview_line()
        import pygfx as gfx
        try:
            p1, p2 = np.array(point1), np.array(point2)
            length = np.linalg.norm(p2 - p1)
            if length < 1e-12:
                return
            line_thickness = 2.5  # pixels, screen-space
            positions = np.array([p1, p2], dtype=np.float32)
            geom = gfx.Geometry(positions=positions)
            mat = gfx.LineMaterial(color="#000000", thickness=line_thickness, depth_test=False, depth_write=False)
            mat.render_queue = 3000  # Preview line renders behind labels
            line_obj = gfx.Line(geom, mat)
            self._scene.add(line_obj)
            self._preview_line_obj = line_obj
        except Exception as e:
            logger.debug(f"_update_preview_line: {e}")
        if self._canvas:
            self._canvas.request_draw()

    def clear_measurements(self):
        """Clear all measurement visualizations."""
        self._clear_preview_line()
        for obj in self.measurement_actors:
            try:
                self._scene.remove(obj)
            except Exception:
                pass
        self.measurement_actors = []
        self.measurement_points = []
        if self._canvas:
            self._canvas.request_draw()

    def enable_ruler_mode(self):
        """Enable point-to-point measurement mode with orthographic projection."""
        if not self._initialized or self._camera is None:
            logger.warning("enable_ruler_mode: Not initialized")
            return False
        if self.current_mesh is None or self._mesh_obj is None:
            logger.warning("enable_ruler_mode: No mesh loaded")
            return False
        logger.info("enable_ruler_mode: Enabling ruler mode...")
        self.ruler_mode = True
        self.measurement_points = []
        self._clear_preview_line()
        # Install event filter on canvas, self, viewer_container, and app to catch all events
        if self._canvas and not self._ruler_event_filter_installed:
            self._canvas.installEventFilter(self)
            self.installEventFilter(self)
            self.viewer_container.installEventFilter(self)
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
            self._ruler_event_filter_installed = True
        # Switch to orthographic camera, always starting with Front view
        self._ruler_current_view = "front"
        self._switch_to_orthographic_camera()
        # Ensure canvas has focus so wheel events reach it for zoom
        if self._canvas:
            self._canvas.setFocus(Qt.OtherFocusReason)
        # Restrict to zoom-only (event filter blocks rotate/pan)
        logger.info("enable_ruler_mode: Ruler mode enabled")
        return True

    def disable_ruler_mode(self):
        """Disable measurement mode and restore perspective projection."""
        logger.info("disable_ruler_mode: Disabling ruler mode...")
        self.ruler_mode = False
        self.measurement_points = []
        if self._canvas and self._ruler_event_filter_installed:
            self._canvas.removeEventFilter(self)
            self.removeEventFilter(self)
            self.viewer_container.removeEventFilter(self)
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
            self._ruler_event_filter_installed = False
        self._clear_preview_line()
        self.clear_measurements()
        self._restore_perspective_camera()
        logger.info("disable_ruler_mode: Ruler mode disabled")

    def _switch_to_orthographic_camera(self):
        """Switch to OrthographicCamera for ruler mode."""
        import pygfx as gfx
        if self._mesh_obj is None or self._camera is None:
            return
        try:
            cw, ch = self._canvas.get_logical_size() if hasattr(self._canvas, 'get_logical_size') else (self.width(), self.height())
        except Exception:
            cw, ch = max(1, self.width()), max(1, self.height())
        try:
            self._camera_before_ruler = self._camera
            # OrthographicCamera width/height are in world units; size view to fit mesh
            max_dim = max(
                self.current_mesh.bounds[1] - self.current_mesh.bounds[0],
                self.current_mesh.bounds[3] - self.current_mesh.bounds[2],
                self.current_mesh.bounds[5] - self.current_mesh.bounds[4],
                1.0,
            ) * 1.2
            aspect = cw / ch if ch > 0 else 1
            ortho = gfx.OrthographicCamera(max_dim * aspect, max_dim)
            ortho.maintain_aspect = True
            # Always start ruler mode with Front view (view_dir +X, Y up)
            ortho.show_object(self._mesh_obj, view_dir=(1, 0, 0), scale=1.8, up=(0, 1, 0))
            self._camera = ortho
            self._controller.camera = ortho
            if self._canvas:
                self._canvas.request_draw()
            logger.info("_switch_to_orthographic_camera: Switched to orthographic, front view")
        except Exception as e:
            logger.warning(f"_switch_to_orthographic_camera: {e}")

    def _restore_perspective_camera(self):
        """Restore PerspectiveCamera after ruler mode."""
        if self._camera_before_ruler is not None:
            self._camera = self._camera_before_ruler
            self._controller.camera = self._camera_before_ruler
            self._camera_before_ruler = None
        if self._canvas:
            self._canvas.request_draw()

    def _show_overlay(self, show):
        if show:
            self.drop_overlay.show()
            self.drop_overlay.raise_()
        else:
            self.drop_overlay.hide()

    # ========== Annotation Mode Methods ==========

    def enable_annotation_mode(self, callback=None):
        """Enable annotation mode for adding 3D point annotations on mesh surface.

        Args:
            callback: Function to call when a point is picked. Receives (point_tuple,).
        """
        if not self._initialized or self._scene is None:
            logger.warning("enable_annotation_mode (pygfx): Not initialized")
            return False
        if self.current_mesh is None or self._mesh_obj is None:
            logger.warning("enable_annotation_mode (pygfx): No mesh loaded")
            return False

        logger.info("enable_annotation_mode (pygfx): Enabling...")
        self.annotation_mode = True
        self._annotation_callback = callback

        # Disable ruler mode if active
        if self.ruler_mode:
            self.disable_ruler_mode()

        # Install Qt event filter for click picking
        if not self._annotation_event_filter_installed and self._canvas is not None:
            self._canvas.installEventFilter(self)
            self.installEventFilter(self)
            self.viewer_container.installEventFilter(self)
            self._annotation_event_filter_installed = True

        # Show 3D control overlay
        if self._object_control_overlay is not None:
            self._object_control_overlay.show()
            self._object_control_overlay.raise_()

        logger.info("enable_annotation_mode (pygfx): Annotation mode enabled")
        return True

    def _on_gizmo_rotate(self, dx: float, dy: float):
        """Handle drag on orientation gizmo - rotate the camera (matches main canvas drag direction)."""
        if self._controller is None or self._canvas is None:
            return
        try:
            # Convert pixel delta to radians (match TrackballController sensitivity)
            # Use (dx, dy) so gizmo drag direction matches main canvas rotation
            scale = 0.005
            delta = (dx * scale, dy * scale)
            try:
                w, h = self._canvas.get_logical_size() if hasattr(self._canvas, 'get_logical_size') else (self._canvas.width(), self._canvas.height())
            except Exception:
                w, h = self._canvas.width(), self._canvas.height()
            rect = (0, 0, max(1, w), max(1, h))
            self._controller.rotate(delta, rect)
            self._canvas.request_draw()
        except Exception as e:
            logger.warning(f"_on_gizmo_rotate: {e}")

    def disable_annotation_mode(self):
        """Disable annotation mode."""
        logger.info("disable_annotation_mode (pygfx): Disabling...")
        self.annotation_mode = False
        self._annotation_callback = None

        # Remove event filter
        if self._annotation_event_filter_installed and self._canvas is not None:
            self._canvas.removeEventFilter(self)
            self.removeEventFilter(self)
            self.viewer_container.removeEventFilter(self)
            self._annotation_event_filter_installed = False

        # Hide 3D control overlay
        if self._object_control_overlay is not None:
            self._object_control_overlay.hide()

        logger.info("disable_annotation_mode (pygfx): Annotation mode disabled")

    def _annotation_event_filter_impl(self, obj, event):
        """Handle annotation mode events. Only intercept left clicks that hit the mesh.
        Clicks on empty space pass through so user can rotate by dragging.
        """
        if not self.annotation_mode or self._canvas is None:
            return False
        t = event.type()
        if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            pos = event.pos()
            picked = self._on_annotation_click(pos.x(), pos.y())
            # Only consume when we picked a point (mesh hit); otherwise let TrackballController rotate
            return picked
        return False  # Let other events (wheel zoom, right-click, drag in empty space) pass through

    def _on_annotation_click(self, x, y):
        """Handle left click in annotation mode: raycast against mesh to pick surface point.
        Returns True if a point was picked (annotation added), False otherwise (e.g. clicked empty space).
        """
        if not self.annotation_mode or self._annotation_trimesh is None:
            return False

        # Build ray from screen coords
        ray_origin, ray_direction = self._screen_to_ray(x, y)
        if ray_origin is None:
            return False

        try:
            import trimesh
            # Raycast against mesh
            locations, index_ray, index_tri = self._annotation_trimesh.ray.intersects_location(
                ray_origins=[ray_origin],
                ray_directions=[ray_direction],
            )
            if len(locations) == 0:
                logger.debug(f"_on_annotation_click: No hit at ({x}, {y}) - pass through for rotate")
                return False

            # Pick closest intersection to camera
            cam_pos = np.array(self._camera.local.position)
            dists = np.linalg.norm(locations - cam_pos, axis=1)
            closest_idx = np.argmin(dists)
            point_tuple = tuple(float(c) for c in locations[closest_idx])

            logger.info(f"_on_annotation_click: Hit at {point_tuple}")

            if self._annotation_callback is not None:
                self._annotation_callback(point_tuple)
            return True

        except Exception as e:
            logger.error(f"_on_annotation_click: Raycasting failed: {e}", exc_info=True)
            return False

    def _is_dot_visible(self, point) -> bool:
        """Return True if the annotation point is not occluded by the mesh (ray from camera to dot)."""
        if self._annotation_trimesh is None or self._camera is None:
            return True
        try:
            cam_pos = np.array(self._camera.local.position)
            pt = np.array(point, dtype=np.float64)
            direction = pt - cam_pos
            dist_to_dot = np.linalg.norm(direction)
            if dist_to_dot < 1e-9:
                return True
            direction = direction / dist_to_dot
            locations, _, _ = self._annotation_trimesh.ray.intersects_location(
                ray_origins=[cam_pos],
                ray_directions=[direction],
            )
            if len(locations) == 0:
                return True
            dists = np.linalg.norm(np.asarray(locations) - cam_pos, axis=1)
            closest = float(np.min(dists))
            if closest < dist_to_dot - 1e-6:
                return False
            return True
        except Exception:
            return True

    def _update_annotation_label_visibility(self):
        """Update each annotation label's visibility: hide when dot is occluded by mesh."""
        if not self.annotations or self._annotation_trimesh is None:
            return
        for ann in self.annotations:
            try:
                visible = self._is_dot_visible(ann['point'])
                ann['label'].visible = visible
            except Exception:
                pass

    def _screen_to_ray(self, x, y):
        """Convert screen (x, y) to a world-space ray (origin, direction). Returns (origin, direction) or (None, None)."""
        if self._camera is None or self._canvas is None:
            return None, None
        try:
            cw, ch = self._canvas.get_logical_size() if hasattr(self._canvas, 'get_logical_size') else (self.width(), self.height())
        except Exception:
            return None, None
        if cw <= 0 or ch <= 0:
            return None, None
        try:
            ndc_x = 2.0 * float(x) / cw - 1.0
            ndc_y = 1.0 - 2.0 * float(y) / ch

            vm = np.array(self._camera.view_matrix)
            ipm = np.array(self._camera.projection_matrix_inverse)
            ivm = np.linalg.inv(vm)

            ndc_near = np.array([ndc_x, ndc_y, 0, 1])
            ndc_far = np.array([ndc_x, ndc_y, 1, 1])
            world_near = ivm @ ipm @ ndc_near
            world_far = ivm @ ipm @ ndc_far
            world_near = world_near[:3] / (world_near[3] + 1e-12)
            world_far = world_far[:3] / (world_far[3] + 1e-12)

            direction = world_far - world_near
            d_norm = np.linalg.norm(direction)
            if d_norm < 1e-12:
                return None, None
            direction = direction / d_norm
            return world_near, direction
        except Exception as e:
            logger.debug(f"_screen_to_ray: {e}")
            return None, None

    def add_annotation_marker(self, annotation_id: int, point: tuple, color: str = '#909d92',
                              display_date: str = None) -> object:
        """Add a visible marker sphere + numbered label for an annotation point.

        Args:
            annotation_id: Unique ID for the annotation
            point: (x, y, z) world coordinates
            color: Marker color hex string
            display_date: Label text (e.g. '1', '2')

        Returns:
            The pygfx marker object, or None
        """
        if not self._initialized or self._scene is None or self.current_mesh is None:
            return None

        display_date = display_date or str(annotation_id)

        try:
            import pygfx as gfx

            # Sphere radius: 1.2% of max model dimension
            bounds = self.current_mesh.bounds
            max_dim = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4], 0.01)
            sphere_radius = max_dim * 0.012

            # Create sphere marker - depth_test=True so it is occluded by object when behind
            geom = gfx.sphere_geometry(sphere_radius, 24, 16)
            r, g, b = self._hex_to_rgb_normalized(color)
            mat = gfx.MeshPhongMaterial(
                color=(r, g, b),
                specular=(0.6, 0.6, 0.6),
                shininess=50,
                depth_test=True,
                depth_write=True,
            )
            marker = gfx.Mesh(geom, mat)
            marker.local.position = point
            self._scene.add(marker)

            # Create numbered label above sphere
            label_offset = sphere_radius * 1.8
            label_pos = (point[0], point[1] + label_offset, point[2])
            text_color = self._get_label_color_for_badge(color)
            tr, tg, tb = self._hex_to_rgb_normalized(text_color)

            lbl_mat = gfx.TextMaterial(color=(tr, tg, tb))
            lbl_mat.depth_test = False
            lbl_mat.depth_write = False
            lbl_mat.render_queue = 4000  # Always on top - numbers never covered by geometry
            label = gfx.Text(
                text=display_date,
                material=lbl_mat,
                font_size=16,
                anchor="middle-center",
                screen_space=True,
            )
            label.local.position = label_pos
            self._scene.add(label)

            ann_data = {
                'id': annotation_id,
                'point': point,
                'marker': marker,
                'label': label,
                'base_color': color,
                'display_date': display_date,
                'selected': False,
            }
            self.annotations.append(ann_data)
            self.annotation_actors.extend([marker, label])

            if self._canvas:
                self._canvas.request_draw()

            logger.info(f"add_annotation_marker (pygfx): Added id={annotation_id} at {point}")
            return marker

        except Exception as e:
            logger.error(f"add_annotation_marker (pygfx): Failed: {e}", exc_info=True)
            return None

    def update_annotation_marker_color(self, annotation_id: int, color: str):
        """Update color of an annotation marker and its label."""
        for ann in self.annotations:
            if ann['id'] == annotation_id:
                ann['base_color'] = color
                if not ann.get('selected', False):
                    try:
                        r, g, b = self._hex_to_rgb_normalized(color)
                        ann['marker'].material.color = (r, g, b)
                    except Exception as e:
                        logger.debug(f"update_annotation_marker_color: {e}")
                # Update label text color for contrast
                self._update_label_color(ann, color)
                if self._canvas:
                    self._canvas.request_draw()
                break

    def set_annotation_selected(self, annotation_id: int, selected: bool):
        """Set annotation marker to yellow when selected, restore base color when deselected."""
        if selected:
            for ann in self.annotations:
                if ann.get('selected', False):
                    ann['selected'] = False
                    try:
                        r, g, b = self._hex_to_rgb_normalized(ann.get('base_color', '#909d92'))
                        ann['marker'].material.color = (r, g, b)
                        self._update_label_color(ann, ann.get('base_color', '#909d92'))
                    except Exception:
                        pass
        for ann in self.annotations:
            if ann['id'] == annotation_id:
                ann['selected'] = selected
                color = '#FACC15' if selected else ann.get('base_color', '#909d92')
                try:
                    r, g, b = self._hex_to_rgb_normalized(color)
                    ann['marker'].material.color = (r, g, b)
                    self._update_label_color(ann, color)
                except Exception as e:
                    logger.debug(f"set_annotation_selected: {e}")
                if self._canvas:
                    self._canvas.request_draw()
                break

    def remove_annotation_marker(self, annotation_id: int):
        """Remove an annotation marker by ID."""
        for i, ann in enumerate(self.annotations):
            if ann['id'] == annotation_id:
                try:
                    self._scene.remove(ann['marker'])
                    if ann['marker'] in self.annotation_actors:
                        self.annotation_actors.remove(ann['marker'])
                except Exception:
                    pass
                try:
                    self._scene.remove(ann['label'])
                    if ann['label'] in self.annotation_actors:
                        self.annotation_actors.remove(ann['label'])
                except Exception:
                    pass
                self.annotations.pop(i)
                if self._canvas:
                    self._canvas.request_draw()
                logger.info(f"remove_annotation_marker (pygfx): Removed id={annotation_id}")
                break

    def update_annotation_labels_from_list(self, annotations_with_display):
        """Update labels whose display number changed (renumber after delete).

        Args:
            annotations_with_display: List of (annotation_id, display_number, color) tuples.
        """
        import pygfx as gfx
        lookup = {aid: (dnum, color) for aid, dnum, color in annotations_with_display}
        updated = 0
        for ann in self.annotations:
            aid = ann['id']
            if aid not in lookup:
                continue
            display_number, color = lookup[aid]
            new_display = str(display_number)
            if ann.get('display_date') != new_display or ann.get('base_color') != color:
                ann['display_date'] = new_display
                ann['base_color'] = color
                # Update label text
                try:
                    ann['label'].set_text(new_display)
                except Exception:
                    try:
                        # Recreate label if set_text not available
                        self._scene.remove(ann['label'])
                        if ann['label'] in self.annotation_actors:
                            self.annotation_actors.remove(ann['label'])
                        bounds = self.current_mesh.bounds
                        max_dim = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4], 0.01)
                        sphere_radius = max_dim * 0.012
                        label_offset = sphere_radius * 1.8
                        point = ann['point']
                        label_pos = (point[0], point[1] + label_offset, point[2])
                        text_color = self._get_label_color_for_badge(color)
                        tr, tg, tb = self._hex_to_rgb_normalized(text_color)
                        lbl_mat = gfx.TextMaterial(color=(tr, tg, tb))
                        lbl_mat.depth_test = False
                        lbl_mat.depth_write = False
                        lbl_mat.render_queue = 4000  # Always on top - numbers never covered by geometry
                        new_label = gfx.Text(text=new_display, material=lbl_mat, font_size=16,
                                             anchor="middle-center", screen_space=True)
                        new_label.local.position = label_pos
                        self._scene.add(new_label)
                        ann['label'] = new_label
                        self.annotation_actors.append(new_label)
                    except Exception as e2:
                        logger.debug(f"update_annotation_labels_from_list: recreate failed: {e2}")
                # Update marker color
                if not ann.get('selected', False):
                    try:
                        r, g, b = self._hex_to_rgb_normalized(color)
                        ann['marker'].material.color = (r, g, b)
                    except Exception:
                        pass
                self._update_label_color(ann, color)
                updated += 1
        if updated > 0 and self._canvas:
            self._canvas.request_draw()
        logger.debug(f"update_annotation_labels_from_list (pygfx): Updated {updated}")

    def clear_all_annotation_markers(self):
        """Remove all annotation markers and labels."""
        for ann in self.annotations:
            try:
                self._scene.remove(ann['marker'])
            except Exception:
                pass
            try:
                self._scene.remove(ann['label'])
            except Exception:
                pass
        self.annotations = []
        self.annotation_actors = []
        if self._canvas:
            self._canvas.request_draw()
        logger.info("clear_all_annotation_markers (pygfx): Cleared")

    def focus_on_annotation(self, annotation_id: int):
        """Focus the camera on a specific annotation point."""
        for ann in self.annotations:
            if ann['id'] == annotation_id:
                point = ann['point']
                try:
                    if self._mesh_obj is not None:
                        self._safe_set_aspect()
                        # Point camera at annotation while keeping current view direction
                        cam_pos = np.array(self._camera.local.position)
                        center = np.array(self._get_view_center_and_distance()[0])
                        view_dir = center - cam_pos
                        view_dir_norm = np.linalg.norm(view_dir)
                        if view_dir_norm > 1e-12:
                            view_dir = view_dir / view_dir_norm
                        # Move camera to look at annotation point from same distance
                        bounds = self.current_mesh.bounds
                        max_dim = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4], 1.0)
                        dist = max_dim * 1.0
                        new_pos = np.array(point) - view_dir * dist
                        self._camera.local.position = tuple(new_pos)
                        self._camera.show_pos(point)
                    if self._canvas:
                        self._canvas.request_draw()
                    logger.info(f"focus_on_annotation (pygfx): Focused on id={annotation_id}")
                except Exception as e:
                    logger.warning(f"focus_on_annotation (pygfx): Failed: {e}")
                break

    def _get_label_color_for_badge(self, badge_color: str) -> str:
        """Return label text color for contrast. Validated (blue) uses green; other dark badges use white."""
        if badge_color and badge_color.lower().lstrip('#') == '1821b4':
            return '#22C55E'  # Green for validated
        return '#FFFFFF' if self._is_dark_hex_color(badge_color) else '#000000'

    def _update_label_color(self, ann: dict, badge_color: str):
        """Update label text color for contrast against badge color."""
        try:
            text_color = self._get_label_color_for_badge(badge_color)
            r, g, b = self._hex_to_rgb_normalized(text_color)
            ann['label'].material.color = (r, g, b)
        except Exception:
            pass

    def _hex_to_rgb_normalized(self, hex_color: str) -> tuple:
        """Convert hex color to normalized RGB tuple (0-1)."""
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
        return 0.299 * r + 0.587 * g + 0.114 * b < 0.5

    # ========== Screenshot Mode ==========

    def enable_screenshot_mode(self):
        """Enable screenshot mode: show overlay for rubber-band selection."""
        if not self._model_loaded:
            return False
        from ui.screenshot_overlay import ScreenshotOverlay
        if self._screenshot_overlay is None:
            self._screenshot_overlay = ScreenshotOverlay(self.viewer_container, zoom_callback=self._screenshot_zoom)
            self._screenshot_overlay.region_selected.connect(self._on_screenshot_region_selected)
        self._screenshot_overlay.setGeometry(self.viewer_container.rect())
        self._screenshot_overlay.raise_()
        self._screenshot_overlay.show()
        self.screenshot_mode = True
        # Show zoom controls (bottom-left) and rotation gizmo (bottom-right)
        self._zoom_controls_overlay.show()
        self._zoom_controls_overlay.raise_()
        self._object_control_overlay.show()
        self._object_control_overlay.raise_()
        return True

    def disable_screenshot_mode(self):
        """Disable screenshot mode: hide overlay and reset cursor."""
        self.screenshot_mode = False
        if self._screenshot_overlay is not None:
            self._screenshot_overlay.hide()
            # Reset cursor - CrossCursor from overlay can persist after hide on some platforms
            self.viewer_container.setCursor(Qt.ArrowCursor)
        self._zoom_controls_overlay.hide()
        # Only hide gizmo if annotation mode is not active
        if not self.annotation_mode:
            self._object_control_overlay.hide()

    def _screenshot_zoom(self, factor):
        """Zoom the camera by the given factor (>1 = zoom in, <1 = zoom out)."""
        if self._controller is None or self._canvas is None:
            return
        try:
            import pygfx as gfx
            try:
                w, h = self._canvas.get_logical_size() if hasattr(self._canvas, 'get_logical_size') else (self._canvas.width(), self._canvas.height())
            except Exception:
                w, h = self._canvas.width(), self._canvas.height()
            rect = (0, 0, max(1, w), max(1, h))
            # Use zoom method: positive delta = zoom in
            delta = factor - 1.0
            self._controller.zoom((delta, delta), rect)
            self._canvas.request_draw()
        except Exception as e:
            logger.warning(f"_screenshot_zoom: {e}")

    def _on_screenshot_region_selected(self, rect):
        """Capture the selected region at high resolution from the canvas."""
        from PyQt5.QtCore import QRect
        from PyQt5.QtGui import QImage, QPixmap
        import numpy as np

        captured = False
        # Try pygfx: create an offscreen renderer at high resolution, render, then crop
        if self._renderer and self._scene and self._camera:
            try:
                import pygfx as gfx

                cw, ch = self._canvas.get_logical_size() if hasattr(self._canvas, 'get_logical_size') else (self.viewer_container.width(), self.viewer_container.height())
                target_w = int(cw * SCREENSHOT_CAPTURE_SCALE)
                target_h = int(ch * SCREENSHOT_CAPTURE_SCALE)
                me = max(target_w, target_h)
                if me > _SCREENSHOT_MAX_EDGE_PX:
                    r = _SCREENSHOT_MAX_EDGE_PX / me
                    target_w = max(1, int(target_w * r))
                    target_h = max(1, int(target_h * r))
                px = target_w * target_h
                if px > _SCREENSHOT_MAX_PIXELS:
                    r = (_SCREENSHOT_MAX_PIXELS / px) ** 0.5
                    target_w = max(1, int(target_w * r))
                    target_h = max(1, int(target_h * r))

                logger.info(f"Screenshot render: {target_w}x{target_h} (scale from {cw}x{ch})")

                # Create offscreen texture target and renderer at the desired resolution
                texture = gfx.Texture(dim=2, size=(target_w, target_h, 1), format="rgba8unorm")
                offscreen_renderer = gfx.renderers.wgpu.WgpuRenderer(texture)
                offscreen_renderer.render(self._scene, self._camera)
                img_array = offscreen_renderer.snapshot()

                if img_array is not None:
                    img_array = np.ascontiguousarray(img_array)
                    h_img, w_img = img_array.shape[:2]
                    channels = img_array.shape[2] if img_array.ndim == 3 else 1

                    if channels == 4:
                        fmt = QImage.Format_RGBA8888
                    else:
                        fmt = QImage.Format_RGB888

                    qimg = QImage(img_array.data, w_img, h_img, img_array.strides[0], fmt)
                    full_pixmap = QPixmap.fromImage(qimg.copy())

                    # Map rubber-band rect from widget coords to snapshot pixels
                    sx = w_img / cw
                    sy = h_img / ch
                    hr_rect = QRect(
                        int(rect.x() * sx), int(rect.y() * sy),
                        int(rect.width() * sx), int(rect.height() * sy)
                    )
                    cropped = full_pixmap.copy(hr_rect)
                    logger.info(f"Screenshot crop: {cropped.width()}x{cropped.height()} px")
                    captured = True
            except Exception as e:
                logger.warning(f"High-res screenshot failed, falling back to grab(): {e}")
            except Exception as e:
                logger.warning(f"High-res screenshot failed, falling back to grab(): {e}")

        # Fallback: widget grab (screen resolution)
        if not captured:
            full_pixmap = self.viewer_container.grab()
            dpr = full_pixmap.devicePixelRatio() if hasattr(full_pixmap, 'devicePixelRatio') else 1.0
            if dpr > 1.0:
                device_rect = QRect(
                    int(rect.x() * dpr), int(rect.y() * dpr),
                    int(rect.width() * dpr), int(rect.height() * dpr)
                )
                cropped = full_pixmap.copy(device_rect)
                cropped.setDevicePixelRatio(dpr)
            else:
                cropped = full_pixmap.copy(rect)

        if self._screenshot_captured_callback:
            self._screenshot_captured_callback(cropped)

    @property
    def _screenshot_captured_callback(self):
        return getattr(self, '_screenshot_cb', None)

    @_screenshot_captured_callback.setter
    def _screenshot_captured_callback(self, cb):
        self._screenshot_cb = cb

    # ========== Draw Mode (freehand drawing on mesh surface) ==========

    def enable_draw_mode(self):
        """Enable freehand draw mode. Clicks on mesh surface start strokes."""
        if not self._initialized or self._scene is None:
            logger.warning("enable_draw_mode: Not initialized")
            return False
        if self.current_mesh is None or self._mesh_obj is None:
            logger.warning("enable_draw_mode: No mesh loaded")
            return False
        if self._annotation_trimesh is None:
            # Build trimesh for raycasting (same as annotation mode)
            try:
                import trimesh
                if hasattr(self, '_pv_mesh') and self._pv_mesh is not None:
                    self._annotation_trimesh = _pyvista_to_trimesh(self._pv_mesh)
                elif self.current_mesh is not None:
                    self._annotation_trimesh = _pyvista_to_trimesh(self.current_mesh)
            except Exception as e:
                logger.warning(f"enable_draw_mode: Could not build trimesh: {e}")
                return False

        self.draw_mode = True
        self._drawing_active = False

        # Disable other modes
        if self.ruler_mode:
            self.disable_ruler_mode()
        if self.annotation_mode:
            self.disable_annotation_mode()

        # Install event filter
        if not self._draw_event_filter_installed and self._canvas is not None:
            self._canvas.installEventFilter(self)
            self.installEventFilter(self)
            self.viewer_container.installEventFilter(self)
            self._draw_event_filter_installed = True

        # Show gizmo overlay for camera control
        if self._object_control_overlay is not None:
            self._object_control_overlay.show()
            self._object_control_overlay.raise_()

        logger.info("enable_draw_mode: Draw mode enabled")
        return True

    def disable_draw_mode(self):
        """Disable draw mode."""
        self.draw_mode = False
        self._drawing_active = False
        self._eraser_mode = False
        self._current_stroke_points = []
        self._remove_current_stroke_line()

        if self._draw_event_filter_installed and self._canvas is not None:
            self._canvas.removeEventFilter(self)
            self.removeEventFilter(self)
            self.viewer_container.removeEventFilter(self)
            self._draw_event_filter_installed = False

        if self._object_control_overlay is not None:
            self._object_control_overlay.hide()

        logger.info("disable_draw_mode: Draw mode disabled")

    def set_draw_color(self, color: str):
        """Set the pen color for drawing."""
        self._draw_color = color

    def clear_drawings(self):
        """Remove all drawn strokes from the scene."""
        for stroke in self._draw_strokes:
            try:
                self._scene.remove(stroke)
            except Exception:
                pass
        self._draw_strokes.clear()
        self._draw_strokes_data.clear()
        if self._canvas:
            self._canvas.request_draw()

    def get_draw_strokes(self):
        """Return serializable list of strokes for .ecto export. Each stroke: {'points': [[x,y,z],...], 'color': '#RRGGBB'}."""
        # Use stored stroke data (populated at draw time) for reliable export
        return [{'points': [p.tolist() if hasattr(p, 'tolist') else list(p) for p in s['points']], 'color': s['color']}
                for s in self._draw_strokes_data]

    def restore_draw_strokes(self, strokes):
        """Restore strokes from .ecto import. Each stroke: {'points': [[x,y,z],...], 'color': '#RRGGBB'}."""
        import pygfx as gfx
        for stroke in self._draw_strokes:
            try:
                self._scene.remove(stroke)
            except Exception:
                pass
        self._draw_strokes.clear()
        self._draw_strokes_data.clear()
        for stroke_data in strokes or []:
            try:
                points = stroke_data.get('points', [])
                color = stroke_data.get('color', self._draw_color)
                if len(points) < 2:
                    continue
                positions = np.array(points, dtype=np.float32)
                segments = []
                for i in range(len(positions) - 1):
                    segments.append(positions[i])
                    segments.append(positions[i + 1])
                seg_positions = np.array(segments, dtype=np.float32)
                geom = gfx.Geometry(positions=seg_positions)
                mat = gfx.LineSegmentMaterial(
                    color=color, thickness=3.0,
                    depth_test=True, depth_write=True
                )
                line_obj = gfx.Line(geom, mat)
                self._scene.add(line_obj)
                self._draw_strokes.append(line_obj)
                self._draw_strokes_data.append({'points': points, 'color': color})
            except Exception as e:
                logger.warning(f"restore_draw_strokes: Skip stroke: {e}")
        if self._canvas:
            self._canvas.request_draw()

    def undo_last_stroke(self):
        """Remove the most recently drawn stroke."""
        if self._draw_strokes:
            stroke = self._draw_strokes.pop()
            if self._draw_strokes_data:
                self._draw_strokes_data.pop()
            try:
                self._scene.remove(stroke)
            except Exception:
                pass
            if self._canvas:
                self._canvas.request_draw()

    def set_eraser_mode(self, enabled: bool):
        """Toggle eraser mode. When on, clicks remove strokes instead of drawing."""
        self._eraser_mode = enabled
        logger.info(f"set_eraser_mode: {enabled}")

    def erase_stroke_at(self, x, y):
        """Erase the stroke closest to the click point on the mesh surface."""
        if self._annotation_trimesh is None or not self._draw_strokes:
            return False
        ray_origin, ray_direction = self._screen_to_ray(x, y)
        if ray_origin is None:
            return False
        try:
            locations, _, _ = self._annotation_trimesh.ray.intersects_location(
                ray_origins=[ray_origin], ray_directions=[ray_direction]
            )
            if len(locations) == 0:
                return False
            cam_pos = np.array(self._camera.local.position)
            dists = np.linalg.norm(locations - cam_pos, axis=1)
            hit_point = locations[np.argmin(dists)]

            # Find the closest stroke to hit_point
            threshold = self._get_draw_normal_offset() * 50  # generous click radius
            best_idx = -1
            best_dist = float('inf')
            for i, stroke_data in enumerate(self._draw_strokes_data):
                pts = np.array(stroke_data['points'], dtype=np.float32)
                if len(pts) == 0:
                    continue
                d = np.min(np.linalg.norm(pts - hit_point, axis=1))
                if d < best_dist:
                    best_dist = d
                    best_idx = i
            if best_idx >= 0 and best_dist < threshold:
                stroke_obj = self._draw_strokes.pop(best_idx)
                self._draw_strokes_data.pop(best_idx)
                try:
                    self._scene.remove(stroke_obj)
                except Exception:
                    pass
                if self._canvas:
                    self._canvas.request_draw()
                logger.info(f"erase_stroke_at: Removed stroke {best_idx} (dist={best_dist:.4f})")
                return True
            return False
        except Exception as e:
            logger.debug(f"erase_stroke_at: {e}")
            return False

    def _draw_event_filter_impl(self, obj, event):
        """Handle draw mode mouse events."""
        if not self.draw_mode or self._canvas is None:
            return False
        t = event.type()
        if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            pos = event.pos()
            if self._eraser_mode:
                return self.erase_stroke_at(pos.x(), pos.y())
            hit = self._draw_start_stroke(pos.x(), pos.y())
            return hit
        elif t == QEvent.MouseMove and self._drawing_active:
            pos = event.pos()
            self._draw_continue_stroke(pos.x(), pos.y())
            return True
        elif t == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and self._drawing_active:
            self._draw_finish_stroke()
            return True
        return False

    def _draw_start_stroke(self, x, y):
        """Start a new stroke if the click hits the mesh surface."""
        if self._annotation_trimesh is None:
            return False
        ray_origin, ray_direction = self._screen_to_ray(x, y)
        if ray_origin is None:
            return False
        try:
            locations, _, index_tri = self._annotation_trimesh.ray.intersects_location(
                ray_origins=[ray_origin], ray_directions=[ray_direction]
            )
            if len(locations) == 0:
                return False
            cam_pos = np.array(self._camera.local.position)
            dists = np.linalg.norm(locations - cam_pos, axis=1)
            closest_idx = np.argmin(dists)
            hit_point = locations[closest_idx]
            # Offset along face normal to prevent z-fighting
            normal = self._annotation_trimesh.face_normals[index_tri[closest_idx]]
            offset = self._get_draw_normal_offset()
            hit_point = hit_point + normal * offset
            self._current_stroke_points = [hit_point.astype(np.float32)]
            self._drawing_active = True
            return True
        except Exception as e:
            logger.debug(f"_draw_start_stroke: {e}")
            return False

    def _draw_continue_stroke(self, x, y):
        """Continue the current stroke with a new point from raycasting."""
        if self._annotation_trimesh is None or not self._drawing_active:
            return
        ray_origin, ray_direction = self._screen_to_ray(x, y)
        if ray_origin is None:
            return
        try:
            locations, _, index_tri = self._annotation_trimesh.ray.intersects_location(
                ray_origins=[ray_origin], ray_directions=[ray_direction]
            )
            if len(locations) == 0:
                return
            cam_pos = np.array(self._camera.local.position)
            dists = np.linalg.norm(locations - cam_pos, axis=1)
            closest_idx = np.argmin(dists)
            hit_point = locations[closest_idx]
            normal = self._annotation_trimesh.face_normals[index_tri[closest_idx]]
            offset = self._get_draw_normal_offset()
            hit_point = hit_point + normal * offset
            self._current_stroke_points.append(hit_point.astype(np.float32))
            self._update_current_stroke_line()
        except Exception as e:
            logger.debug(f"_draw_continue_stroke: {e}")

    def _draw_finish_stroke(self):
        """Finalize the current stroke and add it permanently to the scene."""
        self._drawing_active = False
        if len(self._current_stroke_points) < 2:
            self._current_stroke_points = []
            self._remove_current_stroke_line()
            return
        # Remove preview line and create final stroke
        self._remove_current_stroke_line()
        import pygfx as gfx
        try:
            positions = np.array(self._current_stroke_points, dtype=np.float32)
            # Create line segments: pairs of consecutive points
            segments = []
            for i in range(len(positions) - 1):
                segments.append(positions[i])
                segments.append(positions[i + 1])
            seg_positions = np.array(segments, dtype=np.float32)
            geom = gfx.Geometry(positions=seg_positions)
            mat = gfx.LineSegmentMaterial(
                color=self._draw_color, thickness=3.0,
                depth_test=True, depth_write=True
            )
            line_obj = gfx.Line(geom, mat)
            self._scene.add(line_obj)
            self._draw_strokes.append(line_obj)
            points = [p.tolist() if hasattr(p, 'tolist') else list(p) for p in self._current_stroke_points]
            self._draw_strokes_data.append({'points': points, 'color': self._draw_color})
        except Exception as e:
            logger.warning(f"_draw_finish_stroke: {e}")
        self._current_stroke_points = []
        if self._canvas:
            self._canvas.request_draw()

    def _update_current_stroke_line(self):
        """Update the live preview line for the current stroke being drawn."""
        self._remove_current_stroke_line()
        if len(self._current_stroke_points) < 2:
            return
        import pygfx as gfx
        try:
            positions = np.array(self._current_stroke_points, dtype=np.float32)
            segments = []
            for i in range(len(positions) - 1):
                segments.append(positions[i])
                segments.append(positions[i + 1])
            seg_positions = np.array(segments, dtype=np.float32)
            geom = gfx.Geometry(positions=seg_positions)
            mat = gfx.LineSegmentMaterial(
                color=self._draw_color, thickness=3.0,
                depth_test=True, depth_write=True
            )
            self._current_stroke_line = gfx.Line(geom, mat)
            self._scene.add(self._current_stroke_line)
        except Exception as e:
            logger.debug(f"_update_current_stroke_line: {e}")
        if self._canvas:
            self._canvas.request_draw()

    def _remove_current_stroke_line(self):
        """Remove the live preview stroke line from the scene."""
        if self._current_stroke_line is not None:
            try:
                self._scene.remove(self._current_stroke_line)
            except Exception:
                pass
            self._current_stroke_line = None

    def _get_draw_normal_offset(self):
        """Get a small offset along surface normal to prevent z-fighting."""
        if self.current_mesh is None:
            return 0.1
        try:
            b = self.current_mesh.bounds
            diag = np.sqrt(
                (b[1] - b[0]) ** 2 + (b[3] - b[2]) ** 2 + (b[5] - b[4]) ** 2
            )
            return max(diag * 0.001, 0.01)
        except Exception:
            return 0.1

    # ========== 3D Arrow Mode Methods ==========

    def enable_arrow_mode(self):
        """Enable 3D arrow placement mode. Click on mesh to place arrows, drag to orient."""
        if not self._initialized or self._scene is None:
            logger.warning("enable_arrow_mode: Not initialized")
            return False
        if self.current_mesh is None or self._mesh_obj is None:
            logger.warning("enable_arrow_mode: No mesh loaded")
            return False

        logger.info("enable_arrow_mode: Enabling...")
        self.arrow_mode = True

        # Ensure we have a trimesh for raycasting
        if self._annotation_trimesh is None:
            self._build_arrow_trimesh()

        # Install event filter
        if not self._arrow_event_filter_installed and self._canvas is not None:
            self._canvas.installEventFilter(self)
            self.installEventFilter(self)
            self.viewer_container.installEventFilter(self)
            self._arrow_event_filter_installed = True

        logger.info("enable_arrow_mode: Arrow mode enabled")
        return True

    def disable_arrow_mode(self):
        """Disable arrow mode. Arrows remain visible."""
        logger.info("disable_arrow_mode: Disabling...")
        self.arrow_mode = False
        self._arrow_dragging = None
        self._arrow_drag_start = None

        if self._arrow_event_filter_installed and self._canvas is not None:
            self._canvas.removeEventFilter(self)
            self.removeEventFilter(self)
            self.viewer_container.removeEventFilter(self)
            self._arrow_event_filter_installed = False

        logger.info("disable_arrow_mode: Arrow mode disabled")

    def _build_arrow_trimesh(self):
        """Build trimesh for raycasting if not already built."""
        if self._annotation_trimesh is not None:
            return
        try:
            import trimesh
            if hasattr(self.current_mesh, 'points') and hasattr(self.current_mesh, 'faces'):
                faces_raw = self.current_mesh.faces
                if faces_raw is not None and len(faces_raw) > 0:
                    if faces_raw.ndim == 1:
                        n_cols = faces_raw[0] + 1
                        faces_2d = faces_raw.reshape(-1, n_cols)[:, 1:]
                    else:
                        faces_2d = faces_raw
                    self._annotation_trimesh = trimesh.Trimesh(
                        vertices=np.asarray(self.current_mesh.points, dtype=np.float64),
                        faces=np.asarray(faces_2d, dtype=np.int32),
                    )
        except Exception as e:
            logger.warning(f"_build_arrow_trimesh: {e}")

    def _arrow_event_filter_impl(self, obj, event):
        """Handle arrow mode events: click on surface to place arrow (no drag)."""
        if not self.arrow_mode or self._canvas is None:
            return False
        t = event.type()

        if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            pos = event.pos()
            ray_origin, ray_direction = self._screen_to_ray(pos.x(), pos.y())
            if ray_origin is None:
                return False

            if self._annotation_trimesh is None:
                return False

            try:
                locations, _, index_tri = self._annotation_trimesh.ray.intersects_location(
                    ray_origins=[ray_origin],
                    ray_directions=[ray_direction],
                )
                if len(locations) == 0:
                    return False  # No hit - pass through for camera orbit

                cam_pos = np.array(self._camera.local.position)
                dists = np.linalg.norm(locations - cam_pos, axis=1)
                closest_idx = np.argmin(dists)
                hit_point = tuple(float(c) for c in locations[closest_idx])

                # Get surface normal at hit point
                tri_idx = index_tri[closest_idx]
                normal = self._annotation_trimesh.face_normals[tri_idx]
                normal = normal / (np.linalg.norm(normal) + 1e-12)

                arrow_id = self._add_arrow(hit_point, tuple(float(c) for c in normal))
                # Notify callback (ArrowPanel) about the new arrow
                if hasattr(self, '_arrow_added_callback') and self._arrow_added_callback:
                    self._arrow_added_callback(arrow_id)
                return True

            except Exception as e:
                logger.error(f"_arrow_event_filter_impl: {e}", exc_info=True)
                return False

        return False

    def _get_model_diag(self):
        """Return the diagonal of the current mesh bounding box."""
        bounds = self.current_mesh.bounds
        return np.sqrt(
            (bounds[1] - bounds[0]) ** 2 +
            (bounds[3] - bounds[2]) ** 2 +
            (bounds[5] - bounds[4]) ** 2
        )

    def _add_arrow(self, point, direction, color='#E53935', length_factor=0.08):
        """Add a 3D arrow (cone + shaft) at point with direction."""
        import pygfx as gfx

        diag = self._get_model_diag()
        arrow_length = diag * length_factor
        cone_length = arrow_length * 0.35
        shaft_length = arrow_length * 0.65
        cone_radius = arrow_length * 0.10
        shaft_radius = arrow_length * 0.05

        r, g, b = self._hex_to_rgb_normalized(color)
        emissive = (r * 0.15, g * 0.15, b * 0.15)

        group = gfx.Group()

        # pygfx cylinder extends along Z; we need Y. Rotate +90° around X so +Z → +Y.
        rot_x_90 = (0.7071068, 0, 0, 0.7071068)  # quat for +90° around X

        # Shaft cylinder - extends along Z locally; after rot, along Y from 0 to shaft_length
        shaft_geom = gfx.cylinder_geometry(
            radius_bottom=shaft_radius, radius_top=shaft_radius,
            height=shaft_length, radial_segments=24
        )
        shaft_mat = gfx.MeshPhongMaterial(
            color=(r, g, b), emissive=emissive, shininess=80
        )
        shaft = gfx.Mesh(shaft_geom, shaft_mat)
        shaft.local.rotation = rot_x_90
        shaft.local.position = np.array([0, shaft_length / 2, 0], dtype=np.float32)
        group.add(shaft)

        # Cone head - cylinder radius_top=0 (base at -h/2, tip at +h/2 along Z)
        # Use -90° around X so base meets shaft and tip points away (opposite of shaft)
        rot_x_neg90 = (-0.7071068, 0, 0, 0.7071068)
        cone_geom = gfx.cylinder_geometry(
            radius_bottom=cone_radius, radius_top=0,
            height=cone_length, radial_segments=32
        )
        cone_mat = gfx.MeshPhongMaterial(
            color=(r, g, b), emissive=emissive, shininess=80
        )
        cone = gfx.Mesh(cone_geom, cone_mat)
        cone.local.rotation = rot_x_neg90
        cone.local.position = np.array([0, shaft_length + cone_length / 2, 0], dtype=np.float32)
        group.add(cone)

        # Orient along direction
        dir_arr = np.array(direction, dtype=np.float64)
        dir_arr = dir_arr / (np.linalg.norm(dir_arr) + 1e-12)

        offset = diag * 0.002
        placed_point = (
            point[0] + dir_arr[0] * offset,
            point[1] + dir_arr[1] * offset,
            point[2] + dir_arr[2] * offset,
        )

        group.local.position = placed_point
        self._apply_arrow_rotation(group, dir_arr)

        self._scene.add(group)

        arrow_id = self._arrow_next_id
        self._arrow_next_id += 1
        self._arrow_objects.append({
            'id': arrow_id,
            'group': group,
            'point': placed_point,
            'direction': dir_arr.tolist(),
            'length_factor': length_factor,
            'color': color,
        })

        if self._canvas:
            self._canvas.request_draw()

        logger.info(f"_add_arrow: Added arrow {arrow_id} at {point}")
        return arrow_id

    def _apply_arrow_rotation(self, group, direction):
        """Rotate group so local +Y aligns with direction vector."""
        up = np.array([0, 1, 0], dtype=np.float64)
        dir_arr = np.array(direction, dtype=np.float64)
        dir_arr = dir_arr / (np.linalg.norm(dir_arr) + 1e-12)

        try:
            from pylinalg import quat_from_vecs
            q = quat_from_vecs(up, dir_arr)
            group.local.rotation = q
        except Exception:
            cross = np.cross(up, dir_arr)
            dot = np.dot(up, dir_arr)
            if np.linalg.norm(cross) < 1e-8:
                if dot > 0:
                    group.local.rotation = (0, 0, 0, 1)
                else:
                    group.local.rotation = (1, 0, 0, 0)
            else:
                w = 1.0 + dot
                q = np.array([cross[0], cross[1], cross[2], w], dtype=np.float64)
                q = q / (np.linalg.norm(q) + 1e-12)
                group.local.rotation = tuple(q)

    def _find_arrow(self, arrow_id):
        """Find arrow dict by ID."""
        for a in self._arrow_objects:
            if a['id'] == arrow_id:
                return a
        return None

    def rotate_arrow(self, arrow_id, axis, angle_deg):
        """Rotate an arrow by angle_deg around the given world axis ('x', 'y', 'z')."""
        arrow = self._find_arrow(arrow_id)
        if arrow is None:
            return

        angle_rad = np.radians(angle_deg)
        cos_a = np.cos(angle_rad)
        sin_a = np.sin(angle_rad)

        dir_arr = np.array(arrow['direction'], dtype=np.float64)

        if axis == 'x':
            rot = np.array([[1, 0, 0], [0, cos_a, -sin_a], [0, sin_a, cos_a]])
        elif axis == 'y':
            rot = np.array([[cos_a, 0, sin_a], [0, 1, 0], [-sin_a, 0, cos_a]])
        else:  # z
            rot = np.array([[cos_a, -sin_a, 0], [sin_a, cos_a, 0], [0, 0, 1]])

        new_dir = rot @ dir_arr
        new_dir = new_dir / (np.linalg.norm(new_dir) + 1e-12)

        arrow['direction'] = new_dir.tolist()
        self._apply_arrow_rotation(arrow['group'], new_dir)

        if self._canvas:
            self._canvas.request_draw()

    def scale_arrow(self, arrow_id, factor):
        """Scale an arrow's length by factor (e.g. 1.15 to grow, 0.85 to shrink)."""
        arrow = self._find_arrow(arrow_id)
        if arrow is None:
            return

        old_factor = arrow.get('length_factor', 0.08)
        new_factor = old_factor * factor
        new_factor = max(0.02, min(0.5, new_factor))  # clamp

        # Remove old arrow group and re-create
        point = arrow['point']
        direction = arrow['direction']
        color = arrow.get('color', '#E53935')

        try:
            self._scene.remove(arrow['group'])
        except Exception:
            pass

        # Remove from list
        self._arrow_objects = [a for a in self._arrow_objects if a['id'] != arrow_id]

        # Re-add with new size, preserving ID
        old_next = self._arrow_next_id
        self._arrow_next_id = arrow_id
        self._add_arrow(point, direction, color=color, length_factor=new_factor)
        self._arrow_next_id = old_next if old_next > arrow_id else arrow_id + 1

    def move_arrow(self, arrow_id, dx, dy, dz):
        """Move an arrow by (dx, dy, dz) scaled relative to model size."""
        arrow = self._find_arrow(arrow_id)
        if arrow is None:
            return

        diag = self._get_model_diag()
        step = diag * 0.02  # 2% of model size per click

        pos = np.array(arrow['point'], dtype=np.float64)
        pos[0] += dx * step
        pos[1] += dy * step
        pos[2] += dz * step

        arrow['point'] = tuple(float(c) for c in pos)
        arrow['group'].local.position = np.array(pos, dtype=np.float32)

        if self._canvas:
            self._canvas.request_draw()

    def set_arrow_color(self, arrow_id, color):
        """Change the color of an existing arrow."""
        arrow = self._find_arrow(arrow_id)
        if arrow is None:
            return

        r, g, b = self._hex_to_rgb_normalized(color)
        emissive = (r * 0.15, g * 0.15, b * 0.15)
        arrow['color'] = color

        # Update materials on children (shaft + cone)
        for child in arrow['group'].children:
            if hasattr(child, 'material'):
                child.material.color = (r, g, b)
                if hasattr(child.material, 'emissive'):
                    child.material.emissive = emissive

        if self._canvas:
            self._canvas.request_draw()

    def get_arrow_list(self):
        """Return list of arrow dicts with id, point, direction, length_factor, color."""
        return [
            {
                'id': a['id'],
                'point': a['point'],
                'direction': a['direction'],
                'length_factor': a.get('length_factor', 0.08),
                'color': a.get('color', '#E53935'),
            }
            for a in self._arrow_objects
        ]

    def remove_arrow(self, arrow_id):
        """Remove a specific arrow by ID."""
        for i, a in enumerate(self._arrow_objects):
            if a['id'] == arrow_id:
                try:
                    self._scene.remove(a['group'])
                except Exception:
                    pass
                self._arrow_objects.pop(i)
                if self._canvas:
                    self._canvas.request_draw()
                break

    def clear_all_arrows(self):
        """Remove all 3D arrows from the scene."""
        for a in self._arrow_objects:
            try:
                self._scene.remove(a['group'])
            except Exception:
                pass
        self._arrow_objects.clear()
        if self._canvas:
            self._canvas.request_draw()

    def undo_last_arrow(self):
        """Remove the most recently added arrow."""
        if self._arrow_objects:
            self.remove_arrow(self._arrow_objects[-1]['id'])

    # ========== Part Visibility Methods ==========

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
        logger.info(f"parts_debug (pygfx): get_parts_list returning {len(parts)} parts: {[(x['name'], x['face_count']) for x in parts]}")
        return parts

    def get_parts_hierarchy(self):
        """Return grouped parts sorted largest-to-smallest.
        
        Large parts are standalone entries. Small nearby parts are clustered
        into groups. Each group is a single selectable item with internal
        child_ids for visibility/highlighting control.
        
        Returns list of dicts:
          Standalone: {'id': int, 'name': str, 'face_count': int, 'visible': bool}
          Group:      {'id': int, 'name': str, 'face_count': int, 'visible': bool, 'child_ids': [int, ...]}
        """
        from scipy.cluster.hierarchy import linkage, fcluster
        from scipy.spatial.distance import pdist

        flat_parts = self.get_parts_list()
        if len(flat_parts) <= 1:
            return flat_parts

        # Compute face count threshold — parts above this are standalone
        face_counts = [p['face_count'] for p in flat_parts]
        threshold_faces = max(500, int(np.percentile(face_counts, 80))) if len(face_counts) > 5 else 500

        large_parts = []
        small_parts = []
        for p in flat_parts:
            if p['face_count'] >= threshold_faces:
                large_parts.append(p)
            else:
                small_parts.append(p)

        result = []

        # Large parts go as standalone entries
        for p in large_parts:
            result.append(p)

        # Cluster small parts by spatial proximity
        if len(small_parts) > 1:
            # Get centroids of small parts from mesh_parts data
            centroids = []
            for sp in small_parts:
                mp = next((m for m in self._mesh_parts if m['id'] == sp['id']), None)
                if mp and 'trimesh' in mp and mp['trimesh'] is not None:
                    centroids.append(mp['trimesh'].centroid)
                elif mp and hasattr(mp.get('mesh_obj'), 'geometry') and mp['mesh_obj'].geometry is not None:
                    positions = mp['mesh_obj'].geometry.positions
                    if positions is not None:
                        centroids.append(np.mean(positions.data, axis=0))
                    else:
                        centroids.append(np.array([0.0, 0.0, 0.0]))
                else:
                    centroids.append(np.array([0.0, 0.0, 0.0]))

            centroids = np.array(centroids)

            # Distance threshold based on bounding box
            bbox_min = centroids.min(axis=0)
            bbox_max = centroids.max(axis=0)
            bbox_diag = np.linalg.norm(bbox_max - bbox_min)
            dist_threshold = bbox_diag * 0.08 if bbox_diag > 0 else 1.0

            if len(small_parts) >= 2:
                try:
                    dists = pdist(centroids)
                    Z = linkage(dists, method='average')
                    labels = fcluster(Z, t=dist_threshold, criterion='distance')
                except Exception:
                    labels = list(range(len(small_parts)))
            else:
                labels = [0]

            # Group small parts by cluster label
            clusters = {}
            for i, label in enumerate(labels):
                clusters.setdefault(label, []).append(small_parts[i])

            # Use negative IDs for groups to avoid collision with real part IDs
            group_counter = -1
            for cluster_parts in sorted(clusters.values(), key=lambda c: -sum(p['face_count'] for p in c)):
                if len(cluster_parts) == 1:
                    # Single-part cluster — just add as standalone
                    result.append(cluster_parts[0])
                else:
                    total_faces = sum(p['face_count'] for p in cluster_parts)
                    child_ids = [p['id'] for p in cluster_parts]
                    group_entry = {
                        'id': group_counter,
                        'name': f"Group {abs(group_counter)}",
                        'face_count': total_faces,
                        'visible': all(p.get('visible', True) for p in cluster_parts),
                        'child_ids': child_ids,
                    }
                    result.append(group_entry)
                    group_counter -= 1
        elif len(small_parts) == 1:
            result.append(small_parts[0])

        # Sort by face count descending
        result.sort(key=lambda x: -x.get('face_count', 0))
        logger.info(f"parts_debug (pygfx): get_parts_hierarchy returning {len(result)} entries "
                     f"({len(large_parts)} standalone, {len(result) - len(large_parts)} groups/small)")
        return result

    def set_part_visible(self, part_id, visible):
        """Show or hide a specific part by ID."""
        for p in self._mesh_parts:
            if p['id'] == part_id:
                p['visible'] = visible
                p['mesh_obj'].visible = visible
                break
        if self._canvas:
            self._canvas.request_draw()

    def show_all_parts(self):
        """Make all parts visible."""
        for p in self._mesh_parts:
            p['visible'] = True
            p['mesh_obj'].visible = True
        if self._canvas:
            self._canvas.request_draw()

    def hide_all_parts(self):
        """Hide all parts."""
        for p in self._mesh_parts:
            p['visible'] = False
            p['mesh_obj'].visible = False
        if self._canvas:
            self._canvas.request_draw()

    def invert_parts_visibility(self):
        """Invert visibility of all parts."""
        for p in self._mesh_parts:
            p['visible'] = not p['visible']
            p['mesh_obj'].visible = p['visible']
        if self._canvas:
            self._canvas.request_draw()

    def isolate_part(self, part_id):
        """Show only the specified part, hide all others."""
        for p in self._mesh_parts:
            vis = (p['id'] == part_id)
            p['visible'] = vis
            p['mesh_obj'].visible = vis
        if self._canvas:
            self._canvas.request_draw()

    def isolate_parts(self, part_ids):
        """Show only the specified parts, hide all others."""
        id_set = set(part_ids)
        for p in self._mesh_parts:
            vis = p['id'] in id_set
            p['visible'] = vis
            p['mesh_obj'].visible = vis
        if self._canvas:
            self._canvas.request_draw()

    def highlight_part(self, part_id):
        """Briefly highlight a selected part (make others semi-transparent)."""
        import pygfx as gfx
        for p in self._mesh_parts:
            if not p['visible']:
                continue
            if p['id'] == part_id:
                # Restore full opacity
                if self._render_mode == 'wireframe':
                    p['mesh_obj'].material = gfx.MeshBasicMaterial(wireframe=True, color="#333333", wireframe_thickness=1)
                elif self._render_mode == 'shaded':
                    p['mesh_obj'].material = gfx.MeshPhongMaterial(color="#b8b8c0", specular="#a0a0a0", shininess=90)
                else:
                    p['mesh_obj'].material = gfx.MeshPhongMaterial(color="#ADD9E6", specular="#333333", shininess=20)
            else:
                # Semi-transparent
                p['mesh_obj'].material = gfx.MeshPhongMaterial(
                    color="#ADD9E6", specular="#333333", shininess=20, opacity=0.25
                )
        if self._canvas:
            self._canvas.request_draw()

    def highlight_parts(self, part_ids):
        """Highlight multiple parts (e.g. a group) — make others semi-transparent."""
        import pygfx as gfx
        highlighted = set(part_ids)
        for p in self._mesh_parts:
            if not p['visible']:
                continue
            if p['id'] in highlighted:
                if self._render_mode == 'wireframe':
                    p['mesh_obj'].material = gfx.MeshBasicMaterial(wireframe=True, color="#333333", wireframe_thickness=1)
                elif self._render_mode == 'shaded':
                    p['mesh_obj'].material = gfx.MeshPhongMaterial(color="#b8b8c0", specular="#a0a0a0", shininess=90)
                else:
                    p['mesh_obj'].material = gfx.MeshPhongMaterial(color="#ADD9E6", specular="#333333", shininess=20)
            else:
                p['mesh_obj'].material = gfx.MeshPhongMaterial(
                    color="#ADD9E6", specular="#333333", shininess=20, opacity=0.25
                )
        if self._canvas:
            self._canvas.request_draw()

    def unhighlight_parts(self):
        """Restore normal materials on all parts."""
        self.set_render_mode(self._render_mode)

    # ========== Parts Pick Mode (click-to-select in 3D) ==========

    def enable_parts_pick_mode(self):
        """Enable click-to-select parts in the 3D viewport."""
        self.parts_pick_mode = True
        if not self._parts_pick_event_filter_installed and self._canvas is not None:
            self._canvas.installEventFilter(self)
            self.installEventFilter(self)
            self.viewer_container.installEventFilter(self)
            self._parts_pick_event_filter_installed = True
        logger.info("enable_parts_pick_mode: Parts pick mode enabled")

    def disable_parts_pick_mode(self):
        """Disable click-to-select parts."""
        self.parts_pick_mode = False
        if self._parts_pick_event_filter_installed and self._canvas is not None:
            self._canvas.removeEventFilter(self)
            self.removeEventFilter(self)
            self.viewer_container.removeEventFilter(self)
            self._parts_pick_event_filter_installed = False
        logger.info("disable_parts_pick_mode: Parts pick mode disabled")

    def _parts_pick_event_filter_impl(self, obj, event):
        """Handle parts pick mode events. Only intercept left clicks that hit a part."""
        if not self.parts_pick_mode or self._canvas is None:
            return False
        t = event.type()
        if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            pos = event.pos()
            picked = self._on_parts_pick_click(pos.x(), pos.y())
            return picked  # consume only if we hit a part; else let trackball rotate
        return False

    def _on_parts_pick_click(self, x, y):
        """Raycast against each part's trimesh to find which part was clicked."""
        if not self._mesh_parts:
            return False
        ray_origin, ray_direction = self._screen_to_ray(x, y)
        if ray_origin is None:
            return False

        import trimesh
        best_part_id = None
        best_dist = float('inf')
        cam_pos = np.array(self._camera.local.position)

        for p in self._mesh_parts:
            if not p.get('visible', True):
                continue
            tm = p.get('trimesh')
            if tm is None:
                continue
            try:
                locations, _, _ = tm.ray.intersects_location(
                    ray_origins=[ray_origin],
                    ray_directions=[ray_direction],
                )
                if len(locations) > 0:
                    dists = np.linalg.norm(locations - cam_pos, axis=1)
                    min_dist = np.min(dists)
                    if min_dist < best_dist:
                        best_dist = min_dist
                        best_part_id = p['id']
            except Exception as e:
                logger.debug(f"_on_parts_pick_click: raycast error for part {p['id']}: {e}")

        if best_part_id is not None:
            logger.info(f"_on_parts_pick_click: clicked part {best_part_id}")
            self.part_clicked.emit(best_part_id)
            return True
        return False

    # ========== Texture Mode Methods ==========

    def enable_texture_drop_mode(self):
        """Enable texture drag-and-drop onto model parts."""
        self._texture_drop_mode = True
        if self._canvas is not None:
            self._canvas.setAcceptDrops(True)
            self.viewer_container.setAcceptDrops(True)
            self.setAcceptDrops(True)
        logger.info("enable_texture_drop_mode: Texture drop mode enabled")

    def disable_texture_drop_mode(self):
        """Disable texture drag-and-drop."""
        self._texture_drop_mode = False
        if self._canvas is not None:
            self._canvas.setAcceptDrops(False)
            self.viewer_container.setAcceptDrops(False)
            self.setAcceptDrops(False)
        logger.info("disable_texture_drop_mode: Texture drop mode disabled")

    def dragEnterEvent(self, event):
        """Accept drag events carrying texture or material preset data."""
        if getattr(self, '_texture_drop_mode', False):
            mime = event.mimeData()
            if (mime.hasFormat("application/x-ectoform-texture")
                    or mime.hasFormat("application/x-ectoform-material-preset")
                    or mime.hasText()):
                event.acceptProposedAction()
                return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        """Accept drag move events."""
        if getattr(self, '_texture_drop_mode', False):
            mime = event.mimeData()
            if (mime.hasFormat("application/x-ectoform-texture")
                    or mime.hasFormat("application/x-ectoform-material-preset")
                    or mime.hasText()):
                event.acceptProposedAction()
                return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        """Handle texture / material preset drop on model."""
        if not getattr(self, '_texture_drop_mode', False):
            super().dropEvent(event)
            return

        mime = event.mimeData()

        # --- Material preset drop ---
        if mime.hasFormat("application/x-ectoform-material-preset"):
            import json as _json
            try:
                payload = _json.loads(bytes(mime.data("application/x-ectoform-material-preset")).decode('utf-8'))
            except Exception:
                event.ignore()
                return
            pos = event.pos()
            canvas_pos = self._canvas.mapFrom(self, pos) if self._canvas else pos
            part_id = self._raycast_part_at(canvas_pos.x(), canvas_pos.y())
            if part_id is not None:
                self.apply_material_preset_to_part(part_id, payload)
                event.acceptProposedAction()
                logger.info(f"dropEvent: Applied material preset to part {part_id}")
            elif self._mesh_obj is not None and len(self._mesh_parts) <= 1:
                self._apply_material_preset_to_mesh(self._mesh_obj, payload)
                event.acceptProposedAction()
                logger.info("dropEvent: Applied material preset to entire model")
            else:
                event.ignore()
            return

        # --- Image texture drop ---
        if mime.hasFormat("application/x-ectoform-texture"):
            image_path = bytes(mime.data("application/x-ectoform-texture")).decode('utf-8')
        elif mime.hasText():
            image_path = mime.text()
        else:
            event.ignore()
            return

        if not image_path or not os.path.isfile(image_path):
            logger.warning(f"dropEvent: Invalid image path: {image_path}")
            event.ignore()
            return

        # Raycast to find which part was dropped on
        pos = event.pos()
        canvas_pos = self._canvas.mapFrom(self, pos) if self._canvas else pos
        part_id = self._raycast_part_at(canvas_pos.x(), canvas_pos.y())

        if part_id is not None:
            self.apply_texture_to_part(part_id, image_path)
            event.acceptProposedAction()
            logger.info(f"dropEvent: Applied texture to part {part_id}")
        else:
            if self._mesh_obj is not None and len(self._mesh_parts) <= 1:
                self._apply_texture_to_mesh(self._mesh_obj, self.current_mesh, image_path)
                event.acceptProposedAction()
                logger.info("dropEvent: Applied texture to entire model")
            else:
                logger.info("dropEvent: No part hit by raycast")
                event.ignore()

    def _raycast_part_at(self, x, y):
        """Raycast to find which part is under screen position (x, y). Returns part_id or None."""
        if not self._mesh_parts or self._camera is None:
            return None
        ray_origin, ray_direction = self._screen_to_ray(x, y)
        if ray_origin is None:
            return None

        best_part_id = None
        best_dist = float('inf')
        cam_pos = np.array(self._camera.local.position)

        for p in self._mesh_parts:
            if not p.get('visible', True):
                continue
            tm = p.get('trimesh')
            if tm is None:
                continue
            try:
                locations, _, _ = tm.ray.intersects_location(
                    ray_origins=[ray_origin],
                    ray_directions=[ray_direction],
                )
                if len(locations) > 0:
                    dists = np.linalg.norm(locations - cam_pos, axis=1)
                    min_dist = np.min(dists)
                    if min_dist < best_dist:
                        best_dist = min_dist
                        best_part_id = p['id']
            except Exception as e:
                logger.debug(f"_raycast_part_at: error for part {p['id']}: {e}")

        return best_part_id

    def apply_texture_to_part(self, part_id, image_path):
        """Apply a texture image to a specific part mesh."""
        part = None
        for p in self._mesh_parts:
            if p['id'] == part_id:
                part = p
                break
        if part is None:
            logger.warning(f"apply_texture_to_part: Part {part_id} not found")
            return

        mesh_obj = part.get('mesh_obj')
        tm = part.get('trimesh')
        if mesh_obj is None:
            logger.warning(f"apply_texture_to_part: Part {part_id} has no mesh_obj")
            return

        self._apply_texture_to_mesh(mesh_obj, tm, image_path)

    def _apply_texture_to_mesh(self, mesh_obj, tm, image_path):
        """Apply texture to a pygfx mesh object, generating UVs if needed."""
        import pygfx as gfx
        from PIL import Image

        try:
            img = Image.open(image_path).convert("RGB")
            tex_data = np.array(img, dtype=np.uint8)
            texture = gfx.Texture(tex_data, dim=2)

            # Generate UV coordinates via box projection if the geometry lacks them
            geom = mesh_obj.geometry
            if geom is not None:
                positions = geom.positions
                if positions is not None:
                    uvs = self._generate_box_uvs(positions.data if hasattr(positions, 'data') else positions)
                    geom.texcoords = gfx.Buffer(uvs)

            material = gfx.MeshPhongMaterial(map=texture)
            # Store original material for removal
            if not hasattr(mesh_obj, '_original_material'):
                mesh_obj._original_material = mesh_obj.material
            mesh_obj.material = material

            if self._canvas:
                self._canvas.request_draw()
            logger.info(f"_apply_texture_to_mesh: Texture applied from {image_path}")
        except Exception as e:
            logger.error(f"_apply_texture_to_mesh: Failed: {e}", exc_info=True)

    def apply_material_preset_to_part(self, part_id, preset_data):
        """Apply a material preset (color + specular + shininess) to a part."""
        part = None
        for p in self._mesh_parts:
            if p['id'] == part_id:
                part = p
                break
        if part is None:
            logger.warning(f"apply_material_preset_to_part: Part {part_id} not found")
            return
        mesh_obj = part.get('mesh_obj')
        if mesh_obj is None:
            logger.warning(f"apply_material_preset_to_part: Part {part_id} has no mesh_obj")
            return
        self._apply_material_preset_to_mesh(mesh_obj, preset_data)

    def _create_studio_env_map(self):
        """Create a procedural warm studio environment cube texture for PBR reflections.
        Simulates a jewelry photography light box with bright warm panels."""
        import numpy as np
        import pygfx as gfx

        if hasattr(self, '_studio_env_tex') and self._studio_env_tex is not None:
            return self._studio_env_tex

        size = 512
        # Vectorized face creation — smooth radial gradient, no per-pixel loop
        def _make_face(center_rgb, edge_rgb):
            y_coords = np.arange(size, dtype=np.float32) - size / 2.0
            x_coords = np.arange(size, dtype=np.float32) - size / 2.0
            xx, yy = np.meshgrid(x_coords, y_coords)
            max_dist = (((size / 2.0) ** 2) * 2) ** 0.5
            dist = np.sqrt(xx * xx + yy * yy)
            t = np.clip(dist / max_dist, 0.0, 1.0)
            # Smooth hermite interpolation
            t = t * t * (3.0 - 2.0 * t)
            face = np.zeros((size, size, 4), dtype=np.uint8)
            for c in range(3):
                face[:, :, c] = (center_rgb[c] * (1.0 - t) + edge_rgb[c] * t).astype(np.uint8)
            face[:, :, 3] = 255
            return face

        # 6 faces with warm studio lighting contrast
        softbox_center = (255, 245, 220)
        softbox_edge = (120, 100, 70)
        top_center = (255, 255, 245)
        top_edge = (200, 190, 160)
        bottom_center = (180, 145, 80)
        bottom_edge = (80, 60, 35)

        faces = [
            _make_face(softbox_center, softbox_edge),
            _make_face(softbox_edge, softbox_center),
            _make_face(top_center, top_edge),
            _make_face(bottom_center, bottom_edge),
            _make_face(softbox_center, softbox_edge),
            _make_face(softbox_edge, softbox_center),
        ]

        # Shape must be (6, size, size, channels) per pygfx docs
        cube_data = np.stack(faces, axis=0)  # (6, size, size, 4)

        try:
            self._studio_env_tex = gfx.Texture(cube_data, dim=2, size=(size, size, 6), generate_mipmaps=True)
            logger.info("_create_studio_env_map: Created procedural studio env map")
        except Exception as e:
            logger.warning(f"_create_studio_env_map: Failed to create env texture: {e}")
            self._studio_env_tex = None

        return self._studio_env_tex

    def _apply_material_preset_to_mesh(self, mesh_obj, preset_data):
        """Apply material preset to a mesh — uses PBR MeshStandardMaterial for
        metallic presets (Gold/Silver) with environment map, and MeshPhongMaterial
        for non-metallic presets."""
        import pygfx as gfx
        try:
            color = preset_data.get("color", "#CCCCCC")
            emissive = preset_data.get("emissive", None)
            metalness = preset_data.get("metalness", None)
            roughness = preset_data.get("roughness", None)

            if metalness is not None and metalness > 0:
                # PBR path for metallic presets (Gold, Silver)
                mat_kwargs = dict(
                    color=color,
                    metalness=float(metalness),
                    roughness=float(roughness) if roughness is not None else 0.2,
                )
                if emissive:
                    mat_kwargs["emissive"] = emissive

                material = gfx.MeshStandardMaterial(**mat_kwargs)

                # env_map must be set as property, not constructor kwarg
                env_tex = self._create_studio_env_map()
                if env_tex is not None:
                    material.env_map = env_tex
                    material.env_mapping_mode = "CUBE-REFLECTION"
                    material.env_map_intensity = 1.5

                if emissive:
                    material.emissive_intensity = 0.25
            else:
                # Phong path for non-metallic presets (Leather)
                specular = preset_data.get("specular", "#FFFFFF")
                shininess = preset_data.get("shininess", 100)
                mat_kwargs = dict(
                    color=color,
                    specular=specular,
                    shininess=shininess,
                )
                if emissive:
                    mat_kwargs["emissive"] = emissive
                material = gfx.MeshPhongMaterial(**mat_kwargs)
                if emissive:
                    material.emissive_intensity = 0.15

            if not hasattr(mesh_obj, '_original_material'):
                mesh_obj._original_material = mesh_obj.material
            mesh_obj.material = material

            # Add accent lights for metallic presets
            self._add_preset_accent_lights()

            if self._canvas:
                self._canvas.request_draw()
            logger.info(f"_apply_material_preset_to_mesh: Applied preset color={color} metalness={metalness} roughness={roughness} env_map={'yes' if metalness and metalness > 0 else 'no'}")
        except Exception as e:
            logger.error(f"_apply_material_preset_to_mesh: Failed: {e}", exc_info=True)

    def _add_preset_accent_lights(self):
        """Add clean 4-light rig — env map handles reflections, these add
        controlled specular bands and prevent pitch-black shadows."""
        import pygfx as gfx
        # Remove any existing accent lights first
        self._remove_preset_accent_lights()
        if self._scene is None:
            return
        self._preset_accent_lights = []

        light_configs = [
            # Key light — main specular band
            {"color": "#FFFFFF", "intensity": 2.0, "pos": (5, 5, 5)},
            # Fill light — front, prevents dark camera-facing surfaces
            {"color": "#FFFFFF", "intensity": 1.0, "pos": (0, 2, 8)},
            # Rim light — edge definition
            {"color": "#FFFFFF", "intensity": 1.5, "pos": (-6, 3, -3)},
            # Bottom bounce — warm, simulates floor reflection
            {"color": "#FFF5E0", "intensity": 0.5, "pos": (0, -5, 0)},
        ]
        for cfg in light_configs:
            light = gfx.DirectionalLight(color=cfg["color"], intensity=cfg["intensity"])
            light.local.position = cfg["pos"]
            light.look_at((0, 0, 0))
            self._scene.add(light)
            self._preset_accent_lights.append(light)

    def _remove_preset_accent_lights(self):
        """Remove accent lights added for material presets."""
        if not hasattr(self, '_preset_accent_lights') or not self._preset_accent_lights:
            return
        for light in self._preset_accent_lights:
            if self._scene and light in self._scene.children:
                self._scene.remove(light)
        self._preset_accent_lights = []

    def update_texture_settings(self, settings):
        """Update material/texture properties based on slider values from the texture panel.
        settings: dict with keys scale, rotation, roughness, metalness, opacity."""
        import pygfx as gfx
        import math

        opacity = settings.get("opacity", 1.0)
        roughness = settings.get("roughness", 0.5)
        metalness = settings.get("metalness", 0.0)
        scale = settings.get("scale", 1.0)
        rotation_deg = settings.get("rotation", 0)

        # Apply to all parts that have been textured/preset-applied
        meshes = []
        for p in self._mesh_parts:
            mo = p.get('mesh_obj')
            if mo and hasattr(mo, '_original_material'):
                meshes.append(mo)
        # Fallback: single mesh
        if not meshes and self._mesh_obj and hasattr(self._mesh_obj, '_original_material'):
            meshes = [self._mesh_obj]

        for mesh_obj in meshes:
            mat = mesh_obj.material
            if mat is None:
                continue
            # Opacity
            if hasattr(mat, 'opacity'):
                mat.opacity = opacity
                mat.transparent = opacity < 1.0
            # Shininess modulation via roughness (invert: high roughness = low shininess)
            if hasattr(mat, 'shininess'):
                mat.shininess = max(1, int((1.0 - roughness) * 500))
            # UV scale and rotation
            geom = mesh_obj.geometry
            if geom is not None and hasattr(geom, 'texcoords') and geom.texcoords is not None:
                base_uvs = geom.texcoords.data if hasattr(geom.texcoords, 'data') else geom.texcoords
                if base_uvs is not None:
                    import numpy as _np
                    uvs = _np.array(base_uvs, dtype=_np.float32).copy()
                    # Scale
                    uvs = uvs * scale
                    # Rotation around UV center (0.5, 0.5)
                    if rotation_deg != 0:
                        rad = math.radians(rotation_deg)
                        cos_r, sin_r = math.cos(rad), math.sin(rad)
                        cx, cy = 0.5, 0.5
                        u = uvs[:, 0] - cx
                        v = uvs[:, 1] - cy
                        uvs[:, 0] = u * cos_r - v * sin_r + cx
                        uvs[:, 1] = u * sin_r + v * cos_r + cy
                    geom.texcoords = gfx.Buffer(uvs)

        if self._canvas:
            self._canvas.request_draw()

    def remove_texture_from_part(self, part_id):
        """Revert a part to its original material (remove texture)."""
        for p in self._mesh_parts:
            if p['id'] == part_id:
                mesh_obj = p.get('mesh_obj')
                if mesh_obj and hasattr(mesh_obj, '_original_material'):
                    mesh_obj.material = mesh_obj._original_material
                    del mesh_obj._original_material
                    if self._canvas:
                        self._canvas.request_draw()
                # Remove accent lights if no more presets active
                has_presets = any(
                    hasattr(pp.get('mesh_obj'), '_original_material')
                    for pp in self._mesh_parts if pp.get('mesh_obj')
                )
                if not has_presets:
                    self._remove_preset_accent_lights()
                return

    def _generate_box_uvs(self, vertices):
        """Generate UV coordinates using box/planar projection from vertex positions."""
        verts = np.asarray(vertices, dtype=np.float32)
        if verts.ndim != 2 or verts.shape[1] < 3:
            return np.zeros((len(verts), 2), dtype=np.float32)

        mins = verts.min(axis=0)
        maxs = verts.max(axis=0)
        size = maxs - mins
        size[size == 0] = 1.0

        # Project onto the two axes with the largest span
        spans = size[:3]
        axes = np.argsort(spans)[-2:]  # Two largest axes
        ax0, ax1 = sorted(axes)

        uvs = np.zeros((len(verts), 2), dtype=np.float32)
        uvs[:, 0] = (verts[:, ax0] - mins[ax0]) / size[ax0]
        uvs[:, 1] = (verts[:, ax1] - mins[ax1]) / size[ax1]

        return uvs
