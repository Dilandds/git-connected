"""
Estimated Cost screen — trade-based cost estimation with partner comparison.

Structure:
  EstimatedCostWidget
  └── Trade tabs  (Trade 1, Trade 2 … + Add trade)
      └── TradeWidget  (sub-tabs per trade)
          ├── Overview tab   – global best-partner summary, password-protected
          ├── Comparison tab – read-only all-partners table for this trade
          └── Partner tabs   (Partner 1, Partner 2 … + Add partner)
              └── PartnerPanel
                  ├── Project info card
                  └── Task details table (Component | Task | Hours | Rate | Total)
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QDoubleSpinBox, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QStackedWidget, QMessageBox, QSizePolicy, QDialog,
    QDateEdit, QSpacerItem
)
from PyQt5.QtCore import Qt, pyqtSignal, QDate
from PyQt5.QtGui import QColor, QFont
from ui.styles import default_theme, make_font, dropdown_arrow_url as _get_arrow, TOOLTIP_STYLE, arrow_up_url as _arrow_up, arrow_down_url as _arrow_down
from ui.modal_utils import (
    ask_yes_no_dialog, ask_password_dialog,
    show_warning_dialog, show_message_dialog, ask_text_input_dialog,
)
_ARROW_URL = _get_arrow()

logger = logging.getLogger(__name__)

# ── palette ───────────────────────────────────────────────────────────────────
_BG       = '#f8f9fa'
_CARD     = '#ffffff'
_BORDER   = '#e5e7eb'
_TEXT     = '#1e2430'
_MUTED    = '#6b7280'
_ACCENT   = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover

# ── styles ────────────────────────────────────────────────────────────────────
_INPUT = f"""
    QLineEdit, QDoubleSpinBox, QComboBox, QDateEdit {{
        background-color: #f5f6f8; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 6px; font-size: 11px;
    }}
    QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus {{
        border-color: {_ACCENT};
    }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
    QComboBox QAbstractItemView {{
        background: {_CARD}; color: {_TEXT}; border: 1px solid {_BORDER};
        selection-background-color: {_ACCENT}; selection-color: white;
    }}
    QDateEdit::drop-down {{ border: none; width: 18px; }}
    QDateEdit::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
"""

_TABLE_STYLE = f"""
    QTableWidget {{
        background-color: {_CARD}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 6px;
        gridline-color: {_BORDER}; font-size: 11px;
    }}
    QTableWidget::item {{ padding: 3px 5px; }}
    QTableWidget::item:selected {{ background-color: #dbeafe; color: {_TEXT}; }}
    QHeaderView::section {{
        background-color: #f1f3f5; color: {_MUTED};
        border: none; border-bottom: 1px solid {_BORDER};
        border-right: 1px solid {_BORDER};
        padding: 5px 8px; font-size: 10px; font-weight: bold;
    }}
"""

_BTN_PRIMARY = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: white; border: none;
        border-radius: 5px; padding: 5px 14px; font-size: 11px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: {_ACCENT_H}; }}
    QPushButton:pressed {{ background-color: {default_theme.button_primary_pressed}; }}
"""
_BTN_SMALL = f"""
    QPushButton {{
        background-color: #f1f3f5; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 8px; font-size: 10px;
    }}
    QPushButton:hover {{ background-color: #e5e7eb; border-color: {_ACCENT}; color: {_ACCENT}; }}
"""
_BTN_OUTLINE = f"""
    QPushButton {{
        background-color: transparent; color: {_ACCENT};
        border: 1px solid {_ACCENT}; border-radius: 5px;
        padding: 4px 12px; font-size: 10px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: #dbeafe; }}
"""
_BTN_BEST_OFF = f"""
    QPushButton {{
        background-color: #f1f3f5; color: {_MUTED};
        border: 1px solid {_BORDER}; border-radius: 5px;
        padding: 4px 14px; font-size: 10px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: #dcfce7; border-color: #16a34a; color: #16a34a; }}
"""
_BTN_BEST_ON = f"""
    QPushButton {{
        background-color: #16a34a; color: white; border: none;
        border-radius: 5px; padding: 4px 14px; font-size: 10px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: #15803d; }}
"""
_TAB_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: white; border: none;
        border-radius: 5px; padding: 5px 14px; font-size: 11px; font-weight: bold;
    }}
""" + TOOLTIP_STYLE
_TAB_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {_MUTED};
        border: 1px solid {_BORDER}; border-radius: 5px; padding: 5px 14px; font-size: 11px;
    }}
    QPushButton:hover {{ color: {_TEXT}; border-color: {_ACCENT}; background-color: #e8f0fe; }}
""" + TOOLTIP_STYLE
_TAB_ACTIVE_L   = _TAB_ACTIVE.replace("border-radius: 5px;", "border-radius: 5px 0 0 5px;")
_TAB_INACTIVE_L = _TAB_INACTIVE.replace("border-radius: 5px;", "border-radius: 5px 0 0 5px;")
_CLOSE_TAB_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: rgba(255,255,255,0.55);
        border: none; border-left: 1px solid rgba(255,255,255,0.18);
        border-radius: 0 5px 5px 0; font-size: 13px; font-weight: bold; padding: 0 5px;
    }}
    QPushButton:hover {{ color: white; background-color: #ef4444; }}
""" + TOOLTIP_STYLE
_CLOSE_TAB_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {_MUTED};
        border: 1px solid {_BORDER}; border-left: none;
        border-radius: 0 5px 5px 0; font-size: 13px; font-weight: bold; padding: 0 5px;
    }}
    QPushButton:hover {{ color: #ef4444; background-color: #fee2e2; border-color: #fca5a5; }}
""" + TOOLTIP_STYLE
_RENAME_TAB_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: rgba(255,255,255,0.55);
        border: none; border-left: 1px solid rgba(255,255,255,0.18);
        border-radius: 0; font-size: 11px; padding: 0 5px;
    }}
    QPushButton:hover {{ color: white; background-color: {_ACCENT_H}; }}
""" + TOOLTIP_STYLE
_RENAME_TAB_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {_MUTED};
        border: 1px solid {_BORDER}; border-left: none;
        border-radius: 0; font-size: 11px; padding: 0 5px;
    }}
    QPushButton:hover {{ color: {_ACCENT}; background-color: #e8f0fe; border-color: {_ACCENT}; }}
""" + TOOLTIP_STYLE

