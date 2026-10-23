"""
generate_report.py - Generate a human-readable PDF report of detected barcodes.
Usage: python -m scripts.generate_report path/to/input.pdf
Output: input_report.pdf (next to the input file)
"""

import sys
import io
import os
from pathlib import Path

# Force UTF-8 output on Windows terminal
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime
from PIL import Image, ImageDraw
import pymupdf as fitz
from pyzbar.pyzbar import decode
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, PageBreak, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from bidi.algorithm import get_display

# ── Hebrew-capable font (Arial ships with Windows) ──────────────────────────
FONT_PATH = "C:/Windows/Fonts/arial.ttf"
FONT_BOLD_PATH = "C:/Windows/Fonts/arialbd.ttf"
try:
    pdfmetrics.registerFont(TTFont("Arial", FONT_PATH))
    pdfmetrics.registerFont(TTFont("Arial-Bold", FONT_BOLD_PATH))
    BASE_FONT = "Arial"
    BOLD_FONT = "Arial-Bold"
except Exception:
    BASE_FONT = "Helvetica"
    BOLD_FONT = "Helvetica-Bold"

def rtl(text: str) -> str:
    """Fix Hebrew/RTL text direction for ReportLab."""
    return get_display(text)


PAGE_W, PAGE_H = A4
PREVIEW_MAX_W = 14 * cm   # max width for page preview image in report
HIGHLIGHT_COLOR = (255, 80, 80)   # red rectangle on barcode
HIGHLIGHT_WIDTH = 4


def pil_to_rl_image(pil_img: Image.Image, max_width: float) -> RLImage:
    """Convert PIL image to a ReportLab Image flowable, scaled to max_width."""
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    buf.seek(0)
    ratio = pil_img.height / pil_img.width
    w = max_width
    h = w * ratio
    return RLImage(buf, width=w, height=h)


def highlight_barcodes(pil_img: Image.Image, barcodes: list, scale: float) -> Image.Image:
    """Draw red rectangles around each barcode on a copy of the image."""
    img = pil_img.copy()
    draw = ImageDraw.Draw(img)
    for bc in barcodes:
        x, y, w, h = bc["x"], bc["y"], bc["width"], bc["height"]
        if w == 0 or h == 0:
            # fallback: small cross marker
            cx, cy = int(x * scale), int(y * scale)
            r = 20
            draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                         outline=HIGHLIGHT_COLOR, width=HIGHLIGHT_WIDTH)
        else:
            x0 = int(x * scale)
            y0 = int(y * scale)
            x1 = int((x + w) * scale)
            y1 = int((y + h) * scale)
            draw.rectangle([x0, y0, x1, y1],
                           outline=HIGHLIGHT_COLOR, width=HIGHLIGHT_WIDTH)
    return img


def scan_pdf(pdf_path: Path) -> tuple[list, list]:
    """
    Returns:
        pages_data: list of {page_num, barcodes, pil_image}
        all_barcodes: flat list of all barcodes with page number
    """
    doc = fitz.open(str(pdf_path))
    pages_data = []
    all_barcodes = []

    for page in doc:
        pix = page.get_pixmap(dpi=200)
        pil_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        barcodes = []
        for bc in decode(pil_img):
            rect = bc.rect
            entry = {
                "page": page.number + 1,
                "data": bc.data.decode("utf-8", errors="replace").strip(),
                "type": bc.type,
                "x": rect.left, "y": rect.top,
                "width": rect.width, "height": rect.height,
            }
            barcodes.append(entry)
            all_barcodes.append(entry)

        pages_data.append({
            "page_num": page.number + 1,
            "barcodes": barcodes,
            "pil_image": pil_img,
        })

    doc.close()
    return pages_data, all_barcodes


def build_styles():
    styles = getSampleStyleSheet()
    def s(name, parent="Normal", **kw):
        return ParagraphStyle(name, parent=styles[parent], **kw)
    return {
        "title":    s("title",    fontSize=22, leading=28, alignment=TA_CENTER,
                      fontName=BOLD_FONT, textColor=colors.HexColor("#1a1a2e")),
        "subtitle": s("subtitle", fontSize=12, leading=16, alignment=TA_CENTER,
                      textColor=colors.HexColor("#555555")),
        "section":  s("section",  fontSize=14, leading=20,
                      fontName=BOLD_FONT, textColor=colors.HexColor("#1a1a2e"),
                      spaceBefore=12),
        "body":     s("body",     fontSize=10, leading=14),
        "caption":  s("caption",  fontSize=9,  leading=12,
                      textColor=colors.HexColor("#666666"), alignment=TA_CENTER),
        "tag_green": s("tag_green", fontSize=10, leading=14,
                       textColor=colors.HexColor("#1a7a1a"), fontName=BOLD_FONT),
        "tag_gray":  s("tag_gray",  fontSize=10, leading=14,
                       textColor=colors.HexColor("#888888")),
    }


