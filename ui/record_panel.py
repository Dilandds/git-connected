"""
Record Panel — three-state side panel for 3D viewport recording.

States
------
IDLE       Panel open, settings editable, Start button shown.
RECORDING  Capture active, live timer, Stop button shown.
STOPPED    Capture finished — Save and Discard buttons shown.
"""
import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSlider, QComboBox, QCheckBox, QStackedWidget,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer

from ui.styles import default_theme

logger = logging.getLogger(__name__)

# ── palette ───────────────────────────────────────────────────────────────────
_BG    = default_theme.card_background
_TEXT  = default_theme.text_primary
_MUTED = default_theme.text_secondary
_BORD  = default_theme.border_standard
_REC   = "#e63946"
_REC_H = "#c0303a"
_GREEN   = "#16a34a"
_GREEN_H = "#15803d"


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color: {_BORD}; background: {_BORD};")
    f.setFixedHeight(1)
    return f


class RecordPanel(QWidget):
    """
    Signals
    -------
    start_recording_clicked   — user pressed Start Recording
    stop_recording_clicked    — user pressed Stop
    save_recording_clicked    — user pressed Save (after stopping)
    discard_recording_clicked — user pressed Discard (after stopping)
    exit_record_mode          — user pressed × in banner
    rotate_toggled            — (bool) checkbox toggled
    speed_changed             — (float) °/sec
    direction_changed         — (int) +1 / -1
    """

    start_recording_clicked   = pyqtSignal()
    stop_recording_clicked    = pyqtSignal()
    save_recording_clicked    = pyqtSignal()
    discard_recording_clicked = pyqtSignal()
    exit_record_mode          = pyqtSignal()
    rotate_toggled            = pyqtSignal(bool)
    speed_changed             = pyqtSignal(float)
    direction_changed         = pyqtSignal(int)

    # ── state constants ───────────────────────────────────────────────────────
    IDLE      = 0
    RECORDING = 1
    STOPPED   = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(260)
        self.setMaximumWidth(340)
        self.setStyleSheet(f"background-color: {_BG};")

        self._state = self.IDLE
        self._elapsed_sec = 0
        self._frame_count = 0

        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._tick_clock)

        self._build_ui()
        self._apply_state(self.IDLE)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Banner (always visible)
        banner = QWidget()
        banner.setFixedHeight(52)
        banner.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {_REC}, stop:1 #b91c1c);
                border-bottom: 1px solid {_BORD};
            }}
        """)
        ban_lay = QHBoxLayout(banner)
        ban_lay.setContentsMargins(14, 0, 10, 0)
        ban_lay.setSpacing(8)

        self._banner_dot = QLabel("⏺")
        self._banner_dot.setStyleSheet("color: #ffffff; font-size: 14px; background: transparent;")
        ban_lay.addWidget(self._banner_dot)

        self._banner_title = QLabel("Record")
        self._banner_title.setStyleSheet(
            "color: #ffffff; font-size: 14px; font-weight: bold; background: transparent;"
        )
        ban_lay.addWidget(self._banner_title)
        ban_lay.addStretch(1)

        exit_btn = QPushButton("×")
        exit_btn.setFixedSize(28, 28)
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setStyleSheet("""
            QPushButton {
                color: rgba(255,255,255,0.8); background: transparent;
                border: none; font-size: 18px; font-weight: bold;
            }
            QPushButton:hover {
                color: #ffffff; background: rgba(255,255,255,0.2); border-radius: 4px;
            }
        """)
        exit_btn.clicked.connect(self.exit_record_mode)
        ban_lay.addWidget(exit_btn)
        root.addWidget(banner)

        # Body
        body = QWidget()
        body.setStyleSheet(f"background-color: {_BG};")
        blay = QVBoxLayout(body)
        blay.setContentsMargins(14, 14, 14, 14)
        blay.setSpacing(12)

        # ── Status row (timer + frames) ───────────────────────────────────────
        status_row = QHBoxLayout()
        self._status_label = QLabel("Ready to record")
        self._status_label.setStyleSheet(f"color: {_MUTED}; font-size: 12px; font-weight: bold;")
        status_row.addWidget(self._status_label)
        status_row.addStretch(1)
        self._frames_label = QLabel("")
        self._frames_label.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        status_row.addWidget(self._frames_label)
        blay.addLayout(status_row)

        blay.addWidget(_sep())

        # ── Settings (locked while recording) ────────────────────────────────
        self._add_section_label(blay, "SETTINGS")

        self._settings_widget = QWidget()
        sw_lay = QVBoxLayout(self._settings_widget)
        sw_lay.setContentsMargins(0, 0, 0, 0)
        sw_lay.setSpacing(8)

        res_row = QHBoxLayout()
        res_row.addWidget(self._muted("Resolution"))
        self.res_combo = QComboBox()
        self.res_combo.addItems(["Viewport", "720p", "1080p"])
        self.res_combo.setCurrentIndex(0)
        self.res_combo.setStyleSheet(self._combo_style())
        res_row.addWidget(self.res_combo)
        sw_lay.addLayout(res_row)

        fps_row = QHBoxLayout()
        fps_row.addWidget(self._muted("Frame rate"))
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["24 fps", "30 fps", "60 fps"])
        self.fps_combo.setCurrentIndex(1)
        self.fps_combo.setStyleSheet(self._combo_style())
        fps_row.addWidget(self.fps_combo)
        sw_lay.addLayout(fps_row)

        blay.addWidget(self._settings_widget)
        blay.addWidget(_sep())

        # ── Auto-Rotate ───────────────────────────────────────────────────────
        self._add_section_label(blay, "AUTO-ROTATE")

        self._rotate_cb = QCheckBox("Enable turntable rotation")
        self._rotate_cb.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
        self._rotate_cb.toggled.connect(self.rotate_toggled)
        blay.addWidget(self._rotate_cb)

        self._add_section_label(blay, "SPEED  (°/sec)")
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setMinimum(2)
        self.speed_slider.setMaximum(90)
        self.speed_slider.setValue(15)
        self.speed_slider.setTickPosition(QSlider.TicksBelow)
        self.speed_slider.setTickInterval(22)
        self.speed_slider.setStyleSheet(self._slider_style())
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        blay.addWidget(self.speed_slider)

        speed_hints = QHBoxLayout()
        speed_hints.addWidget(self._muted("Slow"))
        speed_hints.addStretch(1)
        self._speed_val_label = QLabel("15°/sec")
        self._speed_val_label.setStyleSheet(f"color: {_TEXT}; font-size: 11px; font-weight: bold;")
        speed_hints.addWidget(self._speed_val_label)
        speed_hints.addStretch(1)
        speed_hints.addWidget(self._muted("Fast"))
        blay.addLayout(speed_hints)

        dir_row = QHBoxLayout()
        dir_row.addWidget(self._muted("Direction"))
        dir_row.addStretch(1)
        self._dir_left_btn = QPushButton("← Left")
        self._dir_right_btn = QPushButton("Right →")
        for b in (self._dir_left_btn, self._dir_right_btn):
            b.setFixedHeight(26)
            b.setCursor(Qt.PointingHandCursor)
            b.setCheckable(True)
        self._dir_right_btn.setChecked(True)
        self._dir_left_btn.setStyleSheet(self._dir_btn_style(False))
        self._dir_right_btn.setStyleSheet(self._dir_btn_style(True))
        self._dir_left_btn.clicked.connect(lambda: self._set_direction(-1))
        self._dir_right_btn.clicked.connect(lambda: self._set_direction(1))
        dir_row.addWidget(self._dir_left_btn)
        dir_row.addWidget(self._dir_right_btn)
        blay.addLayout(dir_row)

        blay.addWidget(_sep())

        # ── Action area — swaps between three states ──────────────────────────
        self._action_stack = QStackedWidget()

        # Page 0 — IDLE: Start button
        idle_page = QWidget()
        idle_lay = QVBoxLayout(idle_page)
        idle_lay.setContentsMargins(0, 0, 0, 0)
        idle_lay.setSpacing(0)
        self._start_btn = QPushButton("▶  Start Recording")
        self._start_btn.setFixedHeight(38)
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_GREEN};
                color: #ffffff; border: none; border-radius: 7px;
                font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {_GREEN_H}; }}
        """)
        self._start_btn.clicked.connect(self.start_recording_clicked)
        idle_lay.addWidget(self._start_btn)
        self._action_stack.addWidget(idle_page)   # index 0

        # Page 1 — RECORDING: Stop button
        rec_page = QWidget()
        rec_lay = QVBoxLayout(rec_page)
        rec_lay.setContentsMargins(0, 0, 0, 0)
        rec_lay.setSpacing(0)
        self._stop_btn = QPushButton("⏹  Stop")
        self._stop_btn.setFixedHeight(38)
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_REC};
                color: #ffffff; border: none; border-radius: 7px;
                font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {_REC_H}; }}
        """)
        self._stop_btn.clicked.connect(self.stop_recording_clicked)
        rec_lay.addWidget(self._stop_btn)
        self._action_stack.addWidget(rec_page)    # index 1

        # Page 2 — STOPPED: Save + Discard
        stopped_page = QWidget()
        stopped_lay = QVBoxLayout(stopped_page)
        stopped_lay.setContentsMargins(0, 0, 0, 0)
        stopped_lay.setSpacing(8)
        self._save_btn = QPushButton("💾  Save Video")
        self._save_btn.setFixedHeight(38)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_GREEN};
                color: #ffffff; border: none; border-radius: 7px;
                font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {_GREEN_H}; }}
        """)
        self._save_btn.clicked.connect(self.save_recording_clicked)
        stopped_lay.addWidget(self._save_btn)

        self._discard_btn = QPushButton("Discard")
        self._discard_btn.setFixedHeight(30)
        self._discard_btn.setCursor(Qt.PointingHandCursor)
        self._discard_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: {_MUTED};
                border: 1px solid {_BORD}; border-radius: 6px; font-size: 12px;
            }}
            QPushButton:hover {{ color: {_TEXT}; border-color: {_TEXT}; }}
        """)
        self._discard_btn.clicked.connect(self.discard_recording_clicked)
        stopped_lay.addWidget(self._discard_btn)
        self._action_stack.addWidget(stopped_page)  # index 2

        blay.addWidget(self._action_stack)
        blay.addStretch(1)
        root.addWidget(body, 1)

    # ── State transitions (called from stl_viewer.py) ─────────────────────────

    def _apply_state(self, state: int):
        self._state = state
        self._action_stack.setCurrentIndex(state)

        if state == self.IDLE:
            self._banner_title.setText("Record")
            self._status_label.setText("Ready to record")
            self._status_label.setStyleSheet(f"color: {_MUTED}; font-size: 12px; font-weight: bold;")
            self._frames_label.setText("")
            self._settings_widget.setEnabled(True)

        elif state == self.RECORDING:
            self._banner_title.setText("● Recording…")
            self._status_label.setStyleSheet(f"color: {_REC}; font-size: 12px; font-weight: bold;")
            self._settings_widget.setEnabled(False)   # lock settings during capture

        elif state == self.STOPPED:
            self._banner_title.setText("Record — stopped")
            self._status_label.setStyleSheet(
                f"color: {_MUTED}; font-size: 12px; font-weight: bold;"
            )
            self._settings_widget.setEnabled(False)

    def show_idle(self):
        """Reset to idle state (before any recording)."""
        self._clock.stop()
        self._elapsed_sec = 0
        self._frame_count = 0
        self._apply_state(self.IDLE)
        self._status_label.setText("Ready to record")
        self._frames_label.setText("")

    def show_recording(self):
        """Switch to active-recording state and start the wall clock."""
        self._elapsed_sec = 0
        self._frame_count = 0
        self._apply_state(self.RECORDING)
        self._update_status()
        self._clock.start()

    def show_stopped(self):
        """Freeze the clock and show Save / Discard."""
        self._clock.stop()
        self._apply_state(self.STOPPED)
        self._status_label.setText(
            f"Stopped — {self._format_time(self._elapsed_sec)}  ·  {self._frame_count} frames"
        )
        self._frames_label.setText("")

    def update_frame_count(self, count: int):
        self._frame_count = count
        self._frames_label.setText(f"{count} frames")

    # ── Convenience accessors ─────────────────────────────────────────────────

    def current_fps(self) -> int:
        return {0: 24, 1: 30, 2: 60}.get(self.fps_combo.currentIndex(), 30)

    def current_resolution(self) -> str:
        return self.res_combo.currentText().lower()

    def current_speed(self) -> float:
        return float(self.speed_slider.value())

    def current_direction(self) -> int:
        return -1 if self._dir_left_btn.isChecked() else 1

    def rotate_enabled(self) -> bool:
        return self._rotate_cb.isChecked()

    # ── Internal slots ────────────────────────────────────────────────────────

    def _tick_clock(self):
        self._elapsed_sec += 1
        self._update_status()

    def _update_status(self):
        self._status_label.setText(f"● REC  {self._format_time(self._elapsed_sec)}")

    @staticmethod
    def _format_time(secs: int) -> str:
        m, s = divmod(secs, 60)
        return f"{m:02d}:{s:02d}"

    def _on_speed_changed(self, value: int):
        self._speed_val_label.setText(f"{value}°/sec")
        self.speed_changed.emit(float(value))

    def _set_direction(self, direction: int):
        left_active = (direction == -1)
        self._dir_left_btn.setChecked(left_active)
        self._dir_right_btn.setChecked(not left_active)
        self._dir_left_btn.setStyleSheet(self._dir_btn_style(left_active))
        self._dir_right_btn.setStyleSheet(self._dir_btn_style(not left_active))
        self.direction_changed.emit(direction)

    # ── Style helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _muted(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        return lbl

    def _add_section_label(self, layout, text: str):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;"
        )
        layout.addWidget(lbl)

    def _combo_style(self) -> str:
        return f"""
            QComboBox {{
                background-color: {default_theme.background};
                color: {_TEXT}; border: 1px solid {_BORD};
                border-radius: 5px; padding: 3px 8px;
                font-size: 11px; min-width: 90px;
            }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{
                background-color: {default_theme.card_background};
                color: {_TEXT}; border: 1px solid {_BORD};
                selection-background-color: {default_theme.button_primary};
                selection-color: #ffffff;
            }}
        """

    def _slider_style(self) -> str:
        return f"""
            QSlider::groove:horizontal {{
                height: 4px; background: {_BORD}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {_REC}; border: none;
                width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{
                background: {_REC}; border-radius: 2px;
            }}
        """

    def _dir_btn_style(self, active: bool) -> str:
        bg = _REC if active else "transparent"
        color = "#ffffff" if active else _MUTED
        border = _REC if active else _BORD
        return f"""
            QPushButton {{
                background-color: {bg}; color: {color};
                border: 1px solid {border}; border-radius: 5px;
                font-size: 11px; padding: 2px 8px;
            }}
        """