CURRENCIES = ["EUR", "USD", "GBP", "CHF", "JPY", "CNY", "AED", "CAD", "AUD"]
_CURRENCY_SYMBOLS = {
    "EUR": "€", "USD": "$", "GBP": "£", "CHF": "Fr",
    "JPY": "¥", "CNY": "¥", "AED": "د.إ", "CAD": "$", "AUD": "$",
}
DEFAULT_ROWS = 10

# ── data model ────────────────────────────────────────────────────────────────

@dataclass
class CostTask:
    component:   str   = ""
    task:        str   = ""
    hours:       float = 0.0
    hourly_rate: float = 0.0

    @property
    def total(self) -> float:
        return round(self.hours * self.hourly_rate, 2)


@dataclass
class CostPartner:
    id:            int
    name:          str   = "Partner"
    activity:      str   = ""
    start_date:    str   = ""
    delivery_date: str   = ""
    is_best:       bool  = False
    tax_rate:      float = 0.0
    tasks:         List[CostTask] = field(default_factory=list)

    @property
    def total_hours(self) -> float:
        return sum(t.hours for t in self.tasks)

    @property
    def total_cost(self) -> float:
        return sum(t.total for t in self.tasks)

    @property
    def total_cost_with_tax(self) -> float:
        return round(self.total_cost * (1 + self.tax_rate / 100), 2)

    @property
    def rate(self) -> float:
        for t in self.tasks:
            if t.hourly_rate > 0:
                return t.hourly_rate
        return 0.0


@dataclass
class CostTrade:
    id:       int
    name:     str = "Trade"
    partners: List[CostPartner] = field(default_factory=list)

    @property
    def best_partner(self) -> Optional[CostPartner]:
        for p in self.partners:
            if p.is_best:
                return p
        return None


def _default_trade(tid: int) -> CostTrade:
    p = CostPartner(id=1, name="Partner 1",
                    tasks=[CostTask() for _ in range(DEFAULT_ROWS)])
    return CostTrade(id=tid, name=f"Trade {tid}", partners=[p])


# ── helpers ───────────────────────────────────────────────────────────────────

def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-height: 1px; border: none;")
    return f


def _vdiv() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-width: 1px; border: none;")
    return f


def _card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setStyleSheet(
        f"QFrame {{ background-color: {_CARD}; border: 1px solid {_BORDER}; border-radius: 8px; }}"
    )
    return f


def _lbl(text: str, muted=True, bold=False, size=10) -> QLabel:
    l = QLabel(text)
    col = _MUTED if muted else _TEXT
    fw  = "bold" if bold else "normal"
    l.setStyleSheet(
        f"color: {col}; font-size: {size}px; font-weight: {fw}; background: transparent; border: none;"
    )
    return l


def _field(placeholder="", h=26) -> QLineEdit:
    w = QLineEdit()
    w.setPlaceholderText(placeholder)
    w.setStyleSheet(_INPUT)
    w.setFixedHeight(h)
    return w


class _NumericSpin(QDoubleSpinBox):
    """SpinBox that shows blank when value is 0 (placeholder look), reveals on focus."""

    def __init__(self, decimals=1, max_val=99999.0):
        super().__init__()
        self.setDecimals(decimals)
        self.setRange(0.0, max_val)
        self.setFixedHeight(26)
        self.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.setSpecialValueText(' ')   # show blank when value == minimum (0.0)
        self._apply_style()
        self.valueChanged.connect(lambda _: self._apply_style())

    def _apply_style(self):
        color = _MUTED if self.value() == 0.0 else _TEXT
        self.setStyleSheet(_INPUT + f"\nQDoubleSpinBox {{ color: {color}; }}")

    def focusInEvent(self, event):
        super().focusInEvent(event)
        if self.value() == 0.0:
            self.setSpecialValueText('')   # reveal "0.0" so user can overwrite it
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self.selectAll)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if self.value() == 0.0:
            self.setSpecialValueText(' ')  # hide 0 again when leaving empty field

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self.selectAll)


def _spin(decimals=1, max_val=99999.0) -> _NumericSpin:
    return _NumericSpin(decimals=decimals, max_val=max_val)


def _fmt(value: float, currency: str) -> str:
    sym = _CURRENCY_SYMBOLS.get(currency, currency + " ")
    return f"{sym}{value:,.2f}"


# ── PartnerPanel ──────────────────────────────────────────────────────────────

