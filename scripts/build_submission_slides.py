"""Build a six-slide editable MOTIONIQ draft deck and matching PDF locally."""
from __future__ import annotations

import json
import math
import re
import tempfile
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[1]
PPTX_PATH = ROOT / "slides" / "MOTIONIQ.pptx"
PDF_PATH = ROOT / "slides" / "MOTIONIQ.pdf"
BENCHMARK_PATH = ROOT / "runs" / "laptop-benchmark" / "final.json"

SW, SH = 13.333333, 7.5
PAPER = "F8F7F3"
WHITE = "FFFFFF"
INK = "22333B"
MUTED = "56666D"
LINE = "D9DDD9"
ORANGE = "D97832"
BLUE = "327DA8"
PALE = "EEEDE7"
FONT = "Arial"

NOTES = [
    "Sources: product brief and current submission summary. Generic factory workflow; no footage shown.",
    "Sources: implementation summary and coordinate status. 3D estimates keep their coordinate-frame limits.",
    "Source: current viewer controls. Demonstrate Review, Analysis, Diagnostics, Camera, Side, Top, and Follow hand.",
    "Sources: current project status and the historical experiment report. Common-clip accuracy awaits human-reviewed labels. The historical hybrid decision belongs to a separate, provisional one-clip experiment.",
    "Sources: the final team-laptop benchmark artifact, when available, and the review-time pilot protocol. An empty or missing benchmark is reported as not measured.",
    "Sources: experimental 3D status, known limitations, and submission summary.",
]


def words(text: str) -> int:
    return len(re.findall(r"\b[\w]+(?:[./-][\w]+)*\b", text, re.UNICODE))


def load_performance() -> list[dict] | None:
    """Load only the final isolated laptop run; never consume warm-up benchmark.json."""
    if not BENCHMARK_PATH.is_file() or BENCHMARK_PATH.stat().st_size == 0:
        return None
    data = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    if data.get("status") not in (None, "complete"):
        raise ValueError("Final laptop benchmark is not complete")
    rows = data.get("results")
    if not isinstance(rows, list):
        raise ValueError("Final laptop benchmark must contain a results list")
    presets = {"baseline", "recall", "accurate", "hybrid"}
    validated = []
    for row in rows:
        preset = row.get("preset")
        if preset not in presets:
            raise ValueError("Benchmark contains an unknown preset")
        if row.get("error") or row.get("status") not in (None, "complete"):
            validated.append({"preset": preset, "status": "failed"})
            continue
        seconds = row.get("wall_s", row.get("processing_seconds"))
        fps = row.get("end_to_end_fps")
        frames = row.get("frames", row.get("processed_frames"))
        if not all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0
                   for x in (seconds, fps, frames)):
            raise ValueError(f"Benchmark result for {preset} lacks valid seconds, FPS, or frames")
        if abs(fps - frames / row.get("processing_seconds", seconds)) > max(.05, fps * .02):
            raise ValueError(f"Benchmark result for {preset} has inconsistent FPS")
        validated.append({"preset": preset, "status": "complete", "seconds": seconds,
                          "fps": fps, "frames": int(frames)})
    seen = [r["preset"] for r in validated]
    if len(seen) != len(set(seen)):
        raise ValueError("Benchmark contains duplicate preset rows")
    return validated


def title(slide, text: str, x=.72, y=.52, w=11.9, h=.6, size=31):
    return add_text(slide, text, x, y, w, h, size, INK, bold=True)


def add_text(slide, text: str, x: float, y: float, w: float, h: float,
             size: float, color: str = INK, *, bold=False, align=PP_ALIGN.LEFT,
             valign=MSO_ANCHOR.TOP, font=FONT):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = 0
    frame.margin_top = frame.margin_bottom = 0
    frame.vertical_anchor = valign
    for i, line in enumerate(text.split("\n")):
        p = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        p.alignment = align
        p.space_before = Pt(0)
        p.space_after = Pt(0)
        run = p.add_run()
        run.text = line
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = RGBColor.from_string(color)
    return box


