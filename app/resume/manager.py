"""Master resume loading, validation, and persistence."""

import json
from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import ValidationError

from app.config.settings import Settings
from app.models.resume import MasterResume


class ResumeManager:
    """Manages the master resume JSON file."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._path = settings.master_resume_path

    def ensure_data_dir(self) -> None:
        """Ensure master resume directory exists."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load_master_resume(self) -> MasterResume:
        """Load and validate master resume from JSON file."""
        if not self._path.exists():
            raise FileNotFoundError(
                f"Master resume not found at {self._path}. "
                "Create one using the sample template in data/master_resume.json"
            )

        raw = self._path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
            resume = MasterResume.model_validate(data)
            logger.bind(component="resume_manager").info(
                "Loaded master resume for {}", resume.full_name
            )
            return resume
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"Invalid master resume JSON: {exc}") from exc

    def save_master_resume(self, resume: MasterResume) -> Path:
        """Save master resume to JSON file."""
        self.ensure_data_dir()
        self._path.write_text(
            resume.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.bind(component="resume_manager").info(
            "Saved master resume for {}", resume.full_name
        )
        return self._path

    def create_sample_resume(self) -> MasterResume:
        """Create a sample master resume template."""
        from datetime import date

        sample = MasterResume(
            full_name="Jane Developer",
            email="jane.developer@email.com",
            phone="+1-555-0100",
            location="San Francisco, CA",
            linkedin_url="https://www.linkedin.com/in/janedev",
            github_url="https://github.com/janedev",
            summary=(
                "Full Stack Developer with 5+ years building scalable web applications "
                "using React, Python, and cloud technologies."
            ),
            skills=[
                {"name": "Python", "category": "Languages", "proficiency": "Expert", "years": 5},
                {"name": "React", "category": "Frontend", "proficiency": "Expert", "years": 4},
                {"name": "TypeScript", "category": "Languages", "proficiency": "Advanced", "years": 3},
                {"name": "FastAPI", "category": "Backend", "proficiency": "Advanced", "years": 3},
                {"name": "PostgreSQL", "category": "Database", "proficiency": "Advanced", "years": 4},
                {"name": "Docker", "category": "DevOps", "proficiency": "Intermediate", "years": 2},
            ],
            projects=[
                {
                    "name": "TaskFlow API",
                    "description": "RESTful task management API with real-time updates.",
                    "technologies": ["Python", "FastAPI", "PostgreSQL", "Redis"],
                    "highlights": [
                        "Designed API serving 10K+ daily requests",
                        "Implemented JWT authentication and role-based access",
                    ],
                },
                {
                    "name": "DevPortal Dashboard",
                    "description": "React dashboard for developer analytics and monitoring.",
                    "technologies": ["React", "TypeScript", "D3.js"],
                    "highlights": [
                        "Built responsive UI with 50+ reusable components",
                        "Reduced page load time by 40%",
                    ],
                },
            ],
            work_experience=[
                {
                    "company": "TechCorp Inc.",
                    "title": "Senior Full Stack Developer",
                    "location": "San Francisco, CA",
                    "start_date": date(2021, 3, 1),
                    "is_current": True,
                    "achievements": [
                        "Led migration from monolith to microservices architecture",
                        "Mentored team of 4 junior developers",
                    ],
                    "technologies": ["Python", "React", "AWS", "Kubernetes"],
                },
                {
                    "company": "StartupXYZ",
                    "title": "Frontend Developer",
                    "location": "Remote",
                    "start_date": date(2019, 6, 1),
                    "end_date": date(2021, 2, 28),
                    "achievements": [
                        "Developed customer-facing React application from scratch",
                        "Improved Lighthouse performance score from 65 to 92",
                    ],
                    "technologies": ["React", "JavaScript", "CSS", "Webpack"],
                },
            ],
            education=[
                {
                    "institution": "State University",
                    "degree": "Bachelor of Science",
                    "field_of_study": "Computer Science",
                    "end_date": date(2019, 5, 1),
                    "gpa": "3.7",
                }
            ],
            certifications=[
                {
                    "name": "AWS Certified Developer - Associate",
                    "issuer": "Amazon Web Services",
                    "issue_date": date(2022, 8, 1),
                }
            ],
            achievements=[
                {
                    "title": "Hackathon Winner",
                    "description": "First place at regional developer hackathon for AI-powered tool.",
                    "achieved_date": date(2023, 4, 15),
                }
            ],
        )
        self.save_master_resume(sample)
        return sample