class PartnerPanel(QScrollArea):
    """Editing panel for a single partner within a trade."""

    changed      = pyqtSignal()
    best_toggled = pyqtSignal(int)   # emits partner.id

    def __init__(self, partner: CostPartner,
                 currency_fn: Callable[[], str],
                 parent=None):
        super().__init__(parent)
        self._partner      = partner
        self._currency_fn  = currency_fn
        self._project_info: dict = {}
        self._rate_cells:  List[QDoubleSpinBox] = []
        self._total_cells: List[QLabel]         = []
        self._hours_cells: List[QDoubleSpinBox] = []

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(f"""
            QScrollArea {{ background: {_BG}; border: none; }}
            QScrollBar:vertical {{ background: {_BG}; width: 6px; border-radius: 3px; }}
            QScrollBar::handle:vertical {{ background: {_BORDER}; border-radius: 3px; }}
        """)
        body = QWidget()
        body.setStyleSheet(f"background: {_BG};")
        root = QVBoxLayout(body)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(14)

        root.addWidget(self._build_info_card())
        root.addWidget(self._build_task_card())
        root.addStretch()
        self.setWidget(body)

    # ── project info card ──────────────────────────────────────────────────

    def _build_info_card(self) -> QFrame:
        card = _card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(10)

        # Project context strip (auto-filled from project info sidebar)
        ctx_row = QHBoxLayout()
        ctx_row.setSpacing(16)
        self._ctx_project = _lbl("Project: —", muted=True, size=10)
        self._ctx_company = _lbl("Company: —", muted=True, size=10)
        ctx_row.addWidget(self._ctx_project)
        ctx_row.addWidget(self._ctx_company)
        ctx_row.addStretch()
        cl.addLayout(ctx_row)
        cl.addWidget(_sep())

        # Title row
        title_row = QHBoxLayout()
        company_lbl = QLabel(self._partner.name)
        company_lbl.setFont(make_font(size=16, bold=True))
        company_lbl.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        self._company_name_lbl = company_lbl
        title_row.addWidget(company_lbl)
        title_row.addStretch()

        self._best_btn = QPushButton("★  Mark as Best")
        self._best_btn.setFixedHeight(30)
        self._best_btn.setCursor(Qt.PointingHandCursor)
        self._best_btn.setStyleSheet(_BTN_BEST_ON if self._partner.is_best else _BTN_BEST_OFF)
        self._best_btn.setText("★  Best Partner" if self._partner.is_best else "☆  Mark as Best")
        self._best_btn.clicked.connect(self._on_best_clicked)
        title_row.addWidget(self._best_btn)
        cl.addLayout(title_row)
        cl.addWidget(_sep())

        # Two-column info grid
        grid = QHBoxLayout()
        grid.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(_lbl("Partner / Company name"))
        self._f_name = _field(self._partner.name)
        self._f_name.setText(self._partner.name)
        self._f_name.textChanged.connect(self._on_name_changed)
        left.addWidget(self._f_name)

        left.addWidget(_lbl("Partner activity"))
        self._f_activity = _field("e.g. Manufacturing, Design…")
        self._f_activity.setText(self._partner.activity)
        self._f_activity.textChanged.connect(lambda v: setattr(self._partner, 'activity', v) or self.changed.emit())
        left.addWidget(self._f_activity)
        left.addStretch()
        grid.addLayout(left, 1)

        grid.addWidget(_vdiv())

        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(_lbl("Start date"))
        self._f_start = _field("dd/mm/yyyy")
        self._f_start.setText(self._partner.start_date)
        self._f_start.textChanged.connect(lambda v: setattr(self._partner, 'start_date', v) or self.changed.emit())
        right.addWidget(self._f_start)

        right.addWidget(_lbl("Delivery date"))
        self._f_delivery = _field("dd/mm/yyyy")
        self._f_delivery.setText(self._partner.delivery_date)
        self._f_delivery.textChanged.connect(lambda v: setattr(self._partner, 'delivery_date', v) or self.changed.emit())
        right.addWidget(self._f_delivery)
        right.addStretch()
        grid.addLayout(right, 1)

        cl.addLayout(grid)
        return card

    def _on_name_changed(self, text: str):
        self._partner.name = text or "Partner"
        self._company_name_lbl.setText(self._partner.name)
        self.changed.emit()

    def _on_best_clicked(self):
        self.best_toggled.emit(self._partner.id)

    def set_best(self, is_best: bool):
        self._partner.is_best = is_best
        self._best_btn.setStyleSheet(_BTN_BEST_ON if is_best else _BTN_BEST_OFF)
        self._best_btn.setText("★  Best Partner" if is_best else "☆  Mark as Best")

    # ── task details card ──────────────────────────────────────────────────

    def _build_task_card(self) -> QFrame:
        card = _card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.addWidget(_lbl("Task details", muted=False, bold=True, size=12))
        hdr.addStretch()

        cur_lbl = _lbl("Currency:", muted=True)
        hdr.addWidget(cur_lbl)
        self._cur_lbl = _lbl(self._currency_fn(), muted=False, bold=True, size=11)
        hdr.addWidget(self._cur_lbl)

        add_row_btn = QPushButton("+ Add row")
        add_row_btn.setStyleSheet(_BTN_OUTLINE)
        add_row_btn.setFixedHeight(26)
        add_row_btn.setCursor(Qt.PointingHandCursor)
        add_row_btn.clicked.connect(lambda _: self._add_task_row())
        hdr.addSpacing(8)
        hdr.addWidget(add_row_btn)
        cl.addLayout(hdr)
        cl.addWidget(_sep())

        # Table
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Component", "Task", "Est. Hours", "Hourly Rate", "Total Cost", ""]
        )
        self._table.setStyleSheet(_TABLE_STYLE)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._table.setColumnWidth(2, 90)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self._table.setColumnWidth(3, 100)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self._table.setColumnWidth(4, 110)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self._table.setColumnWidth(5, 32)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(32)
        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        self._table.setFocusPolicy(Qt.NoFocus)
        self._table.viewport().setFocusPolicy(Qt.NoFocus)
        self._table.setMinimumHeight(320)

        # Populate from partner tasks
        for task in self._partner.tasks:
            self._add_task_row(task)

        cl.addWidget(self._table)

        # Totals row
        totals_row = QHBoxLayout()
        totals_row.addStretch()
        self._total_hours_lbl = _lbl("Total hours:  0.0", muted=False, bold=True, size=11)
        self._total_cost_lbl  = _lbl("Total cost:  —", muted=False, bold=True, size=11)
        totals_row.addWidget(self._total_hours_lbl)
        totals_row.addSpacing(24)
        totals_row.addWidget(self._total_cost_lbl)
        cl.addLayout(totals_row)

        # Tax row
        tax_row = QHBoxLayout()
        tax_row.addStretch()
        tax_row.addWidget(_lbl("Tax:", muted=True, size=11))
        self._tax_spin = QDoubleSpinBox()
        self._tax_spin.setRange(0.0, 30.0)
        self._tax_spin.setDecimals(1)
        self._tax_spin.setSingleStep(0.5)
        self._tax_spin.setSuffix(" %")
        self._tax_spin.setValue(self._partner.tax_rate)
        self._tax_spin.setFixedWidth(90)
        self._tax_spin.setFixedHeight(26)
        self._tax_spin.setStyleSheet(f"""
            QDoubleSpinBox {{
                background: #f5f6f8; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 4px;
                padding: 2px 4px; font-size: 11px;
            }}
            QDoubleSpinBox:focus {{ border-color: {_ACCENT}; }}
            QDoubleSpinBox::up-button {{
                subcontrol-origin: border; subcontrol-position: top right;
                width: 16px; border-left: 1px solid {_BORDER};
                border-top-right-radius: 4px; background: #f1f3f5;
            }}
            QDoubleSpinBox::up-button:hover {{ background: {_ACCENT}; }}
            QDoubleSpinBox::up-arrow {{
                image: url({_arrow_up()}); width: 8px; height: 8px;
            }}
            QDoubleSpinBox::down-button {{
                subcontrol-origin: border; subcontrol-position: bottom right;
                width: 16px; border-left: 1px solid {_BORDER};
                border-bottom-right-radius: 4px; background: #f1f3f5;
            }}
            QDoubleSpinBox::down-button:hover {{ background: {_ACCENT}; }}
            QDoubleSpinBox::down-arrow {{
                image: url({_arrow_down()}); width: 8px; height: 8px;
            }}
        """)
        self._tax_spin.valueChanged.connect(self._on_tax_changed)
        tax_row.addSpacing(8)
        tax_row.addWidget(self._tax_spin)
        self._tax_amount_lbl = _lbl("", muted=True, size=11)
        tax_row.addSpacing(8)
        tax_row.addWidget(self._tax_amount_lbl)
        cl.addLayout(tax_row)

        # Total with tax row
        total_tax_row = QHBoxLayout()
        total_tax_row.addStretch()
        self._total_with_tax_lbl = _lbl("Total with tax:  —", muted=False, bold=True, size=12)
        self._total_with_tax_lbl.setStyleSheet(
            f"color: {_ACCENT}; font-size: 12px; font-weight: bold; background: transparent; border: none;"
        )
        total_tax_row.addWidget(self._total_with_tax_lbl)
        cl.addLayout(total_tax_row)

        self._refresh_totals()
        return card

    def _add_task_row(self, task: Optional[CostTask] = None):
        if task is None:
            task = CostTask()
            self._partner.tasks.append(task)
        self._rebuild_table()

    def _rebuild_table(self):
        """Clear and repopulate every row so indices are always correct."""
        self._table.setRowCount(0)
        self._hours_cells.clear()
        self._rate_cells.clear()
        self._total_cells.clear()

        for row, task in enumerate(self._partner.tasks):
            self._table.insertRow(row)

            # Component
            c_inp = _field()
            c_inp.setText(task.component)
            c_inp.textChanged.connect(lambda v, t=task: setattr(t, 'component', v) or self.changed.emit())
            self._table.setCellWidget(row, 0, c_inp)

            # Task
            t_inp = _field()
            t_inp.setText(task.task)
            t_inp.textChanged.connect(lambda v, t=task: setattr(t, 'task', v) or self.changed.emit())
            self._table.setCellWidget(row, 1, t_inp)

            # Hours
            h_spin = _spin(decimals=1)
            h_spin.setValue(task.hours)
            h_spin.valueChanged.connect(lambda v, t=task, r=row: self._on_hours_changed(v, t, r))
            self._table.setCellWidget(row, 2, h_spin)
            self._hours_cells.append(h_spin)

            # Hourly Rate
            r_spin = _spin(decimals=2, max_val=99999.0)
            r_spin.setValue(task.hourly_rate)
            r_spin.valueChanged.connect(lambda v, t=task, r=row: self._on_rate_changed(v, t, r))
            self._table.setCellWidget(row, 3, r_spin)
            self._rate_cells.append(r_spin)

            # Total (read-only label)
            tot_lbl = QLabel(self._fmt_total(task.total))
            tot_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tot_lbl.setStyleSheet(
                f"color: {_TEXT}; font-size: 11px; font-weight: bold; "
                f"background: #f5f6f8; border: none; padding-right: 8px;"
            )
            self._table.setCellWidget(row, 4, tot_lbl)
            self._total_cells.append(tot_lbl)

            # Delete button
            del_btn = QPushButton("×")
            del_btn.setFixedSize(24, 24)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setToolTip("Delete row")
            del_btn.setStyleSheet("""
                QPushButton {
                    background: transparent; color: #9ca3af;
                    border: none; font-size: 15px; font-weight: bold;
                }
                QPushButton:hover { color: #ef4444; }
            """)
            del_btn.clicked.connect(lambda _, t=task: self._delete_task_row(t))
            self._table.setCellWidget(row, 5, del_btn)

    def _delete_task_row(self, task: CostTask):
        if task in self._partner.tasks:
            self._partner.tasks.remove(task)
        self._rebuild_table()
        self._refresh_totals()
        self.changed.emit()

    def _on_hours_changed(self, value: float, task: CostTask, row: int):
        task.hours = value
        task_total = task.total
        if row < len(self._total_cells):
            self._total_cells[row].setText(self._fmt_total(task_total))
        self._refresh_totals()
        self.changed.emit()

    def _on_rate_changed(self, value: float, task: CostTask, row: int):
        task.hourly_rate = value
        if row < len(self._total_cells):
            self._total_cells[row].setText(self._fmt_total(task.total))
        self._refresh_totals()
        self.changed.emit()

    def _on_tax_changed(self, value: float):
        self._partner.tax_rate = value
        self._refresh_totals()
        self.changed.emit()

    def _refresh_totals(self):
        h = sum(t.hours for t in self._partner.tasks)
        c = sum(t.total for t in self._partner.tasks)
        tax_rate = self._partner.tax_rate
        tax_amount = round(c * tax_rate / 100, 2)
        total_with_tax = round(c + tax_amount, 2)
        cur = self._currency_fn()
        self._total_hours_lbl.setText(f"Total hours:  {h:,.1f}")
        self._total_cost_lbl.setText(f"Total cost:  {_fmt(c, cur)}")
        if tax_rate > 0:
            self._tax_amount_lbl.setText(f"(+{_fmt(tax_amount, cur)})")
            self._total_with_tax_lbl.setText(f"Total with tax:  {_fmt(total_with_tax, cur)}")
            self._total_with_tax_lbl.setVisible(True)
        else:
            self._tax_amount_lbl.setText("")
            self._total_with_tax_lbl.setVisible(False)

    def _fmt_total(self, value: float) -> str:
        return _fmt(value, self._currency_fn())

    def update_project_info(self, info: dict):
        self._project_info = info
        self._ctx_project.setText(f"Project: {info.get('title', '') or '—'}")
        self._ctx_company.setText(f"Company: {info.get('company', '') or '—'}")

    def refresh_currency(self):
        self._cur_lbl.setText(self._currency_fn())
        for i, (t, lbl) in enumerate(zip(self._partner.tasks, self._total_cells)):
            lbl.setText(self._fmt_total(t.total))
        self._refresh_totals()


