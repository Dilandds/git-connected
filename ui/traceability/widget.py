"""
TraceabilityWidget — main container.
Assembles the 4-row layout from its sub-modules.
"""
import logging
from typing import List
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import pyqtSignal
from .models import TracePart, TraceSubStage, TraceStage, TraceComponent
from .shared import _BG
from .row1_product_info import _ProductInfoRow
from .row2_components import _ComponentsRow
from .row3_timeline import _StageTimelineRow
from .row4_substages import _SubStagePanel

logger = logging.getLogger(__name__)


class TraceabilityWidget(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._components: List[TraceComponent] = [
            TraceComponent(
                id=1, name='Main Product', is_main=True,
                stages=[
                    TraceStage(
                        id=1, number=1, name='Initial Design', status='Upcoming',
                        sub_stages=[TraceSubStage(id=1, name='Sub-stage 1')]
                    )
                ]
            )
        ]
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

        self._stage_row = _StageTimelineRow()
        self._stage_row.stage_selected.connect(self._on_stage_selected)
        self._stage_row.changed.connect(self.changed)
        root.addWidget(self._stage_row)

        self._sub_panel = _SubStagePanel()
        self._sub_panel.changed.connect(self.changed)
        root.addWidget(self._sub_panel, 1)

    def _load_component(self, idx: int):
        if not self._components:
            return
        idx = max(0, min(idx, len(self._components) - 1))
        self._current_component = idx
        comp = self._components[idx]
        self._comp_row.load_components(self._components, idx)
        self._stage_row.load_stages(comp.stages, selected=0)
        self._sub_panel.load_stage(comp.stages[0] if comp.stages else None)

    def _on_stage_selected(self, stage_idx: int):
        comp  = self._components[self._current_component]
        stage = comp.stages[stage_idx] if 0 <= stage_idx < len(comp.stages) else None
        self._sub_panel.load_stage(stage)

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
        """Add component names from Project Brief that aren't already present."""
        names = [r[0].strip() for r in brief_components if r and r[0].strip()]
        existing = {c.name for c in self._components}
        changed = False
        for name in names:
            if name not in existing:
                new_id = max((c.id for c in self._components), default=0) + 1
                self._components.append(TraceComponent(
                    id=new_id, name=name,
                    stages=[TraceStage(
                        id=1, number=1, name='Stage 1', status='Upcoming',
                        sub_stages=[TraceSubStage(id=1, name='Sub-stage 1')]
                    )]
                ))
                existing.add(name)
                changed = True
        if changed:
            self._comp_row.load_components(self._components, self._current_component)

    # ── serialisation ──────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        def _sp(p: TracePart) -> dict:
            return {
                'id': p.id, 'name': p.name,
                'suppliers': p.suppliers, 'action': p.action,
                'current_task': p.current_task,
                'start_date': p.start_date, 'due_date': p.due_date,
                'status': p.status, 'progress': p.progress,
                'comments': p.comments,
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
            'version':           2,
            'current_component': self._current_component,
            'extra':             self._info_row.get_extra_data(),
            'components':        [_sc(c) for c in self._components],
        }

    def set_data(self, data: dict):
        if data.get('version', 1) < 2:
            return  # old step-based format — start fresh

        components = []
        for cd in data.get('components', []):
            stages = []
            for sd in cd.get('stages', []):
                sub_stages = []
                for ssd in sd.get('sub_stages', []):
                    parts = [
                        TracePart(
                            id=pd['id'], name=pd.get('name', 'Part'),
                            suppliers=pd.get('suppliers', ''),
                            action=pd.get('action', ''),
                            current_task=pd.get('current_task', ''),
                            start_date=pd.get('start_date', ''),
                            due_date=pd.get('due_date', ''),
                            status=pd.get('status', 'Upcoming'),
                            progress=pd.get('progress', 0),
                            comments=pd.get('comments', []),
                        )
                        for pd in ssd.get('parts', [])
                    ]
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

        if components:
            self._components = components
        self._info_row.set_extra_data(data.get('extra', {}))
        self._load_component(data.get('current_component', 0))
