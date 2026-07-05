"""
Desktop window picker — shows a grid of open app windows with live thumbnails.
macOS  : ctypes + CoreGraphics (no pyobjc needed) for enumeration;
          screencapture -l <id> for thumbnails, region capture for full capture.
Windows: ctypes for enumeration; PIL ImageGrab for capture.
"""
import ctypes
import logging
import os
import platform
import subprocess
import tempfile
import time
from typing import List, Optional, Tuple

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

logger = logging.getLogger(__name__)

_IS_MAC = platform.system() == 'Darwin'
_IS_WIN = platform.system() == 'Windows'


# ── macOS: CoreGraphics via ctypes ────────────────────────────────────────────

def _load_mac_libs():
    """Load CoreGraphics and CoreFoundation via ctypes. Cached after first call."""
    global _cg, _cf
    if getattr(_load_mac_libs, '_done', False):
        return _cg, _cf
    _cg = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    _cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')

    _cg.CGWindowListCopyWindowInfo.restype  = ctypes.c_void_p
    _cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]

    _cg.CGRectMakeWithDictionaryRepresentation.restype  = ctypes.c_bool
    _cg.CGRectMakeWithDictionaryRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    _cf.CFArrayGetCount.restype  = ctypes.c_long
    _cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]

    _cf.CFArrayGetValueAtIndex.restype  = ctypes.c_void_p
    _cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]

    _cf.CFDictionaryGetValue.restype  = ctypes.c_void_p
    _cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    _cf.CFStringCreateWithCString.restype  = ctypes.c_void_p
    _cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]

    _cf.CFStringGetCString.restype  = ctypes.c_bool
    _cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]

    _cf.CFNumberGetValue.restype  = ctypes.c_bool
    _cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]

    _cf.CFRelease.restype  = None
    _cf.CFRelease.argtypes = [ctypes.c_void_p]

    _load_mac_libs._done = True
    return _cg, _cf

_cg = None
_cf = None

_kCFStringEncodingUTF8 = 0x08000100
_kCFNumberSInt32Type   = 3

class _CGPoint(ctypes.Structure):
    _fields_ = [('x', ctypes.c_double), ('y', ctypes.c_double)]

class _CGSize(ctypes.Structure):
    _fields_ = [('width', ctypes.c_double), ('height', ctypes.c_double)]

class _CGRect(ctypes.Structure):
    _fields_ = [('origin', _CGPoint), ('size', _CGSize)]

_kCGWindowListOptionAll              = 0
_kCGWindowListOptionOnScreenOnly     = 1
_kCGWindowListExcludeDesktopElements = 16
_kCGNullWindowID                     = 0


def _cfstr(s: str) -> int:
    return _cf.CFStringCreateWithCString(None, s.encode('utf-8'), _kCFStringEncodingUTF8)

def _py_str(ref) -> str:
    if not ref:
        return ''
    buf = ctypes.create_string_buffer(1024)
    if _cf.CFStringGetCString(ref, buf, 1024, _kCFStringEncodingUTF8):
        return buf.value.decode('utf-8', errors='replace')
    return ''

def _py_int(ref) -> int:
    if not ref:
        return 0
    val = ctypes.c_int32(0)
    _cf.CFNumberGetValue(ref, _kCFNumberSInt32Type, ctypes.byref(val))
    return val.value


