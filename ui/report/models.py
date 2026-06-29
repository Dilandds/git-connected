"""
Data models for the Report screen. No Qt imports — pure Python dataclasses.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import List


@dataclass
class PhotoCell:
    caption:    str = ""
    image_path: str = ""


@dataclass
class PhotoRow:
    photos: List[PhotoCell] = field(default_factory=lambda: [PhotoCell() for _ in range(4)])


@dataclass
class PhotoBlock:
    """One bordered block: 6 photo+caption slots (2 cols × 3 rows) + a comment."""
    photos:  List[PhotoCell] = field(default_factory=lambda: [PhotoCell() for _ in range(6)])
    comment: str = ""


@dataclass
class AttendeeColumn:
    header: str = ""
    name:   str = ""


@dataclass
class CompanyRow:
    label: str = ""
    value: str = ""


@dataclass
class ReportPage:
    id:           int
    followup:     str             = ""
    comments:     str             = ""
    photo_rows:   List[PhotoRow]  = field(default_factory=list)   # legacy
    photo_blocks: List[PhotoBlock] = field(default_factory=list)  # current


@dataclass
class Report:
    id:                  int
    date:                str  = ""
    locked:              bool = False
    launch_deadline:     str  = ""
    project_name:        str  = ""
    project_reference:   str  = ""
    project_manager:     str  = ""
    technical_manager:   str  = ""
    quality_lead:        str  = ""
    company_extras:      List[CompanyRow]     = field(default_factory=list)
    partner_1:           str  = ""
    partner_2:           str  = ""
    partner_3:           str  = ""
    partner_extras:      List[CompanyRow]     = field(default_factory=list)
    attendees:           List[AttendeeColumn] = field(default_factory=list)
    pages:               List[ReportPage]     = field(default_factory=list)
    project_photo_path:  str  = ""

    def display_name(self) -> str:
        prefix = "🔒  " if self.locked else ""
        if self.date:
            parts = self.date.split("/")
            if len(parts) == 3:
                return f"{prefix}Report  {parts[0]}.{parts[1]}.{parts[2][-2:]}"
        return f"{prefix}Report {self.id}"


def _default_report(rid: int) -> Report:
    today = date.today().strftime("%d/%m/%Y")
    r = Report(id=rid, date=today)
    r.company_extras = []
    r.partner_extras = []
    r.attendees = [
        AttendeeColumn(h, "") for h in
        ["Production", "Studio", "Marketing", "Partners 1", "Other", "Other"]
    ]
    page = ReportPage(id=1)
    page.photo_blocks = [PhotoBlock()]
    r.pages = [page]
    return r
