"""
pdf_exporter.py
===============
Generates university-standard Question Paper PDFs using ReportLab.
Uses atomic file writing (os_concurrency.atomic_write_file) to guarantee OS-level atomic persistence.
"""

import io
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)
from reportlab.pdfgen import canvas
from os_concurrency import atomic_write_file

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and print 'Page X of Y' in the footer.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#4B5563"))
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(letter[0] - 0.75 * inch, 0.5 * inch, page_text)
        self.drawString(0.75 * inch, 0.5 * inch, "Confidential - Department Examination Cell")
        self.setStrokeColor(colors.HexColor("#D1D5DB"))
        self.setLineWidth(0.5)
        self.line(0.75 * inch, 0.65 * inch, letter[0] - 0.75 * inch, 0.65 * inch)
        self.restoreState()

def export_paper_to_pdf(paper_metadata: dict, sections: list, output_filepath: str) -> str:
    """
    Builds the question paper PDF in memory and writes atomically to output_filepath.
    """
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.85 * inch
    )

    styles = getSampleStyleSheet()
    
    # Custom Typography Styles
    univ_style = ParagraphStyle(
        'UnivHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        alignment=1, # Center
        textColor=colors.HexColor("#1E3A8A")
    )
    dept_style = ParagraphStyle(
        'DeptHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        alignment=1,
        textColor=colors.HexColor("#1F2937")
    )
    exam_style = ParagraphStyle(
        'ExamHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        alignment=1,
        textColor=colors.HexColor("#111827")
    )
    meta_key_style = ParagraphStyle('MetaKey', fontName='Helvetica-Bold', fontSize=9.5, leading=12)
    meta_val_style = ParagraphStyle('MetaVal', fontName='Helvetica', fontSize=9.5, leading=12)
    
    sec_header_style = ParagraphStyle(
        'SectionHeader',
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14,
        alignment=1,
        textColor=colors.HexColor("#1E3A8A")
    )
    inst_style = ParagraphStyle(
        'Instructions',
        fontName='Helvetica-Oblique',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#4B5563")
    )
    q_num_style = ParagraphStyle('QNum', fontName='Helvetica-Bold', fontSize=9.5, leading=12, alignment=1)
    q_text_style = ParagraphStyle('QText', fontName='Helvetica', fontSize=9.5, leading=13)
    q_meta_style = ParagraphStyle('QMeta', fontName='Helvetica-Bold', fontSize=8.5, leading=11, alignment=1, textColor=colors.HexColor("#374151"))
    q_marks_style = ParagraphStyle('QMarks', fontName='Helvetica-Bold', fontSize=9.5, leading=12, alignment=1)

    story = []

    # 1. University & Department Header
    story.append(Paragraph("INSTITUTE OF TECHNOLOGY & SCIENCE", univ_style))
    story.append(Paragraph("DEPARTMENT OF COMPUTER SCIENCE & ENGINEERING", dept_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(paper_metadata.get('paper_title', 'SEMESTER EXAMINATION'), exam_style))
    story.append(Spacer(1, 6))

    # 2. Metadata Box (Course Code, Subject, Time, Max Marks)
    meta_table_data = [
        [
            Paragraph(f"<b>Course Code:</b> {paper_metadata.get('subject_code', 'N/A')}", meta_val_style),
            Paragraph(f"<b>Course Title:</b> {paper_metadata.get('subject_name', 'N/A')}", meta_val_style)
        ],
        [
            Paragraph(f"<b>Duration:</b> {paper_metadata.get('duration_minutes', 180)} Minutes", meta_val_style),
            Paragraph(f"<b>Max Marks:</b> {paper_metadata.get('total_marks', 100)}", meta_val_style)
        ]
    ]
    meta_table = Table(meta_table_data, colWidths=[2.5 * inch, 4.5 * inch])
    meta_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#9CA3AF")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 6))

    # General Instructions
    instructions_text = (
        "<b>Instructions to Candidates:</b><br/>"
        "1. All questions are compulsory. Read questions carefully before attempting.<br/>"
        "2. Figures to the right indicate full marks for each question.<br/>"
        "3. Assume suitable data if necessary and state the assumptions clearly."
    )
    story.append(Paragraph(instructions_text, inst_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1F2937"), spaceAfter=10))

    # 3. Question Sections
    q_counter = 1
    for sec in sections:
        sec_name = sec.get('section_name', 'SECTION')
        sec_marks_info = f"[{sec.get('num_questions')} × {sec.get('marks_per_q')} = {sec.get('total_section_marks')} Marks]"
        sec_title = f"{sec_name.upper()} &nbsp;&nbsp;&nbsp; {sec_marks_info}"
        
        # Section Header Banner
        sec_banner = Table(
            [[Paragraph(f"<b>{sec_title}</b>", sec_header_style)]],
            colWidths=[7.0 * inch]
        )
        sec_banner.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#EEF2F6")),
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor("#CBD5E1")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        
        # Section questions table
        q_table_data = [
            [
                Paragraph("<b>Q.No</b>", q_num_style),
                Paragraph("<b>Question Statement</b>", ParagraphStyle('H1', fontName='Helvetica-Bold', fontSize=9.5)),
                Paragraph("<b>Bloom's / Unit</b>", q_num_style),
                Paragraph("<b>Marks</b>", q_num_style)
            ]
        ]

        for q in sec.get('questions', []):
            unit_info = f"Unit {q.get('unit_number', 1)}"
            blooms_info = f"{q.get('blooms_level', 'L1')}<br/><font color='#6B7280' size='7'>{unit_info}</font>"
            q_table_data.append([
                Paragraph(f"<b>{q_counter}.</b>", q_num_style),
                Paragraph(q.get('question_text', ''), q_text_style),
                Paragraph(blooms_info, q_meta_style),
                Paragraph(f"[{q.get('marks', '')}]", q_marks_style)
            ])
            q_counter += 1

        q_table = Table(
            q_table_data,
            colWidths=[0.6 * inch, 4.6 * inch, 1.1 * inch, 0.7 * inch]
        )
        q_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor("#1E293B")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))

        story.append(KeepTogether([
            sec_banner,
            Spacer(1, 4),
            q_table,
            Spacer(1, 10)
        ]))

    # End of paper indicator
    story.append(Spacer(1, 8))
    story.append(Paragraph("<b>--- END OF QUESTION PAPER ---</b>", ParagraphStyle('End', fontName='Helvetica-Bold', fontSize=9, alignment=1, textColor=colors.HexColor("#64748B"))))

    # Build the document
    doc.build(story, canvasmaker=NumberedCanvas)

    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()

    # OS Concept: Atomic file write using temporary file, sync, and atomic rename
    atomic_write_file(output_filepath, pdf_bytes)
    return output_filepath
