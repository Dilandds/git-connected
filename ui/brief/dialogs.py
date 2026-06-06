"""
All form dialogs used by the Project Brief module.
Every dialog extends FormModal — styling is guaranteed consistent.
Same pattern as ui/traceability/dialogs.py.
"""
from PyQt5.QtWidgets import QLineEdit, QDialog
from ui.modal_utils import FormModal


class _AddBulletDialog(FormModal):
    """Single-line input for adding a bullet point to a list."""

    def __init__(self, label: str = 'Item', parent=None):
        super().__init__(parent, f'Add {label}',
                         theme=FormModal.LIGHT, min_width=320)
        self.f_text = self.add_field(label.upper(), QLineEdit())
        self.f_text.setPlaceholderText('Enter text…')
        self.finish()
        self.f_text.returnPressed.connect(self.ok_btn.click)
        self.f_text.setFocus()

    @property
    def text(self) -> str:
        return self.f_text.text().strip()


class _AddComponentRowDialog(FormModal):
    """Three-field dialog for adding a Components table row."""

    def __init__(self, component: str = '', material: str = '',
                 colour: str = '', parent=None):
        is_edit = bool(component or material or colour)
        super().__init__(parent,
                         'Edit Component' if is_edit else 'Add Component',
                         theme=FormModal.LIGHT, min_width=400)

        self.f_component, self.f_material, self.f_colour = self.add_row_fields(
            ('COMPONENT', QLineEdit(component)),
            ('MATERIAL',  QLineEdit(material)),
            ('COLOUR',    QLineEdit(colour)),
        )
        self.f_component.setPlaceholderText('Component name')
        self.f_material.setPlaceholderText('e.g. ABS')
        self.f_colour.setPlaceholderText('e.g. Black')

        self.finish(delete='Remove' if is_edit else None)
        self.f_component.setFocus()

    @property
    def values(self) -> tuple:
        return (
            self.f_component.text().strip(),
            self.f_material.text().strip(),
            self.f_colour.text().strip(),
        )
