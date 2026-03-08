"""
Technical Overview PDF Exporter.

Generates a PDF report containing:
1. The document image with numbered arrow annotations rendered on top.
2. A table listing each annotation number, label, and description text.
3. Metadata from the sidebar (property, title, manufacturers, dates, comments).
"""
import logging
import os
import tempfile
from typing import List, Optional

logger = logging.getLogger(__name__)


class TechnicalPDFExporter:
    """Exports a Technical Overview workspace to a printable PDF report."""

    @staticmethod
    def export(
        document_pixmap,          # QPixmap of the loaded document
        annotations: list,        # List[ArrowAnnotation] dataclass instances
        metadata: dict,           # from TechnicalSidebar.get_metadata()
        output_path: str,
        title: str = "Technical Overview",
    ) -> tuple:
        """
        Export the Technical Overview to a PDF.

        Returns:
            (bool, str) — (success, output_path or error message)
        """
        if document_pixmap is None or document_pixmap.isNull():
            return False, "No document loaded"

        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.lib.enums import TA_CENTER, TA_LEFT
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Image,
                Table, TableStyle, PageBreak
            )
        except ImportError:
            return False, "reportlab is not installed. Install with: pip install reportlab"

        temp_dir = tempfile.mkdtemp()

        try:
            # --- 1. Render annotated image ---------------------------------------------------
            annotated_img_path = os.path.join(temp_dir, "annotated_document.png")
            TechnicalPDFExporter._render_annotated_image(
                document_pixmap, annotations, annotated_img_path
            )

            if not os.path.exists(annotated_img_path):
                return False, "Failed to render annotated image"

            # --- 2. Build PDF ----------------------------------------------------------------
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=15 * mm,
                leftMargin=15 * mm,
                topMargin=15 * mm,
                bottomMargin=15 * mm,
            )

            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                "TOTitle",
                parent=styles["Heading1"],
                fontSize=22,
                spaceAfter=6,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#1E293B"),
            )
            subtitle_style = ParagraphStyle(
                "TOSubtitle",
                parent=styles["Normal"],
                fontSize=11,
                spaceAfter=16,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#64748B"),
            )
            section_style = ParagraphStyle(
                "TOSection",
                parent=styles["Heading2"],
                fontSize=14,
                spaceBefore=14,
                spaceAfter=6,
                textColor=colors.HexColor("#1E293B"),
            )
            body_style = ParagraphStyle(
                "TOBody",
                parent=styles["Normal"],
                fontSize=10,
                leading=14,
                textColor=colors.HexColor("#334155"),
            )
            cell_style = ParagraphStyle(
                "TOCell",
                parent=styles["Normal"],
                fontSize=10,
                leading=13,
                textColor=colors.HexColor("#334155"),
            )

            story = []

            # --- Header ---
            doc_title = metadata.get("title") or title
            story.append(Paragraph(doc_title, title_style))

            subtitle_parts = []
            if metadata.get("property"):
                subtitle_parts.append(f"Property: {metadata['property']}")
            if metadata.get("manufacturers"):
                subtitle_parts.append(f"Manufacturer: {', '.join(metadata['manufacturers'])}")
            if subtitle_parts:
                story.append(Paragraph(" · ".join(subtitle_parts), subtitle_style))
            story.append(Spacer(1, 6))

            # --- Metadata table ---
            meta_rows = [["Field", "Details"]]
            if metadata.get("property"):
                meta_rows.append(["Property", metadata["property"]])
            if metadata.get("title"):
                meta_rows.append(["Object Title", metadata["title"]])
            if metadata.get("manufacturers"):
                meta_rows.append(["Manufacturer(s)", ", ".join(metadata["manufacturers"])])
            if metadata.get("start_date"):
                meta_rows.append(["Start Date", metadata["start_date"]])
            if metadata.get("deadline"):
                meta_rows.append(["Deadline", metadata["deadline"]])

            if len(meta_rows) > 1:
                story.append(Paragraph("Project Details", section_style))
                meta_table = Table(meta_rows, colWidths=[50 * mm, 120 * mm])
                meta_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F7FF")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]))
                story.append(meta_table)
                story.append(Spacer(1, 10))

            # --- Comments ---
            if metadata.get("comments"):
                story.append(Paragraph("Comments", section_style))
                story.append(Paragraph(metadata["comments"].replace("\n", "<br/>"), body_style))
                story.append(Spacer(1, 10))

            # --- Annotated document image ---
            story.append(Paragraph("Annotated Document", section_style))
            page_width = A4[0] - 30 * mm
            # Maintain aspect ratio
            from PIL import Image as PILImage
            pil_img = PILImage.open(annotated_img_path)
            iw, ih = pil_img.size
            pil_img.close()
            aspect = ih / iw if iw else 1
            img_w = page_width
            img_h = img_w * aspect
            # Cap height to avoid overflowing a page
            max_h = A4[1] - 60 * mm
            if img_h > max_h:
                img_h = max_h
                img_w = img_h / aspect

            story.append(Image(annotated_img_path, width=img_w, height=img_h))
            story.append(Spacer(1, 14))

            # --- Annotations table ---
            if annotations:
                story.append(Paragraph("Annotations", section_style))
                ann_header = ["#", "Label", "Description"]
                ann_rows = [ann_header]
                for idx, ann in enumerate(annotations, start=1):
                    label = getattr(ann, "label", "") or ""
                    text = getattr(ann, "text", "") or ""
                    ann_rows.append([
                        str(idx),
                        Paragraph(label, cell_style),
                        Paragraph(text.replace("\n", "<br/>") if text else "—", cell_style),
                    ])

                ann_table = Table(ann_rows, colWidths=[12 * mm, 40 * mm, 118 * mm])
                ann_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F7FF")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                    ("ALIGN", (0, 0), (0, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]))
                story.append(ann_table)

            doc.build(story)
            logger.info("Technical Overview PDF exported: %s", output_path)
            return True, output_path

        except Exception as e:
            logger.error("Technical PDF export failed: %s", e, exc_info=True)
            return False, str(e)
        finally:
            # Cleanup temp files
            try:
                for f in os.listdir(temp_dir):
                    try:
                        os.remove(os.path.join(temp_dir, f))
                    except Exception:
                        pass
                os.rmdir(temp_dir)
            except Exception:
                pass

    @staticmethod
    def _render_annotated_image(pixmap, annotations, output_path: str):
        """
        Render the document pixmap with arrow annotations drawn on top
        and save as a PNG image for embedding in the PDF.
        """
        from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QBrush, QImage
        from PyQt5.QtCore import Qt, QPointF, QRectF

        if pixmap is None or pixmap.isNull():
            return

        # Work on a copy with margins for arrow origins
        margin = 50  # px margin around image for badges
        total_w = pixmap.width() + margin * 2
        total_h = pixmap.height() + margin * 2

        canvas = QImage(total_w, total_h, QImage.Format_ARGB32)
        canvas.fill(QColor("#FFFFFF"))

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw the document image centred in the canvas
        img_rect = QRectF(margin, margin, pixmap.width(), pixmap.height())
        painter.drawPixmap(img_rect.toRect(), pixmap)

        # Draw each annotation arrow
        margin_gap = 40
        for idx, ann in enumerate(annotations, start=1):
            target = QPointF(
                img_rect.x() + ann.target_x * img_rect.width(),
                img_rect.y() + ann.target_y * img_rect.height(),
            )

            # Use stored origin coordinates
            origin = QPointF(
                img_rect.x() + ann.origin_x * img_rect.width(),
                img_rect.y() + ann.origin_y * img_rect.height(),
            )

            arrow_color = QColor(getattr(ann, "color", "#5294E2") or "#5294E2")

            # Arrow line
            pen = QPen(arrow_color, 2.5)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(origin, target)

            # Bullet at target
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(arrow_color))
            painter.drawEllipse(target, 3.0, 3.0)

            # Numbered badge at origin
            badge_size = 24
            badge_rect = QRectF(
                origin.x() - badge_size / 2,
                origin.y() - badge_size / 2,
                badge_size,
                badge_size,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(arrow_color))
            painter.drawEllipse(badge_rect)

            painter.setPen(QColor("#FFFFFF"))
            font = QFont()
            font.setBold(True)
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(badge_rect, Qt.AlignCenter, str(idx))

        painter.end()
        canvas.save(output_path, "PNG")
        logger.info("Annotated image rendered: %s (%dx%d)", output_path, total_w, total_h)