# ── ComparisonPanel ───────────────────────────────────────────────────────────

class ComparisonPanel(QWidget):
    """Read-only table showing all partners for one trade side-by-side."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        hdr = QLabel("Partner Comparison")
        hdr.setFont(make_font(size=14, bold=True))
        hdr.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        sub = _lbl("Auto-populated from partner tabs — read only", muted=True)
        root.addWidget(hdr)
        root.addWidget(sub)
        root.addWidget(_sep())

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Partner", "Total Hours", "Hourly Rate", "Total Cost", "Delivery Date"]
        )
        self._table.setStyleSheet(_TABLE_STYLE)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 5):
            self._table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setMinimumHeight(280)
        root.addWidget(self._table)
        root.addStretch()

    def refresh(self, trade: CostTrade, currency: str):
        sym = _CURRENCY_SYMBOLS.get(currency, currency + " ")
        self._table.setRowCount(0)
        for p in trade.partners:
            row = self._table.rowCount()
            self._table.insertRow(row)

            name_item = QTableWidgetItem(
                f"{'★ ' if p.is_best else ''}{p.name}"
            )
            if p.is_best:
                name_item.setForeground(QColor("#16a34a"))
                font = make_font(size=11, bold=True)
                name_item.setFont(font)
            self._table.setItem(row, 0, name_item)
            self._table.setItem(row, 1, QTableWidgetItem(f"{p.total_hours:,.1f} h"))
            self._table.setItem(row, 2, QTableWidgetItem(f"{sym}{p.rate:,.2f}"))
            self._table.setItem(row, 3, QTableWidgetItem(f"{sym}{p.total_cost:,.2f}"))
            self._table.setItem(row, 4, QTableWidgetItem(p.delivery_date or "—"))

            if p.is_best:
                for col in range(5):
                    item = self._table.item(row, col)
                    if item:
                        item.setBackground(QColor("#f0fdf4"))


# ── OverviewPanel ─────────────────────────────────────────────────────────────

class OverviewPanel(QWidget):
    """Global read-only panel — best partner from every trade. Password-protected."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._password: str = ""
        self._unlocked: bool = True
        self.setStyleSheet(f"background: {_BG};")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(16, 14, 16, 14)
        self._root.setSpacing(10)
        self._build_ui()

    def _build_ui(self):
        # Header
        hdr_row = QHBoxLayout()
        hdr = QLabel("Overview — Best Partner per Trade")
        hdr.setFont(make_font(size=14, bold=True))
        hdr.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()
        self._lock_btn = QPushButton("🔒  Set Password")
        self._lock_btn.setStyleSheet(f"""
            QPushButton {{
                background: #f1f3f5; color: {_MUTED};
                border: 1px solid {_BORDER}; border-radius: 4px;
                font-size: 10px; padding: 3px 10px;
            }}
            QPushButton:hover {{ color: {_TEXT}; border-color: {_ACCENT}; }}
        """)
        self._lock_btn.setCursor(Qt.PointingHandCursor)
        self._lock_btn.clicked.connect(self._manage_password)
        hdr_row.addWidget(self._lock_btn)
        self._root.addLayout(hdr_row)

        sub = _lbl("Auto-generated from Best partner selection in each trade — read only", muted=True)
        self._root.addWidget(sub)
        self._root.addWidget(_sep())

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Trade", "Best Partner", "Total Hours", "Hourly Rate", "Total Cost"]
        )
        self._table.setStyleSheet(_TABLE_STYLE)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for c in range(2, 5):
            self._table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setMinimumHeight(280)
        self._root.addWidget(self._table)

        # Grand total row
        total_row = QHBoxLayout()
        total_row.addStretch()
        self._grand_total_lbl = _lbl("Grand Total:  —", muted=False, bold=True, size=12)
        total_row.addWidget(self._grand_total_lbl)
        self._root.addLayout(total_row)
        self._root.addStretch()

        # Lock overlay
        self._overlay = QWidget(self)
        self._overlay.setStyleSheet(f"background: rgba(248,249,250,0.96);")
        self._overlay.setVisible(False)
        overlay_l = QVBoxLayout(self._overlay)
        overlay_l.setAlignment(Qt.AlignCenter)
        lock_icon = QLabel("🔒")
        lock_icon.setAlignment(Qt.AlignCenter)
        lock_icon.setStyleSheet("font-size: 40px; background: transparent; border: none;")
        lock_msg = QLabel("This section is password-protected.")
        lock_msg.setAlignment(Qt.AlignCenter)
        lock_msg.setStyleSheet(f"color: {_TEXT}; font-size: 13px; background: transparent; border: none;")
        unlock_btn = QPushButton("🔓  Enter Password")
        unlock_btn.setStyleSheet(_BTN_PRIMARY)
        unlock_btn.setFixedWidth(180)
        unlock_btn.setFixedHeight(34)
        unlock_btn.setCursor(Qt.PointingHandCursor)
        unlock_btn.clicked.connect(self._try_unlock)
        overlay_l.addWidget(lock_icon)
        overlay_l.addSpacing(10)
        overlay_l.addWidget(lock_msg)
        overlay_l.addSpacing(12)
        overlay_l.addWidget(unlock_btn, alignment=Qt.AlignCenter)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())

    def refresh(self, trades: List[CostTrade], currency: str):
        sym = _CURRENCY_SYMBOLS.get(currency, currency + " ")
        self._table.setRowCount(0)
        grand_total = 0.0
        for trade in trades:
            bp = trade.best_partner
            if bp is None:
                continue
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(trade.name))
            self._table.setItem(row, 1, QTableWidgetItem(f"★  {bp.name}"))
            self._table.item(row, 1).setForeground(QColor("#16a34a"))
            self._table.setItem(row, 2, QTableWidgetItem(f"{bp.total_hours:,.1f} h"))
            self._table.setItem(row, 3, QTableWidgetItem(f"{sym}{bp.rate:,.2f}"))
            self._table.setItem(row, 4, QTableWidgetItem(f"{sym}{bp.total_cost:,.2f}"))
            grand_total += bp.total_cost
            for col in range(5):
                item = self._table.item(row, col)
                if item:
                    item.setBackground(QColor("#f0fdf4"))
        self._grand_total_lbl.setText(f"Grand Total:  {sym}{grand_total:,.2f}")

    def show_and_lock_if_needed(self):
        if self._password and not self._unlocked:
            self._overlay.setVisible(True)
        else:
            self._overlay.setVisible(False)

    def _try_unlock(self):
        pwd, ok = ask_password_dialog(self, "Password Required", "Enter password to view Overview")
        if ok and pwd == self._password:
            self._unlocked = True
            self._overlay.setVisible(False)
        elif ok:
            show_warning_dialog(self, "Incorrect Password", "The password you entered is incorrect.")

    def _manage_password(self):
        if self._password:
            current, ok = ask_password_dialog(
                self, "Confirm Password", "Enter current password to change or clear it"
            )
            if not ok:
                return
            if current != self._password:
                show_warning_dialog(self, "Incorrect Password", "Current password is incorrect.")
                return
        new_pwd, ok = ask_password_dialog(
            self, "Set Password",
            "Enter new password (leave empty to remove password protection)"
        )
        if ok:
            self._password = new_pwd.strip()
            self._unlocked = not bool(self._password)
            self._lock_btn.setText("🔒  Change Password" if self._password else "🔒  Set Password")
            if self._password:
                show_message_dialog(self, "Password Set", "Overview is now password-protected.")
            else:
                self._overlay.setVisible(False)


