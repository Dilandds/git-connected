"""
File Lock - Prevents two people from silently overwriting each other's
work when a .lyns.pjt project is open on two machines at once.

A small sidecar JSON file is written next to the project file when it's
opened for editing (who, which machine, when) and removed when it's
closed. It's just a sibling file, so it works on any storage the project
itself is saved to (local disk, network share, SharePoint sync folder,
...) with no predefined shared-folder setup required.

Staleness: a heartbeat (driven by the caller, not this module) is expected
to call refresh_lock() every few minutes while a project is open. If
last_active_at is older than the staleness threshold, the app that held it
most likely crashed rather than merely being slow to save, so the next
person is offered an override instead of being blocked forever.
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.identity import get_display_name
from core.machine_id import get_machine_fingerprint

logger = logging.getLogger(__name__)

STALE_THRESHOLD_MINUTES = 15

# check_lock_status() return values
FREE = 'FREE'
OWN = 'OWN'
HELD_ACTIVE = 'HELD_ACTIVE'
HELD_STALE = 'HELD_STALE'


def lock_path_for(project_path: str) -> Path:
    """Sidecar lock path for a given project file — same name, '.lock' appended."""
    return Path(str(project_path) + '.lock')


def read_lock(project_path: str) -> Optional[dict]:
    """Read the sidecar lock file. Returns None if absent or corrupt (corrupt
    is treated the same as absent — never blocks opening a project)."""
    path = lock_path_for(project_path)
    if not path.exists():
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get('last_active_at'):
            return data
        return None
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f'file_lock: Failed to read lock for {project_path}: {e}')
        return None


def _write_lock(project_path: str, data: dict) -> bool:
    path = lock_path_for(project_path)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    except IOError as e:
        logger.warning(f'file_lock: Failed to write lock for {project_path}: {e}')
        return False


def is_stale(lock_data: dict, threshold_minutes: int = STALE_THRESHOLD_MINUTES) -> bool:
    """Whether a lock's last heartbeat is old enough to assume the app that
    held it crashed rather than still being open."""
    try:
        last_active = datetime.fromisoformat(lock_data['last_active_at'])
    except (KeyError, ValueError):
        # Can't parse a timestamp at all — treat as stale so it doesn't
        # block forever on a malformed lock.
        return True
    if last_active.tzinfo is None:
        last_active = last_active.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - last_active
    return age.total_seconds() > threshold_minutes * 60


def is_own_lock(lock_data: dict) -> bool:
    """Whether this lock was acquired by this exact user on this exact
    device — used to silently reclaim a lock left behind by this same
    person (e.g. reopening after a crash), and to guard release_lock()
    from ever deleting someone else's lock."""
    if not lock_data:
        return False
    return (
        lock_data.get('machine_fingerprint') == get_machine_fingerprint()
        and lock_data.get('user') == get_display_name()
    )


def check_lock_status(project_path: str) -> str:
    """FREE (no lock), OWN (this user/device already holds it), HELD_ACTIVE
    (someone else holds it and the heartbeat is recent), or HELD_STALE
    (someone else holds it but the heartbeat is old enough to assume a
    crash)."""
    lock_data = read_lock(project_path)
    if lock_data is None:
        return FREE
    if is_own_lock(lock_data):
        return OWN
    return HELD_STALE if is_stale(lock_data) else HELD_ACTIVE


def acquire_lock(project_path: str, force: bool = False) -> bool:
    """Write the sidecar lock for this user/device. Returns False without
    writing anything if someone else already holds a non-stale lock and
    force is False."""
    status = check_lock_status(project_path)
    if status == HELD_ACTIVE and not force:
        return False
    now = datetime.now(timezone.utc).isoformat()
    data = {
        'user': get_display_name(),
        'machine': _machine_name(),
        'machine_fingerprint': get_machine_fingerprint(),
        'pid': os.getpid(),
        'acquired_at': now,
        'last_active_at': now,
    }
    return _write_lock(project_path, data)


def refresh_lock(project_path: str) -> None:
    """Rewrite last_active_at to now — called by the caller's heartbeat
    timer and after every save. Best-effort: silently does nothing if this
    device doesn't currently hold the lock (e.g. it was released already)."""
    lock_data = read_lock(project_path)
    if lock_data is None or not is_own_lock(lock_data):
        return
    lock_data['last_active_at'] = datetime.now(timezone.utc).isoformat()
    _write_lock(project_path, lock_data)


def release_lock(project_path: str) -> None:
    """Delete the sidecar lock, but only if this device currently owns it —
    never deletes a lock belonging to someone else (e.g. a stale reference
    to a project path this session no longer has open)."""
    lock_data = read_lock(project_path)
    if lock_data is None or not is_own_lock(lock_data):
        return
    path = lock_path_for(project_path)
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning(f'file_lock: Failed to release lock for {project_path}: {e}')


def _machine_name() -> str:
    try:
        import platform
        return platform.node()
    except Exception:
        return ''
