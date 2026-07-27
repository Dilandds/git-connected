"""
ValidationWidget — top-level screen for the Validation tab.
"""
from typing import List

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSplitter,
)
from PyQt5.QtCore import Qt, pyqtSignal

from ui.styles import make_font
from ui.modal_utils import MessageModal

from .models import ValidationSession, _default_session
from .shared import _BG, _BORDER, _TEXT, _MUTED, _ACCENT, _BTN_PRIMARY, _TAB_ACTIVE, _TAB_INACTIVE
from .panels import PreparationPanel, ReportPanel
from .signature import SignatureBar
from i18n import t


class ValidationWidget(QWidget):

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sessions: List[ValidationSession] = [_default_session(1)]
        self._current_idx = 0
        self._next_id = 2
        self.setStyleSheet(f"background-color: {_BG};")
        self._build_ui()
        self._refresh_tabs()
        self._load_session(0)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── title bar ──
        top = QWidget()
        top.setFixedHeight(46)
        top.setStyleSheet(f"background-color: {_BG}; border-bottom: 1px solid {_BORDER};")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 0, 16, 0)
        title = QLabel(t("project.validation.title"))
        title.setFont(make_font(size=15, bold=True))
        title.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        subtitle = QLabel(t("project.validation.subtitle"))
        subtitle.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
        t_col = QVBoxLayout()
        t_col.setSpacing(1)
        t_col.addWidget(title)
        t_col.addWidget(subtitle)
        tl.addLayout(t_col)
        tl.addStretch()
        new_btn = QPushButton(t("project.validation.new_session"))
        new_btn.setStyleSheet(_BTN_PRIMARY)
        new_btn.setFixedHeight(30)
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.clicked.connect(self._add_session)
        tl.addWidget(new_btn)
        root.addWidget(top)

        # ── session tabs ──
        self._tabs_bar = QWidget()
        self._tabs_bar.setStyleSheet(f"background-color: {_BG}; border-bottom: 2px solid {_BORDER};")
        self._tabs_bar.setFixedHeight(40)
        self._tabs_layout = QHBoxLayout(self._tabs_bar)
        self._tabs_layout.setContentsMargins(12, 5, 12, 5)
        self._tabs_layout.setSpacing(6)
        self._tabs_layout.addStretch()
        root.addWidget(self._tabs_bar)

        # ── horizontal splitter ──
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {_BORDER}; width: 1px; }}"
        )
        self._prep_panel   = PreparationPanel()
        self._report_panel = ReportPanel()
        self._prep_panel.changed.connect(self.changed)
        self._report_panel.changed.connect(self.changed)
        self._splitter.addWidget(self._prep_panel)
        self._splitter.addWidget(self._report_panel)
        self._splitter.setSizes([460, 580])
        root.addWidget(self._splitter, 1)

        # ── signature bar ──
        self._sig_bar = SignatureBar()
        self._sig_bar.signed.connect(self._on_signed)
        root.addWidget(self._sig_bar)

    def update_cost_summary(self, summary: list, currency: str, target_budget: float = 0.0):
        """Push Estimated Cost best-partner data into the preparation panel."""
        self._prep_panel.update_cost_summary(summary, currency, target_budget)

    # ── session management ────────────────────────────────────────────────────

    def _refresh_tabs(self):
        while self._tabs_layout.count():
            item = self._tabs_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, session in enumerate(self._sessions):
            is_active = (i == self._current_idx)
            label = ("🔒  " if session.locked else "") + session.display_name()

            # Compound tab: [label btn] [× btn]
            tab_w = QWidget()
            tab_w.setStyleSheet("background: transparent;")
            tab_l = QHBoxLayout(tab_w)
            tab_l.setContentsMargins(0, 0, 0, 0)
            tab_l.setSpacing(0)

            name_btn = QPushButton(label)
            name_btn.setFixedHeight(28)
            name_btn.setCursor(Qt.PointingHandCursor)
            name_btn.clicked.connect(lambda _, idx=i: self._load_session(idx))

            del_btn = QPushButton("×")
            del_btn.setFixedSize(22, 28)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.clicked.connect(lambda _, idx=i: self._delete_session(idx))

            if is_active:
                name_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {_ACCENT}; color: white; border: none;
                        border-top-left-radius: 5px; border-bottom-left-radius: 5px;
                        border-top-right-radius: 0px; border-bottom-right-radius: 0px;
                        padding: 5px 10px 5px 14px; font-size: 15px; font-weight: bold;
                    }}
                """)
                del_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {_ACCENT}; color: rgba(255,255,255,180); border: none;
                        border-top-right-radius: 5px; border-bottom-right-radius: 5px;
                        border-top-left-radius: 0px; border-bottom-left-radius: 0px;
                        font-size: 14px; font-weight: bold; padding: 0;
                    }}
                    QPushButton:hover {{ color: white; background-color: #ef4444; }}
                """)
            else:
                name_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent; color: {_MUTED};
                        border: 1px solid {_BORDER}; border-right: none;
                        border-top-left-radius: 5px; border-bottom-left-radius: 5px;
                        border-top-right-radius: 0px; border-bottom-right-radius: 0px;
                        padding: 5px 10px 5px 14px; font-size: 15px;
                    }}
                    QPushButton:hover {{ color: {_TEXT}; border-color: {_BORDER}; background-color: #e8f0fe; }}
                """)
                del_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent; color: {_MUTED};
                        border: 1px solid {_BORDER}; border-left: none;
                        border-top-right-radius: 5px; border-bottom-right-radius: 5px;
                        border-top-left-radius: 0px; border-bottom-left-radius: 0px;
                        font-size: 14px; font-weight: bold; padding: 0;
                    }}
                    QPushButton:hover {{ color: white; background-color: #ef4444; border-color: #ef4444; }}
                """)

            tab_l.addWidget(name_btn)
            tab_l.addWidget(del_btn)
            self._tabs_layout.addWidget(tab_w)

        self._tabs_layout.addStretch()

    def _load_session(self, idx: int):
        if 0 <= self._current_idx < len(self._sessions):
            self._prep_panel.sync_to_session()
            self._report_panel.sync_to_session()

        self._current_idx = idx
        session = self._sessions[idx]
        self._prep_panel.load_session(session)
        self._report_panel.load_session(session)
        self._sig_bar.set_signature(session.signature, session.locked)
        if session.locked:
            self._prep_panel.lock()
            self._report_panel.lock()
        self._refresh_tabs()

    def _add_session(self):
        s = _default_session(self._next_id)
        self._next_id += 1
        self._sessions.append(s)
        self._load_session(len(self._sessions) - 1)
        self.changed.emit()

    def _delete_session(self, idx: int):
        session = self._sessions[idx]

        if len(self._sessions) <= 1:
            dlg = MessageModal(self, t("project.validation.delete_session_title"),
                               t("project.validation.cannot_delete_last"),
                               theme='light', primary_text=t("common.ok"))
            dlg.primary_btn.clicked.connect(dlg.accept)
            dlg.exec_()
            return

        if session.locked:
            dlg = MessageModal(self, t("project.validation.delete_session_title"),
                               t("project.validation.cannot_delete_locked"),
                               theme='light', primary_text=t("common.ok"))
            dlg.primary_btn.clicked.connect(dlg.accept)
            dlg.exec_()
            return

        dlg = MessageModal(
            self,
            t("project.validation.delete_session_title"),
            t("project.validation.delete_session_body").format(name=session.display_name()),
            theme='light',
            primary_text=t("project.validation.delete_session_btn"),
            secondary_text=t("common.cancel"),
        )
        dlg.primary_btn.setStyleSheet(
            dlg.primary_btn.styleSheet() +
            "QPushButton { background-color: #ef4444; }"
            "QPushButton:hover { background-color: #dc2626; }"
        )
        dlg.primary_btn.clicked.connect(dlg.accept)
        dlg.secondary_btn.clicked.connect(dlg.reject)
        if dlg.exec_() != dlg.Accepted:
            return

        self._sessions.pop(idx)
        new_idx = min(idx, len(self._sessions) - 1)
        self._current_idx = new_idx
        self._load_session(new_idx)
        self.changed.emit()

    def _on_signed(self, sig: str):
        dlg = MessageModal(
            self,
            t("project.validation.sign_confirm_title").format(sig=sig),
            t("project.validation.sign_confirm_body"),
            theme='light',
            primary_text=t("project.validation.sign_btn"),
            secondary_text=t("common.cancel"),
        )
        dlg.primary_btn.clicked.connect(dlg.accept)
        dlg.secondary_btn.clicked.connect(dlg.reject)
        if dlg.exec_() != dlg.Accepted:
            return
        self._prep_panel.sync_to_session()
        self._report_panel.sync_to_session()
        session = self._sessions[self._current_idx]
        session.signature = sig
        session.locked = True
        self._sig_bar.set_signature(sig, True)
        self._prep_panel.lock()
        self._report_panel.lock()
        self._refresh_tabs()
        self.changed.emit()

    # ── serialisation ─────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        self._prep_panel.sync_to_session()
        self._report_panel.sync_to_session()

        def _ser_stk(s: 'Stakeholder') -> dict:
            return {"id": s.id, "role": s.role, "name": s.name,
                    "responsibility": s.responsibility, "status": s.status,
                    "progress": s.progress, "deliverables": s.deliverables,
                    "comments": s.comments}

        def _ser_mod(m: 'ModificationRow') -> dict:
            return {"description": m.description, "priority": m.priority,
                    "responsible": m.responsible, "due_date": m.due_date,
                    "status": m.status}

        def _ser_action(a: 'ActionRow') -> dict:
            return {"department": a.department, "actions": a.actions,
                    "deliverables": a.deliverables, "responsible": a.responsible,
                    "due_date": a.due_date, "status": a.status}

        def _ser_session(sess: ValidationSession) -> dict:
            return {
                "id": sess.id, "date": sess.date,
                "locked": sess.locked, "signature": sess.signature,
                "stakeholders":      [_ser_stk(s)    for s in sess.stakeholders],
                "modifications":     [_ser_mod(m)    for m in sess.modifications],
                "action_plan":       [_ser_action(a) for a in sess.action_plan],
                "overall_decision":  sess.overall_decision,
                "present_attendees": sess.present_attendees,
                "attendees_remarks": sess.attendees_remarks,
                "decision_maker":    sess.decision_maker,
                "presentation_lead": sess.presentation_lead,
                "ceo_feedback":      sess.ceo_feedback,
                "risks":             sess.risks,
                "open_comments":     sess.open_comments,
                "meeting_date":      sess.meeting_date,
                "meeting_time_from": sess.meeting_time_from,
                "meeting_time_to":   sess.meeting_time_to,
                "meeting_location":  sess.meeting_location,
                "schedule_dates":    sess.schedule_dates,
            }

        return {"sessions": [_ser_session(s) for s in self._sessions]}

    def set_data(self, data: dict):
        from .models import Stakeholder, ModificationRow, ActionRow
        sessions = []
        for sd in data.get("sessions", []):
            sess = ValidationSession(
                id=sd["id"], date=sd.get("date", ""),
                locked=sd.get("locked", False),
                signature=sd.get("signature", ""),
            )
            sess.stakeholders = [
                Stakeholder(**{k: v for k, v in s.items()})
                for s in sd.get("stakeholders", [])
            ]
            sess.modifications = [
                ModificationRow(**{k: v for k, v in m.items()})
                for m in sd.get("modifications", [])
            ]
            sess.action_plan = [
                ActionRow(**{k: v for k, v in a.items()})
                for a in sd.get("action_plan", [])
            ]
            sess.overall_decision   = sd.get("overall_decision", "")
            sess.present_attendees  = sd.get("present_attendees", "")
            sess.attendees_remarks  = sd.get("attendees_remarks", "")
            sess.decision_maker     = sd.get("decision_maker", "")
            sess.presentation_lead  = sd.get("presentation_lead", "")
            sess.ceo_feedback       = sd.get("ceo_feedback", "")
            sess.risks              = sd.get("risks", "")
            sess.open_comments      = sd.get("open_comments", "")
            sess.meeting_date       = sd.get("meeting_date", "")
            sess.meeting_time_from  = sd.get("meeting_time_from", "")
            sess.meeting_time_to    = sd.get("meeting_time_to", "")
            sess.meeting_location   = sd.get("meeting_location", "")
            sess.schedule_dates     = sd.get("schedule_dates", [""] * 7)
            sessions.append(sess)

        if not sessions:
            # Without this fallback, loading data with no sessions (e.g.
            # New Project) left the previous project's sessions/panels
            # displayed, since the block below never ran — mirror the same
            # fresh-state default used in __init__.
            sessions = [_default_session(1)]
        self._sessions    = sessions
        self._next_id     = max(s.id for s in sessions) + 1
        self._current_idx = 0
        self._load_session(0)