# ── TradeWidget ───────────────────────────────────────────────────────────────

class TradeWidget(QWidget):
    """Holds the sub-tabs and content for one trade."""

    changed = pyqtSignal()

    def __init__(self, trade: CostTrade,
                 all_trades_fn: Callable[[], List[CostTrade]],
                 currency_fn: Callable[[], str],
                 parent=None):
        super().__init__(parent)
        self._trade         = trade
        self._all_trades    = all_trades_fn
        self._currency_fn   = currency_fn
        self._project_info: dict = {}
        self._current_sub   = 0   # 0=Overview 1=Comparison 2+=Partners
        self._partner_panels: List[PartnerPanel] = []
        self._next_partner_id = 2
        self.setStyleSheet(f"background: {_BG};")
        self._build_ui()
        self._rebuild_partners()
        self._switch_sub(0)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sub-tabs bar
        self._sub_bar = QWidget()
        self._sub_bar.setFixedHeight(40)
        self._sub_bar.setStyleSheet(
            f"background: {_BG}; border-bottom: 2px solid {_BORDER};"
        )
        self._sub_layout = QHBoxLayout(self._sub_bar)
        self._sub_layout.setContentsMargins(12, 5, 12, 5)
        self._sub_layout.setSpacing(6)
        self._sub_layout.addStretch()
        root.addWidget(self._sub_bar)

        # Stacked content
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        # Fixed panels: 0=Overview, 1=Comparison
        self._overview_panel    = OverviewPanel()
        self._comparison_panel  = ComparisonPanel()
        self._stack.addWidget(self._overview_panel)   # index 0
        self._stack.addWidget(self._comparison_panel) # index 1

    # ── sub-tab management ────────────────────────────────────────────────────

    def _refresh_sub_tabs(self):
        while self._sub_layout.count():
            item = self._sub_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for idx, label in enumerate(["Overview", "Comparison"]):
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_TAB_ACTIVE if idx == self._current_sub else _TAB_INACTIVE)
            btn.clicked.connect(lambda _, i=idx: self._switch_sub(i))
            self._sub_layout.addWidget(btn)

        for i, partner in enumerate(self._trade.partners):
            p_idx = i + 2
            is_active = (p_idx == self._current_sub)
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            ch = QHBoxLayout(container)
            ch.setContentsMargins(0, 0, 0, 0)
            ch.setSpacing(0)
            name = f"{'★ ' if partner.is_best else ''}{partner.name}"
            btn = QPushButton(name)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_TAB_ACTIVE_L if is_active else _TAB_INACTIVE_L)
            btn.clicked.connect(lambda _, pi=p_idx: self._switch_sub(pi))
            close = QPushButton("×")
            close.setFixedSize(22, 28)
            close.setCursor(Qt.PointingHandCursor)
            close.setToolTip(f"Remove {partner.name}")
            close.setStyleSheet(_CLOSE_TAB_ACTIVE if is_active else _CLOSE_TAB_INACTIVE)
            close.clicked.connect(lambda _, pi=i: self._remove_partner(pi))
            ch.addWidget(btn)
            ch.addWidget(close)
            self._sub_layout.addWidget(container)

        add_btn = QPushButton("＋  Add partner")
        add_btn.setStyleSheet(_BTN_SMALL)
        add_btn.setFixedHeight(28)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_partner)
        self._sub_layout.addWidget(add_btn)
        self._sub_layout.addStretch()

    def _switch_sub(self, idx: int):
        self._current_sub = idx
        if idx == 0:
            self._overview_panel.refresh(self._all_trades(), self._currency_fn())
            self._overview_panel.show_and_lock_if_needed()
            self._stack.setCurrentIndex(0)
        elif idx == 1:
            self._comparison_panel.refresh(self._trade, self._currency_fn())
            self._stack.setCurrentIndex(1)
        else:
            p_idx = idx - 2
            if 0 <= p_idx < len(self._partner_panels):
                self._stack.setCurrentWidget(self._partner_panels[p_idx])
        self._refresh_sub_tabs()

    # ── partner management ────────────────────────────────────────────────────

    def _rebuild_partners(self):
        # Remove old partner panels from stack (keep 0=Overview, 1=Comparison)
        while self._stack.count() > 2:
            w = self._stack.widget(2)
            self._stack.removeWidget(w)
            w.deleteLater()
        self._partner_panels.clear()

        for partner in self._trade.partners:
            pp = PartnerPanel(partner, self._currency_fn)
            pp.changed.connect(self.changed)
            pp.changed.connect(self._on_partner_data_changed)
            pp.best_toggled.connect(self._on_best_toggled)
            self._stack.addWidget(pp)
            self._partner_panels.append(pp)
            if partner.id >= self._next_partner_id:
                self._next_partner_id = partner.id + 1

    def _add_partner(self):
        p = CostPartner(
            id=self._next_partner_id,
            name=f"Partner {self._next_partner_id}",
            tasks=[CostTask() for _ in range(DEFAULT_ROWS)],
        )
        self._next_partner_id += 1
        self._trade.partners.append(p)
        pp = PartnerPanel(p, self._currency_fn)
        pp.changed.connect(self.changed)
        pp.changed.connect(self._on_partner_data_changed)
        pp.best_toggled.connect(self._on_best_toggled)
        if self._project_info:
            pp.update_project_info(self._project_info)
        self._stack.addWidget(pp)
        self._partner_panels.append(pp)
        self._switch_sub(len(self._trade.partners) + 1)
        self.changed.emit()

    def _remove_partner(self, idx: int):
        if idx < 0 or idx >= len(self._trade.partners):
            return
        partner = self._trade.partners[idx]
        if not ask_yes_no_dialog(
            self, "Remove Partner",
            f"Remove partner '{partner.name}' and all their task data?\n\nThis cannot be undone."
        ):
            return
        self._trade.partners.pop(idx)
        panel = self._partner_panels.pop(idx)
        self._stack.removeWidget(panel)
        panel.deleteLater()
        self._current_sub = 0
        self._switch_sub(0)
        self.changed.emit()

    def _on_partner_data_changed(self):
        """Refresh Overview live when partner costs change and Overview is visible."""
        if self._current_sub == 0:
            self._overview_panel.refresh(self._all_trades(), self._currency_fn())
        self._refresh_sub_tabs()

    def _on_best_toggled(self, partner_id: int):
        already_best = any(p.id == partner_id and p.is_best for p in self._trade.partners)
        for p in self._trade.partners:
            p.is_best = False if already_best else (p.id == partner_id)
        for pp in self._partner_panels:
            pp.set_best(pp._partner.is_best)
        self._overview_panel.refresh(self._all_trades(), self._currency_fn())
        self._refresh_sub_tabs()
        self.changed.emit()

    def update_project_info(self, info: dict):
        self._project_info = info
        for pp in self._partner_panels:
            pp.update_project_info(info)

    def refresh_currency(self):
        for pp in self._partner_panels:
            pp.refresh_currency()

    def get_best_summary(self) -> Optional[dict]:
        bp = self._trade.best_partner
        if not bp:
            return None
        return {
            "trade":        self._trade.name,
            "partner":      bp.name,
            "total_hours":  bp.total_hours,
            "hourly_rate":  bp.rate,
            "total_cost":   bp.total_cost,
            "delivery_date": bp.delivery_date,
        }


