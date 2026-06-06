# Re-export shim — kept for backward compatibility.
# All logic now lives in ui/timeline/
from ui.timeline import TimelineWidget
from ui.timeline.models import Task, Operation, Operator, TASK_TYPES, DEFAULT_TYPE

__all__ = ['TimelineWidget', 'Task', 'Operation', 'Operator', 'TASK_TYPES', 'DEFAULT_TYPE']
