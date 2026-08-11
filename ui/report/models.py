"""
Data models for the Report screen. No Qt imports — pure Python dataclasses.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import List

from i18n import t, t_in


@dataclass
class PhotoCell:
    caption:   str = ""
    image_b64: str = ""


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
    project_photo_b64:   str  = ""

    def display_name(self) -> str:
        prefix = "🔒  " if self.locked else ""
        if self.date:
            parts = self.date.split("/")
            if len(parts) == 3:
                return f"{prefix}Report  {parts[0]}.{parts[1]}.{parts[2][-2:]}"
        return f"{prefix}Report {self.id}"


_ATTENDEE_DEFAULT_KEYS = [
    "project.report.attendee_default_production",
    "project.report.attendee_default_studio",
    "project.report.attendee_default_marketing",
    "project.report.attendee_default_partner1",
    "project.report.attendee_default_other",
]

_SUPPORTED_LANGS = ("en", "fr")


def display_attendee_header(header: str) -> str:
    """If `header` exactly matches one of the known default column names in
    *any* supported language, return that default translated into the
    *current* language. Otherwise return it unchanged.

    Headers used to get translated once, at report-creation time, and
    stored as plain text from then on — so a column created in English
    stayed "Partner 1"/"Other" forever, even after switching the app to
    French (or opening a project saved while it was still in English).
    Re-deriving the display text from a canonical key on every render
    fixes that, while a value the user typed themselves never matches one
    of these keys and is always shown exactly as they wrote it.
    """
    for key in _ATTENDEE_DEFAULT_KEYS:
        if any(header == t_in(key, lang) for lang in _SUPPORTED_LANGS):
            return t(key)
    return header


def _default_report(rid: int) -> Report:
    today = date.today().strftime("%d/%m/%Y")
    r = Report(id=rid, date=today)
    r.company_extras = []
    r.partner_extras = []
    r.attendees = [
        AttendeeColumn(t(k), "") for k in [
            "project.report.attendee_default_production",
            "project.report.attendee_default_studio",
            "project.report.attendee_default_marketing",
            "project.report.attendee_default_partner1",
            "project.report.attendee_default_other",
            "project.report.attendee_default_other",
        ]
    ]
    page = ReportPage(id=1)
    page.photo_blocks = [PhotoBlock()]
    r.pages = [page]
    return r
