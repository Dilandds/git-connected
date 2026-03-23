

# Fix Build + Implement Multi-Strategy Segmentation & Surface Area

## Step 1: Create `lovable.toml`
Add a minimal config so Lovable stops complaining about missing dev commands. This is a Python desktop app — there's no web server to run.

```toml
[run]
dev = "echo 'Desktop Python app — run locally with: python main.py'"
```

## Step 2: Multi-Strategy `_segment_mesh()` in `viewer_widget_pygfx.py`

Replace the current `_segment_by_angle()` with a cascading segmenter that tries strategies **in order, stopping at the first success**:

1. **Facets (coplanar grouping)** — `trimesh.graph.facets()` groups coplanar adjacent faces. Merge adjacent facets whose average normals are within ~30°. Best for CAD models with flat plates + cylinders.

2. **Multi-threshold dihedral angle** — Try 15°, 10°, 5° in sequence. Catches tessellated curves where the default 30° was too coarse.

3. **Normal-based clustering** — `scipy.cluster.hierarchy.fcluster` on face normal vectors (angular distance, ~45° threshold), then split each cluster into spatially connected sub-regions via face adjacency.

**Success criteria**: 2–200 segments, each with ≥1% of total surface area. If a strategy doesn't meet this, try the next. If none work, return the mesh as a single part.

## Step 3: Surface Area Instead of Face Count

- Store `surface_area` per part using `trimesh.area` / `mesh.area_faces`
- Sort parts by surface area (largest first) in `get_parts_hierarchy()`
- Update `PartCard` in `ui/parts_panel.py` to display formatted area (e.g. "12.4 cm²") instead of "X faces"

## Files to Modify

| File | Change |
|---|---|
| `lovable.toml` | Create — fix build error |
| `viewer_widget_pygfx.py` | Replace `_segment_by_angle` with cascading `_segment_mesh`, add surface area tracking |
| `ui/parts_panel.py` | Display surface area instead of face count |

