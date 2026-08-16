"""
Registers this edition's project file type with Windows so File Explorer
shows the app's icon on those files instead of a generic blank-page icon
(the same icon shown in the app's own window/taskbar — see
ui/annotation_icon.py's get_app_window_icon(), both ultimately derived
from assets/logo.png).

Commercial opens .lyns.pjt under one ProgID (a user only ever has one
edition installed). LYNS Lite opens a *different* file type
(.lyns.review) and gets its own ProgID so the two associations don't
collide if someone ever has both a full edition and Lite installed at
once (e.g. a PM who's also acting as a reviewer).

There's no traditional installer step (build_windows.ps1 just copies the
built EXE to a "-Setup" filename — see its own comments), so this
self-registers on startup instead of during install. Writes to
HKEY_CURRENT_USER\\Software\\Classes, which File Explorer honors per-user
and doesn't require admin rights (unlike HKEY_CLASSES_ROOT machine-wide).
"""
import logging
import sys

logger = logging.getLogger(__name__)

_PROJECT_PROG_ID = 'LYNS360.Project'
_PROJECT_EXT = '.lyns.pjt'
_PROJECT_FRIENDLY_NAME = 'LYNS360 Project'

_REVIEW_PROG_ID = 'LYNS360.Review'
_REVIEW_EXT = '.lyns.review'
_REVIEW_FRIENDLY_NAME = 'LYNS360 Supplier Review'


def register_file_association():
    """Best-effort; any failure is logged and swallowed — this is a nice-to-
    have and must never block or crash app startup."""
    if sys.platform != 'win32':
        return
    if not getattr(sys, 'frozen', False):
        # Dev mode: sys.executable is the Python interpreter, not the app,
        # so there's no sensible target to register as the file opener.
        return

    from core.edition import is_lite
    if is_lite():
        _register(_REVIEW_EXT, _REVIEW_PROG_ID, _REVIEW_FRIENDLY_NAME)
    else:
        _register(_PROJECT_EXT, _PROJECT_PROG_ID, _PROJECT_FRIENDLY_NAME)


def _register(ext: str, prog_id: str, friendly_name: str):
    try:
        import winreg
        exe_path = sys.executable
        icon_ref = f'"{exe_path}",0'
        open_cmd = f'"{exe_path}" "%1"'

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf'Software\Classes\{ext}') as k:
            current, _ = _try_query(k, '')
            if current != prog_id:
                winreg.SetValueEx(k, '', 0, winreg.REG_SZ, prog_id)

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf'Software\Classes\{prog_id}') as k:
            winreg.SetValueEx(k, '', 0, winreg.REG_SZ, friendly_name)

        icon_key = rf'Software\Classes\{prog_id}\DefaultIcon'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, icon_key) as k:
            current, _ = _try_query(k, '')
            icon_changed = current != icon_ref
            if icon_changed:
                winreg.SetValueEx(k, '', 0, winreg.REG_SZ, icon_ref)

        cmd_key = rf'Software\Classes\{prog_id}\shell\open\command'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cmd_key) as k:
            current, _ = _try_query(k, '')
            if current != open_cmd:
                winreg.SetValueEx(k, '', 0, winreg.REG_SZ, open_cmd)

        if icon_changed:
            # Explorer caches file-type icons — nudge it to refresh so the
            # new icon shows up without the user having to sign out/reboot.
            _notify_explorer()

        logger.info(f'file_association: {ext} registered -> {exe_path}')
    except Exception as e:
        logger.warning(f'file_association: registration failed (non-fatal): {e}')


def _try_query(key, name):
    import winreg
    try:
        return winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return None, None


def _notify_explorer():
    import ctypes
    SHCNE_ASSOCCHANGED = 0x08000000
    SHCNF_IDLIST = 0x0000
    ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
