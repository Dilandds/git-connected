"""
Windows-only self-repair for rhino3dm's "DLL load failed" error.

rhino3dm ships a compiled C++ extension that needs the Microsoft Visual C++
2015-2022 runtime present on the machine. We already bundle our own copies
of the runtime DLLs into the frozen build (see the *_windows*.spec files),
which covers most machines — but a machine can still be missing other
pieces of that runtime, or a policy/antivirus can strip a bundled DLL. This
module is the last-resort fallback: silently run the full Microsoft
redistributable installer we bundle as assets/vc_redist.x64.exe, so the
user never has to find or download anything themselves. The only thing
they see is one Windows UAC ("Do you want to allow this app...") prompt,
which is unavoidable — installing a system runtime always requires
elevation.
"""
import ctypes
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_ALREADY_ATTEMPTED = False


def _get_assets_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'assets'
    return Path(__file__).resolve().parent.parent / 'assets'


def is_dll_load_error(exc: BaseException) -> bool:
    """True if `exc` looks like rhino3dm's missing-VC++-runtime failure."""
    return 'DLL load failed' in str(exc)


def attempt_repair() -> bool:
    """Silently install the bundled VC++ Redistributable (one UAC prompt).

    Returns True if the installer ran and reported success (or "success,
    reboot required"), False otherwise — including: not on Windows, the
    installer isn't bundled, or the user declined the UAC prompt. Only the
    first call per process actually runs the installer; later calls return
    False immediately so a bad file doesn't trigger repeated UAC prompts
    while the user keeps retrying the same load.
    """
    global _ALREADY_ATTEMPTED
    if sys.platform != 'win32':
        return False
    if _ALREADY_ATTEMPTED:
        return False
    _ALREADY_ATTEMPTED = True

    installer = _get_assets_dir() / 'vc_redist.x64.exe'
    if not installer.exists():
        logger.error(f"vcredist_repair: bundled installer not found at {installer}")
        return False

    logger.info(f"vcredist_repair: launching {installer} (elevated, silent)")
    try:
        import ctypes.wintypes as wintypes

        SEE_MASK_NOCLOSEPROCESS = 0x00000040
        SW_HIDE = 0

        class SHELLEXECUTEINFOW(ctypes.Structure):
            _fields_ = [
                ('cbSize', wintypes.DWORD),
                ('fMask', ctypes.c_ulong),
                ('hwnd', wintypes.HWND),
                ('lpVerb', wintypes.LPCWSTR),
                ('lpFile', wintypes.LPCWSTR),
                ('lpParameters', wintypes.LPCWSTR),
                ('lpDirectory', wintypes.LPCWSTR),
                ('nShow', ctypes.c_int),
                ('hInstApp', wintypes.HINSTANCE),
                ('lpIDList', ctypes.c_void_p),
                ('lpClass', wintypes.LPCWSTR),
                ('hKeyClass', wintypes.HKEY),
                ('dwHotKey', wintypes.DWORD),
                ('hIconOrMonitor', wintypes.HANDLE),
                ('hProcess', wintypes.HANDLE),
            ]

        sei = SHELLEXECUTEINFOW()
        sei.cbSize = ctypes.sizeof(sei)
        sei.fMask = SEE_MASK_NOCLOSEPROCESS
        sei.hwnd = None
        sei.lpVerb = 'runas'  # triggers the UAC elevation prompt
        sei.lpFile = str(installer)
        sei.lpParameters = '/install /quiet /norestart'
        sei.lpDirectory = None
        sei.nShow = SW_HIDE
        sei.hInstApp = None

        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
            err = ctypes.GetLastError()
            logger.warning(f"vcredist_repair: ShellExecuteEx failed or was declined (error {err})")
            return False

        if sei.hProcess:
            WAIT_TIMEOUT_MS = 120_000  # installer is ~25MB, should finish well within 2 min
            ctypes.windll.kernel32.WaitForSingleObject(sei.hProcess, WAIT_TIMEOUT_MS)
            exit_code = wintypes.DWORD()
            ctypes.windll.kernel32.GetExitCodeProcess(sei.hProcess, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(sei.hProcess)
            logger.info(f"vcredist_repair: installer exit code {exit_code.value}")
            # 0 = success, 3010 = success but a reboot is recommended — both
            # mean the runtime is now usable for the current process.
            return exit_code.value in (0, 3010)

        return True
    except Exception as e:
        logger.error(f"vcredist_repair: repair attempt failed: {e}", exc_info=True)
        return False