def summary_table(all_barcodes: list, styles: dict) -> Table:
    header = ["#", rtl("עמוד"), rtl("סוג"), rtl("ערך הברקוד")]
    rows = [header]
    for i, bc in enumerate(all_barcodes, 1):
        rows.append([
            str(i),
            str(bc["page"]),
            bc["type"],
            bc["data"],
        ])

    col_widths = [1.2 * cm, 1.8 * cm, 3.2 * cm, 9.5 * cm]
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        # header
        ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), BOLD_FONT),
        ("FONTSIZE",     (0, 0), (-1, 0), 10),
        ("ALIGN",        (0, 0), (-1, 0), "CENTER"),
        # body
        ("FONTNAME",     (0, 1), (-1, -1), BASE_FONT),
        ("FONTSIZE",     (0, 1), (-1, -1), 9),
        ("ALIGN",        (0, 1), (2, -1),  "CENTER"),
        ("ALIGN",        (3, 1), (3, -1),  "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#f7f7f7"), colors.white]),
        ("GRID",         (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    return t


def generate_report(pdf_path: str) -> str:
    src = Path(pdf_path)
    out_path = src.parent / (src.stem + "_report.pdf")

    print(f"Scanning: {src.name} ...")
    pages_data, all_barcodes = scan_pdf(src)
    total_pages = len(pages_data)
    total_barcodes = len(all_barcodes)
    print(f"  -> {total_pages} pages, {total_barcodes} barcodes found.")

    styles = build_styles()
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    story = []

    # ── Cover ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 2 * cm))
    story.append(Paragraph(rtl("דוח קריאת ברקודים"), styles["title"]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(src.name, styles["subtitle"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        rtl(datetime.now().strftime("נוצר: %d/%m/%Y  %H:%M")),
        styles["subtitle"]
    ))
    story.append(Spacer(1, 0.6 * cm))
    story.append(HRFlowable(width="100%", thickness=1,
                             color=colors.HexColor("#1a1a2e")))
    story.append(Spacer(1, 0.6 * cm))

    # stats boxes
    stats = [
        [rtl("עמודים סרוקים"), rtl("ברקודים שנמצאו"), rtl("עמודים עם ברקוד")],
        [
            str(total_pages),
            str(total_barcodes),
            str(len({bc["page"] for bc in all_barcodes})),
        ]
    ]
    st = Table(stats, colWidths=[5 * cm, 5 * cm, 5 * cm])
    st.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
        ("BACKGROUND",    (0, 1), (-1, 1), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR",     (0, 1), (-1, 1), colors.white),
        ("FONTNAME",      (0, 0), (-1, -1), BOLD_FONT),
        ("FONTSIZE",      (0, 0), (-1, 0), 9),
        ("FONTSIZE",      (0, 1), (-1, 1), 22),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ROUNDEDCORNERS", [6]),
        ("BOX",           (0, 0), (-1, -1), 0, colors.white),
        ("INNERGRID",     (0, 0), (-1, -1), 2, colors.white),
    ]))
    story.append(st)
    story.append(Spacer(1, 1 * cm))

    # ── Summary table ────────────────────────────────────────────────────────
    if all_barcodes:
        story.append(Paragraph(rtl("סיכום כל הברקודים"), styles["section"]))
        story.append(Spacer(1, 0.3 * cm))
        story.append(summary_table(all_barcodes, styles))
    else:
        story.append(Paragraph(rtl("לא נמצאו ברקודים בקובץ."), styles["body"]))

    story.append(PageBreak())

    # ── Per-page section ─────────────────────────────────────────────────────
    story.append(Paragraph(rtl("פירוט לפי עמוד"), styles["title"]))
    story.append(Spacer(1, 0.5 * cm))

    for pd in pages_data:
        pnum = pd["page_num"]
        barcodes = pd["barcodes"]
        pil_img = pd["pil_image"]

        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=colors.HexColor("#cccccc")))
        story.append(Spacer(1, 0.3 * cm))

        # page header row
        status_style = styles["tag_green"] if barcodes else styles["tag_gray"]
        status_text = rtl(f"✔ {len(barcodes)} ברקוד/ים") if barcodes else rtl("— אין ברקודים")
        header_row = Table(
            [[Paragraph(rtl(f"עמוד {pnum}"), styles["section"]),
              Paragraph(status_text, status_style)]],
            colWidths=[13 * cm, 3.5 * cm]
        )
        header_row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN",  (1, 0), (1, 0),   "RIGHT"),
        ]))
        story.append(header_row)
        story.append(Spacer(1, 0.3 * cm))

        # page preview with highlights
        scale = 1.0  # images are already at 200dpi, no rescale needed
        annotated = highlight_barcodes(pil_img, barcodes, scale)
        story.append(pil_to_rl_image(annotated, PREVIEW_MAX_W))

        if barcodes:
            story.append(Spacer(1, 0.3 * cm))
            # mini table for this page
            rows = [[rtl("סוג"), rtl("ערך הברקוד"), rtl("מיקום (x,y)")]]
            for bc in barcodes:
                rows.append([
                    bc["type"],
                    bc["data"],
                    f"({bc['x']}, {bc['y']})",
                ])
            pt = Table(rows, colWidths=[3 * cm, 8.5 * cm, 3 * cm])
            pt.setStyle(TableStyle([
                ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#e8e8f0")),
                ("FONTNAME",     (0, 0), (-1, 0), BOLD_FONT),
                ("FONTSIZE",     (0, 0), (-1, -1), 8),
                ("FONTNAME",     (0, 1), (-1, -1), BASE_FONT),
                ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
                ("ALIGN",        (1, 1), (1, -1),  "LEFT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.HexColor("#fafafa"), colors.white]),
                ("GRID",         (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
                ("TOPPADDING",   (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ]))
            story.append(pt)

        story.append(Spacer(1, 0.5 * cm))

    doc.build(story)
    print(f"  -> Report saved: {out_path}")
    return str(out_path)


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.generate_report path/to/file.pdf")
        sys.exit(1)
    generate_report(sys.argv[1])


if __name__ == "__main__":
    main()
