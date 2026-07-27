"""
TraceabilityWidget — main container.
Assembles the 4-row layout from its sub-modules.
"""
import logging
from typing import List
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import pyqtSignal, QTimer, QPoint, Qt
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QPainterPath
from .models import TracePart, TraceTask, TraceStep, TraceSubStage, TraceStage, TraceComponent
from .shared import _BG, _ACCENT, _SEL_BORDER
from i18n import t
from .row1_product_info import _ProductInfoRow
from .row2_components import _ComponentsRow
from .row3_timeline import _StageTimelineRow
from .row4_substages import _SubStagePanel


def _default_components() -> List[TraceComponent]:
    """The single blank 'Main Product' component the widget starts with —
    also used to reset back to this state (New Project, or a saved file too
    old to parse) instead of leaving stale data on screen."""
    return [
        TraceComponent(
            id=1, name=t('project.traceability.main_product'), is_main=True,
            stages=[
                TraceStage(
                    id=1, number=1, name=t('project.traceability.default_stage_name'), status='Upcoming',
                    sub_stages=[TraceSubStage(id=1, name=t('project.traceability.default_substage_name').format(n=1))]
                )
            ]
        )
    ]


class _ArrowConnector(QWidget):
    """Horizontal band that draws a straight orthogonal connector arrow between two x positions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._x_from = -1
        self._x_to   = -1
        self.setFixedHeight(32)
        self.setStyleSheet(f'background: {_BG};')

    def set_positions(self, x_from: int, x_to: int):
        self._x_from = x_from
        self._x_to   = x_to
        self.update()

    def paintEvent(self, _):
        if self._x_from < 0 or self._x_to < 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        h = float(self.height())
        x1 = float(self._x_from)
        x2 = float(self._x_to)
        # Elbow midpoint — horizontal jog happens here
        mid_y = h / 2.0
        tip_y = h

        # Orthogonal path: straight down → straight across → straight down
        path = QPainterPath()
        path.moveTo(x1, 0.0)
        path.lineTo(x1, mid_y)
        path.lineTo(x2, mid_y)
        path.lineTo(x2, tip_y - 9)   # stop just above arrowhead base

        p.setPen(QPen(QColor(_SEL_BORDER), 2, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # Filled arrowhead pointing down
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(_SEL_BORDER)))
        head = QPainterPath()
        head.moveTo(x2,     tip_y)
        head.lineTo(x2 - 6, tip_y - 9)
        head.lineTo(x2 + 6, tip_y - 9)
        head.closeSubpath()
        p.drawPath(head)
        p.end()

logger = logging.getLogger(__name__)


class TraceabilityWidget(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._components: List[TraceComponent] = _default_components()
        self._current_component = 0
        self.setStyleSheet(f'background: {_BG};')
        self._build_ui()
        self._load_component(0)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._info_row  = _ProductInfoRow()
        self._info_row.changed.connect(self.changed)
        root.addWidget(self._info_row)

        self._comp_row  = _ComponentsRow()
        self._comp_row.component_selected.connect(self._load_component)
        self._comp_row.changed.connect(self.changed)
        root.addWidget(self._comp_row)

        self._arrow1 = _ArrowConnector()
        root.addWidget(self._arrow1)

        self._stage_row = _StageTimelineRow()
        self._stage_row.stage_selected.connect(self._on_stage_selected)
        self._stage_row.changed.connect(self.changed)
        root.addWidget(self._stage_row)

        self._arrow2 = _ArrowConnector()
        root.addWidget(self._arrow2)

        self._sub_panel = _SubStagePanel()
        self._sub_panel.changed.connect(self.changed)
        self._sub_panel.tab_switched.connect(lambda: QTimer.singleShot(0, self._update_arrow2))
        root.addWidget(self._sub_panel, 1)

        # Update arrows when either row is scrolled
        self._comp_row._scroll.horizontalScrollBar().valueChanged.connect(
            lambda _: self._update_arrow1())
        self._stage_row._scroll_area.horizontalScrollBar().valueChanged.connect(
            lambda _: self._update_arrow2())

    def _load_component(self, idx: int):
        if not self._components:
            return
        idx = max(0, min(idx, len(self._components) - 1))
        self._current_component = idx
        comp = self._components[idx]
        self._comp_row.load_components(self._components, idx)
        self._stage_row.load_stages(comp.stages, selected=0)
        self._sub_panel.load_stage(
            comp.stages[0] if comp.stages else None,
            is_main=comp.is_main,
        )
        QTimer.singleShot(0, self._update_arrows)

    def _on_stage_selected(self, stage_idx: int):
        comp  = self._components[self._current_component]
        stage = comp.stages[stage_idx] if 0 <= stage_idx < len(comp.stages) else None
        self._sub_panel.load_stage(stage, is_main=comp.is_main)
        QTimer.singleShot(0, self._update_arrows)   # both arrows: comp→stage and stage→sub

    def _update_arrow1(self):
        self._arrow1.set_positions(
            self._comp_row.selected_center_x(),
            self._stage_row.selected_center_x(),
        )

    def _update_arrow2(self):
        self._arrow2.set_positions(
            self._stage_row.selected_center_x(),
            self._sub_panel.selected_tab_center_x(),
        )

    def _update_arrows(self):
        self._update_arrow1()
        self._update_arrow2()

    # ── public API (called by TheProjectWidget) ────────────────────────────────

    def update_project_info(self, info: dict):
        self._info_row.update_project_info(info)
        photo = info.get('photo_path', '')
        if photo:
            main = next((c for c in self._components if c.is_main), None)
            if main and main.image_path != photo:
                main.image_path = photo
                self._comp_row.load_components(self._components, self._current_component)

    def update_components_from_brief(self, brief_components: list):
        """Full reconcile of non-main components against the Brief component list.

        - Adds components that appear in brief but not in traceability.
        - Removes non-main components that are no longer in brief.
        - Preserves stages/sub-stages for any component whose name is unchanged.
        """
        names = [r[0].strip() for r in brief_components if r and r[0].strip()]

        main_comps = [c for c in self._components if c.is_main]
        existing_by_name = {c.name: c for c in self._components if not c.is_main}

        new_non_main = []
        next_id = max((c.id for c in self._components), default=0)
        for name in names:
            if name in existing_by_name:
                new_non_main.append(existing_by_name[name])
            else:
                next_id += 1
                new_non_main.append(TraceComponent(
                    id=next_id, name=name,
                    stages=[TraceStage(
                        id=1, number=1, name=t('project.traceability.default_stage_number_name').format(n=1),
                        status='Upcoming',
                        sub_stages=[TraceSubStage(id=1, name=t('project.traceability.default_substage_name').format(n=1))]
                    )]
                ))

        self._components = main_comps + new_non_main
        self._current_component = min(
            self._current_component, max(0, len(self._components) - 1)
        )
        self._comp_row.load_components(self._components, self._current_component)

    def get_non_main_component_names(self) -> list:
        """Return names of non-main components for reverse brief sync."""
        return [c.name for c in self._components if not c.is_main]

    # ── serialisation ──────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        def _sstep(s: TraceStep) -> dict:
            return {
                'id': s.id, 'name': s.name,
                'description': s.description,
                'status': s.status, 'progress': s.progress,
            }

        def _stask(t: TraceTask) -> dict:
            return {
                'id': t.id, 'name': t.name,
                'subject': t.subject, 'performed_by': t.performed_by,
                'suppliers': t.suppliers, 'action': t.action,
                'current_task': t.current_task,
                'start_date': t.start_date, 'due_date': t.due_date,
                'status': t.status, 'progress': t.progress,
                'comments': t.comments,
                'steps': [_sstep(s) for s in t.steps],
            }

        def _sp(p: TracePart) -> dict:
            return {
                'id': p.id, 'name': p.name,
                'tasks': [_stask(tk) for tk in p.tasks],
            }

        def _ss(s: TraceSubStage) -> dict:
            return {'id': s.id, 'name': s.name, 'parts': [_sp(p) for p in s.parts]}

        def _st(s: TraceStage) -> dict:
            return {
                'id': s.id, 'number': s.number, 'name': s.name, 'status': s.status,
                'sub_stages': [_ss(ss) for ss in s.sub_stages],
            }

        def _sc(c: TraceComponent) -> dict:
            return {
                'id': c.id, 'name': c.name,
                'image_path': c.image_path, 'is_main': c.is_main,
                'stages': [_st(s) for s in c.stages],
            }

        return {
            'version':           3,
            'current_component': self._current_component,
            'extra':             self._info_row.get_extra_data(),
            'components':        [_sc(c) for c in self._components],
        }

    def set_data(self, data: dict):
        version = data.get('version', 1)
        if version < 2:
            # Old/unsupported format (or empty data, e.g. New Project) —
            # nothing to migrate. This used to just `return` here without
            # resetting anything, which only produced the "start fresh"
            # this comment promises the very first time; every later call
            # (New Project, opening a v1 file) left whatever was already
            # loaded on screen untouched.
            self._components = _default_components()
            self._info_row.set_extra_data({})
            self._load_component(0)
            return

        components = []
        for cd in data.get('components', []):
            stages = []
            for sd in cd.get('stages', []):
                sub_stages = []
                for ssd in sd.get('sub_stages', []):
                    parts = []
                    for pd in ssd.get('parts', []):
                        if version >= 3 and 'tasks' in pd:
                            # v3: full nested structure
                            tasks = []
                            for i, td in enumerate(pd.get('tasks', [])):
                                steps = [
                                    TraceStep(
                                        id=s.get('id', i2 + 1),
                                        name=s.get('name', 'Step'),
                                        description=s.get('description', ''),
                                        status=s.get('status', 'Upcoming'),
                                        progress=s.get('progress', 0),
                                    )
                                    for i2, s in enumerate(td.get('steps', []))
                                ]
                                tasks.append(TraceTask(
                                    id=td.get('id', i + 1),
                                    name=td.get('name', 'Task'),
                                    subject=td.get('subject', ''),
                                    performed_by=td.get('performed_by', ''),
                                    suppliers=td.get('suppliers', ''),
                                    action=td.get('action', ''),
                                    current_task=td.get('current_task', ''),
                                    start_date=td.get('start_date', ''),
                                    due_date=td.get('due_date', ''),
                                    status=td.get('status', 'Upcoming'),
                                    progress=td.get('progress', 0),
                                    comments=td.get('comments', []),
                                    steps=steps,
                                ))
                            parts.append(TracePart(id=pd['id'], name=pd.get('name', 'Part'), tasks=tasks))
                        else:
                            # v2 backward compat: flat TracePart → one TraceTask per part
                            task = TraceTask(
                                id=1,
                                name=pd.get('name', 'Task'),
                                subject=pd.get('subject', ''),
                                performed_by=pd.get('performed_by', ''),
                                suppliers=pd.get('suppliers', ''),
                                action=pd.get('action', ''),
                                current_task=pd.get('current_task', ''),
                                start_date=pd.get('start_date', ''),
                                due_date=pd.get('due_date', ''),
                                status=pd.get('status', 'Upcoming'),
                                progress=pd.get('progress', 0),
                                comments=pd.get('comments', []),
                            )
                            parts.append(TracePart(id=pd['id'], name=pd.get('name', 'Part'), tasks=[task]))
                    sub_stages.append(TraceSubStage(id=ssd['id'], name=ssd.get('name', 'Sub-stage'), parts=parts))
                stages.append(TraceStage(
                    id=sd['id'], number=sd.get('number', 1),
                    name=sd.get('name', 'Stage'), status=sd.get('status', 'Upcoming'),
                    sub_stages=sub_stages,
                ))
            components.append(TraceComponent(
                id=cd['id'], name=cd.get('name', 'Component'),
                image_path=cd.get('image_path', ''), is_main=cd.get('is_main', False),
                stages=stages,
            ))

        self._components = components if components else _default_components()
        self._info_row.set_extra_data(data.get('extra', {}))
        self._load_component(data.get('current_component', 0))
