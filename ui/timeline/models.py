"""
Data models, layout constants, and sample-data helpers for the Timeline module.
No Qt widgets here — safe to import anywhere without a QApplication.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from PyQt5.QtCore import QDate
from ui.styles import default_theme
from i18n import t

# ── palette (light content area) ─────────────────────────────────────────────
BG      = '#f8f9fa'
CARD    = '#ffffff'
BORDER  = '#e5e7eb'
TEXT    = '#1e2430'
MUTED   = '#6b7280'
ACCENT  = default_theme.button_primary
SIDEBAR = '#1c2029'

# ── task type registry ────────────────────────────────────────────────────────
TASK_TYPES = {
    'Manufacturing':   '#3b82f6',
    'Modification':    '#8b5cf6',
    'Validation':      '#10b981',
    'Quality Control': '#f59e0b',
    'Delivery':        '#06b6d4',
    'Holidays':        '#6b7280',
    'Issue':           '#ef4444',
}
DEFAULT_TYPE = 'Manufacturing'
URGENT_COLOR = '#ef4444'

# ── Gantt layout constants ────────────────────────────────────────────────────
ROW_H       = 36    # px per operation row
OP_HEADER_H = 22    # px for the operator name mini-strip
HEADER_H    = 52    # date header height
OP_LABEL_W  = 150   # frozen left column width
DAY_W_DAY   = 38    # px per day in Day view
DAY_W_WEEK  = 26    # px per day in Week view  (7 days × 26 = 182 px/week)
DAY_W_MONTH = 11    # px per day in Month view (~30 days × 11 = 330 px/month)
DAY_W_YEAR  = 3     # px per day in Year view  (~365 days × 3 = ~1095 px/year)


# ── data models ───────────────────────────────────────────────────────────────

@dataclass
class Task:
    id:                int
    name:              str
    start:             QDate
    end:               QDate
    task_type:         str            = DEFAULT_TYPE
    is_urgent:         bool           = False
    status:            str            = 'In progress'
    comments:          List[str]      = field(default_factory=list)
    deadline:          Optional[QDate] = None
    duration_days:     int            = 1
    project_manager:   str            = ''
    technical_manager: str            = ''
    contributors:      str            = ''
    unavailable_start: Optional[QDate] = None
    unavailable_end:   Optional[QDate] = None
    photo_path:        str            = ''
    components_impacted: str          = ''
    priority:          str            = 'Normal'
    delay_end:         Optional[QDate] = None

    def __post_init__(self):
        self.duration_days = max(1, self.start.daysTo(self.end))


@dataclass
class Operation:
    id:    int
    name:  str
    tasks: List[Task] = field(default_factory=list)


@dataclass
class Operator:
    id:         int
    name:       str
    operations: List[Operation] = field(default_factory=list)


# ── helpers ───────────────────────────────────────────────────────────────────

def today() -> QDate:
    return QDate.currentDate()


def sample_data() -> List[Operator]:
    """Default demo operators shown on first launch."""
    t_date = today()
    _operator_label = t('project.timeline.dlg_operator')
    op1 = Operator(1, f'{_operator_label} 1', [
        Operation(1, 'Operation 1', [
            Task(1, 'Initial concept',    t_date.addDays(-10), t_date.addDays(-7),  'Modification'),
            Task(2, '3D Modification',    t_date.addDays(-4),  t_date.addDays(1),   'Modification'),
            Task(3, 'Check and update',   t_date.addDays(3),   t_date.addDays(6),   'Validation'),
        ]),
        Operation(2, 'Operation 2', [
            Task(4, 'Factory production', t_date.addDays(-6),  t_date.addDays(-2),  'Manufacturing'),
            Task(5, 'Quality check',      t_date.addDays(0),   t_date.addDays(4),   'Quality Control'),
        ]),
        Operation(3, 'Operation 3', [
            Task(6, 'URGENT DELIVERY',    t_date.addDays(2),   t_date.addDays(5),   'Delivery', is_urgent=True),
        ]),
    ])
    op2 = Operator(2, f'{_operator_label} 2', [
        Operation(4, 'Operation 1', [
            Task(7, 'Design review',      t_date.addDays(-8),  t_date.addDays(-3),  'Validation'),
            Task(8, 'Prototype build',    t_date.addDays(1),   t_date.addDays(8),   'Manufacturing'),
        ]),
        Operation(5, 'Operation 2', [
            Task(9, 'Supplier sourcing',  t_date.addDays(-2),  t_date.addDays(6),   'Manufacturing'),
        ]),
    ])
    return [op1, op2]
