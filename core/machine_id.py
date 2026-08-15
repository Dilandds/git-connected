"""
Machine fingerprint helpers for subscription seat tracking and file locks
(core/file_lock.py).
"""

from __future__ import annotations

import hashlib
import logging
import platform
import sys
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# Same app config location as core/identity.py's display name — local
# import (license_validator only imports machine_id lazily, inside a
# function, so this doesn't create a circular import).
try:
    from core.license_validator import get_config_directory
except ImportError:
    def get_config_directory() -> Path:
        if sys.platform == "darwin":
            config_dir = Path.home() / "Library" / "Application Support" / "ECTOFORM"
        elif sys.platform == "win32":
            config_dir = Path.home() / "AppData" / "Local" / "ECTOFORM"
        else:
            config_dir = Path.home() / ".config" / "ectoform"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir


def _device_id_path() -> Path:
    return get_config_directory() / "device_id"


def _load_or_create_device_id() -> str:
    """A random id generated once per install and persisted to disk — the
    actual source of stability for get_machine_fingerprint(). Needed
    because uuid.getnode() (a hardware MAC address) silently falls back to
    a RANDOM 48-bit number, regenerated on every process launch, on any
    machine where Python can't determine a real MAC (seen on some Windows
    machines — no wired adapter, disabled adapters, certain VPN/virtualized
    setups). That instability made get_machine_fingerprint() change on
    every app launch on affected machines, which made file_lock.py's
    is_own_lock() treat a machine's own leftover lock (from a session that
    didn't release it cleanly on exit) as belonging to a "different"
    device the next time the SAME person opened the SAME file — showing a
    false "Currently Being Edited" prompt to someone editing alone."""
    path = _device_id_path()
    try:
        if path.exists():
            existing = path.read_text(encoding='utf-8').strip()
            if existing:
                return existing
    except OSError as e:
        logger.warning(f"machine_id: could not read device id: {e}")
    new_id = uuid.uuid4().hex
    try:
        get_config_directory().mkdir(parents=True, exist_ok=True)
        path.write_text(new_id, encoding='utf-8')
    except OSError as e:
        logger.warning(f"machine_id: could not persist device id: {e}")
    return new_id


def get_machine_fingerprint() -> str:
    """Return a stable short fingerprint for the current device. Stability
    comes from a persisted random id (see _load_or_create_device_id) —
    hostname/platform are folded in for readability/debugging only, never
    as the sole source of uniqueness (unlike the hardware MAC address this
    used to rely on, which isn't always available or stable — see above)."""
    host_name = platform.node().strip().lower()
    machine_name = platform.machine().strip().lower()
    platform_name = platform.platform().strip().lower()
    device_id = _load_or_create_device_id()

    fingerprint_source = f"{sys.platform}|{host_name}|{machine_name}|{platform_name}|{device_id}"
    digest = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
    return digest[:16].upper()
