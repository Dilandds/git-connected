"""
Identity - Stores a persistent per-device display name.

Suggested from the OS account on first run, editable once, then reused
everywhere the app needs to know "who is this" — created_by/last_saved_by
on project saves, file locks, and merge-conflict prompts — so they all
agree on the same name instead of each asking the OS independently.
"""
import getpass
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Import config directory from license validator (same app config location)
try:
    from core.license_validator import get_config_directory
except ImportError:
    # Fallback if license_validator not available
    import sys
    def get_config_directory() -> Path:
        if sys.platform == "darwin":
            config_dir = Path.home() / "Library" / "Application Support" / "ECTOFORM"
        elif sys.platform == "win32":
            config_dir = Path.home() / "AppData" / "Local" / "ECTOFORM"
        else:
            config_dir = Path.home() / ".config" / "ectoform"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir


def get_identity_path() -> Path:
    """Path to the identity JSON file."""
    return get_config_directory() / "identity.json"


def _load_identity() -> Optional[dict]:
    """Load the stored identity dict from disk, or None if absent/corrupt."""
    path = get_identity_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("display_name"):
            return data
        return None
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"identity: Failed to load identity: {e}")
        return None


def _save_identity(name: str) -> bool:
    """Persist the display name to disk."""
    path = get_identity_path()
    try:
        get_config_directory().mkdir(parents=True, exist_ok=True)
        data = {
            "display_name": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except IOError as e:
        logger.warning(f"identity: Failed to save identity: {e}")
        return False


def has_identity() -> bool:
    """Whether a display name has already been stored on this device."""
    return _load_identity() is not None


def suggest_name_from_os() -> str:
    """Best-effort OS account name, used only to pre-fill the first-run prompt."""
    try:
        return getpass.getuser()
    except Exception:
        return ""


def get_display_name() -> str:
    """Return the stored display name, falling back to the OS account name
    if nothing has been stored yet. Pure accessor, no UI — every other
    piece of the app (created_by/last_saved_by, file locks, merge-conflict
    prompts) should call this instead of asking the OS directly, so they
    all agree on the same name."""
    identity = _load_identity()
    if identity:
        return identity["display_name"]
    return suggest_name_from_os()


def set_display_name(name: str) -> bool:
    """Persist a new display name. No-ops (returns False) on an empty name."""
    name = (name or "").strip()
    if not name:
        return False
    return _save_identity(name)


def ensure_identity_prompt(parent) -> str:
    """Return the stored display name, prompting the user to confirm/edit it
    once if nothing has been stored yet. Safe to call every app start —
    it's a no-op once an identity exists."""
    if has_identity():
        return get_display_name()

    from ui.modal_utils import ask_text_input_dialog
    from i18n import t

    suggested = suggest_name_from_os()
    name, accepted = ask_text_input_dialog(
        parent,
        t('identity.prompt_title'),
        t('identity.prompt_label'),
        default_text=suggested,
    )
    final_name = name.strip() if accepted and name.strip() else suggested
    if final_name:
        set_display_name(final_name)
    return final_name
