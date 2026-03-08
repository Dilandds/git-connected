

# Plan: Save Technical Overview in .ecto Format with Passcode Protection

## Overview

Extend the `.ecto` format to support Technical Overview data (metadata + 2D annotations + uploaded image) and add passcode-based edit protection. The passcode hash is stored **inside the .ecto file itself** (in `manifest.json`), so anyone with the file can view it, but only someone who knows the passcode can edit.

## Where Passcodes Are Stored

The passcode is **not stored in plain text anywhere**. Instead:
- A SHA-256 hash of the passcode is saved inside the `.ecto` file's `manifest.json` under `"passcode_hash"`.
- When someone opens the `.ecto` file and tries to edit, they are prompted for the passcode. The app hashes their input and compares it to the stored hash.
- No external server or database is needed — the hash travels with the file.

## Changes

### 1. Extend `core/ecto_format.py`

Add a new static method `export_technical` that bundles:
- `manifest.json` — includes `type: "technical_overview"`, `passcode_hash` (SHA-256), format version, metadata
- `document.{png|jpg|pdf}` — the uploaded image/PDF
- `annotations.json` — arrow annotations (id, target_x/y, color, text, label, image_paths)
- `metadata.json` — sidebar fields (property, title, manufacturers, dates, comments)
- `images/` — annotation-attached photos

Add `import_technical` method to extract and return all data, plus a `verify_passcode` check.

### 2. Add passcode dialog `ui/passcode_dialog.py` (new file)

- A small `QDialog` with a password field and OK/Cancel buttons.
- Two modes: **Set Passcode** (on export, with confirm field) and **Enter Passcode** (on edit attempt).
- Uses `hashlib.sha256` to hash input.

### 3. Update `ui/technical_sidebar.py`

- Add an **"Export .ecto"** button to the sidebar.
- On click: prompt for passcode via the dialog, gather `get_metadata()`, then call `EctoFormat.export_technical(...)`.

### 4. Update `ui/technical_overview.py`

- Add a `get_annotations_data()` method to serialize arrow annotations to dicts.
- Add a `load_from_ecto(metadata, annotations, image_path, passcode_hash)` method to restore state.
- When loaded from .ecto with a passcode hash, annotation mode and metadata editing are locked until the user enters the correct passcode.

### 5. Update `stl_viewer.py`

- In the file-open flow, detect `.ecto` files with `type: "technical_overview"` and route them to the Technical Overview workspace instead of the 3D viewer.
- Wire the export button signal from the technical sidebar.

## Security Note

SHA-256 hashing without a salt is sufficient for this use case (local file protection, not server authentication). The passcode prevents casual editing but is not meant to be cryptographically unbreakable — the file contents are still accessible in the ZIP.

