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
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QEvent, QPoint, QPointF, QRectF
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QPixmap
from ui.drop_zone_overlay import DropZoneOverlay

logger = logging.getLogger(__name__)


from ui.orientation_gizmo import OrientationGizmoWidget


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
        self._mesh_obj = None
        self.current_mesh = None  # Trimesh object for compatibility
        self.current_actor = None  # Not used; kept for hasattr checks
        self.plotter = None  # Not used; kept for hasattr checks
        self._model_loaded = False
        self._initialized = False
        self._render_mode = 'solid'
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

            # PyVista-equivalent lighting: main (1,1,1) intensity 1.0, fill (-1,-0.5,0.5) intensity 0.4
            self._scene.add(gfx.AmbientLight())
            light1 = gfx.DirectionalLight(color="white", intensity=1.0)
            light1.local.position = (1, 1, 1)
            light1.look_at((0, 0, 0))
            self._scene.add(light1)
            light2 = gfx.DirectionalLight(color="white", intensity=0.4)
            light2.local.position = (-1, -0.5, 0.5)
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
        supported = ('.stl', '.obj', '.ply', '.step', '.stp', '.3dm', '.iges', '.igs')
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
            # OBJ: try trimesh first, fallback to PyVista/meshio/ObjLoader
            elif file_ext.endswith('.obj'):
                mesh_tri = None
                try:
                    mesh_tri = trimesh.load(file_path, force='mesh')
                except Exception:
                    pass
                if mesh_tri is None or (isinstance(mesh_tri, trimesh.Trimesh) and len(mesh_tri.vertices) == 0):
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
                if mesh_tri is None or (isinstance(mesh_tri, trimesh.Trimesh) and len(mesh_tri.vertices) == 0):
                    raise ValueError("OBJ file could not be loaded")
                if pv_mesh is None:
                    pv_mesh = _trimesh_to_pyvista(mesh_tri)
            # STL, PLY: trimesh
            else:
                mesh_tri = trimesh.load(file_path, force='mesh')
                if mesh_tri is None:
                    raise ValueError("No mesh in file")
                pv_mesh = _trimesh_to_pyvista(mesh_tri)

            # Normalize mesh_tri (Scene -> single Trimesh)
            if isinstance(mesh_tri, trimesh.Scene):
                all_meshes = [g for g in mesh_tri.geometry.values() if isinstance(g, trimesh.Trimesh)]
                if not all_meshes:
                    raise ValueError("No meshes in file")
                mesh_tri = trimesh.util.concatenate(all_meshes) if len(all_meshes) > 1 else all_meshes[0]
            if not isinstance(mesh_tri, trimesh.Trimesh) or len(mesh_tri.vertices) == 0:
                raise ValueError("No mesh in file")

            # Use flat-shaded mesh for sharp edges (original geometry has sharp edges)
            mesh_tri = _trimesh_to_flat_shaded(mesh_tri)

            # Ensure PyVista for MeshCalculator
            if pv_mesh is None:
                pv_mesh = _trimesh_to_pyvista(mesh_tri)
            if pv_mesh is None:
                raise ValueError("Could not convert mesh for dimensions/volume calculation")

            # PyVista-equivalent material (light blue per spec: RGB 0.68, 0.85, 0.90 = #ADD9E6)
            material = gfx.MeshPhongMaterial(
                color="#ADD9E6",
                specular="#333333",
                shininess=20,
            )
            from pygfx.geometries import geometry_from_trimesh
            geometry = geometry_from_trimesh(mesh_tri)
            mesh_obj = gfx.Mesh(geometry, material)
            self._mesh_obj = mesh_obj
            self._scene.add(self._mesh_obj)
            self.set_render_mode(self._render_mode)

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
        if mode == 'wireframe':
            self._mesh_obj.material = gfx.MeshBasicMaterial(
                wireframe=True, color="#333333", wireframe_thickness=1
            )
        elif mode == 'shaded':
            self._mesh_obj.material = gfx.MeshPhongMaterial(
                color="#b8b8c0", specular="#a0a0a0", shininess=90
            )
        else:  # solid
            self._mesh_obj.material = gfx.MeshPhongMaterial(
                color="#ADD9E6", specular="#333333", shininess=20
            )
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
        """Qt event filter: handle ruler_mode and annotation_mode events."""
        if self._canvas is None:
            return super().eventFilter(obj, event)
        if not self.ruler_mode and not self.annotation_mode:
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
            self._screenshot_overlay = ScreenshotOverlay(self.viewer_container)
            self._screenshot_overlay.region_selected.connect(self._on_screenshot_region_selected)
        self._screenshot_overlay.setGeometry(self.viewer_container.rect())
        self._screenshot_overlay.raise_()
        self._screenshot_overlay.show()
        self.screenshot_mode = True
        return True

    def disable_screenshot_mode(self):
        """Disable screenshot mode: hide overlay."""
        self.screenshot_mode = False
        if self._screenshot_overlay is not None:
            self._screenshot_overlay.hide()

    def _on_screenshot_region_selected(self, rect):
        """Capture the selected region from the canvas."""
        from PyQt5.QtGui import QPixmap
        # Grab the viewer container (which contains the rendered canvas)
        full_pixmap = self.viewer_container.grab()
        cropped = full_pixmap.copy(rect)
        if self._screenshot_captured_callback:
            self._screenshot_captured_callback(cropped)

    @property
    def _screenshot_captured_callback(self):
        return getattr(self, '_screenshot_cb', None)

    @_screenshot_captured_callback.setter
    def _screenshot_captured_callback(self, cb):
        self._screenshot_cb = cb
