"""AI-powered resume tailoring agent with anti-fabrication safeguards."""

from typing import Set

from loguru import logger
from pydantic import ValidationError

from app.models.job import Job
from app.models.resume import MasterResume, TailoredResume
from app.prompts import load_prompt, render_prompt
from app.services.ollama_service import OllamaService


class ResumeFabricationError(ValueError):
    """Raised when tailored resume contains fabricated content."""


class ResumeTailor:
    """Tailors master resume for a specific job without fabricating content."""

    def __init__(self, ollama: OllamaService) -> None:
        self._ollama = ollama
        self._prompt_template = load_prompt("resume_tailoring.txt")

    @staticmethod
    def _collect_identifiers(resume: MasterResume) -> dict[str, Set[str]]:
        """Collect canonical identifiers from master resume for validation."""
        return {
            "skills": {s.name.lower().strip() for s in resume.skills},
            "projects": {p.name.lower().strip() for p in resume.projects},
            "experience": {
                f"{e.company} - {e.title}".lower().strip() for e in resume.work_experience
            },
            "education": {e.institution.lower().strip() for e in resume.education},
            "certifications": {c.name.lower().strip() for c in resume.certifications},
            "achievements": {a.title.lower().strip() for a in resume.achievements},
        }

    def _validate_no_fabrication(
        self, master: MasterResume, tailored: TailoredResume
    ) -> None:
        """Ensure tailored resume only contains content from master resume."""
        master_ids = self._collect_identifiers(master)
        violations: list[str] = []

        for skill in tailored.skills:
            if skill.name.lower().strip() not in master_ids["skills"]:
                violations.append(f"Fabricated skill: {skill.name}")

        for project in tailored.projects:
            if project.name.lower().strip() not in master_ids["projects"]:
                violations.append(f"Fabricated project: {project.name}")

        for exp in tailored.work_experience:
            key = f"{exp.company} - {exp.title}".lower().strip()
            if key not in master_ids["experience"]:
                violations.append(f"Fabricated experience: {exp.company} - {exp.title}")

        for edu in tailored.education:
            if edu.institution.lower().strip() not in master_ids["education"]:
                violations.append(f"Fabricated education: {edu.institution}")

        for cert in tailored.certifications:
            if cert.name.lower().strip() not in master_ids["certifications"]:
                violations.append(f"Fabricated certification: {cert.name}")

        for ach in tailored.achievements:
            if ach.title.lower().strip() not in master_ids["achievements"]:
                violations.append(f"Fabricated achievement: {ach.title}")

        if violations:
            raise ResumeFabricationError(
                "Tailored resume contains fabricated content: " + "; ".join(violations)
            )

    async def tailor(self, master: MasterResume, job: Job) -> TailoredResume:
        """Generate a tailored resume for the given job."""
        prompt = render_prompt(
            self._prompt_template,
            resume_json=master.model_dump_json(indent=2),
            job_title=job.title,
            company=job.company,
            job_description=job.description,
        )

        logger.bind(component="resume_tailor").info(
            "Tailoring resume for {} at {}", job.title, job.company
        )

        raw = await self._ollama.generate_structured(prompt, TailoredResume)
        raw.job_id = job.id

        try:
            self._validate_no_fabrication(master, raw)
        except ResumeFabricationError:
            logger.bind(component="resume_tailor").warning(
                "Fabrication detected, falling back to reordered master resume"
            )
            return self._fallback_tailor(master, job)

        logger.bind(component="resume_tailor").info("Resume tailored successfully")
        return raw

    def _fallback_tailor(self, master: MasterResume, job: Job) -> TailoredResume:
        """Safe fallback: return master resume with minimal reordering."""
        description_lower = job.description.lower()
        title_lower = job.title.lower()
        search_text = f"{description_lower} {title_lower}"

        def skill_relevance(skill_name: str) -> int:
            return search_text.count(skill_name.lower())

        sorted_skills = sorted(master.skills, key=lambda s: -skill_relevance(s.name))
        sorted_projects = sorted(
            master.projects,
            key=lambda p: -sum(skill_relevance(t) for t in p.technologies),
        )

        tailored = TailoredResume(
            **{
                **master.model_dump(),
                "job_id": job.id,
                "tailored_summary": master.summary,
                "relevance_notes": "Fallback tailoring: keyword-based reorder only",
                "skill_order": [s.name for s in sorted_skills],
                "project_order": [p.name for p in sorted_projects],
                "experience_order": [
                    f"{e.company} - {e.title}" for e in master.work_experience
                ],
                "skills": sorted_skills,
                "projects": sorted_projects,
            }
        )
        return tailored

    def tailor_without_ai(self, master: MasterResume, job: Job) -> TailoredResume:
        """Deterministic tailoring without LLM (for tests and fallback)."""
        return self._fallback_tailor(master, job)
