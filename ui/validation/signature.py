"""
SignatureBar — bottom bar for digital sign-off on a validation session.
"""
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, pyqtSignal

from .shared import _CARD, _BORDER, _TEXT, _MUTED, _TOOLTIP_STYLE
from i18n import t


class SignatureBar(QWidget):

    signed = pyqtSignal(str)

    @property
    def _SIG_BTN(self):
        return {
            t("project.validation.sig_approved"):   ("#16a34a", "#15803d"),
            t("project.validation.sig_rejected"):   ("#dc2626", "#b91c1c"),
            t("project.validation.sig_correction"): ("#d97706", "#b45309"),
        }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setStyleSheet(f"background-color: {_CARD}; border-top: 1px solid {_BORDER};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        sig_lbl = QLabel(t("project.validation.signature_label"))
        sig_lbl.setStyleSheet(
            f"color: {_TEXT}; font-size: 11px; font-weight: bold; background: transparent; border: none;"
        )
        layout.addWidget(sig_lbl)

        self._btns: dict = {}
        for label, (bg, hover) in self._SIG_BTN.items():
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg}; color: white;
                    border: none; border-radius: 5px;
                    padding: 4px 14px; font-size: 11px; font-weight: bold;
                }}
                QPushButton:hover {{ background-color: {hover}; }}
            """ + _TOOLTIP_STYLE)
            btn.clicked.connect(lambda _, l=label: self.signed.emit(l))
            self._btns[label] = btn
            layout.addWidget(btn)

        layout.addStretch()

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"color: {_MUTED}; font-size: 11px; background: transparent; border: none;"
        )
        layout.addWidget(self._status_lbl)

        self._locked_lbl = QLabel("")
        self._locked_lbl.setStyleSheet(
            f"color: #dc2626; font-size: 10px; font-weight: bold; background: transparent; border: none;"
        )
        layout.addWidget(self._locked_lbl)

    def set_signature(self, sig: str, locked: bool):
        self._status_lbl.setText(
            t("project.validation.sig_current").format(sig=sig) if sig else t("project.validation.sig_not_signed")
        )
        self._locked_lbl.setText(t("project.validation.sig_locked") if locked else "")
        for btn in self._btns.values():
            btn.setEnabled(not locked)
