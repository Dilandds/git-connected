"""
PreparationPanel and ReportPanel for the Validation module.
"""
import logging
from typing import List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QGridLayout, QFileDialog, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QDate, QTime, QPoint, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap, QIcon

from ui.styles import make_font

from .models import (
    Stakeholder, ModificationRow, ActionRow, ValidationSession,
    COST_CATEGORIES, COST_CATEGORY_I18N_KEYS,
    SCHEDULE_MILESTONES, MILESTONE_I18N_KEYS,
)
from .shared import (
    _BG, _CARD, _BORDER, _TEXT, _MUTED, _ACCENT,
    _INPUT, _TABLE_STYLE, _BTN_OUTLINE, _BTN_SMALL,
    _TIMEEDIT_STYLE, _COMBO_STYLE, _ARROW_URL,
    _sep, _vdiv, _card_frame, _section_title, _lbl, _combo,
    _ProgressCell,
)
from i18n import t, on_language_changed

logger = logging.getLogger(__name__)


# ── Photo button with hover zoom preview ──────────────────────────────────────

class _PhotoButton(QPushButton):
    """Photo upload button that shows a large floating preview when hovering over a loaded photo."""

    _PREVIEW_W = 340
    _PREVIEW_H = 300

    def __init__(self, w: int, h: int, parent=None):
        super().__init__(parent)
        self._photo_path = ""
        self._preview: Optional[QLabel] = None
        self.setFixedSize(w, h)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_empty_style()

    def _apply_empty_style(self):
        self.setText(t("project.validation.add_photo"))
        self.setIcon(QIcon())
        self.setStyleSheet(f"""
            QPushButton {{
                background: #f1f3f5; border: 1px dashed {_BORDER};
                border-radius: 6px; color: {_MUTED}; font-size: 14px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
        """)

    def set_photo(self, path: str):
        self._photo_path = path
        if not path:
            self._apply_empty_style()
            return
        pix = QPixmap(path)
        if pix.isNull():
            self._apply_empty_style()
            return
        self.setIcon(QIcon(pix.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)))
        self.setIconSize(self.size())
        self.setText("")
        self.setStyleSheet(f"""
            QPushButton {{
                background: #f1f3f5; border: 1px solid {_BORDER}; border-radius: 6px;
            }}
            QPushButton:hover {{ border: 2px solid {_ACCENT}; }}
        """)

    def enterEvent(self, event):
        if self._photo_path:
            self._show_preview()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hide_preview()
        super().leaveEvent(event)

    def _show_preview(self):
        pix = QPixmap(self._photo_path)
        if pix.isNull():
            return

        if self._preview is None:
            self._preview = QLabel()
            self._preview.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
            self._preview.setStyleSheet("""
                QLabel {
                    background: white;
                    border: 1px solid #d1d5db;
                    border-radius: 8px;
                    padding: 5px;
                }
            """)

        scaled = pix.scaled(self._PREVIEW_W, self._PREVIEW_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._preview.setPixmap(scaled)
        self._preview.setFixedSize(scaled.width() + 10, scaled.height() + 10)

        # Position to the right of the button; fall back to left if near screen edge
        from PyQt5.QtWidgets import QApplication
        global_pos = self.mapToGlobal(QPoint(self.width() + 6, 0))
        screen = QApplication.screenAt(global_pos)
        if screen:
            sr = screen.geometry()
            if global_pos.x() + self._preview.width() > sr.right():
                global_pos = self.mapToGlobal(QPoint(-(self._preview.width() + 6), 0))
            if global_pos.y() + self._preview.height() > sr.bottom():
                global_pos.setY(sr.bottom() - self._preview.height() - 4)

        self._preview.move(global_pos)
        self._preview.show()
        self._preview.raise_()

    def _hide_preview(self):
        if self._preview:
            self._preview.hide()


# ── Preparation Panel ─────────────────────────────────────────────────────────

class PreparationPanel(QScrollArea):

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session: Optional[ValidationSession] = None
        self._progress_cells: List[_ProgressCell] = []
        self._milestone_name_labels: List[QLabel] = []
        self._read_only = False

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(f"""
            QScrollArea {{ background: {_BG}; border: none; }}
            QScrollBar:vertical {{ background: {_BG}; width: 12px; border-radius: 6px; }}
            QScrollBar::handle:vertical {{ background: {_ACCENT}; border-radius: 6px; min-height: 30px; }}
        """)
        self._body = QWidget()
        self._body.setStyleSheet(f"background: {_BG};")
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(14)
        self.setWidget(self._body)
        self._build_static()
        on_language_changed(self._update_texts)

    def _build_static(self):
        hdr = QLabel(t("project.validation.prep_header"))
        hdr.setFont(make_font(size=14, bold=True))
        hdr.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none; padding-bottom: 4px;")
        self._layout.addWidget(hdr)

        # ── 1. Stakeholders & Contributors ──────────────────────────────────
        card = _card_frame()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(8)

        sh = QHBoxLayout()
        sh.addWidget(_section_title(t("project.validation.stakeholders")))
        self._add_contributor_btn = QPushButton(t("project.validation.add_contributor"))
        self._add_contributor_btn.setStyleSheet(_BTN_OUTLINE)
        self._add_contributor_btn.setCursor(Qt.PointingHandCursor)
        self._add_contributor_btn.clicked.connect(self._add_stakeholder)
        sh.addStretch()
        sh.addWidget(self._add_contributor_btn)
        cl.addLayout(sh)
        cl.addWidget(_sep())

        self._stakeholder_table = QTableWidget(0, 7)
        self._stakeholder_table.setHorizontalHeaderLabels([
            t("project.validation.col_role"),
            t("project.validation.col_name_company"),
            t("project.validation.col_responsibility"),
            t("project.validation.col_status"),
            t("project.validation.col_progress"),
            t("project.validation.col_deliverables"),
            t("project.validation.col_comments"),
        ])
        self._stakeholder_table.setStyleSheet(_TABLE_STYLE)
        hdr_h = self._stakeholder_table.horizontalHeader()
        hdr_h.setSectionResizeMode(QHeaderView.Interactive)
        hdr_h.setStretchLastSection(True)
        hdr_h.setMinimumSectionSize(50)
        for col, w in enumerate([80, 120, 140, 148, 96, 120]):
            self._stakeholder_table.setColumnWidth(col, w)
        self._stakeholder_table.verticalHeader().setDefaultSectionSize(44)
        self._stakeholder_table.verticalHeader().setVisible(False)
        self._stakeholder_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._stakeholder_table.setAlternatingRowColors(True)
        self._stakeholder_table.setMinimumHeight(220)
        self._stakeholder_table.itemChanged.connect(lambda: self.changed.emit())
        cl.addWidget(self._stakeholder_table)
        self._layout.addWidget(card)

        # ── 2. Presentation Elements ────────────────────────────────────────
        card2 = _card_frame()
        cl2 = QVBoxLayout(card2)
        cl2.setContentsMargins(14, 12, 14, 12)
        cl2.setSpacing(8)
        cl2.addWidget(_section_title(t("project.validation.presentation")))
        cl2.addWidget(_sep())

        grid = QGridLayout()
        grid.setSpacing(10)
        self._photo_btns:   List[QPushButton] = []
        self._photo_labels: List[QLineEdit]   = []

        for i in range(8):
            btn = _PhotoButton(112, 88)
            btn.clicked.connect(lambda _, idx=i: self._upload_photo(idx))

            lbl_inp = QLineEdit()
            lbl_inp.setPlaceholderText(t("project.validation.photo_placeholder"))
            lbl_inp.setFixedWidth(112)
            lbl_inp.setStyleSheet(_INPUT)
            lbl_inp.textChanged.connect(lambda _: self.changed.emit())

            col = i % 4
            row = (i // 4) * 2
            grid.addWidget(btn,     row,     col)
            grid.addWidget(lbl_inp, row + 1, col)
            self._photo_btns.append(btn)
            self._photo_labels.append(lbl_inp)

        cl2.addLayout(grid)
        self._layout.addWidget(card2)

        # ── 3. Estimated Cost & Lead Time ───────────────────────────────────
        card3 = _card_frame()
        cl3 = QVBoxLayout(card3)
        cl3.setContentsMargins(14, 12, 14, 12)
        cl3.setSpacing(8)

        hdr3 = QHBoxLayout()
        hdr3.addWidget(_section_title(t("project.validation.cost_section")))
        hdr3.addStretch()
        auto_note = QLabel(t("project.validation.cost_auto_note"))
        auto_note.setStyleSheet(
            f"color: {_MUTED}; font-size: 13px; background: transparent; border: none; font-style: italic;"
        )
        hdr3.addWidget(auto_note)
        cl3.addLayout(hdr3)
        cl3.addWidget(_sep())

        split = QHBoxLayout()
        split.setSpacing(16)

        # Left — cost table
        cost_side = QVBoxLayout()
        cost_side.setSpacing(6)
        cost_cap = QLabel(t("project.validation.cost_caption"))
        cost_cap.setStyleSheet(f"color: {_MUTED}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        cost_side.addWidget(cost_cap)

        self._cost_table = QTableWidget(len(COST_CATEGORIES) + 3, 2)
        self._cost_table.setHorizontalHeaderLabels([t("project.validation.col_category"), t("project.validation.col_amount")])
        self._cost_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._cost_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self._cost_table.setColumnWidth(1, 90)
        self._cost_table.verticalHeader().setVisible(False)
        self._cost_table.setMinimumHeight(240)
        self._cost_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._cost_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._cost_table.setStyleSheet(_TABLE_STYLE)

        for i, key in enumerate(COST_CATEGORY_I18N_KEYS):
            self._cost_table.setItem(i, 0, QTableWidgetItem(t(key)))
            self._cost_table.setItem(i, 1, QTableWidgetItem("—"))

        total_row = len(COST_CATEGORIES)
        bold_font = make_font(size=11, bold=True)
        for col, txt in enumerate([t("project.validation.total_est"), "—"]):
            it = QTableWidgetItem(txt)
            it.setFont(bold_font)
            it.setBackground(QColor("#f1f3f5"))
            self._cost_table.setItem(total_row, col, it)

        self._cost_table.setItem(total_row + 1, 0, QTableWidgetItem(t("project.validation.target_budget")))
        self._cost_table.setItem(total_row + 1, 1, QTableWidgetItem("—"))
        var_label = QTableWidgetItem(t("project.validation.variance"))
        var_label.setForeground(QColor(_MUTED))
        var_value = QTableWidgetItem("—")
        var_value.setForeground(QColor("#22c55e"))
        self._cost_table.setItem(total_row + 2, 0, var_label)
        self._cost_table.setItem(total_row + 2, 1, var_value)

        cost_side.addWidget(self._cost_table)
        split.addLayout(cost_side, 3)
        split.addWidget(_vdiv())

        # Right — schedule milestones
        sched_side = QVBoxLayout()
        sched_side.setSpacing(6)
        sched_cap = QLabel(t("project.validation.schedule_caption"))
        sched_cap.setStyleSheet(f"color: {_MUTED}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        sched_side.addWidget(sched_cap)

        self._milestone_indicators: List[QLabel] = []
        self._milestone_date_edits: List         = []
        _NULL_DATE = QDate(2000, 1, 1)

        from ui.date_picker import EctoDateEdit
        for idx, key in enumerate(MILESTONE_I18N_KEYS):
            row_w = QWidget()
            row_w.setStyleSheet("background: transparent;")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 2, 0, 2)
            row_l.setSpacing(6)

            dot = QLabel("○")
            dot.setFixedWidth(14)
            dot.setStyleSheet(f"color: {_MUTED}; font-size: 13px; background: transparent; border: none;")

            name_lbl = QLabel(t(key))
            name_lbl.setFixedWidth(120)
            name_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 14px; background: transparent; border: none;")

            de = EctoDateEdit(QDate.currentDate())
            de.setFixedHeight(24)
            de.setFixedWidth(100)
            de.dateChanged.connect(lambda d, i=idx: self._on_milestone_date_changed(i, d))
            de.dateChanged.connect(lambda _: self.changed.emit())

            row_l.addWidget(dot)
            row_l.addWidget(name_lbl)
            row_l.addWidget(de)
            sched_side.addWidget(row_w)
            self._milestone_indicators.append(dot)
            self._milestone_name_labels.append(name_lbl)
            self._milestone_date_edits.append(de)

        sched_side.addStretch()
        split.addLayout(sched_side, 2)
        cl3.addLayout(split)
        self._layout.addWidget(card3)
        self._layout.addStretch()

    # ── language ───────────────────────────────────────────────────────────────

    def _update_texts(self):
        for lbl, key in zip(self._milestone_name_labels, MILESTONE_I18N_KEYS):
            lbl.setText(t(key))
        for i, key in enumerate(COST_CATEGORY_I18N_KEYS):
            item = self._cost_table.item(i, 0)
            if item:
                item.setText(t(key))
        for btn in self._photo_btns:
            if not btn._photo_path:
                btn._apply_empty_style()

    # ── public ─────────────────────────────────────────────────────────────────

    def lock(self):
        self._add_contributor_btn.setEnabled(False)
        self._stakeholder_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for row in range(self._stakeholder_table.rowCount()):
            combo = self._stakeholder_table.cellWidget(row, 3)
            if combo:
                combo.setEnabled(False)
            pc = self._stakeholder_table.cellWidget(row, 4)
            if pc:
                pc._spin.setEnabled(False)
        for btn in self._photo_btns:
            btn.setEnabled(False)
            btn.setStyleSheet(btn.styleSheet() + "QPushButton { opacity: 0.5; }")
        for de in self._milestone_date_edits:
            de.setEnabled(False)

    def unlock(self):
        """Reverse of lock() — control-for-control mirror. Only ever called
        by set_read_only() below, which already folds in the session's own
        business .locked flag, so calling this directly would bypass that."""
        self._add_contributor_btn.setEnabled(True)
        self._stakeholder_table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        for row in range(self._stakeholder_table.rowCount()):
            combo = self._stakeholder_table.cellWidget(row, 3)
            if combo:
                combo.setEnabled(True)
            pc = self._stakeholder_table.cellWidget(row, 4)
            if pc:
                pc._spin.setEnabled(True)
        for btn in self._photo_btns:
            btn.setEnabled(True)
            # set_photo() fully replaces the stylesheet (rather than
            # appending), which cleanly drops the "opacity: 0.5" fragment
            # lock() tacked on above.
            btn.set_photo(btn._photo_path)
        for de in self._milestone_date_edits:
            de.setEnabled(True)

    def set_read_only(self, read_only: bool):
        """Two-way toggle for the app-wide read-only mode (see
        core/file_lock.py / TheProjectWidget._update_read_only_ui), kept
        independent of ValidationSession.locked — the signing/workflow
        flag ValidationWidget already drives lock() with. A control here
        ends up disabled if EITHER read_only is True OR the loaded session
        is separately locked/signed, so calling this with False never
        re-enables a signed session. Never touches self.setEnabled() —
        this class IS the QScrollArea; disabling it would break scrolling,
        which is the exact bug this method exists to avoid."""
        self._read_only = read_only
        effective_locked = read_only or bool(self._session and self._session.locked)
        if effective_locked:
            self.lock()
        else:
            self.unlock()

    def _on_milestone_date_changed(self, idx: int, date: QDate):
        dot = self._milestone_indicators[idx]
        null = QDate(2000, 1, 1)
        if date == null:
            dot.setText("○")
            dot.setStyleSheet(f"color: {_MUTED}; font-size: 13px; background: transparent; border: none;")
        elif date <= QDate.currentDate():
            dot.setText("✓")
            dot.setStyleSheet("color: #22c55e; font-size: 13px; background: transparent; border: none;")
        else:
            dot.setText("○")
            dot.setStyleSheet(f"color: {_ACCENT}; font-size: 13px; background: transparent; border: none;")

    def load_session(self, session: ValidationSession):
        self._session = session
        self._reload_stakeholders()
        self._reload_schedule()

    def _reload_schedule(self):
        if not self._session:
            return
        null = QDate(2000, 1, 1)
        dates = self._session.schedule_dates or [""] * len(SCHEDULE_MILESTONES)
        for i, (de, raw) in enumerate(zip(self._milestone_date_edits, dates)):
            de.blockSignals(True)
            if raw:
                d = QDate.fromString(raw, "dd/MM/yyyy")
                de.setDate(d if d.isValid() else null)
            else:
                de.setDate(null)
            de.blockSignals(False)
            self._on_milestone_date_changed(i, de.date())

    def update_cost_summary(self, summary: list, currency: str, target_budget: float = 0.0):
        """Rebuild the cost table from Estimated Cost best-partner data."""
        _symbols = {
            "EUR": "€", "USD": "$", "GBP": "£", "CHF": "Fr",
            "JPY": "¥", "CNY": "¥", "AED": "د.إ", "CAD": "$", "AUD": "$",
        }
        sym = _symbols.get(currency, currency + " ")
        n = len(summary)
        self._cost_table.setRowCount(n + 3)

        grand_total = 0.0
        for i, item in enumerate(summary):
            self._cost_table.setItem(i, 0, QTableWidgetItem(item.get("trade", f"Trade {i+1}")))
            cost = item.get("total_cost", 0.0)
            grand_total += cost
            self._cost_table.setItem(i, 1, QTableWidgetItem(f"{sym}{cost:,.2f}"))

        total_row = n
        bold_font = make_font(size=11, bold=True)
        for col, txt in enumerate([t("project.validation.total_est"), f"{sym}{grand_total:,.2f}"]):
            it = QTableWidgetItem(txt)
            it.setFont(bold_font)
            it.setBackground(QColor("#f1f3f5"))
            self._cost_table.setItem(total_row, col, it)

        budget_text = f"{sym}{target_budget:,.2f}" if target_budget > 0 else "—"
        self._cost_table.setItem(total_row + 1, 0, QTableWidgetItem(t("project.validation.target_budget")))
        budget_item = QTableWidgetItem(budget_text)
        budget_item.setFont(bold_font if target_budget > 0 else make_font(size=11))
        self._cost_table.setItem(total_row + 1, 1, budget_item)

        var_label = QTableWidgetItem(t("project.validation.variance"))
        var_label.setForeground(QColor(_MUTED))
        self._cost_table.setItem(total_row + 2, 0, var_label)
        if target_budget > 0 and grand_total > 0:
            variance = grand_total - target_budget
            pct      = (variance / target_budget) * 100
            sign     = "+" if variance >= 0 else ""
            var_text = f"{sign}{sym}{abs(variance):,.2f}  ({sign}{pct:.1f}%)"
            var_item = QTableWidgetItem(var_text)
            var_item.setForeground(QColor("#ef4444" if variance > 0 else "#22c55e"))
            var_item.setFont(bold_font)
        else:
            var_item = QTableWidgetItem("—")
            var_item.setForeground(QColor("#22c55e"))
        self._cost_table.setItem(total_row + 2, 1, var_item)

    def sync_to_session(self):
        if not self._session:
            return
        s = self._session
        null = QDate(2000, 1, 1)
        s.schedule_dates = [
            (de.date().toString("dd/MM/yyyy") if de.date() != null else "")
            for de in self._milestone_date_edits
        ]
        s.stakeholders = []
        for row in range(self._stakeholder_table.rowCount()):
            stk = Stakeholder(id=row + 1)
            for col, attr in enumerate(["role", "name", "responsibility"]):
                item = self._stakeholder_table.item(row, col)
                setattr(stk, attr, item.text() if item else "")
            combo = self._stakeholder_table.cellWidget(row, 3)
            stk.status = combo.currentText() if combo else "In progress"
            pc = self._stakeholder_table.cellWidget(row, 4)
            stk.progress = pc.value() if pc else 0
            for col, attr in enumerate(["deliverables", "comments"], start=5):
                item = self._stakeholder_table.item(row, col)
                setattr(stk, attr, item.text() if item else "")
            s.stakeholders.append(stk)

    # ── internals ──────────────────────────────────────────────────────────────

    def _reload_stakeholders(self):
        self._progress_cells.clear()
        self._stakeholder_table.blockSignals(True)
        self._stakeholder_table.setRowCount(0)
        if self._session:
            for stk in self._session.stakeholders:
                self._add_stakeholder_row(stk)
        self._stakeholder_table.blockSignals(False)

    def _add_stakeholder_row(self, stk: Stakeholder):
        row = self._stakeholder_table.rowCount()
        self._stakeholder_table.insertRow(row)
        self._stakeholder_table.setRowHeight(row, 44)

        for col, val in enumerate([stk.role, stk.name, stk.responsibility]):
            self._stakeholder_table.setItem(row, col, QTableWidgetItem(val))

        status_combo = _combo([
            t("project.validation.status_in_progress"),
            t("project.validation.status_not_started"),
            t("project.validation.status_done"),
            t("project.validation.status_on_hold"),
        ])
        status_combo.setCurrentText(stk.status)
        status_combo.currentTextChanged.connect(lambda v, r=row: self._on_status_change(r, v))
        self._stakeholder_table.setCellWidget(row, 3, status_combo)

        pc = _ProgressCell(stk.progress)
        pc.valueChanged.connect(lambda v, r=row: self._on_progress_change(r, v))
        self._stakeholder_table.setCellWidget(row, 4, pc)
        self._progress_cells.append(pc)

        for col, val in enumerate([stk.deliverables, stk.comments], start=5):
            self._stakeholder_table.setItem(row, col, QTableWidgetItem(val))

    def _add_stakeholder(self):
        if not self._session:
            return
        new_id = max((s.id for s in self._session.stakeholders), default=0) + 1
        stk = Stakeholder(new_id)
        self._session.stakeholders.append(stk)
        self._add_stakeholder_row(stk)
        self.changed.emit()

    def _on_status_change(self, row: int, value: str):
        if self._session and row < len(self._session.stakeholders):
            self._session.stakeholders[row].status = value
            self.changed.emit()

    def _on_progress_change(self, row: int, value: int):
        if self._session and row < len(self._session.stakeholders):
            self._session.stakeholders[row].progress = value
            self.changed.emit()

    def _upload_photo(self, idx: int):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Photo", "", "Images (*.png *.jpg *.jpeg)"
        )
        if path:
            btn = self._photo_btns[idx]
            btn.set_photo(path)
            self.changed.emit()


# ── Report Panel ──────────────────────────────────────────────────────────────

class ReportPanel(QScrollArea):

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session: Optional[ValidationSession] = None
        self._read_only = False
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(f"""
            QScrollArea {{ background: {_BG}; border: none; }}
            QScrollBar:vertical {{ background: {_BG}; width: 12px; border-radius: 6px; }}
            QScrollBar::handle:vertical {{ background: {_ACCENT}; border-radius: 6px; min-height: 30px; }}
        """)
        body = QWidget()
        body.setStyleSheet(f"background: {_BG};")
        self._layout = QVBoxLayout(body)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(12)
        self.setWidget(body)
        self._build_static()

    def _build_static(self):
        hdr = QLabel(t("project.validation.report_header"))
        hdr.setFont(make_font(size=14, bold=True))
        hdr.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none; padding-bottom: 4px;")
        self._layout.addWidget(hdr)

        from PyQt5.QtWidgets import QTimeEdit
        from ui.date_picker import EctoDateEdit

        # ── Row 1: Meeting Info | Overall Decision | Present Attendees | Attendees' Remarks ──
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        meet_card = _card_frame()
        mc = QVBoxLayout(meet_card)
        mc.setContentsMargins(12, 10, 12, 10)
        mc.setSpacing(4)
        mc.addWidget(_section_title(t("project.validation.meeting_info")))
        mc.addWidget(_sep())

        mc.addWidget(_lbl(t("project.validation.date")))
        self._r_date = EctoDateEdit(QDate.currentDate())
        self._r_date.setFixedHeight(26)
        mc.addWidget(self._r_date)

        mc.addWidget(_lbl(t("project.validation.time_from_to")))
        tr = QHBoxLayout()
        self._r_time_from = QTimeEdit(QTime(9, 0))
        self._r_time_to   = QTimeEdit(QTime(10, 0))
        for tw in (self._r_time_from, self._r_time_to):
            tw.setStyleSheet(_TIMEEDIT_STYLE)
            tw.setFixedHeight(26)
        to_lbl = QLabel(t("project.validation.to"))
        to_lbl.setStyleSheet(f"color: {_MUTED}; background: transparent; border: none; font-size: 14px;")
        tr.addWidget(self._r_time_from)
        tr.addWidget(to_lbl)
        tr.addWidget(self._r_time_to)
        mc.addLayout(tr)

        mc.addWidget(_lbl(t("project.validation.location")))
        self._r_location = QLineEdit()
        self._r_location.setPlaceholderText(t("project.validation.location_ph"))
        self._r_location.setStyleSheet(_INPUT)
        self._r_location.setFixedHeight(26)
        mc.addWidget(self._r_location)

        mc.addWidget(_lbl(t("project.validation.decision_maker")))
        self._r_decision_maker = QLineEdit()
        self._r_decision_maker.setPlaceholderText(t("project.validation.name_ph"))
        self._r_decision_maker.setStyleSheet(_INPUT)
        self._r_decision_maker.setFixedHeight(26)
        mc.addWidget(self._r_decision_maker)

        mc.addWidget(_lbl(t("project.validation.presentation_lead")))
        self._r_presentation_lead = QLineEdit()
        self._r_presentation_lead.setPlaceholderText(t("project.validation.name_ph"))
        self._r_presentation_lead.setStyleSheet(_INPUT)
        self._r_presentation_lead.setFixedHeight(26)
        mc.addWidget(self._r_presentation_lead)
        mc.addStretch()
        row1.addWidget(meet_card, 1)

        od_card = _card_frame()
        od = QVBoxLayout(od_card)
        od.setContentsMargins(12, 10, 12, 10)
        od.setSpacing(4)
        od.addWidget(_section_title(t("project.validation.overall_decision")))
        od.addWidget(_sep())
        self._r_overall_decision = QTextEdit()
        self._r_overall_decision.setPlaceholderText(t("project.validation.overall_dec_ph"))
        self._r_overall_decision.setStyleSheet(_INPUT)
        od.addWidget(self._r_overall_decision, 1)
        row1.addWidget(od_card, 1)

        pa_card = _card_frame()
        pa = QVBoxLayout(pa_card)
        pa.setContentsMargins(12, 10, 12, 10)
        pa.setSpacing(4)
        pa.addWidget(_section_title(t("project.validation.present_attendees")))
        pa.addWidget(_sep())
        self._r_attendees = QTextEdit()
        self._r_attendees.setPlaceholderText(t("project.validation.attendees_ph"))
        self._r_attendees.setStyleSheet(_INPUT)
        pa.addWidget(self._r_attendees, 1)
        row1.addWidget(pa_card, 1)

        ar_card = _card_frame()
        ar = QVBoxLayout(ar_card)
        ar.setContentsMargins(12, 10, 12, 10)
        ar.setSpacing(4)
        ar.addWidget(_section_title(t("project.validation.attendees_remarks")))
        ar.addWidget(_sep())
        self._r_attendee_remarks = QTextEdit()
        self._r_attendee_remarks.setPlaceholderText(t("project.validation.remarks_ph"))
        self._r_attendee_remarks.setStyleSheet(_INPUT)
        ar.addWidget(self._r_attendee_remarks, 1)
        row1.addWidget(ar_card, 1)

        self._layout.addLayout(row1)

        # ── CEO Feedback ────────────────────────────────────────────────────
        ceo_card = _card_frame()
        cc = QVBoxLayout(ceo_card)
        cc.setContentsMargins(14, 12, 14, 12)
        cc.setSpacing(6)
        cc.addWidget(_section_title(t("project.validation.ceo_feedback")))
        cc.addWidget(_sep())
        hint = QLabel(t("project.validation.ceo_hint"))
        hint.setStyleSheet(f"color: {_MUTED}; font-size: 14px; background: transparent; border: none;")
        cc.addWidget(hint)
        self._r_ceo_feedback = QTextEdit()
        self._r_ceo_feedback.setPlaceholderText(t("project.validation.ceo_ph"))
        self._r_ceo_feedback.setMinimumHeight(70)
        self._r_ceo_feedback.setStyleSheet(_INPUT)
        cc.addWidget(self._r_ceo_feedback)
        self._layout.addWidget(ceo_card)

        # ── Modifications / Actions Required ────────────────────────────────
        mod_card = _card_frame()
        ml = QVBoxLayout(mod_card)
        ml.setContentsMargins(14, 12, 14, 12)
        ml.setSpacing(8)
        mod_hdr = QHBoxLayout()
        mod_hdr.addWidget(_section_title(t("project.validation.modifications")))
        self._add_mod_btn = QPushButton(t("project.validation.add_row"))
        self._add_mod_btn.setStyleSheet(_BTN_SMALL)
        self._add_mod_btn.setCursor(Qt.PointingHandCursor)
        self._add_mod_btn.clicked.connect(lambda: self._add_modification_row())
        mod_hdr.addStretch()
        mod_hdr.addWidget(self._add_mod_btn)
        ml.addLayout(mod_hdr)
        ml.addWidget(_sep())

        self._mod_table = QTableWidget(0, 6)
        self._mod_table.setHorizontalHeaderLabels([
            t("project.validation.col_id"),
            t("project.validation.col_description"),
            t("project.validation.col_priority"),
            t("project.validation.col_responsible"),
            t("project.validation.col_due_date"),
            t("project.validation.col_status"),
        ])
        self._mod_table.setStyleSheet(_TABLE_STYLE)
        self._mod_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._mod_table.setColumnWidth(0, 36)
        self._mod_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        # Fixed column widths — wide enough for the longest option text
        self._mod_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._mod_table.setColumnWidth(2, 160)   # "To modify"
        for c in range(3, 5):
            self._mod_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Fixed)
        self._mod_table.setColumnWidth(3, 140)   # Responsible
        self._mod_table.setColumnWidth(4, 120)   # Due Date
        self._mod_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self._mod_table.setColumnWidth(5, 165)   # "In progress"
        # Minimum width = sum of all fixed columns + min description column
        # Forces the outer QScrollArea to scroll horizontally instead of squishing
        self._mod_table.setMinimumWidth(36 + 220 + 160 + 140 + 120 + 165)  # = 841 px
        self._mod_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._mod_table.setHorizontalScrollMode(self._mod_table.ScrollPerPixel)
        self._mod_table.setMinimumHeight(140)
        self._mod_table.verticalHeader().setVisible(False)
        self._mod_table.itemChanged.connect(lambda: self.changed.emit())
        ml.addWidget(self._mod_table)
        self._layout.addWidget(mod_card)

        # ── Action Plan ──────────────────────────────────────────────────────
        ap_card = _card_frame()
        al = QVBoxLayout(ap_card)
        al.setContentsMargins(14, 12, 14, 12)
        al.setSpacing(8)
        ap_hdr = QHBoxLayout()
        ap_hdr.addWidget(_section_title(t("project.validation.action_plan")))
        self._add_ap_btn = QPushButton(t("project.validation.add_row"))
        self._add_ap_btn.setStyleSheet(_BTN_SMALL)
        self._add_ap_btn.setCursor(Qt.PointingHandCursor)
        self._add_ap_btn.clicked.connect(lambda: self._add_action_row())
        ap_hdr.addStretch()
        ap_hdr.addWidget(self._add_ap_btn)
        al.addLayout(ap_hdr)
        al.addWidget(_sep())

        self._ap_table = QTableWidget(0, 6)
        self._ap_table.setHorizontalHeaderLabels([
            t("project.validation.col_dept"),
            t("project.validation.col_actions"),
            t("project.validation.col_expected_del"),
            t("project.validation.col_responsible"),
            t("project.validation.col_due_date"),
            t("project.validation.col_status"),
        ])
        self._ap_table.setStyleSheet(_TABLE_STYLE)
        self._ap_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # Status column: fixed width so "In progress" is never clipped
        self._ap_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self._ap_table.setColumnWidth(5, 165)
        self._ap_table.setMinimumWidth(841)
        self._ap_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._ap_table.setHorizontalScrollMode(self._ap_table.ScrollPerPixel)
        self._ap_table.setMinimumHeight(180)
        self._ap_table.verticalHeader().setVisible(False)
        self._ap_table.itemChanged.connect(lambda: self.changed.emit())
        al.addWidget(self._ap_table)
        self._layout.addWidget(ap_card)

        # ── Risks + Open Comments ────────────────────────────────────────────
        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        for title, attr in [(t("project.validation.risks"), "_r_risks"),
                             (t("project.validation.open_comments"), "_r_open_comments")]:
            c = _card_frame()
            cl = QVBoxLayout(c)
            cl.setContentsMargins(14, 10, 14, 10)
            cl.setSpacing(4)
            cl.addWidget(_section_title(title))
            cl.addWidget(_sep())
            ta = QTextEdit()
            ta.setPlaceholderText(f"{title}...")
            ta.setMinimumHeight(80)
            ta.setStyleSheet(_INPUT)
            setattr(self, attr, ta)
            cl.addWidget(ta)
            bottom.addWidget(c)
        self._layout.addLayout(bottom)
        self._layout.addStretch()

    # ── public ─────────────────────────────────────────────────────────────────

    def load_session(self, session: ValidationSession):
        self._session = session
        self._reload_tables()

    def lock(self):
        for w in (self._r_location, self._r_decision_maker, self._r_presentation_lead):
            w.setReadOnly(True)
            w.setStyleSheet(w.styleSheet() + f"QLineEdit {{ background: #f1f3f5; color: {_MUTED}; }}")
        for w in (self._r_overall_decision, self._r_attendees, self._r_attendee_remarks,
                  self._r_ceo_feedback, self._r_risks, self._r_open_comments):
            w.setReadOnly(True)
        self._r_date.setEnabled(False)
        self._r_time_from.setEnabled(False)
        self._r_time_to.setEnabled(False)
        self._mod_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._ap_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._add_mod_btn.setEnabled(False)
        self._add_ap_btn.setEnabled(False)
        for table in (self._mod_table, self._ap_table):
            for row in range(table.rowCount()):
                for col in range(table.columnCount()):
                    w = table.cellWidget(row, col)
                    if w:
                        w.setEnabled(False)

    def unlock(self):
        """Reverse of lock() — control-for-control mirror. Only ever called
        by set_read_only() below, which already folds in the session's own
        business .locked flag, so calling this directly would bypass that."""
        for w in (self._r_location, self._r_decision_maker, self._r_presentation_lead):
            w.setReadOnly(False)
            # Restore the original input style rather than trying to peel
            # off the "background/color" fragment lock() appended.
            w.setStyleSheet(_INPUT)
        for w in (self._r_overall_decision, self._r_attendees, self._r_attendee_remarks,
                  self._r_ceo_feedback, self._r_risks, self._r_open_comments):
            w.setReadOnly(False)
        self._r_date.setEnabled(True)
        self._r_time_from.setEnabled(True)
        self._r_time_to.setEnabled(True)
        self._mod_table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self._ap_table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self._add_mod_btn.setEnabled(True)
        self._add_ap_btn.setEnabled(True)
        for table in (self._mod_table, self._ap_table):
            for row in range(table.rowCount()):
                for col in range(table.columnCount()):
                    w = table.cellWidget(row, col)
                    if w:
                        w.setEnabled(True)

    def set_read_only(self, read_only: bool):
        """Two-way toggle for the app-wide read-only mode, kept independent
        of ValidationSession.locked the same way PreparationPanel.set_read_only
        does — see that docstring for the combining rule. Never touches
        self.setEnabled() — this class IS the QScrollArea."""
        self._read_only = read_only
        effective_locked = read_only or bool(self._session and self._session.locked)
        if effective_locked:
            self.lock()
        else:
            self.unlock()

    def sync_to_session(self):
        if not self._session:
            return
        s = self._session
        s.meeting_date       = self._r_date.date().toString("dd/MM/yyyy")
        s.meeting_time_from  = self._r_time_from.time().toString("HH:mm")
        s.meeting_time_to    = self._r_time_to.time().toString("HH:mm")
        s.meeting_location   = self._r_location.text()
        s.decision_maker     = self._r_decision_maker.text()
        s.presentation_lead  = self._r_presentation_lead.text()
        s.overall_decision   = self._r_overall_decision.toPlainText()
        s.present_attendees  = self._r_attendees.toPlainText()
        s.attendees_remarks  = self._r_attendee_remarks.toPlainText()
        s.ceo_feedback       = self._r_ceo_feedback.toPlainText()
        s.risks              = self._r_risks.toPlainText()
        s.open_comments      = self._r_open_comments.toPlainText()

        s.modifications = []
        for row in range(self._mod_table.rowCount()):
            m = ModificationRow()
            item = self._mod_table.item(row, 1)
            m.description = item.text() if item else ""
            combo = self._mod_table.cellWidget(row, 2)
            m.priority = combo.currentText() if combo else "To modify"
            item = self._mod_table.item(row, 3)
            m.responsible = item.text() if item else ""
            item = self._mod_table.item(row, 4)
            m.due_date = item.text() if item else ""
            combo = self._mod_table.cellWidget(row, 5)
            m.status = combo.currentText() if combo else "To Do"
            s.modifications.append(m)

        s.action_plan = []
        for row in range(self._ap_table.rowCount()):
            a = ActionRow()
            for col, attr in enumerate(["department", "actions", "deliverables",
                                         "responsible", "due_date"]):
                item = self._ap_table.item(row, col)
                setattr(a, attr, item.text() if item else "")
            combo = self._ap_table.cellWidget(row, 5)
            a.status = combo.currentText() if combo else "To Do"
            s.action_plan.append(a)

    # ── internals ──────────────────────────────────────────────────────────────

    def _reload_tables(self):
        if not self._session:
            return
        s = self._session

        if s.meeting_date:
            d = QDate.fromString(s.meeting_date, "dd/MM/yyyy")
            if d.isValid():
                self._r_date.setDate(d)
        if s.meeting_time_from:
            t = QTime.fromString(s.meeting_time_from, "HH:mm")
            if t.isValid():
                self._r_time_from.setTime(t)
        if s.meeting_time_to:
            t = QTime.fromString(s.meeting_time_to, "HH:mm")
            if t.isValid():
                self._r_time_to.setTime(t)
        self._r_location.setText(s.meeting_location)
        self._r_decision_maker.setText(s.decision_maker)
        self._r_presentation_lead.setText(s.presentation_lead)
        self._r_overall_decision.setPlainText(s.overall_decision)
        self._r_attendees.setPlainText(s.present_attendees)
        self._r_attendee_remarks.setPlainText(s.attendees_remarks)
        self._r_ceo_feedback.setPlainText(s.ceo_feedback)
        self._r_risks.setPlainText(s.risks)
        self._r_open_comments.setPlainText(s.open_comments)

        self._mod_table.blockSignals(True)
        self._mod_table.setRowCount(0)
        for m in s.modifications:
            self._add_modification_row(m)
        self._mod_table.blockSignals(False)

        self._ap_table.blockSignals(True)
        self._ap_table.setRowCount(0)
        for a in s.action_plan:
            self._add_action_row(a)
        self._ap_table.blockSignals(False)

    def _add_modification_row(self, data: Optional[ModificationRow] = None):
        row = self._mod_table.rowCount()
        self._mod_table.insertRow(row)
        m = data or ModificationRow()

        id_item = QTableWidgetItem(str(row + 1))
        id_item.setTextAlignment(Qt.AlignCenter)
        id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
        id_item.setForeground(QColor(_MUTED))
        self._mod_table.setItem(row, 0, id_item)

        self._mod_table.setItem(row, 1, QTableWidgetItem(m.description))

        priority_combo = _combo([
            t("project.validation.priority_modify"),
            t("project.validation.priority_accepted"),
            t("project.validation.priority_on_hold"),
            t("project.validation.priority_canceled"),
        ])
        priority_combo.setCurrentText(m.priority)
        self._mod_table.setCellWidget(row, 2, priority_combo)

        self._mod_table.setItem(row, 3, QTableWidgetItem(m.responsible))
        self._mod_table.setItem(row, 4, QTableWidgetItem(m.due_date))

        status_combo = _combo([
            t("project.validation.status_todo"),
            t("project.validation.status_in_progress"),
            t("project.validation.status_done"),
        ])
        status_combo.setCurrentText(m.status)
        self._mod_table.setCellWidget(row, 5, status_combo)

        self.changed.emit()

    def _add_action_row(self, data: Optional[ActionRow] = None):
        row = self._ap_table.rowCount()
        self._ap_table.insertRow(row)
        a = data or ActionRow()
        for col, val in enumerate([a.department, a.actions, a.deliverables,
                                    a.responsible, a.due_date]):
            self._ap_table.setItem(row, col, QTableWidgetItem(val or ""))
        status_combo = _combo([
            t("project.validation.status_todo"),
            t("project.validation.status_in_progress"),
            t("project.validation.status_done"),
        ])
        status_combo.setCurrentText(a.status)
        self._ap_table.setCellWidget(row, 5, status_combo)
        self.changed.emit()
