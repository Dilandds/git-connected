"""
Machine fingerprint helpers for subscription seat tracking.
"""

from __future__ import annotations

import hashlib
import platform
import sys
import uuid


def get_machine_fingerprint() -> str:
    """Return a stable short fingerprint for the current device."""
    host_name = platform.node().strip().lower()
    machine_name = platform.machine().strip().lower()
    platform_name = platform.platform().strip().lower()
    mac_address = uuid.getnode()

    fingerprint_source = f"{sys.platform}|{host_name}|{machine_name}|{platform_name}|{mac_address}"
    digest = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
    return digest[:16].upper()