"""
DXF file loader for converting DXF files to PyVista meshes.
Uses ezdxf library for parsing DXF entities.
Supports both 3D entities (3DFACE, MESH, POLYFACE) and 2D entities (LINE, ARC, CIRCLE, LWPOLYLINE).
"""
import logging
import numpy as np
import pyvista as pv

logger = logging.getLogger(__name__)


class DxfLoader:
    """Handles loading DXF files and converting them to PyVista meshes."""

    @staticmethod
    def _extract_2d_geometry(msp):
        """
        Extract 2D entities from DXF modelspace.
        Supports: LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE, ELLIPSE, SPLINE, TEXT, MTEXT, and others.
        
        Returns:
            list: Points extracted from 2D entities (2D points as [x, y, z=0])
        """
        points_2d = []
        
        try:
            # Extract LINE entities
            try:
                for line in msp.query("LINE"):
                    start = line.dxf.start
                    end = line.dxf.end
                    points_2d.append([start[0], start[1], 0.0])
                    points_2d.append([end[0], end[1], 0.0])
            except Exception as e:
                logger.debug(f"DxfLoader: Could not extract LINE entities: {e}")
            
            # Extract LWPOLYLINE entities
            try:
                for lwpoly in msp.query("LWPOLYLINE"):
                    for point in lwpoly.get_points():
                        points_2d.append([point[0], point[1], 0.0])
            except Exception as e:
                logger.debug(f"DxfLoader: Could not extract LWPOLYLINE entities: {e}")
            
            # Extract POLYLINE entities (older format)
            try:
                for poly in msp.query("POLYLINE"):
                    for point in poly.get_points():
                        pt = point[:2] if len(point) >= 2 else point
                        points_2d.append([pt[0], pt[1], 0.0])
            except Exception as e:
                logger.debug(f"DxfLoader: Could not extract POLYLINE entities: {e}")
            
            # Extract ARC entities (approximate with line segments)
            try:
                for arc in msp.query("ARC"):
                    center = arc.dxf.center
                    radius = arc.dxf.radius
                    start_angle = arc.dxf.start_angle
                    end_angle = arc.dxf.end_angle
                    
                    # Create arc segments
                    segments = 16
                    angles = np.linspace(np.radians(start_angle), np.radians(end_angle), segments)
                    for angle in angles:
                        x = center[0] + radius * np.cos(angle)
                        y = center[1] + radius * np.sin(angle)
                        points_2d.append([x, y, 0.0])
            except Exception as e:
                logger.debug(f"DxfLoader: Could not extract ARC entities: {e}")
            
            # Extract CIRCLE entities (approximate with line segments)
            try:
                for circle in msp.query("CIRCLE"):
                    center = circle.dxf.center
                    radius = circle.dxf.radius
                    
                    # Create circle segments
                    segments = 32
                    angles = np.linspace(0, 2 * np.pi, segments)
                    for angle in angles:
                        x = center[0] + radius * np.cos(angle)
                        y = center[1] + radius * np.sin(angle)
                        points_2d.append([x, y, 0.0])
            except Exception as e:
                logger.debug(f"DxfLoader: Could not extract CIRCLE entities: {e}")
            
            # Extract ELLIPSE entities (approximate with line segments)
            try:
                for ellipse in msp.query("ELLIPSE"):
                    center = ellipse.dxf.center
                    major_axis = np.array(ellipse.dxf.major_axis)
                    minor_ratio = ellipse.dxf.ratio  # Minor axis / Major axis
                    
                    # Create ellipse segments
                    segments = 32
                    angles = np.linspace(0, 2 * np.pi, segments)
                    major_length = np.linalg.norm(major_axis)
                    
                    for angle in angles:
                        # Point on unit circle
                        x_circle = np.cos(angle)
                        y_circle = np.sin(angle) * minor_ratio
                        
                        # Rotate by major axis angle
                        if major_length > 0:
                            major_unit = major_axis / major_length
                            perpendicular = np.array([-major_unit[1], major_unit[0]])
                            
                            x = center[0] + x_circle * major_length * major_unit[0] + y_circle * major_length * perpendicular[0]
                            y = center[1] + x_circle * major_length * major_unit[1] + y_circle * major_length * perpendicular[1]
                            points_2d.append([x, y, 0.0])
            except Exception as e:
                logger.debug(f"DxfLoader: Could not extract ELLIPSE entities: {e}")
            
            # Extract SPLINE entities (approximate with line segments)
            try:
                for spline in msp.query("SPLINE"):
                    # Get spline as approximated points
                    try:
                        control_points = list(spline.control_points)
                        if control_points:
                            for pt in control_points:
                                points_2d.append([pt[0], pt[1], 0.0])
                    except:
                        # Try to get fit points as fallback
                        try:
                            fit_points = list(spline.fit_points)
                            if fit_points:
                                for pt in fit_points:
                                    points_2d.append([pt[0], pt[1], 0.0])
                        except:
                            pass
            except Exception as e:
                logger.debug(f"DxfLoader: Could not extract SPLINE entities: {e}")
            
            # Extract TEXT and MTEXT entities (use insertion point as reference)
            try:
                for text in msp.query("TEXT"):
                    insert = text.dxf.insert
                    points_2d.append([insert[0], insert[1], 0.0])
            except Exception as e:
                logger.debug(f"DxfLoader: Could not extract TEXT entities: {e}")
            
            try:
                for mtext in msp.query("MTEXT"):
                    insert = mtext.dxf.insert
                    points_2d.append([insert[0], insert[1], 0.0])
            except Exception as e:
                logger.debug(f"DxfLoader: Could not extract MTEXT entities: {e}")
            
            # Extract POINT entities
            try:
                for point_ent in msp.query("POINT"):
                    dxf_point = point_ent.dxf.location
                    points_2d.append([dxf_point[0], dxf_point[1], 0.0])
            except Exception as e:
                logger.debug(f"DxfLoader: Could not extract POINT entities: {e}")
        
        except Exception as e:
            logger.warning(f"DxfLoader: Failed to extract 2D geometry: {e}")
        
        return points_2d

    @staticmethod
    def _extrude_2d_to_mesh(points_2d, extrusion_height=0.1):
        """
        Create an extruded mesh from 2D points.
        
        Args:
            points_2d (list): List of [x, y, z] points (z should be 0)
            extrusion_height (float): Height of extrusion (default 0.1)
        
        Returns:
            tuple: (points_array, faces_array) for PyVista mesh
        """
        if not points_2d:
            return None, None
        
        points_2d = np.array(points_2d, dtype=np.float64)
        
        # Create bottom and top layers
        bottom_points = points_2d.copy()
        top_points = points_2d.copy()
        top_points[:, 2] = extrusion_height
        
        # Combine points: bottom first, then top
        all_points = np.vstack([bottom_points, top_points])
        
        # Create faces connecting bottom and top
        n_points = len(points_2d)
        faces = []
        
        # Create simple quad faces (as two triangles) between bottom and top
        # Connect each segment on bottom to corresponding segment on top
        for i in range(n_points - 1):
            bottom_idx_0 = i
            bottom_idx_1 = i + 1
            top_idx_0 = n_points + i
            top_idx_1 = n_points + i + 1
            
            # Triangle 1: bottom_0, bottom_1, top_0
            faces.append([3, bottom_idx_0, bottom_idx_1, top_idx_0])
            # Triangle 2: bottom_1, top_1, top_0
            faces.append([3, bottom_idx_1, top_idx_1, top_idx_0])
        
        # Add bottom face (all bottom points in order)
        if n_points >= 3:
            bottom_face = [n_points] + list(range(n_points))
            faces.append(bottom_face)
        
        # Add top face (all top points in reverse order for correct normal)
        if n_points >= 3:
            top_face = [n_points] + list(range(n_points + n_points - 1, n_points - 1, -1))
            faces.append(top_face)
        
        # Flatten faces array to VTK format
        faces_array = np.hstack(faces).astype(np.int32)
        
        return all_points, faces_array

    @staticmethod
    def load_dxf(file_path):
        """
        Load DXF file and convert 3D entities to a PyVista mesh.
        If no 3D geometry is found, extract and extrude 2D geometry.

        Args:
            file_path (str): Path to the DXF file

        Returns:
            tuple: (pyvista.PolyData, is_2d) where is_2d is True for 2D geometry

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file cannot be loaded or contains no geometry
        """
        import os

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"DXF file not found: {file_path}")

        logger.info(f"DxfLoader: Loading DXF file: {file_path}")

        try:
            import ezdxf
        except ImportError:
            raise ValueError(
                "ezdxf library is required for DXF support. Install with: pip install ezdxf"
            )

        try:
            doc = ezdxf.readfile(file_path)
        except Exception as e:
            raise ValueError(f"Failed to read DXF file: {e}")

        msp = doc.modelspace()

        all_points = []
        all_faces = []
        point_offset = 0

        # 1. Extract 3DFACE entities
        for face in msp.query("3DFACE"):
            pts = [face.dxf.vtx0, face.dxf.vtx1, face.dxf.vtx2, face.dxf.vtx3]
            # Convert Vec3 to list
            pts = [[p[0], p[1], p[2]] for p in pts]

            # Check if it's a triangle (vtx2 == vtx3) or quad
            idx = point_offset
            all_points.extend(pts[:3])
            all_faces.append([3, idx, idx + 1, idx + 2])
            point_offset += 3

            # If quad (4th vertex differs from 3rd)
            if pts[2] != pts[3]:
                all_points.append(pts[3])
                all_faces.append([3, idx, idx + 2, idx + 3])
                point_offset += 1

        # 2. Extract MESH entities
        for mesh_entity in msp.query("MESH"):
            try:
                vertices = list(mesh_entity.vertices)
                faces_data = list(mesh_entity.faces)

                if not vertices or not faces_data:
                    continue

                v_pts = [[v[0], v[1], v[2]] for v in vertices]
                idx_base = point_offset
                all_points.extend(v_pts)

                for face_indices in faces_data:
                    fi = list(face_indices)
                    if len(fi) == 3:
                        all_faces.append([3, fi[0] + idx_base, fi[1] + idx_base, fi[2] + idx_base])
                    elif len(fi) >= 4:
                        # Triangulate quads/polygons as fan
                        for i in range(1, len(fi) - 1):
                            all_faces.append([3, fi[0] + idx_base, fi[i] + idx_base, fi[i + 1] + idx_base])

                point_offset += len(v_pts)
            except Exception as e:
                logger.warning(f"DxfLoader: Failed to process MESH entity: {e}")

        # 3. Extract POLYLINE entities (POLYFACE meshes)
        for polyline in msp.query("POLYLINE"):
            try:
                if not polyline.is_poly_face_mesh:
                    continue

                vertices = []
                face_indices_list = []

                for vertex in polyline.vertices:
                    if vertex.is_face_record:
                        # Face record: vtx0..vtx3 are 1-based indices
                        fi = []
                        for attr in ['vtx0', 'vtx1', 'vtx2', 'vtx3']:
                            val = getattr(vertex.dxf, attr, 0)
                            if val != 0:
                                fi.append(abs(val) - 1)  # Convert 1-based to 0-based
                        if len(fi) >= 3:
                            face_indices_list.append(fi)
                    else:
                        loc = vertex.dxf.location
                        vertices.append([loc[0], loc[1], loc[2]])

                if not vertices or not face_indices_list:
                    continue

                idx_base = point_offset
                all_points.extend(vertices)

                for fi in face_indices_list:
                    if len(fi) == 3:
                        all_faces.append([3, fi[0] + idx_base, fi[1] + idx_base, fi[2] + idx_base])
                    elif len(fi) >= 4:
                        for i in range(1, len(fi) - 1):
                            all_faces.append([3, fi[0] + idx_base, fi[i] + idx_base, fi[i + 1] + idx_base])

                point_offset += len(vertices)
            except Exception as e:
                logger.warning(f"DxfLoader: Failed to process POLYLINE entity: {e}")

        # 4. Extract LINE entities as degenerate geometry (for wireframe DXFs)
        if len(all_points) == 0:
            logger.info("DxfLoader: No solid geometry found, trying LINE/LWPOLYLINE entities...")
            # Try trimesh as fallback for complex DXF files
            try:
                import trimesh
                scene = trimesh.load(file_path)
                if isinstance(scene, trimesh.Scene):
                    meshes = [g for g in scene.geometry.values() if isinstance(g, trimesh.Trimesh)]
                    if meshes:
                        combined = trimesh.util.concatenate(meshes)
                        points_array = np.array(combined.vertices, dtype=np.float64)
                        faces_list = np.column_stack([
                            np.full(len(combined.faces), 3, dtype=np.int32),
                            combined.faces.astype(np.int32)
                        ])
                        pv_mesh = pv.PolyData(points_array, faces_list)
                        logger.info(f"DxfLoader: Loaded via trimesh. Points: {pv_mesh.n_points}")
                        return pv_mesh
                elif isinstance(scene, trimesh.Trimesh) and len(scene.vertices) > 0:
                    points_array = np.array(scene.vertices, dtype=np.float64)
                    faces_list = np.column_stack([
                        np.full(len(scene.faces), 3, dtype=np.int32),
                        scene.faces.astype(np.int32)
                    ])
                    pv_mesh = pv.PolyData(points_array, faces_list)
                    logger.info(f"DxfLoader: Loaded via trimesh. Points: {pv_mesh.n_points}")
                    return pv_mesh
            except Exception as e:
                logger.warning(f"DxfLoader: trimesh fallback failed: {e}")
        
        # 4b. If still no 3D geometry, try extracting 2D entities
        if len(all_points) == 0:
            logger.info("DxfLoader: No 3D geometry found. Attempting to extract and extrude 2D entities...")
            points_2d = DxfLoader._extract_2d_geometry(msp)
            
            if points_2d:
                logger.info(f"DxfLoader: Found {len(points_2d)} 2D points. Creating extruded mesh...")
                all_points_ext, all_faces_ext = DxfLoader._extrude_2d_to_mesh(points_2d, extrusion_height=0.1)
                
                if all_points_ext is not None and all_faces_ext is not None:
                    pv_mesh = pv.PolyData(all_points_ext, all_faces_ext)
                    logger.info(
                        f"DxfLoader: Successfully created 2D extruded mesh. Points: {pv_mesh.n_points}, Faces: {pv_mesh.n_cells}"
                    )
                    return pv_mesh, True
        
        if len(all_points) == 0:
            raise ValueError(
                f"DXF file contains no 3D geometry and no extractable 2D entities: {file_path}\n"
                "The file may be empty or contain only unsupported entity types.\n"
                "DXF import supports: 3DFACE, MESH, POLYFACE, LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE, "
                "ELLIPSE, SPLINE, TEXT, MTEXT, and POINT entities."
            )

        # Build PyVista mesh from 3D geometry
        points_array = np.array(all_points, dtype=np.float64)
        faces_array = np.hstack(all_faces).astype(np.int32)

        pv_mesh = pv.PolyData(points_array, faces_array)

        logger.info(
            f"DxfLoader: Successfully loaded DXF (3D geometry). Points: {pv_mesh.n_points}, Faces: {pv_mesh.n_cells}"
        )
        return pv_mesh, False
