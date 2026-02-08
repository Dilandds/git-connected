"""
EFM Format Handler - Custom .efm file format for ECTOFORM.

The .efm format is a ZIP-based bundle containing:
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
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

# Format version for .efm files
EFM_FORMAT_VERSION = "1.0"


class EfmFormat:
    """Handler for .efm file format - a single-file bundle for sharing annotated 3D models."""
    
    # Supported model formats
    SUPPORTED_FORMATS = ['stl', 'obj']
    
    @staticmethod
    def is_efm_file(file_path: str) -> bool:
        """Check if a file is a valid .efm format.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if the file is a valid .efm bundle
        """
        if not file_path.lower().endswith('.efm'):
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
            logger.debug(f"is_efm_file: Not a valid .efm file: {e}")
            return False
    
    @staticmethod
    def export(mesh, annotations: List[dict], output_path: str, 
               source_format: str = 'stl', original_filename: str = None) -> Tuple[bool, str]:
        """Create an .efm bundle containing the model, annotations, and images.
        
        Args:
            mesh: PyVista mesh object to export
            annotations: List of annotation dictionaries
            output_path: Path for the output .efm file
            source_format: Format to save the model as ('stl' or 'obj')
            original_filename: Original filename for metadata
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if mesh is None:
            return False, "No mesh provided"
        
        # Ensure output has .efm extension
        if not output_path.lower().endswith('.efm'):
            output_path += '.efm'
        
        # Validate source format
        source_format = source_format.lower()
        if source_format not in EfmFormat.SUPPORTED_FORMATS:
            source_format = 'stl'
        
        temp_dir = None
        try:
            # Create temp directory for building the bundle
            temp_dir = tempfile.mkdtemp(prefix='efm_export_')
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
            
            # 4. Create manifest.json
            manifest = {
                'format_version': EFM_FORMAT_VERSION,
                'created_by': 'ECTOFORM',
                'created_at': datetime.now().isoformat(),
                'model_file': model_filename,
                'model_format': source_format,
                'original_filename': original_filename or 'unknown',
                'reader_mode': True,
                'annotation_count': len(processed_annotations),
                'has_images': has_images
            }
            manifest_path = os.path.join(temp_dir, 'manifest.json')
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2)
            logger.info(f"export: Created manifest.json")
            
            # 5. Create the .ecto ZIP file
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Add manifest
                zf.write(manifest_path, 'manifest.json')
                # Add model
                zf.write(model_path, model_filename)
                # Add annotations
                zf.write(annotations_path, 'annotations.json')
                # Add images if any
                if has_images and os.path.exists(images_dir):
                    for img_file in os.listdir(images_dir):
                        img_path = os.path.join(images_dir, img_file)
                        zf.write(img_path, f'images/{img_file}')
            
            logger.info(f"export: Created .efm bundle at {output_path}")
            return True, output_path
            
        except Exception as e:
            logger.error(f"export: Failed to create .efm bundle: {e}", exc_info=True)
            return False, str(e)
        
        finally:
            # Cleanup temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    logger.info(f"export: Cleaned up temp directory")
                except Exception as e:
                    logger.warning(f"export: Failed to cleanup temp directory: {e}")
    
    @staticmethod
    def import_efm(efm_path: str) -> Tuple[Optional[str], Optional[List[dict]], bool, str]:
        """Open an .efm bundle and extract its contents.
        
        Extracts the bundle to a temporary directory and returns paths to the contents.
        The caller is responsible for cleaning up the temp directory when done.
        
        Args:
            efm_path: Path to the .efm file
            
        Returns:
            tuple: (model_path: str or None, annotations: list or None, reader_mode: bool, temp_dir: str)
                   Returns (None, None, False, error_message) on failure
        """
        if not os.path.exists(efm_path):
            return None, None, False, f"File not found: {efm_path}"
        
        if not EfmFormat.is_efm_file(efm_path):
            return None, None, False, "Invalid .efm file format"
        
        temp_dir = None
        try:
            # Create temp directory for extraction
            temp_dir = tempfile.mkdtemp(prefix='efm_import_')
            logger.info(f"import_efm: Extracting to temp directory: {temp_dir}")
            
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
                return None, None, False, f"Model file not found in bundle: {model_filename}"
            
            # Read annotations
            annotations = None
            reader_mode = True  # Default to reader mode for imported files
            annotations_path = os.path.join(temp_dir, 'annotations.json')
            
            if os.path.exists(annotations_path):
                with open(annotations_path, 'r', encoding='utf-8') as f:
                    annotations_data = json.load(f)
                
                annotations = annotations_data.get('annotations', [])
                reader_mode = annotations_data.get('reader_mode', True)
                
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
            
            logger.info(f"import_efm: Successfully extracted. Model: {model_path}, "
                       f"Annotations: {len(annotations) if annotations else 0}, "
                       f"Reader mode: {reader_mode}")
            
            return model_path, annotations, reader_mode, temp_dir
            
        except Exception as e:
            logger.error(f"import_efm: Failed to import .efm file: {e}", exc_info=True)
            # Cleanup on failure
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
            return None, None, False, str(e)
    
    @staticmethod
    def get_manifest(efm_path: str) -> Optional[Dict[str, Any]]:
        """Read the manifest from an .efm file without full extraction.
        
        Args:
            efm_path: Path to the .efm file
            
        Returns:
            Manifest dictionary or None on failure
        """
        try:
            with zipfile.ZipFile(efm_path, 'r') as zf:
                manifest_data = zf.read('manifest.json')
                return json.loads(manifest_data.decode('utf-8'))
        except Exception as e:
            logger.error(f"get_manifest: Failed to read manifest: {e}")
            return None
    
    @staticmethod
    def cleanup_temp_dir(temp_dir: str) -> bool:
        """Clean up a temporary directory created during import.
        
        Args:
            temp_dir: Path to the temporary directory
            
        Returns:
            True if cleanup was successful
        """
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"cleanup_temp_dir: Removed {temp_dir}")
                return True
            except Exception as e:
                logger.warning(f"cleanup_temp_dir: Failed to remove {temp_dir}: {e}")
                return False
        return True
