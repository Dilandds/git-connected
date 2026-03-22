

# Hierarchical Parts Panel Enhancement

## Problem
Currently, `trimesh.split(only_watertight=False)` produces hundreds of tiny disconnected components (e.g. 950 parts) which are unusable — many are too small to visually locate when clicked, and the flat list is overwhelming.

## Solution: Two-Level Hierarchical Grouping

Instead of showing all 950 raw components in a flat list, we cluster nearby small parts into logical groups, then let the user expand a group to see (and toggle) its sub-parts.

```text
Parts Panel
├── ▸ Group 1 (Front Assembly)    👁  [312 faces]
│     ├── Sub-part 1              👁  [45 faces]
│     ├── Sub-part 2              👁  [120 faces]
│     └── ...
├── ▸ Group 2 (Rear Section)      👁  [580 faces]
└── ▸ Group 3 (Body)              👁  [2400 faces]  ← large single part, no children
```

## Implementation Plan

### 1. Smart Grouping Algorithm (viewer_widget_pygfx.py)

Add a `_build_part_hierarchy()` method that runs after splitting:

- **Large parts** (face count above a threshold, e.g. top 80th percentile or >500 faces) stay as standalone top-level entries
- **Small parts** are clustered by spatial proximity using their centroids — parts whose centroids are within a distance threshold get grouped together
- Use `scipy.spatial.KDTree` (already available via trimesh/scipy) or simple agglomerative clustering on centroids with a distance cutoff derived from the model's bounding box (e.g. 5-10% of bbox diagonal)
- Each group gets a name like "Group 1", "Group 2", etc., and stores references to its child part IDs
- Return a tree structure: `[{id, name, face_count, children: [{id, name, face_count}]}]`

### 2. Hierarchical Data in `get_parts_list()` (viewer_widget_pygfx.py)

- Add a new method `get_parts_hierarchy()` that returns the grouped tree structure
- Keep `get_parts_list()` for backward compatibility (flat list)
- The hierarchy data includes `children` arrays for expandable groups

### 3. Expandable Group Cards in Parts Panel (ui/parts_panel.py)

- Create a new `PartGroupCard(QFrame)` widget with:
  - Expand/collapse arrow (▸/▾)
  - Group name + total face count
  - Eye icon that toggles all children at once
  - Click to expand shows child `PartCard` items indented below
- Modify `PartsPanel.set_parts()` to accept hierarchical data
- Single-part groups (large standalone parts) render as regular `PartCard` without expand arrow
- "Isolate Selected" works on both groups (shows all children) and individual sub-parts

### 4. Visibility Propagation

- Toggling a group's eye icon → shows/hides all its child parts in the viewer
- Toggling an individual sub-part updates the group's icon state (full eye, partial indicator, or hidden)
- "Show All" / "Hide All" / "Invert" bulk actions work through groups

### 5. Improved Split Guard (viewer_widget_pygfx.py)

- Raise the component limit from 2000 to allow more splits (since we now group them)
- Remove the `median_faces < 10` early-return that currently collapses everything into one part — instead, let the grouping algorithm handle tiny fragments
- Keep the limit as a safety valve (e.g. 5000 max raw components)

## Files to Modify

| File | Changes |
|---|---|
| `viewer_widget_pygfx.py` | Add `_build_part_hierarchy()`, update `_split_reasonable_components` limits, add `get_parts_hierarchy()` method |
| `ui/parts_panel.py` | Add `PartGroupCard` widget, update `set_parts()` to handle hierarchy, add expand/collapse logic |
| `stl_viewer.py` | Update `_togglePartsMode` to call `get_parts_hierarchy()` instead of `get_parts_list()` |

## Technical Details

- Clustering uses scipy's `fcluster` with `distance` criterion on part centroids — linkage method: `ward` or `average`
- Distance threshold = `bbox_diagonal * 0.08` (tunable, covers ~8% of model size)
- Parts with >500 faces (or above 80th percentile) skip clustering and become top-level
- Maximum ~50 top-level groups for usability