def _enum_windows_mac() -> List[Tuple[int, str, str]]:
    """Return [(window_id, label, owner_name)] for all normal app windows.

    Uses largest-area deduplication per label so we always pick the real app
    window rather than a GPU-helper or network-service sub-window.
    """
    try:
        _load_mac_libs()

        k_owner  = _cfstr('kCGWindowOwnerName')
        k_name   = _cfstr('kCGWindowName')
        k_layer  = _cfstr('kCGWindowLayer')
        k_wid    = _cfstr('kCGWindowNumber')
        k_pid    = _cfstr('kCGWindowOwnerPID')
        k_bounds = _cfstr('kCGWindowBounds')

        arr = _cg.CGWindowListCopyWindowInfo(_kCGWindowListOptionAll, _kCGNullWindowID)
        if not arr:
            return []

        current_pid = os.getpid()
        count = _cf.CFArrayGetCount(arr)

        _sys_skip = {'Dock', 'SystemUIServer', 'Window Server', 'Control Center',
                     'NotificationCenter', 'Spotlight', 'loginwindow',
                     'CursorUIViewService', 'Open and Save Panel Service',
                     'Universal Control', 'Amphetamine', ''}

        candidates: List[Tuple[int, str, str, float]] = []  # (wid, label, owner, area)

        for i in range(count):
            d = _cf.CFArrayGetValueAtIndex(arr, i)
            if not d:
                continue
            layer = _py_int(_cf.CFDictionaryGetValue(d, k_layer))
            if layer != 0:
                continue
            pid = _py_int(_cf.CFDictionaryGetValue(d, k_pid))
            if pid == current_pid:
                continue
            owner = _py_str(_cf.CFDictionaryGetValue(d, k_owner))
            title = _py_str(_cf.CFDictionaryGetValue(d, k_name))
            wid   = _py_int(_cf.CFDictionaryGetValue(d, k_wid))
            if not wid or owner in _sys_skip:
                continue

            bounds_ref = _cf.CFDictionaryGetValue(d, k_bounds)
            if not bounds_ref:
                continue
            rect = _CGRect()
            if not _cg.CGRectMakeWithDictionaryRepresentation(bounds_ref, ctypes.byref(rect)):
                continue
            if rect.size.width < 150 or rect.size.height < 100:
                continue
            area = rect.size.width * rect.size.height

            label = owner + (f' — {title}' if title else '')
            candidates.append((wid, label, owner, area))

        _cf.CFRelease(arr)
        for k in (k_owner, k_name, k_layer, k_wid, k_pid, k_bounds):
            _cf.CFRelease(k)

        # Keep the largest-area window per label
        by_label: dict = {}
        for wid, label, owner, area in candidates:
            if label not in by_label or area > by_label[label][2]:
                by_label[label] = (wid, owner, area)

        return [(wid, label, owner) for label, (wid, owner, _) in by_label.items()]

    except Exception as e:
        logger.warning(f"_enum_windows_mac: {e}")
        return []


def _get_window_bounds_mac(window_id: int) -> Optional[Tuple[int, int, int, int]]:
    """Return (x, y, w, h) in screen points for the given CGWindowID, or None."""
    try:
        _load_mac_libs()
        k_wid    = _cfstr('kCGWindowNumber')
        k_bounds = _cfstr('kCGWindowBounds')

        arr = _cg.CGWindowListCopyWindowInfo(_kCGWindowListOptionAll, _kCGNullWindowID)
        if not arr:
            return None

        result = None
        count = _cf.CFArrayGetCount(arr)
        for i in range(count):
            d = _cf.CFArrayGetValueAtIndex(arr, i)
            if not d:
                continue
            wid = _py_int(_cf.CFDictionaryGetValue(d, k_wid))
            if wid != window_id:
                continue
            bounds_ref = _cf.CFDictionaryGetValue(d, k_bounds)
            if bounds_ref:
                rect = _CGRect()
                if _cg.CGRectMakeWithDictionaryRepresentation(bounds_ref, ctypes.byref(rect)):
                    result = (
                        int(rect.origin.x), int(rect.origin.y),
                        int(rect.size.width), int(rect.size.height),
                    )
            break

        _cf.CFRelease(arr)
        _cf.CFRelease(k_wid)
        _cf.CFRelease(k_bounds)
        return result
    except Exception as e:
        logger.debug(f"_get_window_bounds_mac: {e}")
        return None


def _screencapture_window(window_id: int) -> Optional[QPixmap]:
    """Capture a window by CGWindowID using screencapture -l."""
    try:
        fd, path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        subprocess.run(
            ['screencapture', '-l', str(window_id), '-x', path],
            capture_output=True, timeout=8,
        )
        if os.path.exists(path) and os.path.getsize(path) > 0:
            pix = QPixmap(path)
            try:
                os.unlink(path)
            except OSError:
                pass
            return pix if not pix.isNull() else None
        try:
            os.unlink(path)
        except OSError:
            pass
        return None
    except Exception as e:
        logger.debug(f"_screencapture_window {window_id}: {e}")
        return None


def _capture_region_mac(x: int, y: int, w: int, h: int) -> Optional[QPixmap]:
    """Capture a screen region with screencapture -R (works for GPU-composited apps)."""
    try:
        fd, path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        subprocess.run(
            ['screencapture', '-R', f'{x},{y},{w},{h}', '-x', path],
            capture_output=True, timeout=8,
        )
        if os.path.exists(path) and os.path.getsize(path) > 0:
            pix = QPixmap(path)
            try:
                os.unlink(path)
            except OSError:
                pass
            return pix if not pix.isNull() else None
        try:
            os.unlink(path)
        except OSError:
            pass
        return None
    except Exception as e:
        logger.debug(f"_capture_region_mac: {e}")
        return None


def _activate_app_mac(owner_name: str):
    """Bring an app to the foreground via osascript."""
    if not owner_name:
        return
    try:
        subprocess.run(
            ['osascript', '-e', f'tell application "{owner_name}" to activate'],
            capture_output=True, timeout=4,
        )
    except Exception:
        pass


# ── Windows helpers ───────────────────────────────────────────────────────────

