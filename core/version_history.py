"""
Local version history for project files — a manual, on-demand recovery net,
independent of whatever folder-sharing mechanism (Syncthing, Dropbox,
OneDrive, a raw network share, ...) a customer happens to use.

Every save archives whatever was on disk *before* the overwrite into a
sidecar history folder next to the project file. This is deliberately not
tied to any sync tool's own conflict-detection — a raw network share, for
instance, has no conflict file at all, so the only real protection against
"my change got silently overwritten" is the app keeping its own trail.

Nothing here is automatic recovery: a user has to notice something's wrong
and open the Version History dialog to restore an earlier snapshot.
"""
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, TypedDict

logger = logging.getLogger(__name__)

HISTORY_SUFFIX = '.history'
MAX_SNAPSHOTS = 30
MIN_INTERVAL_MINUTES = 10

_TIMESTAMP_FMT = '%Y%m%dT%H%M%SZ'
_SNAPSHOT_RE = re.compile(r'\.(\d{8}T\d{6}Z)(?:-\d+)?\.bak$')


class Snapshot(TypedDict):
    path: str
    timestamp: datetime
    size: int


def _history_dir_for(project_path: str) -> Path:
    return Path(str(project_path) + HISTORY_SUFFIX)


def _snapshot_path_for(project_path: str, when: datetime) -> Path:
    basename = os.path.basename(project_path)
    stamp = when.strftime(_TIMESTAMP_FMT)
    return _history_dir_for(project_path) / f'{basename}.{stamp}.bak'


def list_snapshots(project_path: str) -> List[Snapshot]:
    """All snapshots for this project, newest first."""
    history_dir = _history_dir_for(project_path)
    if not history_dir.is_dir():
        return []
    out: List[Snapshot] = []
    for entry in history_dir.iterdir():
        m = _SNAPSHOT_RE.search(entry.name)
        if not m or not entry.is_file():
            continue
        try:
            ts = datetime.strptime(m.group(1), _TIMESTAMP_FMT).replace(tzinfo=timezone.utc)
            out.append({'path': str(entry), 'timestamp': ts, 'size': entry.stat().st_size})
        except (ValueError, OSError):
            continue
    out.sort(key=lambda s: s['timestamp'], reverse=True)
    return out


def snapshot_before_overwrite(project_path: str, force: bool = False) -> Optional[str]:
    """Archive whatever is currently at `project_path` into the history
    folder, then prune down to MAX_SNAPSHOTS. No-ops (returns None) if
    there's nothing at project_path yet (first-ever save — nothing to
    protect), or if the most recent snapshot is younger than
    MIN_INTERVAL_MINUTES and `force` isn't set (keeps autosave, which can
    fire every 30s, from flooding the history with near-duplicate
    snapshots). `force=True` (used before a restore) bypasses the
    throttle, since that's a deliberate, infrequent action and the point
    is specifically to protect whatever's about to be replaced.

    Returns the new snapshot's path, or None if none was created."""
    if not os.path.exists(project_path):
        return None

    existing = list_snapshots(project_path)
    if not force and existing:
        age = datetime.now(timezone.utc) - existing[0]['timestamp']
        if age.total_seconds() < MIN_INTERVAL_MINUTES * 60:
            return None

    history_dir = _history_dir_for(project_path)
    try:
        history_dir.mkdir(parents=True, exist_ok=True)
        dest = _snapshot_path_for(project_path, datetime.now(timezone.utc))
        # Same-second collision (e.g. two forced snapshots in quick
        # succession) — the timestamp alone isn't unique enough; disambiguate
        # rather than silently overwriting an earlier snapshot with this name.
        if dest.exists():
            stem, suffix = dest.name[:-4], 2  # strip trailing '.bak'
            while dest.exists():
                dest = dest.with_name(f'{stem}-{suffix}.bak')
                suffix += 1
        shutil.copy2(project_path, dest)
        logger.info(f'snapshot_before_overwrite: archived {project_path} -> {dest}')
    except OSError as e:
        logger.warning(f'snapshot_before_overwrite: could not archive {project_path}: {e}')
        return None

    _prune(project_path)
    return str(dest)


def _prune(project_path: str) -> None:
    snapshots = list_snapshots(project_path)
    for stale in snapshots[MAX_SNAPSHOTS:]:
        try:
            os.remove(stale['path'])
        except OSError as e:
            logger.warning(f'_prune: could not remove old snapshot {stale["path"]}: {e}')


def restore_snapshot(snapshot_path: str, project_path: str) -> bool:
    """Restore `snapshot_path` over `project_path`. Always archives
    whatever's currently at project_path first (force=True — an explicit
    restore should never itself be a way to lose data), so restoring is
    itself always recoverable."""
    if not os.path.exists(snapshot_path):
        logger.warning(f'restore_snapshot: snapshot not found: {snapshot_path}')
        return False
    try:
        # Read the content to restore BEFORE archiving the current live
        # file — that archive step prunes old snapshots, and if
        # snapshot_path itself happens to be the oldest surviving one, it
        # could get pruned out from under us. Reading it into memory first
        # means that can't cost us the restore.
        content = Path(snapshot_path).read_bytes()
    except OSError as e:
        logger.warning(f'restore_snapshot: could not read {snapshot_path}: {e}')
        return False
    snapshot_before_overwrite(project_path, force=True)
    try:
        Path(project_path).write_bytes(content)
        logger.info(f'restore_snapshot: restored {snapshot_path} -> {project_path}')
        return True
    except OSError as e:
        logger.warning(f'restore_snapshot: could not restore {snapshot_path}: {e}')
        return False
