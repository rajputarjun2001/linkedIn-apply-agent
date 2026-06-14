"""Unit tests for PDF generator."""

from datetime import date
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.models.resume import MasterResume, Skill, WorkExperience
from app.pdf.generator import PDFGenerator


@pytest.fixture
def pdf_generator(tmp_path) -> PDFGenerator:
    settings = Settings()
    settings.output_resumes_dir = tmp_path / "resumes"
    return PDFGenerator(settings)


@pytest.fixture
def sample_resume() -> MasterResume:
    return MasterResume(
        full_name="PDF Test User",
        email="pdf@example.com",
        phone="555-1234",
        location="New York, NY",
        summary="Experienced software developer.",
        skills=[Skill(name="Python", proficiency="Expert")],
        work_experience=[
            WorkExperience(
                company="TestCo",
                title="Engineer",
                start_date=date(2021, 1, 1),
                is_current=True,
                achievements=["Built scalable APIs"],
            )
        ],
    )


def test_generate_pdf(pdf_generator, sample_resume):
    """PDF generator creates a valid PDF file."""
    output = pdf_generator.generate(sample_resume)
    assert output.exists()
    assert output.suffix == ".pdf"
    assert output.stat().st_size > 0


def test_sanitize_filename(pdf_generator):
    """Filename sanitization removes unsafe characters."""
    safe = pdf_generator._sanitize_filename("Hello World! @#$")
    assert "@" not in safe
    assert "#" not in safe
