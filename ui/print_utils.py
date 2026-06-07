"""
Print / PDF-export utility for The Project sections.

Usage:
    from ui.print_utils import print_section
    print_section('timeline', widget, 'Timeline', parent_widget)
"""
import math
from PyQt5.QtWidgets import QWidget, QScrollArea
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QPainter, QPixmap


def _get_printable_pixmap(section_key: str, widget: QWidget) -> QPixmap:
    """Return a full-content pixmap for the given section.

    For the Timeline the Gantt canvas is grabbed at its natural (full) size.
    For every other section the inner widget of the first large QScrollArea is
    used so that off-screen (scrolled-past) content is included.
    """
    # Timeline: grab the full canvas, not just the visible viewport
    if section_key == 'timeline':
        canvas = getattr(widget, '_canvas', None)
        if canvas is not None:
            return canvas.grab()

    # Generic: find the main scroll area and grab its inner content widget
    for sa in widget.findChildren(QScrollArea):
        inner = sa.widget()
        if inner is not None and inner.height() > 150:
            return inner.grab()

    # Fallback: grab whatever is visible
    return widget.grab()


def print_section(section_key: str, widget: QWidget,
                  title: str, parent: QWidget,
                  landscape: bool = False) -> None:
    """Open a print-preview dialog for the given section widget.

    Args:
        section_key:  Internal key, e.g. 'timeline', 'report', …
        widget:       The section's root QWidget.
        title:        Human-readable name shown in the dialog title.
        parent:       Parent window for the dialog.
        landscape:    Use landscape page orientation (True for Timeline).
    """
    try:
        from PyQt5.QtPrintSupport import QPrinter, QPrintPreviewDialog
    except ImportError:
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.warning(parent, 'Print unavailable',
                            'PyQt5 print support is not available on this system.')
        return

    from PyQt5.QtGui import QPageLayout

    printer = QPrinter(QPrinter.HighResolution)
    printer.setPageOrientation(
        QPageLayout.Landscape if landscape else QPageLayout.Portrait
    )

    pixmap = _get_printable_pixmap(section_key, widget)

    preview = QPrintPreviewDialog(printer, parent)
    preview.setWindowTitle(f'Print — {title}')
    preview.resize(1000, 750)

    def _render(p: QPrinter):
        if pixmap.isNull():
            return
        painter = QPainter(p)
        page = QRectF(p.pageRect())
        src  = QRectF(pixmap.rect())

        # Scale so width fits the page exactly; content flows over multiple pages
        scale = page.width() / src.width()
        total_h = src.height() * scale
        pages_needed = max(1, math.ceil(total_h / page.height()))

        for page_num in range(pages_needed):
            if page_num > 0:
                p.newPage()
            y_src = (page_num * page.height()) / scale
            h_src = min(page.height() / scale, src.height() - y_src)
            src_strip = QRectF(0, y_src, src.width(), h_src)
            dst_strip = QRectF(0, 0, page.width(), h_src * scale)
            painter.drawPixmap(dst_strip, pixmap, src_strip)

        painter.end()

    preview.paintRequested.connect(_render)
    preview.exec_()
