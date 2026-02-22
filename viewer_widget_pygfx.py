"""
Minimal 3D Viewer Widget using pygfx + wgpu for STL file visualization.
WebGPU-based (avoids OpenGL) - intended to fix Windows black screen.
Settings match PyVista viewer for consistent default view and rendering.
"""
import sys
import os
import logging
import numpy as np
from PyQt5.QtWidgets import QWidget, QStackedLayout, QGridLayout
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QEvent
from ui.drop_zone_overlay import DropZoneOverlay

logger = logging.getLogger(__name__)


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

        # Ruler/measurement mode state (matches viewer_widget.py interface)
        self.ruler_mode = False
        self.measurement_points = []
        self.measurement_actors = []  # pygfx objects for spheres, lines, arrows, labels
        self._ruler_unit = "mm"
        self._preview_line_obj = None
        self._ruler_event_filter_installed = False
        self._camera_before_ruler = None  # Store PerspectiveCamera to restore on exit
        self._controller_before_ruler = None  # Store controller state for zoom-only

        _debug_print("STLViewerWidget (pygfx): Basic init complete")

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initialized:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(100, self._init_pygfx)

    def resizeEvent(self, event):
        """Update camera aspect on resize so framing stays correct."""
        super().resizeEvent(event)
        if self._initialized and self._camera is not None and self._canvas is not None:
            try:
                cw, ch = self._canvas.get_logical_size() if hasattr(self._canvas, 'get_logical_size') else (self.width(), self.height())
                if cw > 0 and ch > 0 and hasattr(self._camera, 'aspect'):
                    self._camera.aspect = cw / ch
            except Exception:
                pass

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
            from pygfx.geometries import geometry_from_trimesh
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

            # Compute vertex normals for smooth shading
            try:
                mesh_tri.fix_normals()
            except Exception:
                pass

            # Ensure PyVista for MeshCalculator
            if pv_mesh is None:
                pv_mesh = _trimesh_to_pyvista(mesh_tri)
            if pv_mesh is None:
                raise ValueError("Could not convert mesh for dimensions/volume calculation")

            # PyVista-equivalent material (lightblue, soft specular)
            material = gfx.MeshPhongMaterial(
                color="#add8e6",
                specular="#333333",
                shininess=20,
            )
            geometry = geometry_from_trimesh(mesh_tri)
            mesh_obj = gfx.Mesh(geometry, material)
            self._mesh_obj = mesh_obj
            self._scene.add(self._mesh_obj)
            self.set_render_mode(self._render_mode)

            self.current_mesh = pv_mesh
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
                color="#add8e6", specular="#333333", shininess=20
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
        self._set_view(view_dir=(1, 0, 0), up=(0, 1, 0))

    def view_top_ortho(self):
        """Top orthographic view (ruler mode)."""
        self._set_view(view_dir=(0, 0, 1), up=(0, 1, 0))

    def view_left_ortho(self):
        """Left orthographic view (camera from -X)."""
        self._set_view(view_dir=(-1, 0, 0), up=(0, 1, 0))

    def view_right_ortho(self):
        """Right orthographic view (camera from +X)."""
        self._set_view(view_dir=(1, 0, 0), up=(0, 1, 0))

    def view_bottom_ortho(self):
        """Bottom orthographic view (camera from -Z)."""
        self._set_view(view_dir=(0, 0, -1), up=(0, 1, 0))

    def view_rear_ortho(self):
        """Rear orthographic view (camera from -Y)."""
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
        self.current_mesh = None
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
        """Qt event filter: when ruler_mode, handle click/move/wheel on canvas or its descendants."""
        if not self.ruler_mode or self._canvas is None:
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
            return self._ruler_event_filter_impl(obj, event)
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
        """Handle left click in ruler mode: unproject and add point."""
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
        nearest = self._get_nearest_mesh_point(world_pos)
        snapped = nearest if nearest != world_pos else self._maybe_snap_to_axis(self.measurement_points[0], world_pos)
        self._update_preview_line(self.measurement_points[0], snapped)

    def _get_nearest_mesh_point(self, world_pos, max_distance_ratio=0.02):
        """Return nearest mesh vertex to world_pos if within threshold, else world_pos."""
        if self.current_mesh is None:
            return world_pos
        try:
            pts = np.asarray(self.current_mesh.points)
            if pts is None or len(pts) == 0:
                return world_pos
            p = np.array(world_pos)
            b = self.current_mesh.bounds
            max_dim = max(b[1] - b[0], b[3] - b[2], b[5] - b[4])
            threshold = max_dim * max_distance_ratio
            dists = np.linalg.norm(pts - p, axis=1)
            idx = np.argmin(dists)
            if dists[idx] <= threshold:
                return tuple(pts[idx])
            return world_pos
        except Exception:
            return world_pos

    def _get_camera_view_axes(self):
        """Return (view_right, view_up) in world space for screen-space snapping."""
        cam = self._camera
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

    def _maybe_snap_to_axis(self, point1, point2, threshold_deg=15):
        """Snap to horizontal or vertical when line is close to that axis in screen space."""
        import math
        try:
            view_right, view_up = self._get_camera_view_axes()
            p1, p2 = np.array(point1), np.array(point2)
            delta = p2 - p1
            dx_screen = np.dot(delta, view_right)
            dy_screen = np.dot(delta, view_up)
            if abs(dx_screen) < 1e-12 and abs(dy_screen) < 1e-12:
                return point2
            angle_deg = math.degrees(math.atan2(abs(dy_screen), abs(dx_screen)))
            if angle_deg < threshold_deg or angle_deg > (90 - threshold_deg):
                return self._snap_to_axis(point1, point2)
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
        import pygfx as gfx
        sphere_radius = self._get_measurement_marker_size()
        try:
            geom = gfx.sphere_geometry(sphere_radius, 16, 12)
            mat = gfx.MeshPhongMaterial(color="#FF69B4", depth_test=False, depth_write=False)
            mat.render_queue = 4000  # overlay - always on top
            sphere = gfx.Mesh(geom, mat)
            sphere.local.position = point
            self._scene.add(sphere)
            self.measurement_actors.append(sphere)
        except Exception as e:
            logger.warning(f"_on_point_picked: Could not add marker: {e}")
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
            # Main line as Line (thin segment; thickness in pixels, screen-space)
            line_thickness = 2.5
            positions = np.array([p1, p2], dtype=np.float32)
            geom = gfx.Geometry(positions=positions)
            mat = gfx.LineMaterial(color="#000000", thickness=line_thickness, depth_test=False, depth_write=False)
            mat.render_queue = 4000
            line_obj = gfx.Line(geom, mat)
            self._scene.add(line_obj)
            self.measurement_actors.append(line_obj)
            # Cone tip is +Y in pygfx. Rotate so +Y aligns with target direction.
            import pylinalg as la
            def _cone_rotation_for_direction(d):
                """Rotation to align cone +Y with direction d."""
                up_y = np.array([0, 1, 0])
                d = d / (np.linalg.norm(d) + 1e-12)
                if np.abs(np.dot(d, up_y)) > 0.999:
                    return la.quat_from_axis_angle(np.array([1, 0, 0]), np.pi if d[1] < 0 else 0)
                axis = np.cross(up_y, d)
                axis = axis / (np.linalg.norm(axis) + 1e-12)
                angle = np.arccos(np.clip(np.dot(up_y, d), -1, 1))
                return la.quat_from_axis_angle(axis, angle)
            # Arrow at p1 (tip at p1, pointing from p2 toward p1, so cone +Y = -dir_unit)
            cone1_mat = gfx.MeshPhongMaterial(color="#000000", depth_test=False, depth_write=False)
            cone1_mat.render_queue = 4000
            cone1 = gfx.Mesh(gfx.cone_geometry(arrow_tip_radius, arrow_tip_length, 12), cone1_mat)
            cone1.local.position = p1 + dir_unit * (arrow_tip_length / 2)
            cone1.local.rotation = _cone_rotation_for_direction(-dir_unit)
            self._scene.add(cone1)
            self.measurement_actors.append(cone1)
            # Arrow at p2 (tip at p2, pointing from p1 toward p2, so cone +Y = dir_unit)
            cone2_mat = gfx.MeshPhongMaterial(color="#000000", depth_test=False, depth_write=False)
            cone2_mat.render_queue = 4000
            cone2 = gfx.Mesh(gfx.cone_geometry(arrow_tip_radius, arrow_tip_length, 12), cone2_mat)
            cone2.local.position = p2 - dir_unit * (arrow_tip_length / 2)
            cone2.local.rotation = _cone_rotation_for_direction(dir_unit)
            self._scene.add(cone2)
            self.measurement_actors.append(cone2)
            # Label at midpoint
            midpoint = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, (p1[2] + p2[2]) / 2)
            unit = getattr(self, '_ruler_unit', 'mm')
            conversion = {"mm": 1.0, "cm": 0.1, "m": 0.001, "inch": 1.0 / 25.4, "ft": 1.0 / 304.8}
            unit_labels = {"mm": "mm", "cm": "cm", "m": "m", "inch": "in", "ft": "ft"}
            converted = distance * conversion.get(unit, 1.0)
            suffix = unit_labels.get(unit, "mm")
            label_text = f"{converted:.4f} {suffix}" if converted < 1 else (f"{converted:.2f} {suffix}" if converted < 100 else f"{converted:.1f} {suffix}")
            lbl_mat = gfx.TextMaterial(color="#000000")
            lbl_mat.depth_test = False
            lbl_mat.depth_write = False
            lbl_mat.render_queue = 4000
            lbl = gfx.Text(text=label_text, material=lbl_mat, font_size=12, anchor="middle-center", screen_space=False)
            lbl.local.position = midpoint
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
            mat.render_queue = 4000
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
        # Switch to orthographic camera
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
            center, dist = self._get_view_center_and_distance()
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
            ortho.show_object(self._mesh_obj, view_dir=tuple(np.array(center) - np.array(self._camera.local.position)), scale=1.8, up=(0, 1, 0))
            self._camera = ortho
            self._controller.camera = ortho
            if self._canvas:
                self._canvas.request_draw()
            logger.info("_switch_to_orthographic_camera: Switched to orthographic")
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
