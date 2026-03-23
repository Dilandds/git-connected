

# Multi-Strategy Mesh Segmentation & Surface Area Display

## Implemented

### Multi-Strategy `_segment_mesh()` in `viewer_widget_pygfx.py`

Replaced the single dihedral angle approach with a cascading segmenter that tries 3 strategies in order, stopping at first success (2–200 segments, each ≥1% total surface area):

1. **Facets (coplanar grouping)** — `trimesh.facets` groups coplanar faces, then merges adjacent facets with normals within 30°
2. **Multi-threshold dihedral angle** — tries 15°, 10°, 5° progressively
3. **Normal-based clustering** — `scipy.cluster.hierarchy.fcluster` on face normals (cosine distance), then splits into spatially connected sub-regions

### Surface Area Display
- Parts panel now shows surface area (e.g. "12.4 cm²") instead of face counts
- Sorting and grouping thresholds use surface area instead of face count
- Groups display total surface area of children

### Files Modified
- `viewer_widget_pygfx.py` — `_segment_mesh()`, `get_parts_list()`, `get_parts_hierarchy()`
- `ui/parts_panel.py` — `PartCard` displays surface area
- `lovable.toml` — created for build config
