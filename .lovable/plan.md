

# Mesh Segmentation for Connected Parts

## Problem
Currently, parts are only separated when they are **topologically disconnected** (no shared edges/vertices). For a model like the pipe with a flange, the entire object is one connected mesh — so it appears as a single part. The user wants to isolate semantically distinct regions (e.g. the flat flange vs. the curved pipe) even when they share edges.

## Solution: Dihedral Angle-Based Segmentation (Faceting)

Trimesh already has `trimesh.graph.facets()` and face adjacency data that can segment a connected mesh by **sharp edges** — where the angle between two adjacent face normals exceeds a threshold. This is exactly how CAD models naturally divide: a flat plate meets a curved pipe at a sharp crease.

### How It Works

```text
Before (connectivity-only split):
  Entire pipe+flange = 1 part

After (dihedral angle segmentation):
  Part 1: Flat flange plate     [sharp edge boundary]
  Part 2: Curved pipe body      [sharp edge boundary]  
  Part 3: Bolt holes (cylinders)
```

The algorithm:
1. For each connected component, compute **face adjacency** and **dihedral angles** between adjacent faces
2. Faces sharing an edge with dihedral angle < threshold (~30°) are grouped together (smooth region)
3. Each smooth region becomes a separate sub-part
4. Very tiny regions (< 4 faces) are merged into their largest neighbor to avoid noise

### Implementation Plan

**File: `viewer_widget_pygfx.py`**

1. Add `_segment_by_angle(trimesh_mesh, angle_threshold=30)` method:
   - Use `trimesh_mesh.face_adjacency` and `trimesh_mesh.face_adjacency_angles`
   - Build a graph where faces are nodes; edges connect faces whose dihedral angle is below the threshold (i.e. smooth continuation)
   - Find connected components of this graph → each component = one "segment"
   - Extract sub-meshes using `trimesh_mesh.submesh()` for each face group
   - Merge tiny segments (< 4 faces) into their nearest larger neighbor
   - Return list of `(name, trimesh)` tuples

2. Update `_split_reasonable_components()`:
   - After splitting by connectivity, apply `_segment_by_angle()` to each connected component that has enough faces (e.g. > 50 faces)
   - Small connected components skip angle segmentation (already isolated)

3. The existing hierarchy grouping (`get_parts_hierarchy()`) will then cluster these finer segments into meaningful groups automatically

**No changes needed to `ui/parts_panel.py` or `stl_viewer.py`** — the panel already handles the hierarchical data structure.

### Technical Details

- **trimesh API**: `mesh.face_adjacency` returns pairs of adjacent face indices; `mesh.face_adjacency_angles` returns the dihedral angle for each pair — both are built-in and fast
- **Graph library**: `networkx` (already a dependency for `trimesh.split()`) for connected components on the face adjacency graph
- **Angle threshold**: Default 30° (0.52 rad) — flat-to-curved transitions are typically 45-90°, so 30° captures most meaningful boundaries. Could be made adjustable later.
- **Safety**: If segmentation produces > 200 sub-parts from a single component, fall back to the unsegmented component (prevents over-fragmentation on organic meshes)
- **Performance**: Face adjacency is O(n_faces) via trimesh's half-edge structure; graph connected components is O(n_faces + n_edges)

### Dependencies
No new dependencies — uses `trimesh` (face_adjacency), `networkx` (connected components), and `numpy`, all already installed.

