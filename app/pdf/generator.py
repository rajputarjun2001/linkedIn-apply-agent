"""ATS-friendly PDF resume generator using ReportLab."""

import re
from datetime import date
from pathlib import Path
from typing import List, Optional, Union

from loguru import logger
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from app.config.settings import Settings
from app.models.job import Job
from app.models.resume import MasterResume, TailoredResume


class PDFGenerator:
    """Generates clean, ATS-friendly PDF resumes."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._output_dir = settings.output_resumes_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, name: str) -> str:
        """Create safe filename from text."""
        safe = re.sub(r"[^\w\s-]", "", name)
        safe = re.sub(r"[\s]+", "_", safe.strip())
        return safe[:80] or "resume"

    def _format_date(self, value: Optional[date]) -> str:
        if not value:
            return ""
        return value.strftime("%b %Y")

    def _date_range(
        self,
        start: Optional[date],
        end: Optional[date],
        is_current: bool = False,
    ) -> str:
        start_str = self._format_date(start)
        end_str = "Present" if is_current else self._format_date(end)
        if start_str and end_str:
            return f"{start_str} - {end_str}"
        return start_str or end_str

    def _build_styles(self) -> dict:
        """Define document paragraph styles."""
        base = getSampleStyleSheet()
        return {
            "name": ParagraphStyle(
                "Name",
                parent=base["Heading1"],
                fontSize=18,
                spaceAfter=4,
                textColor=colors.HexColor("#1a1a2e"),
                alignment=TA_LEFT,
            ),
            "contact": ParagraphStyle(
                "Contact",
                parent=base["Normal"],
                fontSize=9,
                textColor=colors.HexColor("#444444"),
                spaceAfter=10,
            ),
            "section": ParagraphStyle(
                "Section",
                parent=base["Heading2"],
                fontSize=11,
                spaceBefore=10,
                spaceAfter=4,
                textColor=colors.HexColor("#1a1a2e"),
                borderPadding=2,
            ),
            "body": ParagraphStyle(
                "Body",
                parent=base["Normal"],
                fontSize=10,
                leading=13,
                spaceAfter=4,
            ),
            "subtitle": ParagraphStyle(
                "Subtitle",
                parent=base["Normal"],
                fontSize=10,
                textColor=colors.HexColor("#333333"),
                spaceAfter=2,
            ),
            "bullet": ParagraphStyle(
                "Bullet",
                parent=base["Normal"],
                fontSize=9,
                leading=12,
                leftIndent=12,
                spaceAfter=2,
            ),
        }

    def generate(
        self,
        resume: Union[MasterResume, TailoredResume],
        job: Optional[Job] = None,
    ) -> Path:
        """Generate PDF resume and return output path."""
        styles = self._build_styles()
        story: List = []

        # Header
        story.append(Paragraph(resume.full_name, styles["name"]))

        contact_parts = [resume.email]
        if resume.phone:
            contact_parts.append(resume.phone)
        if resume.location:
            contact_parts.append(resume.location)
        if resume.linkedin_url:
            contact_parts.append(str(resume.linkedin_url))
        if resume.github_url:
            contact_parts.append(str(resume.github_url))

        story.append(Paragraph(" | ".join(contact_parts), styles["contact"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
        story.append(Spacer(1, 0.1 * inch))

        # Summary
        summary = None
        if isinstance(resume, TailoredResume):
            summary = resume.tailored_summary or resume.summary
        else:
            summary = resume.summary

        if summary:
            story.append(Paragraph("PROFESSIONAL SUMMARY", styles["section"]))
            story.append(Paragraph(summary, styles["body"]))

        # Skills
        if resume.skills:
            story.append(Paragraph("SKILLS", styles["section"]))
            skill_text = ", ".join(
                s.name + (f" ({s.proficiency})" if s.proficiency else "")
                for s in resume.skills
            )
            story.append(Paragraph(skill_text, styles["body"]))

        # Experience
        if resume.work_experience:
            story.append(Paragraph("WORK EXPERIENCE", styles["section"]))
            for exp in resume.work_experience:
                title_line = f"<b>{exp.title}</b> — {exp.company}"
                if exp.location:
                    title_line += f", {exp.location}"
                story.append(Paragraph(title_line, styles["subtitle"]))
                date_line = self._date_range(exp.start_date, exp.end_date, exp.is_current)
                if date_line:
                    story.append(Paragraph(f"<i>{date_line}</i>", styles["bullet"]))
                if exp.description:
                    story.append(Paragraph(exp.description, styles["body"]))
                for achievement in exp.achievements:
                    story.append(Paragraph(f"• {achievement}", styles["bullet"]))
                if exp.technologies:
                    techs = ", ".join(exp.technologies)
                    story.append(Paragraph(f"<i>Technologies: {techs}</i>", styles["bullet"]))
                story.append(Spacer(1, 0.05 * inch))

        # Projects
        if resume.projects:
            story.append(Paragraph("PROJECTS", styles["section"]))
            for project in resume.projects:
                story.append(Paragraph(f"<b>{project.name}</b>", styles["subtitle"]))
                story.append(Paragraph(project.description, styles["body"]))
                if project.technologies:
                    story.append(
                        Paragraph(
                            f"<i>Technologies: {', '.join(project.technologies)}</i>",
                            styles["bullet"],
                        )
                    )
                for highlight in project.highlights:
                    story.append(Paragraph(f"• {highlight}", styles["bullet"]))
                story.append(Spacer(1, 0.05 * inch))

        # Education
        if resume.education:
            story.append(Paragraph("EDUCATION", styles["section"]))
            for edu in resume.education:
                edu_line = f"<b>{edu.degree}</b>"
                if edu.field_of_study:
                    edu_line += f" in {edu.field_of_study}"
                edu_line += f" — {edu.institution}"
                story.append(Paragraph(edu_line, styles["subtitle"]))
                date_line = self._date_range(edu.start_date, edu.end_date)
                extras = []
                if date_line:
                    extras.append(date_line)
                if edu.gpa:
                    extras.append(f"GPA: {edu.gpa}")
                if extras:
                    story.append(Paragraph(" | ".join(extras), styles["bullet"]))

        # Certifications
        if resume.certifications:
            story.append(Paragraph("CERTIFICATIONS", styles["section"]))
            for cert in resume.certifications:
                cert_line = f"<b>{cert.name}</b>"
                if cert.issuer:
                    cert_line += f" — {cert.issuer}"
                if cert.issue_date:
                    cert_line += f" ({self._format_date(cert.issue_date)})"
                story.append(Paragraph(cert_line, styles["body"]))

        # Achievements
        if resume.achievements:
            story.append(Paragraph("ACHIEVEMENTS", styles["section"]))
            for ach in resume.achievements:
                story.append(Paragraph(f"<b>{ach.title}</b>: {ach.description}", styles["body"]))

        # Output path
        if job:
            filename = (
                f"{self._sanitize_filename(resume.full_name)}_"
                f"{self._sanitize_filename(job.company)}_"
                f"{self._sanitize_filename(job.title)}.pdf"
            )
        else:
            filename = f"{self._sanitize_filename(resume.full_name)}_resume.pdf"

        output_path = self._output_dir / filename

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.6 * inch,
            bottomMargin=0.6 * inch,
        )
        doc.build(story)

        logger.bind(component="pdf_generator").info("Generated PDF: {}", output_path)
        return output_path