def _enum_windows_win() -> List[Tuple[int, str, str]]:
    try:
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32
        results: List[Tuple[int, str, str]] = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

        def _cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n > 0:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    t = buf.value.strip()
                    if t and 'Ectoform' not in t:
                        results.append((hwnd, t, t))
            return True

        user32.EnumWindows(WNDENUMPROC(_cb), 0)
        return results
    except Exception as e:
        logger.debug(f"_enum_windows_win: {e}")
        return []


def _capture_window_win(hwnd: int) -> Optional[QPixmap]:
    try:
        import ctypes.wintypes as wt
        from PIL import ImageGrab
        user32 = ctypes.windll.user32
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.15)
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        bbox = (rect.left, rect.top, rect.right, rect.bottom)
        if bbox[2] - bbox[0] <= 0 or bbox[3] - bbox[1] <= 0:
            return None
        img = ImageGrab.grab(bbox)
        fd, path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        img.save(path)
        pix = QPixmap(path)
        try:
            os.unlink(path)
        except OSError:
            pass
        return pix if not pix.isNull() else None
    except Exception as e:
        logger.debug(f"_capture_window_win: {e}")
        return None


# ── Thumbnail loader thread ───────────────────────────────────────────────────

class _ThumbLoader(QThread):
    thumb_ready  = pyqtSignal(int, QPixmap)
    thumb_failed = pyqtSignal(int)

    def __init__(self, window_ids: List[int]):
        super().__init__()
        self._ids = window_ids
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        for i, wid in enumerate(self._ids):
            if self._cancelled:
                break
            try:
                if _IS_MAC:
                    pix = _screencapture_window(wid)
                elif _IS_WIN:
                    pix = _capture_window_win(wid)
                else:
                    pix = None
                if pix and not pix.isNull():
                    thumb = pix.scaled(190, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.thumb_ready.emit(i, thumb)
                else:
                    self.thumb_failed.emit(i)
            except Exception as e:
                logger.debug(f"_ThumbLoader idx {i}: {e}")
                self.thumb_failed.emit(i)


# ── Window card ───────────────────────────────────────────────────────────────

class _WindowCard(QFrame):
    clicked = pyqtSignal(int)

    _NORMAL = 'background: #f9fafb; border: 2px solid #e5e7eb; border-radius: 10px;'
    _HOVER  = 'background: #eff6ff; border: 2px solid #3b82f6; border-radius: 10px;'
    _SEL    = 'background: #dbeafe; border: 2px solid #2563eb; border-radius: 10px;'

    def __init__(self, window_id: int, label: str, parent=None):
        super().__init__(parent)
        self._wid = window_id
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(200, 165)
        self.setStyleSheet(f'QFrame {{ {self._NORMAL} }}')

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        self._img = QLabel()
        self._img.setAlignment(Qt.AlignCenter)
        self._img.setFixedHeight(110)
        self._img.setStyleSheet(
            'background: #e5e7eb; border-radius: 6px; color: #9ca3af; font-size: 11px; border: none;'
        )
        self._img.setText('Loading…')
        lay.addWidget(self._img)

        name = QLabel(label)
        name.setAlignment(Qt.AlignCenter)
        name.setWordWrap(True)
        name.setFixedHeight(38)
        name.setStyleSheet(
            'color: #111827; font-size: 11px; font-weight: 600;'
            ' background: transparent; border: none;'
        )
        lay.addWidget(name)

    def set_thumbnail(self, pix: QPixmap):
        self._img.setPixmap(pix)
        self._img.setText('')

    def set_no_preview(self):
        self._img.setText('Click to capture')
        self._img.setStyleSheet(
            'background: #f3f4f6; border-radius: 6px; color: #6b7280; font-size: 11px; border: none;'
        )

    def enterEvent(self, e):
        self.setStyleSheet(f'QFrame {{ {self._HOVER} }}')
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setStyleSheet(f'QFrame {{ {self._NORMAL} }}')
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.setStyleSheet(f'QFrame {{ {self._SEL} }}')
            self.clicked.emit(self._wid)
        super().mousePressEvent(e)


# ── Main dialog ───────────────────────────────────────────────────────────────

class WindowPickerDialog(QDialog):
    window_captured = pyqtSignal(QPixmap)

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self._main_win = main_window
        self._cards: List[_WindowCard] = []
        self._loader: Optional[_ThumbLoader] = None
        self._win_ids: List[int] = []
        self._win_owners: dict = {}  # window_id -> owner app name

        self.setWindowTitle('Capture Desktop Window')
        self.setMinimumSize(660, 500)
        self.setModal(True)
        self._build_ui()
        self._load()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        title = QLabel('Select a window to capture')
        title.setStyleSheet('font-size: 15px; font-weight: bold; color: #111827;')
        hdr.addWidget(title)
        hdr.addStretch()
        refresh = QPushButton('↻  Refresh')
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.setStyleSheet("""
            QPushButton { background: #f3f4f6; border: 1px solid #d1d5db;
                border-radius: 6px; padding: 5px 12px; font-size: 12px; color: #374151; }
            QPushButton:hover { background: #e5e7eb; }
        """)
        refresh.clicked.connect(self._load)
        hdr.addWidget(refresh)
        lay.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            'QScrollArea { border: 1px solid #e5e7eb; border-radius: 8px; background: #ffffff; }'
        )
        self._container = QWidget()
        self._container.setStyleSheet('background: #ffffff;')
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(12, 12, 12, 12)
        self._grid.setSpacing(10)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self._container)
        lay.addWidget(scroll, 1)

        self._status = QLabel('Scanning open windows…')
        self._status.setStyleSheet('color: #6b7280; font-size: 12px;')
        lay.addWidget(self._status)

    def _load(self):
        if self._loader and self._loader.isRunning():
            self._loader.cancel()
            self._loader.quit()
            self._loader.wait(1000)

        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()
        self._win_owners.clear()

        self._status.setText('Scanning open windows…')
        QApplication.processEvents()

        if _IS_MAC:
            windows = _enum_windows_mac()
        elif _IS_WIN:
            windows = _enum_windows_win()
        else:
            self._status.setText('Window capture is supported on macOS and Windows only.')
            return

        if not windows:
            self._status.setText(
                'No windows found. On macOS, grant Screen Recording permission '
                'in System Settings → Privacy & Security.'
            )
            return

        self._win_ids = [wid for wid, _, _ in windows]
        cols = 3
        for i, (wid, label, owner) in enumerate(windows):
            self._win_owners[wid] = owner
            card = _WindowCard(wid, label)
            card.clicked.connect(self._on_card_clicked)
            self._cards.append(card)
            self._grid.addWidget(card, i // cols, i % cols)

        self._status.setText(
            f'{len(windows)} windows found — click one to capture it. Thumbnails loading…'
        )

        self._loader = _ThumbLoader(self._win_ids)
        self._loader.thumb_ready.connect(self._on_thumb_ready)
        self._loader.thumb_failed.connect(self._on_thumb_failed)
        self._loader.start()

    def _on_thumb_ready(self, index: int, pix: QPixmap):
        if 0 <= index < len(self._cards):
            self._cards[index].set_thumbnail(pix)

    def _on_thumb_failed(self, index: int):
        if 0 <= index < len(self._cards):
            self._cards[index].set_no_preview()

    def _on_card_clicked(self, window_id: int):
        self._status.setText('Capturing…')
        QApplication.processEvents()

        pix = None
        if _IS_MAC:
            pix = self._capture_mac(window_id)
        elif _IS_WIN:
            pix = _capture_window_win(window_id)

        if pix and not pix.isNull():
            self.window_captured.emit(pix)
            self.accept()
        else:
            self._status.setText(
                'Capture failed. Check Screen Recording permission in '
                'System Settings → Privacy & Security, then Refresh.'
            )
            for card in self._cards:
                card.setStyleSheet(f'QFrame {{ {_WindowCard._NORMAL} }}')

    def _capture_mac(self, window_id: int) -> Optional[QPixmap]:
        """Three-level capture strategy for macOS.

        1. screencapture -l <id>  — fast, works for most apps
        2. Activate app + retry   — handles apps not composited yet
        3. Activate + hide dialog + region capture
                                  — handles GPU-composited apps (Chrome, Brave)
                                    that screencapture -l cannot reach
        """
        owner = self._win_owners.get(window_id, '')

        # Level 1: direct window-ID capture
        pix = _screencapture_window(window_id)
        if pix and not pix.isNull():
            return pix

        # Level 2: activate app, give it time to composite, retry
        self._status.setText('Bringing window to front…')
        QApplication.processEvents()
        _activate_app_mac(owner)
        time.sleep(0.45)
        pix = _screencapture_window(window_id)
        if pix and not pix.isNull():
            return pix

        # Level 3: region capture — hides this dialog so the target window is
        # fully visible, then captures its screen coordinates.
        # Works for any GPU-composited app (Brave, Chrome GPU process, etc.).
        self._status.setText('Capturing window region…')
        QApplication.processEvents()
        bounds = _get_window_bounds_mac(window_id)
        if not bounds:
            return None
        x, y, w, h = bounds

        # Hide the picker so it doesn't obscure the target window
        self.hide()
        QApplication.processEvents()
        time.sleep(0.2)   # let the OS repaint
        pix = _capture_region_mac(x, y, w, h)
        self.show()
        return pix

    def closeEvent(self, event):
        if self._loader and self._loader.isRunning():
            self._loader.cancel()
            self._loader.quit()
            self._loader.wait(1000)
        super().closeEvent(event)
