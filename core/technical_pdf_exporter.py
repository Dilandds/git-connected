"""
Technical Overview PDF Exporter.

Generates a 2- or 3-page portrait PDF report:
  Page 1 – Title "Technical overview" + annotated document image.
  Page 2 – "Details" (left-sidebar fields when filled), separator, "Annotations" + table (N° | Annotations | Photos).
  Continuation – Photo gallery with annotation numbers (optional).
"""
import html
import logging
import os
import tempfile
from typing import List, Optional
from ui.styles import make_font

logger = logging.getLogger(__name__)


class TechnicalPDFExporter:
    """Exports a Technical Overview workspace to a printable PDF report."""

    @staticmethod
    def export(
        document_pixmap,          # QPixmap of the loaded document
        annotations: list,        # List[ArrowAnnotation] dataclass instances
        metadata: dict,           # from TechnicalSidebar.get_metadata()
        output_path: str,
        title: str = "Technical overview",
    ) -> tuple:
        """
        Export the Technical Overview to a 2- or 3-page portrait PDF.

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
                Table, TableStyle, PageBreak, KeepTogether
            )
        except ImportError:
            return False, "reportlab is not installed. Install with: pip install reportlab"

        temp_dir = tempfile.mkdtemp()

        try:
            # --- 1. Render annotated image ---
            annotated_img_path = os.path.join(temp_dir, "annotated_document.png")
            TechnicalPDFExporter._render_annotated_image(
                document_pixmap, annotations, annotated_img_path
            )

            if not os.path.exists(annotated_img_path):
                return False, "Failed to render annotated image"

            # --- 2. Build PDF (portrait A4) ---
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=15 * mm,
                leftMargin=15 * mm,
                topMargin=15 * mm,
                bottomMargin=15 * mm,
            )

            page_width = A4[0] - 30 * mm
            page_height = A4[1] - 30 * mm

            styles = getSampleStyleSheet()

            # --- Styles ---
            title_style = ParagraphStyle(
                "TOTitle",
                parent=styles["Heading1"],
                fontName="Helvetica-Bold",
                fontSize=24,
                spaceAfter=4,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#1E293B"),
            )
            field_label_style = ParagraphStyle(
                "TOFieldLabel",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=10,
                textColor=colors.HexColor("#1E293B"),
            )
            field_value_style = ParagraphStyle(
                "TOFieldValue",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=10,
                textColor=colors.HexColor("#334155"),
                borderWidth=0,
            )
            section_style = ParagraphStyle(
                "TOSection",
                parent=styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=14,
                spaceBefore=14,
                spaceAfter=6,
                textColor=colors.HexColor("#1E293B"),
            )
            body_style = ParagraphStyle(
                "TOBody",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=10,
                leading=14,
                textColor=colors.HexColor("#334155"),
            )
            cell_style = ParagraphStyle(
                "TOCell",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=10,
                leading=13,
                textColor=colors.HexColor("#334155"),
            )
            cell_bold_style = ParagraphStyle(
                "TOCellBold",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=10,
                leading=13,
                textColor=colors.HexColor("#1E293B"),
            )
            photo_num_style = ParagraphStyle(
                "TOPhotoNum",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=9,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#FFFFFF"),
            )

            story = []

            # ==================== PAGE 1: Annotated Drawing ====================
            story.append(Paragraph("Technical overview", title_style))
            story.append(Spacer(1, 4))

            from PIL import Image as PILImage
            pil_img = PILImage.open(annotated_img_path)
            iw, ih = pil_img.size
            pil_img.close()
            aspect = ih / iw if iw else 1

            available_h = page_height - 50
            img_w = page_width
            img_h = img_w * aspect
            if img_h > available_h:
                img_h = available_h
                img_w = img_h / aspect

            story.append(Image(annotated_img_path, width=img_w, height=img_h))

            # ==================== PAGE 2: Details + Annotations ====================
            story.append(PageBreak())

            prop_val = metadata.get("property") or ""
            title_val = metadata.get("title") or ""
            manufacturers = metadata.get("manufacturers", [])
            manuf_val = ", ".join(manufacturers) if manufacturers else ""
            start_date = metadata.get("start_date") or ""
            deadline = metadata.get("deadline") or ""
            comments = metadata.get("comments") or ""

            # --- Details: 3×2 grid (row1: Property, Object title, Manufacturer | row2: dates + Comments) ---
            def _detail_value(s: str) -> str:
                return html.escape(s, quote=False).replace("\n", "<br/>")

            def _detail_cell(label: str, raw: str):
                v = (raw or "").strip()
                if v:
                    return Paragraph(f"<b>{label}</b><br/>{_detail_value(v)}", field_value_style)
                return Paragraph(f"<b>{label}</b>", field_label_style)

            has_details = any(
                x.strip()
                for x in (prop_val, title_val, manuf_val, start_date, deadline, comments)
            )

            if has_details:
                story.append(Paragraph("Details", section_style))
                story.append(Spacer(1, 4))
                col_w = page_width / 3.0
                grid_row1 = [
                    _detail_cell("Property", prop_val),
                    _detail_cell("Object title", title_val),
                    _detail_cell("Manufacturer(s)", manuf_val),
                ]
                grid_row2 = [
                    _detail_cell("Start date", start_date),
                    _detail_cell("Deadline", deadline),
                    _detail_cell("Comments", comments),
                ]
                details_table = Table(
                    [grid_row1, grid_row2],
                    colWidths=[col_w, col_w, col_w],
                )
                details_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("BOTTOMPADDING", (0, 1), (-1, 1), 4),
                    ("TOPPADDING", (0, 1), (-1, 1), 8),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.25, colors.HexColor("#E2E8F0")),
                    ("LINEBELOW", (0, 1), (-1, 1), 0.25, colors.HexColor("#E2E8F0")),
                    ("LINEAFTER", (0, 0), (0, -1), 0.25, colors.HexColor("#E2E8F0")),
                    ("LINEAFTER", (1, 0), (1, -1), 0.25, colors.HexColor("#E2E8F0")),
                ]))
                story.append(details_table)
                story.append(Spacer(1, 10))

                sep_line = Table([[""]], colWidths=[page_width])
                sep_line.setStyle(TableStyle([
                    ("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor("#94A3B8")),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(sep_line)
                story.append(Spacer(1, 10))

            # --- Annotations (table unchanged below) ---
            story.append(Paragraph("Annotations", section_style))
            story.append(Spacer(1, 6))

            # --- Annotations table (N° | Annotations | Photos) ---
            # Only show actual annotation rows, no empty filler
            num_annotations = len(annotations) if annotations else 0

            # Check which annotations have photos
            has_photos = False
            photo_entries = []
            if annotations:
                for idx, ann in enumerate(annotations, start=1):
                    paths = getattr(ann, "image_paths", []) or []
                    existing = [p for p in paths if os.path.exists(p)]
                    if existing:
                        has_photos = True
                        for img_path in existing:
                            photo_entries.append((idx, img_path))

            ann_header = [
                Paragraph("<b>N°</b>", cell_bold_style),
                Paragraph("<b>Annotations</b>", cell_bold_style),
                Paragraph("<b>Photos</b>", cell_bold_style),
            ]

            ann_rows = [ann_header]
            if annotations:
                for idx, ann in enumerate(annotations, start=1):
                    label = getattr(ann, "label", "") or ""
                    text = getattr(ann, "text", "") or ""
                    desc = f"<b>{label}</b>"
                    if text:
                        desc += f" — {text.replace(chr(10), '<br/>')}"
                    # Check if this annotation has photos
                    paths = getattr(ann, "image_paths", []) or []
                    has_img = any(os.path.exists(p) for p in paths)
                    photo_indicator = "Yes" if has_img else ""
                    ann_rows.append([
                        Paragraph(f"<b>{idx}</b>", cell_bold_style),
                        Paragraph(desc, cell_style),
                        Paragraph(photo_indicator, cell_style),
                    ])

            num_col_w = 12 * mm
            photo_col_w = 18 * mm
            ann_table_widget = Table(
                ann_rows,
                colWidths=[num_col_w, page_width - num_col_w - photo_col_w, photo_col_w],
            )

            border_color = colors.HexColor("#94A3B8")
            total_data_rows = len(ann_rows) - 1  # exclude header
            ann_table_widget.setStyle(TableStyle([
                # Header
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F4F8")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 11),
                # All cells
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 0), (2, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, border_color),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                # Alternate row shading
                *[("BACKGROUND", (0, r), (-1, r), colors.HexColor("#FAFBFC"))
                  for r in range(2, total_data_rows + 1, 2)],
            ]))
            story.append(ann_table_widget)

            # ==================== Photos Section ====================
            # If there are photos, add them after the table (same page if space, otherwise page 3)
            if has_photos and photo_entries:
                story.append(Spacer(1, 14))

                photo_title_style = ParagraphStyle(
                    "PhotoTitle",
                    parent=styles["Heading2"],
                    fontName="Helvetica-Bold",
                    fontSize=14,
                    spaceBefore=8,
                    spaceAfter=4,
                    textColor=colors.HexColor("#1E293B"),
                )
                photo_caption_style = ParagraphStyle(
                    "PhotoCaption",
                    parent=body_style,
                    fontSize=9,
                    leading=12,
                    spaceAfter=6,
                    textColor=colors.HexColor("#64748B"),
                )
                story.append(Paragraph("Annotation photos", photo_title_style))
                story.append(Paragraph(
                    "<i>(Photos uploaded for the relevant annotation — please match with the annotation number from the table.)</i>",
                    photo_caption_style,
                ))
                story.append(Spacer(1, 4))

                # Layout: 3 columns grid
                cols = 3
                photo_size = (page_width - 10 * mm) / cols
                max_photo_h = photo_size

                grid_rows = []
                current_row = []

                for ann_num, img_path in photo_entries:
                    photo_cell = TechnicalPDFExporter._create_photo_cell(
                        img_path, ann_num, photo_size, max_photo_h,
                        temp_dir, cell_bold_style
                    )
                    current_row.append(photo_cell)

                    if len(current_row) == cols:
                        grid_rows.append(current_row)
                        current_row = []

                if current_row:
                    while len(current_row) < cols:
                        current_row.append("")
                    grid_rows.append(current_row)

                if grid_rows:
                    photo_table = Table(
                        grid_rows,
                        colWidths=[photo_size + 3 * mm] * cols,
                        rowHeights=[photo_size + 8 * mm] * len(grid_rows),
                    )
                    photo_table.setStyle(TableStyle([
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ]))
                    story.append(photo_table)
            doc.build(story)
            logger.info("Technical Overview PDF exported: %s", output_path)
            return True, output_path

        except Exception as e:
            logger.error("Technical PDF export failed: %s", e, exc_info=True)
            return False, str(e)
        finally:
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
    def _create_photo_cell(img_path, ann_num, target_w, target_h, temp_dir, style):
        """
        Create a photo cell: the image with a numbered badge in the top-left corner.
        Returns a reportlab Image flowable with badge burned in.
        """
        from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QBrush, QImage, QPixmap
        from PyQt5.QtCore import Qt, QRectF
        from reportlab.platypus import Image

        try:
            # Load image
            source = QImage(img_path)
            if source.isNull():
                return ""

            # Scale to target size (square crop)
            size = int(target_w * 2)  # render at 2x for quality
            scaled = source.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

            # Center crop to square
            canvas = QImage(size, size, QImage.Format_ARGB32)
            canvas.fill(QColor("#F5F5F5"))
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.Antialiasing)

            x_off = (scaled.width() - size) // 2
            y_off = (scaled.height() - size) // 2
            painter.drawImage(0, 0, scaled, x_off, y_off, size, size)

            # Draw number badge (top-left corner)
            badge_size = max(36, size // 8)
            badge_margin = 8
            badge_rect = QRectF(badge_margin, badge_margin, badge_size, badge_size)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("#1E293B")))
            painter.drawEllipse(badge_rect)

            # White border
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(badge_rect)

            # Number text
            painter.setPen(QColor("#FFFFFF"))
            from ui.styles import make_font as _mf
            font = _mf(size=int(badge_size * 0.45), bold=True)
            painter.setFont(font)
            painter.drawText(badge_rect, Qt.AlignCenter, str(ann_num))

            painter.end()

            # Save temp
            out_path = os.path.join(temp_dir, f"photo_{ann_num}_{id(img_path)}.png")
            canvas.save(out_path, "PNG")

            if os.path.exists(out_path):
                return Image(out_path, width=target_w, height=target_w)
            return ""
        except Exception as e:
            logger.warning("Failed to create photo cell: %s", e)
            return ""

    @staticmethod
    def _render_annotated_image(pixmap, annotations, output_path: str):
        """
        Render the document pixmap with arrow annotations drawn on top
        and save as a PNG image for embedding in the PDF.

        Uses thicker lines and larger numbered badges for PDF clarity.
        """
        from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QBrush, QImage
        from PyQt5.QtCore import Qt, QPointF, QRectF

        if pixmap is None or pixmap.isNull():
            return

        # Compute margins needed to fit all annotation origins (which may be outside 0-1)
        base_margin = 80
        extra_left = extra_right = extra_top = extra_bottom = 0
        for ann in annotations:
            ox, oy = getattr(ann, 'origin_x', 0.5), getattr(ann, 'origin_y', 0.5)
            if ox < 0:
                extra_left = max(extra_left, -ox * pixmap.width() + 60)
            if ox > 1:
                extra_right = max(extra_right, (ox - 1) * pixmap.width() + 60)
            if oy < 0:
                extra_top = max(extra_top, -oy * pixmap.height() + 60)
            if oy > 1:
                extra_bottom = max(extra_bottom, (oy - 1) * pixmap.height() + 60)

        margin_l = base_margin + int(extra_left)
        margin_r = base_margin + int(extra_right)
        margin_t = base_margin + int(extra_top)
        margin_b = base_margin + int(extra_bottom)

        total_w = pixmap.width() + margin_l + margin_r
        total_h = pixmap.height() + margin_t + margin_b

        canvas = QImage(total_w, total_h, QImage.Format_ARGB32)
        canvas.fill(QColor("#FFFFFF"))

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw the document image
        img_rect = QRectF(margin_l, margin_t, pixmap.width(), pixmap.height())
        painter.drawPixmap(img_rect.toRect(), pixmap)

        # Draw each annotation arrow
        for idx, ann in enumerate(annotations, start=1):
            target = QPointF(
                img_rect.x() + ann.target_x * img_rect.width(),
                img_rect.y() + ann.target_y * img_rect.height(),
            )
            origin = QPointF(
                img_rect.x() + ann.origin_x * img_rect.width(),
                img_rect.y() + ann.origin_y * img_rect.height(),
            )

            arrow_color = QColor(getattr(ann, "color", "#5294E2") or "#5294E2")

            # Arrow line — thick for PDF visibility
            pen = QPen(arrow_color, 5.0)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(origin, target)

            # Bullet at target
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(arrow_color))
            painter.drawEllipse(target, 7.0, 7.0)

            # Numbered badge at origin
            badge_size = 44
            badge_rect = QRectF(
                origin.x() - badge_size / 2,
                origin.y() - badge_size / 2,
                badge_size,
                badge_size,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(arrow_color))
            painter.drawEllipse(badge_rect)

            # Badge number
            painter.setPen(QColor("#FFFFFF"))
            font = make_font(size=18, bold=True)
            painter.setFont(font)
            painter.drawText(badge_rect, Qt.AlignCenter, str(idx))

        painter.end()
        canvas.save(output_path, "PNG")
        logger.info("Annotated image rendered: %s (%dx%d)", output_path, total_w, total_h)
