"""
Per-project supplier registry — a real entity with a stable id (not just a
free-text name), so a .lyns.review export can be tagged with exactly which
supplier it went to, and a later import can resolve the returned file back
to that same supplier even if their name/company is edited afterward. Not
a system-wide registry: the list lives in the project save file itself
(TheProjectWidget._suppliers, saved under the 'suppliers' top-level key),
same as any other project section.
"""
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Supplier:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = ''
    company: str = ''
    contact: str = ''

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> 'Supplier':
        return Supplier(
            id=d.get('id') or uuid.uuid4().hex,
            name=d.get('name', ''),
            company=d.get('company', ''),
            contact=d.get('contact', ''),
        )

    @property
    def display_name(self) -> str:
        if self.company:
            return f"{self.name} ({self.company})" if self.name else self.company
        return self.name or self.id


def find_supplier(suppliers: list, supplier_id: str) -> Optional[dict]:
    """Look up a supplier dict by id in a raw (dict-form) suppliers list."""
    for s in suppliers:
        if s.get('id') == supplier_id:
            return s
    return None
