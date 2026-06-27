from dataclasses import dataclass, field
from typing import List


@dataclass
class TraceStep:
    id:          int
    name:        str = 'Step'
    description: str = ''
    status:      str = 'Upcoming'
    progress:    int = 0


@dataclass
class TraceTask:
    id:           int
    name:         str       = 'Task'
    subject:      str       = ''
    performed_by: str       = ''
    suppliers:    str       = ''
    action:       str       = ''
    current_task: str       = ''
    start_date:   str       = ''
    due_date:     str       = ''
    status:       str       = 'Upcoming'
    progress:     int       = 0
    comments:     List[str] = field(default_factory=list)
    steps:        List[TraceStep] = field(default_factory=list)


@dataclass
class TracePart:
    id:    int
    name:  str             = 'Part'
    tasks: List[TraceTask] = field(default_factory=list)


@dataclass
class TraceSubStage:
    id:    int
    name:  str             = 'Sub-stage'
    parts: List[TracePart] = field(default_factory=list)


@dataclass
class TraceStage:
    id:         int
    number:     int                  = 1
    name:       str                  = 'Stage'
    status:     str                  = 'Upcoming'
    sub_stages: List[TraceSubStage]  = field(default_factory=list)


@dataclass
class TraceComponent:
    id:         int
    name:       str              = 'Component'
    image_path: str              = ''
    is_main:    bool             = False
    stages:     List[TraceStage] = field(default_factory=list)
