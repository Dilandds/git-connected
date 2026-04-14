"""
ECTO Format Handler - Custom .ecto file format for ECTOFORM.

The .ecto format is a ZIP-based bundle containing:
- manifest.json: Metadata and format version
- model.{format}: The 3D geometry (STL, OBJ, etc.)
- annotations.json: Annotation data with reader_mode flag
- images/: Folder with attached photos
"""
import json
import logging
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

# Format version for .ecto files
ECTO_FORMAT_VERSION = "1.0"


class EctoFormat:
    """Handler for .ecto file format - a single-file bundle for sharing annotated 3D models."""
    
    # Supported model formats
    SUPPORTED_FORMATS = ['stl', 'obj']
    
    @staticmethod
    def is_ecto_file(file_path: str) -> bool:
        """Check if a file is a valid .ecto format.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if the file is a valid .ecto bundle
        """
        if not file_path.lower().endswith('.ecto'):
            return False
        
        if not os.path.exists(file_path):
            return False
        
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                # Check for required manifest.json
                if 'manifest.json' not in zf.namelist():
                    return False
                
                # Validate manifest
                manifest_data = zf.read('manifest.json')
                manifest = json.loads(manifest_data.decode('utf-8'))
                
                # Check for required fields
                if 'format_version' not in manifest or 'model_file' not in manifest:
                    return False
                
                # Verify the model file exists in the archive
                if manifest['model_file'] not in zf.namelist():
                    return False
                
                return True
        except (zipfile.BadZipFile, json.JSONDecodeError, KeyError) as e:
            logger.debug(f"is_ecto_file: Not a valid .ecto file: {e}")
            return False
    
    @staticmethod
    def export(mesh, annotations: List[dict], output_path: str,
               source_format: str = 'stl', original_filename: str = None,
               drawings: Optional[List[dict]] = None,
               texture_data: Optional[Dict[str, Any]] = None) -> Tuple[bool, str, Optional[str]]:
        """Create an .ecto bundle containing the model, annotations, images, and drawings.
        
        Args:
            mesh: PyVista mesh object to export
            annotations: List of annotation dictionaries
            output_path: Path for the output .ecto file
            source_format: Format to save the model as ('stl' or 'obj')
            original_filename: Original filename for metadata
            drawings: Optional list of draw strokes [{points: [[x,y,z],...], color: '#RRGGBB'}]
            
        Returns:
            tuple: (success: bool, message_or_path: str, creator_token: str|None)
        """
        if mesh is None:
            return False, "No mesh provided", None
        
        creator_token = str(uuid.uuid4())
        
        # Ensure output has .ecto extension
        if not output_path.lower().endswith('.ecto'):
            output_path += '.ecto'
        
        # Validate source format
        source_format = source_format.lower()
        if source_format not in EctoFormat.SUPPORTED_FORMATS:
            source_format = 'stl'
        
        temp_dir = None
        try:
            # Create temp directory for building the bundle
            temp_dir = tempfile.mkdtemp(prefix='ecto_export_')
            logger.info(f"export: Created temp directory: {temp_dir}")
            
            # 1. Save the mesh
            model_filename = f"model.{source_format}"
            model_path = os.path.join(temp_dir, model_filename)
            mesh.save(model_path)
            logger.info(f"export: Saved mesh to {model_path}")
            
            # 2. Process annotations and copy images
            images_dir = os.path.join(temp_dir, 'images')
            processed_annotations = []
            has_images = False
            
            for ann in annotations:
                ann_copy = ann.copy()
                new_image_paths = []
                
                for i, img_path in enumerate(ann.get('image_paths', [])):
                    if os.path.exists(img_path):
                        # Create images directory if needed
                        if not os.path.exists(images_dir):
                            os.makedirs(images_dir)
                            has_images = True
                        
                        # Get original extension
                        _, ext = os.path.splitext(img_path)
                        # Create new filename within bundle
                        new_filename = f"annotation_{ann['id']}_photo_{i+1}{ext}"
                        new_path = os.path.join(images_dir, new_filename)
                        
                        # Copy image
                        try:
                            shutil.copy2(img_path, new_path)
                            # Store relative path within bundle
                            new_image_paths.append(f"images/{new_filename}")
                            logger.info(f"export: Copied image to {new_path}")
                        except Exception as e:
                            logger.warning(f"export: Failed to copy image {img_path}: {e}")
                    else:
                        # Keep original path if file doesn't exist
                        new_image_paths.append(img_path)
                
                ann_copy['image_paths'] = new_image_paths
                processed_annotations.append(ann_copy)
            
            # 3. Create annotations.json with reader_mode=True
            annotations_data = {
                'version': '1.0',
                'reader_mode': True,  # Always true for shared files
                'annotations': processed_annotations
            }
            annotations_path = os.path.join(temp_dir, 'annotations.json')
            with open(annotations_path, 'w', encoding='utf-8') as f:
                json.dump(annotations_data, f, indent=2, ensure_ascii=False)
            logger.info(f"export: Created annotations.json with {len(processed_annotations)} annotations")
            
            # 4. Create drawings.json if drawings provided
            drawings_data = drawings or []
            if drawings_data:
                drawings_path = os.path.join(temp_dir, 'drawings.json')
                with open(drawings_path, 'w', encoding='utf-8') as f:
                    json.dump({'version': '1.0', 'strokes': drawings_data}, f, indent=2, ensure_ascii=False)
                logger.info(f"export: Created drawings.json with {len(drawings_data)} strokes")

            # 5. Bundle texture/material data if present
            texture_json_data = None
            has_texture = False
            if texture_data:
                texture_json_data = dict(texture_data)
                # Copy texture image files into bundle
                textures_dir = os.path.join(temp_dir, 'textures')
                has_texture = True
                # Handle main albedo_map_path
                albedo_path = texture_data.get('albedo_map_path', '')
                if albedo_path and os.path.exists(albedo_path):
                    os.makedirs(textures_dir, exist_ok=True)
                    _, ext = os.path.splitext(albedo_path)
                    tex_filename = f"texture_albedo{ext}"
                    shutil.copy2(albedo_path, os.path.join(textures_dir, tex_filename))
                    texture_json_data['albedo_map_path'] = f"textures/{tex_filename}"
                    has_texture = True
                    logger.info(f"export: Copied texture image to bundle: {tex_filename}")
                # Handle per-part textures
                for pt in texture_json_data.get('parts_textures', []):
                    pt_path = pt.get('albedo_map_path', '')
                    if pt_path and os.path.exists(pt_path):
                        os.makedirs(textures_dir, exist_ok=True)
                        _, ext = os.path.splitext(pt_path)
                        pt_filename = f"texture_part_{pt.get('part_id', 0)}{ext}"
                        shutil.copy2(pt_path, os.path.join(textures_dir, pt_filename))
                        pt['albedo_map_path'] = f"textures/{pt_filename}"
                        has_texture = True
                if texture_json_data:
                    tex_json_path = os.path.join(temp_dir, 'texture.json')
                    with open(tex_json_path, 'w', encoding='utf-8') as f:
                        json.dump({'version': '1.0', 'material': texture_json_data}, f, indent=2, ensure_ascii=False)
                    logger.info(f"export: Created texture.json (has_texture_image={has_texture})")

            # 6. Create manifest.json (creator_token identifies sender for reopen-as-editor)
            from core.edition import is_education, WATERMARK_TEXT
            manifest = {
                'format_version': ECTO_FORMAT_VERSION,
                'created_by': 'ECTOFORM',
                'created_at': datetime.now().isoformat(),
                'model_file': model_filename,
                'model_format': source_format,
                'original_filename': original_filename or 'unknown',
                'reader_mode': True,
                'creator_token': creator_token,
                'annotation_count': len(processed_annotations),
                'has_images': has_images,
                'drawing_count': len(drawings_data),
                'has_texture': has_texture,
            }
            if is_education():
                manifest['edition'] = 'education'
                manifest['watermark'] = WATERMARK_TEXT
            manifest_path = os.path.join(temp_dir, 'manifest.json')
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2)
            logger.info(f"export: Created manifest.json")

            # 7. Create the .ecto ZIP file
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Add manifest
                zf.write(manifest_path, 'manifest.json')
                # Add model
                zf.write(model_path, model_filename)
                # Add annotations
                zf.write(annotations_path, 'annotations.json')
                # Add drawings if any
                if drawings_data:
                    zf.write(drawings_path, 'drawings.json')
                # Add images if any
                if has_images and os.path.exists(images_dir):
                    for img_file in os.listdir(images_dir):
                        img_path = os.path.join(images_dir, img_file)
                        zf.write(img_path, f'images/{img_file}')
                # Add texture data if any
                if texture_json_data:
                    tex_json_path = os.path.join(temp_dir, 'texture.json')
                    zf.write(tex_json_path, 'texture.json')
                    if os.path.exists(textures_dir):
                        for tex_file in os.listdir(textures_dir):
                            tex_path = os.path.join(textures_dir, tex_file)
                            zf.write(tex_path, f'textures/{tex_file}')
            
            logger.info(f"export: Created .ecto bundle at {output_path}")
            return True, output_path, creator_token
            
        except Exception as e:
            logger.error(f"export: Failed to create .ecto bundle: {e}", exc_info=True)
            return False, str(e), None
        
        finally:
            # Cleanup temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    logger.info(f"export: Cleaned up temp directory")
                except Exception as e:
                    logger.warning(f"export: Failed to cleanup temp directory: {e}")
    
    @staticmethod
    def import_ecto(ecto_path: str):
        """Open an .ecto bundle and extract its contents.
        
        Returns:
            tuple: (model_path, annotations, reader_mode, temp_dir_or_error, drawings, texture_data)
                   On failure: (None, None, False, error_message, None, None)
        """
        if not os.path.exists(ecto_path):
            return None, None, False, f"File not found: {ecto_path}", None, None
        
        if not EctoFormat.is_ecto_file(ecto_path):
            return None, None, False, "Invalid .ecto file format", None, None
        
        temp_dir = None
        try:
            # Create temp directory for extraction
            temp_dir = tempfile.mkdtemp(prefix='ecto_import_')
            logger.info(f"import_ecto: Extracting to temp directory: {temp_dir}")
            
            # Extract the archive
            with zipfile.ZipFile(ecto_path, 'r') as zf:
                zf.extractall(temp_dir)
            
            # Read manifest
            manifest_path = os.path.join(temp_dir, 'manifest.json')
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            
            # Get model path
            model_filename = manifest.get('model_file', 'model.stl')
            model_path = os.path.join(temp_dir, model_filename)
            
            if not os.path.exists(model_path):
                return None, None, False, f"Model file not found in bundle: {model_filename}", None, None
            
            # Sender vs reader: if creator_token is in local registry, this machine created the file
            creator_token = manifest.get('creator_token')
            if creator_token:
                try:
                    from core.creator_registry import is_creator
                    if is_creator(creator_token):
                        reader_mode = False  # Sender mode (editor)
                        logger.info("import_ecto: Creator token matches - opening in sender/editor mode")
                    else:
                        reader_mode = True  # Reader mode (view-only)
                except ImportError:
                    reader_mode = True
            else:
                reader_mode = True  # Old ECTO files: default to reader mode
            
            # Read annotations
            annotations = None
            annotations_path = os.path.join(temp_dir, 'annotations.json')
            
            if os.path.exists(annotations_path):
                with open(annotations_path, 'r', encoding='utf-8') as f:
                    annotations_data = json.load(f)
                
                annotations = annotations_data.get('annotations', [])
                
                # Resolve relative image paths to absolute paths in temp dir
                for ann in annotations:
                    resolved_paths = []
                    for img_path in ann.get('image_paths', []):
                        if not os.path.isabs(img_path):
                            full_path = os.path.join(temp_dir, img_path)
                            if os.path.exists(full_path):
                                resolved_paths.append(full_path)
                            else:
                                resolved_paths.append(img_path)
                        else:
                            resolved_paths.append(img_path)
                    ann['image_paths'] = resolved_paths

            # Read drawings (optional - for 3D model drawings on surface)
            drawings = []
            drawings_path = os.path.join(temp_dir, 'drawings.json')
            if os.path.exists(drawings_path):
                try:
                    with open(drawings_path, 'r', encoding='utf-8') as f:
                        drawings_data = json.load(f)
                    drawings = drawings_data.get('strokes', [])
                    logger.info(f"import_ecto: Loaded {len(drawings)} drawing strokes")
                except Exception as e:
                    logger.warning(f"import_ecto: Could not read drawings.json: {e}")

            # Read texture/material data (optional)
            texture_data = None
            texture_json_path = os.path.join(temp_dir, 'texture.json')
            if os.path.exists(texture_json_path):
                try:
                    with open(texture_json_path, 'r', encoding='utf-8') as f:
                        tex_json = json.load(f)
                    texture_data = tex_json.get('material', {})
                    # Resolve relative texture paths to absolute paths in temp dir
                    albedo_rel = texture_data.get('albedo_map_path', '')
                    if albedo_rel and not os.path.isabs(albedo_rel):
                        abs_path = os.path.join(temp_dir, albedo_rel)
                        if os.path.exists(abs_path):
                            texture_data['albedo_map_path'] = abs_path
                    # Resolve per-part texture paths
                    for pt in texture_data.get('parts_textures', []):
                        pt_rel = pt.get('albedo_map_path', '')
                        if pt_rel and not os.path.isabs(pt_rel):
                            abs_path = os.path.join(temp_dir, pt_rel)
                            if os.path.exists(abs_path):
                                pt['albedo_map_path'] = abs_path
                    logger.info(f"import_ecto: Loaded texture data (image_file={texture_data.get('image_file', False)})")
                except Exception as e:
                    logger.warning(f"import_ecto: Could not read texture.json: {e}")
            
            logger.info(f"import_ecto: Successfully extracted. Model: {model_path}, "
                       f"Annotations: {len(annotations) if annotations else 0}, "
                       f"Drawings: {len(drawings)}, Reader mode: {reader_mode}, "
                       f"Has texture: {texture_data is not None}")
            
            return model_path, annotations, reader_mode, temp_dir, drawings, texture_data
            
        except Exception as e:
            logger.error(f"import_ecto: Failed to import .ecto file: {e}", exc_info=True)
            # Cleanup on failure
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
            return None, None, False, str(e), None, None
    
    @staticmethod
    def get_manifest(ecto_path: str) -> Optional[Dict[str, Any]]:
        """Read the manifest from an .ecto file without full extraction.
        
        Args:
            ecto_path: Path to the .ecto file
            
        Returns:
            Manifest dictionary or None on failure
        """
        try:
            with zipfile.ZipFile(ecto_path, 'r') as zf:
                manifest_data = zf.read('manifest.json')
                return json.loads(manifest_data.decode('utf-8'))
        except Exception as e:
            logger.error(f"get_manifest: Failed to read manifest: {e}")
            return None
    
    @staticmethod
    def cleanup_temp_dir(temp_dir: str) -> bool:
        """Clean up a temporary directory created during import."""
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"cleanup_temp_dir: Removed {temp_dir}")
                return True
            except Exception as e:
                logger.warning(f"cleanup_temp_dir: Failed to remove {temp_dir}: {e}")
                return False
        return True

    # ======================== Technical Overview ========================

    @staticmethod
    def export_technical(
        document_path: str,
        annotations: List[dict],
        metadata: dict,
        output_path: str,
        passcode_hash: str = None,
    ) -> Tuple[bool, str]:
        """Create a technical-overview .ecto bundle.

        Args:
            document_path: Path to the uploaded image/PDF.
            annotations: List of annotation dicts (serialised ArrowAnnotation).
            metadata: Sidebar metadata dict.
            output_path: Destination .ecto path.
            passcode_hash: Optional SHA-256 hash of the edit passcode.

        Returns:
            (success, message_or_path)
        """
        if not document_path or not os.path.exists(document_path):
            return False, "No document file provided"

        if not output_path.lower().endswith('.ecto'):
            output_path += '.ecto'

        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix='ecto_tech_export_')

            # Copy document
            _, doc_ext = os.path.splitext(document_path)
            doc_filename = f"document{doc_ext}"
            doc_dest = os.path.join(temp_dir, doc_filename)
            shutil.copy2(document_path, doc_dest)

            # Process annotation images
            images_dir = os.path.join(temp_dir, 'images')
            has_images = False
            processed = []
            for ann in annotations:
                ac = dict(ann)
                new_paths = []
                for i, img_path in enumerate(ac.get('image_paths', [])):
                    if os.path.exists(img_path):
                        if not os.path.exists(images_dir):
                            os.makedirs(images_dir)
                            has_images = True
                        _, ext = os.path.splitext(img_path)
                        fname = f"ann_{ac.get('id', 0)}_img_{i}{ext}"
                        shutil.copy2(img_path, os.path.join(images_dir, fname))
                        new_paths.append(f"images/{fname}")
                    else:
                        new_paths.append(img_path)
                ac['image_paths'] = new_paths
                processed.append(ac)

            # annotations.json
            ann_path = os.path.join(temp_dir, 'annotations.json')
            with open(ann_path, 'w', encoding='utf-8') as f:
                json.dump({'version': '1.0', 'annotations': processed}, f, indent=2, ensure_ascii=False)

            # metadata.json
            meta_path = os.path.join(temp_dir, 'metadata.json')
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            # manifest.json
            from core.edition import is_education, WATERMARK_TEXT
            manifest = {
                'format_version': ECTO_FORMAT_VERSION,
                'type': 'technical_overview',
                'created_by': 'ECTOFORM',
                'created_at': datetime.now().isoformat(),
                'document_file': doc_filename,
                'annotation_count': len(processed),
                'has_images': has_images,
            }
            if passcode_hash:
                manifest['passcode_hash'] = passcode_hash
            if is_education():
                manifest['edition'] = 'education'
                manifest['watermark'] = WATERMARK_TEXT
            manifest_path = os.path.join(temp_dir, 'manifest.json')
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2)

            # ZIP
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(manifest_path, 'manifest.json')
                zf.write(doc_dest, doc_filename)
                zf.write(ann_path, 'annotations.json')
                zf.write(meta_path, 'metadata.json')
                if has_images and os.path.exists(images_dir):
                    for img in os.listdir(images_dir):
                        zf.write(os.path.join(images_dir, img), f'images/{img}')

            logger.info(f"export_technical: Created {output_path}")
            return True, output_path

        except Exception as e:
            logger.error(f"export_technical: {e}", exc_info=True)
            return False, str(e)
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def import_technical(ecto_path: str) -> Tuple[Optional[str], Optional[List[dict]], Optional[dict], Optional[str], str]:
        """Import a technical-overview .ecto bundle.

        Returns:
            (document_path, annotations, metadata, passcode_hash, temp_dir_or_error)
            On failure the first three are None and last is error string.
        """
        if not os.path.exists(ecto_path):
            return None, None, None, None, f"File not found: {ecto_path}"

        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix='ecto_tech_import_')
            with zipfile.ZipFile(ecto_path, 'r') as zf:
                zf.extractall(temp_dir)

            manifest = json.loads(Path(os.path.join(temp_dir, 'manifest.json')).read_text('utf-8'))
            if manifest.get('type') != 'technical_overview':
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None, None, None, None, "Not a technical overview .ecto file"

            doc_file = manifest.get('document_file', '')
            doc_path = os.path.join(temp_dir, doc_file)
            if not os.path.exists(doc_path):
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None, None, None, None, "Document file missing from bundle"

            passcode_hash = manifest.get('passcode_hash')

            # Annotations
            annotations = []
            ann_file = os.path.join(temp_dir, 'annotations.json')
            if os.path.exists(ann_file):
                data = json.loads(Path(ann_file).read_text('utf-8'))
                annotations = data.get('annotations', [])
                # resolve relative image paths
                for ann in annotations:
                    resolved = []
                    for p in ann.get('image_paths', []):
                        if not os.path.isabs(p):
                            full = os.path.join(temp_dir, p)
                            resolved.append(full if os.path.exists(full) else p)
                        else:
                            resolved.append(p)
                    ann['image_paths'] = resolved

            # Metadata
            metadata = {}
            meta_file = os.path.join(temp_dir, 'metadata.json')
            if os.path.exists(meta_file):
                metadata = json.loads(Path(meta_file).read_text('utf-8'))

            return doc_path, annotations, metadata, passcode_hash, temp_dir

        except Exception as e:
            logger.error(f"import_technical: {e}", exc_info=True)
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            return None, None, None, None, str(e)

    @staticmethod
    def is_technical_ecto(ecto_path: str) -> bool:
        """Check if an .ecto file is a technical overview type (without full extraction)."""
        manifest = EctoFormat.get_manifest(ecto_path)
        return manifest is not None and manifest.get('type') == 'technical_overview'