def add_rule(slide, x1, y1, x2, y2, color=LINE, width=1):
    line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    line.line.color.rgb = RGBColor.from_string(color)
    line.line.width = Pt(width)
    return line


def add_node(slide, text, x, y, w, h, accent):
    node = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    node.fill.solid()
    node.fill.fore_color.rgb = RGBColor.from_string(WHITE)
    node.line.color.rgb = RGBColor.from_string(accent)
    node.line.width = Pt(1.7)
    frame = node.text_frame
    frame.clear()
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = Inches(.08)
    frame.margin_top = frame.margin_bottom = Inches(.06)
    for i, label in enumerate(text.split("\n")):
        p = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        p.space_after = Pt(0)
        run = p.add_run()
        run.text = label
        run.font.name = FONT
        run.font.size = Pt(15)
        run.font.bold = i == 0
        run.font.color.rgb = RGBColor.from_string(INK)
    return node


def add_arrow(slide, x, y):
    shape = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(.25), Inches(.16))
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor.from_string(MUTED)
    shape.line.fill.background()


def set_slide_bg(slide):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor.from_string(PAPER)


def add_notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def build_pptx(performance):
    prs = Presentation()
    prs.slide_width = Inches(SW)
    prs.slide_height = Inches(SH)
    prs.core_properties.author = "MOTIONIQ team"
    prs.core_properties.creator = "MOTIONIQ team"
    prs.core_properties.last_modified_by = "MOTIONIQ team"
    prs.core_properties.title = "MOTIONIQ"
    prs.core_properties.subject = "Draft for team review"
    blank = prs.slide_layouts[6]

    # 1. Cover
    s = prs.slides.add_slide(blank); set_slide_bg(s)
    add_text(s, "MOTIONIQ", .82, 1.12, 11.4, .85, 46, INK, bold=True)
    add_text(s, "Factory POV video holds useful hand motion. Teams need trustworthy cues to find usable seconds.",
             .85, 2.35, 10.5, 1.15, 25, MUTED)
    add_text(s, "WEARER LEFT", .88, 5.25, 3.1, .35, 16, ORANGE, bold=True)
    add_text(s, "WEARER RIGHT", 5.12, 5.25, 3.1, .35, 16, BLUE, bold=True)
    add_text(s, "DRAFT FOR TEAM REVIEW", .88, 6.65, 3.6, .3, 11, MUTED, bold=True)
    add_notes(s, NOTES[0])

    # 2. Editable pipeline diagram
    s = prs.slides.add_slide(blank); set_slide_bg(s)
    title(s, "Processing path")
    labels = ["Video", "Detection\npresets", "Track\nstates", "Smoothing", "Estimated\n3D", "Viewer, timeline\nand exports"]
    x0, y, width, gap, h = .70, 2.5, 1.72, .39, 1.38
    for i, label in enumerate(labels):
        accent = ORANGE if i in (1, 2) else BLUE if i == 4 else MUTED
        x = x0 + i * (width + gap)
        add_node(s, label, x, y, width, h, accent)
        if i < len(labels)-1:
            add_arrow(s, x + width + .07, y + .6)
    add_text(s, "Predicted tracks are 2D only.", .78, 4.45, 5.2, .4, 18, INK)
    add_text(s, "Wearer left", .78, 5.30, 2.6, .4, 16, ORANGE, bold=True)
    add_text(s, "Wearer right", 3.45, 5.30, 2.6, .4, 16, BLUE, bold=True)
    add_notes(s, NOTES[1])

    # 3. Live demo cue
    s = prs.slides.add_slide(blank); set_slide_bg(s)
    title(s, "Live demo cue")
    add_text(s, "REVIEW", .84, 1.70, 2.6, .35, 15, ORANGE, bold=True)
    add_text(s, "Synchronized video, landmarks, 3D, timeline and events", .84, 2.15, 5.2, 1.1, 24, INK)
    add_rule(s, 6.68, 1.65, 6.68, 3.28)
    add_text(s, "ANALYSIS", 7.15, 1.70, 2.6, .35, 15, BLUE, bold=True)
    add_text(s, "Signals and exports", 7.15, 2.15, 4.9, .7, 24, INK)
    add_text(s, "DIAGNOSTICS", .84, 4.35, 2.6, .35, 15, MUTED, bold=True)
    add_text(s, "Pipeline detail", .84, 4.8, 4.9, .55, 21, INK)
    add_text(s, "CAMERA   SIDE   TOP", 7.15, 4.35, 4.9, .35, 15, BLUE, bold=True)
    add_text(s, "Follow hand", 7.15, 4.8, 4.9, .55, 21, INK)
    add_notes(s, NOTES[2])

    # 4. Accuracy evidence table, intentionally N/M for every current common-clip cell.
    s = prs.slides.add_slide(blank); set_slide_bg(s)
    title(s, "Accuracy")
    table = s.shapes.add_table(5, 6, Inches(.85), Inches(1.72), Inches(11.6), Inches(2.68)).table
    widths = [1.6, 1.8, 1.8, 2.0, 1.3, 3.1]
    for col, width in zip(table.columns, widths):
        col.width = Inches(width)
    data = [["Preset", "Accuracy", "Recall", "Precision", "F1", "Wrong-side"],
            ["Baseline", "N/M", "N/M", "N/M", "N/M", "N/M"],
            ["Recall", "N/M", "N/M", "N/M", "N/M", "N/M"],
            ["Accurate", "N/M", "N/M", "N/M", "N/M", "N/M"],
            ["Hybrid", "N/M", "N/M", "N/M", "N/M", "N/M"]]
    for r, row in enumerate(data):
        table.rows[r].height = Inches(.53)
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            cell.text = value
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string(INK if r == 0 else ("F1F0EA" if r % 2 else WHITE))
            cell.margin_left = cell.margin_right = Inches(.10)
            cell.margin_top = cell.margin_bottom = Inches(.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER
                for run in p.runs:
                    run.font.name = FONT
                    run.font.size = Pt(14)
                    run.font.bold = (r == 0 or c == 0)
                    run.font.color.rgb = RGBColor.from_string(WHITE if r == 0 else INK)
    add_text(s, "N/M = awaits human labels.", .88, 4.8, 5.2, .37, 15, MUTED)
    add_text(s, "Historical hybrid: experiment record.", .88, 5.35, 5.2, .37, 15, MUTED)
    add_notes(s, NOTES[3])

    # 5. Current target-laptop performance and review-time evidence
    s = prs.slides.add_slide(blank); set_slide_bg(s)
    title(s, "Laptop and pilot evidence")
    if performance is None:
        add_text(s, "LAPTOP SPEED", .95, 2.18, 4.7, .38, 17, ORANGE, bold=True)
        add_text(s, "NOT MEASURED", .95, 2.75, 5.2, .65, 29, INK, bold=True)
        add_rule(s, 6.67, 2.1, 6.67, 4.9)
        add_text(s, "REVIEW-TIME BENEFIT", 7.15, 2.18, 5.1, .38, 17, BLUE, bold=True)
        add_text(s, "NOT MEASURED", 7.15, 2.75, 5.2, .65, 29, INK, bold=True)
    else:
        rows = [["Preset", "Wall seconds", "FPS", "Frames"]]
        for row in performance:
            rows.append([row["preset"].title(),
                         f"{row['seconds']:.1f}" if row["status"] == "complete" else "Failed",
                         f"{row['fps']:.1f}" if row["status"] == "complete" else "N/M",
                         str(row["frames"]) if row["status"] == "complete" else "N/M"])
        table = s.shapes.add_table(len(rows), 4, Inches(1.05), Inches(1.58), Inches(11.2), Inches(.55*len(rows))).table
        for col, w in zip(table.columns, [3.4, 2.8, 2.3, 2.7]): col.width = Inches(w)
        for r, row in enumerate(rows):
            table.rows[r].height = Inches(.55)
            for c, value in enumerate(row):
                cell = table.cell(r, c); cell.text = value; cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor.from_string(INK if r == 0 else ("F1F0EA" if r % 2 else WHITE))
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                for p in cell.text_frame.paragraphs:
                    p.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER
                    for run in p.runs:
                        run.font.name = FONT; run.font.size = Pt(14); run.font.bold = r == 0
                        run.font.color.rgb = RGBColor.from_string(WHITE if r == 0 else INK)
        add_text(s, "Review-time benefit: NOT MEASURED.", 1.08, 5.4, 6.8, .4, 18, BLUE, bold=True)
    add_notes(s, NOTES[4])

    # 6. Limits
    s = prs.slides.add_slide(blank); set_slide_bg(s)
    title(s, "Limits and next checks")
    add_text(s, "ASSUMPTIONS", .9, 1.65, 3.2, .4, 16, ORANGE, bold=True)
    add_text(s, "Camera depth assumes an uncalibrated lens.\nHead motion is not compensated.\nGenerated hand surfaces are visualizations.",
             .9, 2.2, 5.3, 2.45, 20, INK)
    add_rule(s, 6.67, 1.6, 6.67, 5.4)
    add_text(s, "NEXT CHECKS", 7.15, 1.65, 3.2, .4, 16, BLUE, bold=True)
    add_text(s, "Human review of common-clip labels.\nMeasure the review-time pilot.",
             7.15, 2.2, 5.2, 1.8, 20, INK)
    add_notes(s, NOTES[5])

    if len(prs.slides) != 6:
        raise AssertionError("deck must contain exactly six slides")
    for i, slide in enumerate(prs.slides, 1):
        visible = " ".join(shape.text for shape in slide.shapes if shape.has_text_frame)
        visible += " " + " ".join(cell.text for shape in slide.shapes if shape.has_table
                                   for row in shape.table.rows for cell in row.cells)
        if words(visible) >= 40:
            raise ValueError(f"slide {i} has {words(visible)} visible words, expected fewer than 40")
    return prs


def pdf_font_setup():
    regular = Path(r"C:\Windows\Fonts\arial.ttf")
    bold = Path(r"C:\Windows\Fonts\arialbd.ttf")
    if not regular.is_file() or not bold.is_file():
        raise FileNotFoundError("Arial fonts are required to keep PDF and PPTX typography aligned")
    pdfmetrics.registerFont(TTFont(FONT, str(regular)))
    pdfmetrics.registerFont(TTFont(FONT + "-Bold", str(bold)))


def pc(hex_color):
    return HexColor("#" + hex_color)


def ptext(c, text, x, top, width, size, color=INK, bold=False, leading=None):
    style = ParagraphStyle("slide", fontName=FONT + ("-Bold" if bold else ""), fontSize=size,
                           leading=leading or size * 1.2, textColor=pc(color), spaceAfter=0)
    para = Paragraph(text.replace("\n", "<br/>"), style)
    _, h = para.wrap(width, SH * 72)
    para.drawOn(c, x, SH * 72 - top - h)
    return h


def prect(c, x, top, width, height, fill, stroke=None, radius=0):
    c.setFillColor(pc(fill))
    c.setStrokeColor(pc(stroke or fill))
    if radius:
        c.roundRect(x, SH * 72 - top - height, width, height, radius, fill=1, stroke=int(stroke is not None))
    else:
        c.rect(x, SH * 72 - top - height, width, height, fill=1, stroke=int(stroke is not None))


def pline(c, x1, top1, x2, top2, color=LINE, width=1):
    c.setStrokeColor(pc(color)); c.setLineWidth(width)
    c.line(x1, SH*72-top1, x2, SH*72-top2)


def pdf_cell(c, text, x, top, width, height, fill, *, color=INK, size=13, bold=False, align="left"):
    prect(c, x, top, width, height, fill)
    style = ParagraphStyle("cell", fontName=FONT + ("-Bold" if bold else ""), fontSize=size,
                           leading=size * 1.15, textColor=pc(color), alignment=0 if align == "left" else 1)
    p = Paragraph(text, style)
    _, ph = p.wrap(width-14, height-8)
    p.drawOn(c, x+7, SH*72-top-(height+ph)/2)


def build_pdf(performance, output_path=PDF_PATH):
    pdf_font_setup()
    W, H = SW*72, SH*72
    c = canvas.Canvas(str(output_path), pagesize=(W, H), pageCompression=1)
    c.setTitle("MOTIONIQ")
    c.setAuthor("MOTIONIQ team")
    c.setCreator("MOTIONIQ team")
    c._doc.info.producer = "MOTIONIQ team"

    def start_slide(heading):
        c.setFillColor(pc(PAPER)); c.rect(0, 0, W, H, fill=1, stroke=0)
        ptext(c, heading, 52, 38, W-104, 31, INK, True)

    # 1
    c.setFillColor(pc(PAPER)); c.rect(0, 0, W, H, fill=1, stroke=0)
    ptext(c, "MOTIONIQ", 59, 78, 820, 46, INK, True)
    ptext(c, "Factory POV video holds useful hand motion. Teams need trustworthy cues to find usable seconds.",
          61, 169, 755, 25, MUTED, leading=33)
    ptext(c, "WEARER LEFT", 63, 379, 240, 16, ORANGE, True)
    ptext(c, "WEARER RIGHT", 369, 379, 250, 16, BLUE, True)
    ptext(c, "DRAFT FOR TEAM REVIEW", 63, 478, 320, 11, MUTED, True)
    c.showPage()

    # 2
    start_slide("Processing path")
    labels = ["Video", "Detection<br/>presets", "Track<br/>states", "Smoothing", "Estimated<br/>3D", "Viewer, timeline<br/>and exports"]
    x0, top, nw, gap, nh = 51, 182, 122, 28, 100
    for i, label in enumerate(labels):
        accent = ORANGE if i in (1, 2) else BLUE if i == 4 else MUTED
        x = x0 + i*(nw+gap)
        prect(c, x, top, nw, nh, WHITE, accent, 10)
        ptext(c, label, x+7, top+25, nw-14, 14, INK, True, 18)
        if i < len(labels)-1:
            x1, x2, cy = x+nw+4, x+nw+gap-4, top+nh/2
            pline(c, x1, cy, x2, cy, MUTED, 1.4)
            c.setFillColor(pc(MUTED)); c.setStrokeColor(pc(MUTED))
            c.line(x2-6, SH*72-cy+4, x2, SH*72-cy,)
    ptext(c, "Predicted tracks are 2D only.", 56, 323, 390, 18, INK)
    ptext(c, "Wearer left", 56, 386, 190, 16, ORANGE, True)
    ptext(c, "Wearer right", 248, 386, 190, 16, BLUE, True)
    c.showPage()

    # 3
    start_slide("Live demo cue")
    ptext(c, "REVIEW", 60, 122, 190, 15, ORANGE, True)
    ptext(c, "Synchronized video, landmarks, 3D, timeline and events", 60, 160, 375, 24, INK, leading=31)
    pline(c, 480, 120, 480, 238, LINE, 1)
    ptext(c, "ANALYSIS", 515, 122, 180, 15, BLUE, True)
    ptext(c, "Signals and exports", 515, 160, 350, 24, INK)
    ptext(c, "DIAGNOSTICS", 60, 315, 210, 15, MUTED, True)
    ptext(c, "Pipeline detail", 60, 353, 310, 21, INK)
    ptext(c, "CAMERA   SIDE   TOP", 515, 315, 330, 15, BLUE, True)
    ptext(c, "Follow hand", 515, 353, 300, 21, INK)
    c.showPage()

    # 4
    start_slide("Accuracy")
    table_x, top = 61, 124
    colw = [130, 145, 135, 135, 110, 183]
    data = [["Preset", "Accuracy", "Recall", "Precision", "F1", "Wrong-side"],
            ["Baseline", "N/M", "N/M", "N/M", "N/M", "N/M"],
            ["Recall", "N/M", "N/M", "N/M", "N/M", "N/M"],
            ["Accurate", "N/M", "N/M", "N/M", "N/M", "N/M"],
            ["Hybrid", "N/M", "N/M", "N/M", "N/M", "N/M"]]
    for r, row in enumerate(data):
        for j, value in enumerate(row):
            pdf_cell(c, value, table_x+sum(colw[:j]), top+r*38, colw[j], 38,
                     INK if r == 0 else ("F1F0EA" if r%2 else WHITE),
                     color=WHITE if r == 0 else INK, size=14, bold=(r == 0 or j == 0),
                     align="left" if j == 0 else "center")
    ptext(c, "N/M = awaits human labels.", 63, 336, 420, 15, MUTED)
    ptext(c, "Historical hybrid: experiment record.", 63, 378, 420, 15, MUTED)
    c.showPage()

    # 5
    start_slide("Laptop and pilot evidence")
    if performance is None:
        ptext(c, "LAPTOP SPEED", 68, 158, 340, 17, ORANGE, True)
        ptext(c, "NOT MEASURED", 68, 204, 410, 29, INK, True)
        pline(c, 480, 151, 480, 353, LINE, 1)
        ptext(c, "REVIEW-TIME BENEFIT", 515, 158, 390, 17, BLUE, True)
        ptext(c, "NOT MEASURED", 515, 204, 410, 29, INK, True)
    else:
        x, top = 76, 119
        colw = [245, 220, 180, 190]
        rows = [["Preset", "Wall seconds", "FPS", "Frames"]]
        for row in performance:
            rows.append([row["preset"].title(),
                         f"{row['seconds']:.1f}" if row["status"] == "complete" else "Failed",
                         f"{row['fps']:.1f}" if row["status"] == "complete" else "N/M",
                         str(row["frames"]) if row["status"] == "complete" else "N/M"])
        for r, row in enumerate(rows):
            for j, value in enumerate(row):
                pdf_cell(c, value, x+sum(colw[:j]), top+r*38, colw[j], 38,
                         INK if r == 0 else ("F1F0EA" if r%2 else WHITE),
                         color=WHITE if r == 0 else INK, size=14, bold=r == 0,
                         align="left" if j == 0 else "center")
        ptext(c, "Review-time benefit: NOT MEASURED.", x, 387, 510, 18, BLUE, True)
    c.showPage()

    # 6
    start_slide("Limits and next checks")
    ptext(c, "ASSUMPTIONS", 65, 120, 260, 16, ORANGE, True)
    ptext(c, "Camera depth assumes an uncalibrated lens.<br/>Head motion is not compensated.<br/>Generated hand surfaces are visualizations.",
          65, 163, 400, 20, INK, leading=31)
    pline(c, 480, 116, 480, 390, LINE, 1)
    ptext(c, "NEXT CHECKS", 515, 120, 250, 16, BLUE, True)
    ptext(c, "Human review of common-clip labels.<br/>Measure the review-time pilot.",
          515, 163, 400, 20, INK, leading=31)
    c.save()


def main():
    performance = load_performance()
    PPTX_PATH.parent.mkdir(parents=True, exist_ok=True)
    prs = build_pptx(performance)
    with tempfile.TemporaryDirectory(prefix="MOTIONIQ-", dir=PPTX_PATH.parent) as temp_dir:
        pptx_temp = Path(temp_dir) / "draft.pptx"
        pdf_temp = Path(temp_dir) / "draft.pdf"
        prs.save(pptx_temp)
        build_pdf(performance, pdf_temp)
        pptx_temp.replace(PPTX_PATH)
        pdf_temp.replace(PDF_PATH)
    print(f"Created {len(prs.slides)} editable slides and matching PDF.")


if __name__ == "__main__":
    main()