# ── EstimatedCostWidget ───────────────────────────────────────────────────────

class EstimatedCostWidget(QWidget):
    """Top-level Estimated Cost screen."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._trades:        List[CostTrade]   = [_default_trade(1)]
        self._trade_widgets: List[TradeWidget] = []
        self._current_trade  = 0
        self._currency       = "EUR"
        self._project_info: dict = {}
        self.setStyleSheet(f"background-color: {_BG};")
        self._build_ui()
        self._rebuild_all()
        self._switch_trade(0)

    # ── build ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── top bar ──
        top = QWidget()
        top.setFixedHeight(46)
        top.setStyleSheet(f"background: {_BG}; border-bottom: 1px solid {_BORDER};")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 0, 16, 0)
        tl.setSpacing(10)

        title = QLabel("Estimated Cost")
        title.setFont(make_font(size=15, bold=True))
        title.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        subtitle = QLabel("Trade-based cost estimation with partner comparison.")
        subtitle.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
        t_col = QVBoxLayout()
        t_col.setSpacing(1)
        t_col.addWidget(title)
        t_col.addWidget(subtitle)
        tl.addLayout(t_col)
        tl.addStretch()

        tl.addWidget(_lbl("Currency:", muted=True))
        self._currency_combo = QComboBox()
        self._currency_combo.addItems(CURRENCIES)
        self._currency_combo.setCurrentText(self._currency)
        self._currency_combo.setFixedWidth(80)
        self._currency_combo.setFixedHeight(28)
        self._currency_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {_CARD}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 5px;
                padding: 3px 24px 3px 8px; font-size: 11px; font-weight: bold;
            }}
            QComboBox:hover {{ border-color: #9ca3af; }}
            QComboBox:focus {{ border-color: {_ACCENT}; }}
            QComboBox::drop-down {{
                subcontrol-origin: padding; subcontrol-position: top right;
                width: 20px; background: #f1f3f5;
                border-left: 1px solid {_BORDER};
                border-top-right-radius: 5px; border-bottom-right-radius: 5px;
            }}
            QComboBox::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
            QComboBox QAbstractItemView {{
                background-color: {_CARD}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 4px;
                outline: none; padding: 2px;
                selection-background-color: #dbeafe; selection-color: {_TEXT};
                font-size: 11px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 5px 10px; min-height: 24px; border-radius: 3px;
            }}
            QComboBox QAbstractItemView::item:hover {{ background-color: #eff6ff; }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: #dbeafe; font-weight: bold;
            }}
        """)
        self._currency_combo.currentTextChanged.connect(self._on_currency_changed)
        tl.addWidget(self._currency_combo)
        root.addWidget(top)

        # ── trade tabs bar ──
        self._trade_bar = QWidget()
        self._trade_bar.setFixedHeight(40)
        self._trade_bar.setStyleSheet(f"background: {_BG}; border-bottom: 2px solid {_BORDER};")
        self._trade_layout = QHBoxLayout(self._trade_bar)
        self._trade_layout.setContentsMargins(12, 5, 12, 5)
        self._trade_layout.setSpacing(6)
        self._trade_layout.addStretch()
        root.addWidget(self._trade_bar)

        # ── stacked TradeWidgets ──
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

    # ── trade management ───────────────────────────────────────────────────────

    def _rebuild_all(self):
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.deleteLater()
        self._trade_widgets.clear()

        for trade in self._trades:
            tw = TradeWidget(trade, lambda: self._trades, lambda: self._currency)
            tw.changed.connect(self.changed)
            self._stack.addWidget(tw)
            self._trade_widgets.append(tw)

    def _refresh_trade_tabs(self):
        while self._trade_layout.count():
            item = self._trade_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, trade in enumerate(self._trades):
            is_active = (i == self._current_trade)
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            ch = QHBoxLayout(container)
            ch.setContentsMargins(0, 0, 0, 0)
            ch.setSpacing(0)

            btn = QPushButton(trade.name)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_TAB_ACTIVE_L if is_active else _TAB_INACTIVE_L)
            btn.clicked.connect(lambda _, idx=i: self._switch_trade(idx))
            btn.mouseDoubleClickEvent = lambda _e, idx=i: self._rename_trade(idx)

            rename = QPushButton("✎")
            rename.setFixedSize(22, 28)
            rename.setCursor(Qt.PointingHandCursor)
            rename.setToolTip("Rename trade")
            rename.setStyleSheet(_RENAME_TAB_ACTIVE if is_active else _RENAME_TAB_INACTIVE)
            rename.clicked.connect(lambda _, idx=i: self._rename_trade(idx))

            close = QPushButton("×")
            close.setFixedSize(22, 28)
            close.setCursor(Qt.PointingHandCursor)
            close.setToolTip(f"Remove {trade.name}")
            close.setStyleSheet(_CLOSE_TAB_ACTIVE if is_active else _CLOSE_TAB_INACTIVE)
            close.clicked.connect(lambda _, idx=i: self._remove_trade(idx))

            ch.addWidget(btn)
            ch.addWidget(rename)
            ch.addWidget(close)
            self._trade_layout.addWidget(container)

        add_btn = QPushButton("＋  Add trade")
        add_btn.setStyleSheet(_BTN_SMALL)
        add_btn.setFixedHeight(28)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_trade)
        self._trade_layout.addWidget(add_btn)
        self._trade_layout.addStretch()

    def _switch_trade(self, idx: int):
        self._current_trade = idx
        if 0 <= idx < len(self._trade_widgets):
            self._stack.setCurrentWidget(self._trade_widgets[idx])
        self._refresh_trade_tabs()

    def _next_available_id(self) -> int:
        """Return the lowest positive integer not already used as a trade id."""
        used = {t.id for t in self._trades}
        n = 1
        while n in used:
            n += 1
        return n

    def _rename_trade(self, idx: int):
        if idx < 0 or idx >= len(self._trades):
            return
        trade = self._trades[idx]
        new_name, ok = ask_text_input_dialog(
            self, "Rename Trade", "TRADE NAME", default_text=trade.name
        )
        if ok and new_name:
            trade.name = new_name
            self._refresh_trade_tabs()
            self.changed.emit()

    def _add_trade(self):
        trade = _default_trade(self._next_available_id())
        self._trades.append(trade)
        tw = TradeWidget(trade, lambda: self._trades, lambda: self._currency)
        tw.changed.connect(self.changed)
        if self._project_info:
            tw.update_project_info(self._project_info)
        self._stack.addWidget(tw)
        self._trade_widgets.append(tw)
        self._switch_trade(len(self._trades) - 1)
        self.changed.emit()

    def _remove_trade(self, idx: int):
        if idx < 0 or idx >= len(self._trades):
            return
        if not ask_yes_no_dialog(
            self, "Remove Trade",
            f"Remove trade '{self._trades[idx].name}' and all its partners?\n\nThis cannot be undone."
        ):
            return
        self._trades.pop(idx)
        tw = self._trade_widgets.pop(idx)
        self._stack.removeWidget(tw)
        tw.deleteLater()
        new_idx = min(self._current_trade, len(self._trades) - 1) if self._trades else 0
        self._current_trade = -1
        if self._trades:
            self._switch_trade(new_idx)
        else:
            self._refresh_trade_tabs()
        self.changed.emit()

    def update_project_info(self, info: dict):
        """Called by project_widget whenever sidebar project info changes."""
        self._project_info = info
        for tw in self._trade_widgets:
            tw.update_project_info(info)

    def _on_currency_changed(self, currency: str):
        self._currency = currency
        for tw in self._trade_widgets:
            tw.refresh_currency()
        self.changed.emit()

    # ── data for Validation screen ─────────────────────────────────────────────

    def get_best_summary(self) -> List[dict]:
        """Returns best partner cost data per trade for the Validation screen."""
        result = []
        for tw in self._trade_widgets:
            summary = tw.get_best_summary()
            if summary:
                result.append(summary)
        return result

    # ── serialisation ──────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        def _ser_task(t: CostTask) -> dict:
            return {"component": t.component, "task": t.task,
                    "hours": t.hours, "hourly_rate": t.hourly_rate}

        def _ser_partner(p: CostPartner) -> dict:
            return {"id": p.id, "name": p.name, "activity": p.activity,
                    "start_date": p.start_date, "delivery_date": p.delivery_date,
                    "is_best": p.is_best, "tax_rate": p.tax_rate,
                    "tasks": [_ser_task(t) for t in p.tasks]}

        def _ser_trade(t: CostTrade) -> dict:
            return {"id": t.id, "name": t.name,
                    "partners": [_ser_partner(p) for p in t.partners]}

        return {
            "currency": self._currency,
            "trades":   [_ser_trade(t) for t in self._trades],
        }

    def set_data(self, data: dict):
        self._currency = data.get("currency", "EUR")
        self._currency_combo.blockSignals(True)
        self._currency_combo.setCurrentText(self._currency)
        self._currency_combo.blockSignals(False)

        trades = []
        for td in data.get("trades", []):
            partners = []
            for pd in td.get("partners", []):
                tasks = [CostTask(**t) for t in pd.get("tasks", [])]
                p = CostPartner(
                    id=pd["id"], name=pd.get("name", "Partner"),
                    activity=pd.get("activity", ""),
                    start_date=pd.get("start_date", ""),
                    delivery_date=pd.get("delivery_date", ""),
                    is_best=pd.get("is_best", False),
                    tax_rate=pd.get("tax_rate", 0.0),
                    tasks=tasks,
                )
                partners.append(p)
            trades.append(CostTrade(id=td["id"], name=td.get("name", "Trade"),
                                     partners=partners))
        if trades:
            self._trades = trades
        self._rebuild_all()
        self._switch_trade(0)
