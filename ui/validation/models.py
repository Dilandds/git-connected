"""
Pure data model for the Validation module — no Qt imports.
"""
from dataclasses import dataclass, field
from datetime import date as _date
from typing import List


COST_CATEGORIES = [
    "Design & Engineering",
    "Prototyping",
    "Materials",
    "Manufacturing",
    "Other (items, logistics…)",
]

SCHEDULE_MILESTONES = [
    "Project start",
    "Concept review",
    "Design freeze",
    "Validation meeting",
    "Prototype ready",
    "Production start",
    "Delivery",
]


@dataclass
class Stakeholder:
    id:             int
    role:           str = ""
    name:           str = ""
    responsibility: str = ""
    status:         str = "In progress"
    progress:       int = 0
    deliverables:   str = ""
    comments:       str = ""


@dataclass
class ModificationRow:
    description: str = ""
    priority:    str = "To modify"
    responsible: str = ""
    due_date:    str = ""
    status:      str = "To Do"


@dataclass
class ActionRow:
    department:   str = ""
    actions:      str = ""
    deliverables: str = ""
    responsible:  str = ""
    due_date:     str = ""
    status:       str = "To Do"


@dataclass
class ValidationSession:
    id:                  int
    date:                str = ""
    locked:              bool = False
    signature:           str = ""
    stakeholders:        List[Stakeholder] = field(default_factory=list)
    overall_decision:    str = ""
    present_attendees:   str = ""
    attendees_remarks:   str = ""
    decision_maker:      str = ""
    presentation_lead:   str = ""
    ceo_feedback:        str = ""
    modifications:       List[ModificationRow] = field(default_factory=list)
    action_plan:         List[ActionRow] = field(default_factory=list)
    risks:               str = ""
    open_comments:       str = ""
    meeting_date:        str = ""
    meeting_time_from:   str = ""
    meeting_time_to:     str = ""
    meeting_location:    str = ""
    schedule_dates:      List[str] = field(default_factory=lambda: [""] * 7)

    def display_name(self) -> str:
        if self.date:
            parts = self.date.split("/")
            if len(parts) == 3:
                return f"Validation  {parts[0]}.{parts[1]}.{parts[2][-2:]}"
        return f"Validation {self.id}"


def _default_session(session_id: int) -> ValidationSession:
    today = _date.today().strftime("%d/%m/%Y")
    s = ValidationSession(id=session_id, date=today)
    s.stakeholders = [
        Stakeholder(i + 1, role) for i, role in enumerate(
            ["Design", "Engineering", "Sourcing", "Quality", "Production", "Marketing"]
        )
    ]
    s.modifications = [ModificationRow() for _ in range(3)]
    s.action_plan   = [ActionRow(dept) for dept in
                       ["Design", "Engineering", "Procurement", "Quality", "Production", "Marketing"]]
    return s
