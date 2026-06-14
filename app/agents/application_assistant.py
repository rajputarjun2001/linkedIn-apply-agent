"""Application assistant with human approval workflow."""

from typing import Awaitable, Callable, Optional

from loguru import logger

from app.agents.job_matcher import JobMatcher
from app.agents.resume_tailor import ResumeTailor
from app.config.settings import Settings
from app.database.repository import DatabaseRepository
from app.models.application import Application, ApplicationPreview, ApplicationStatus
from app.models.job import Job, JobStatus
from app.models.resume import MasterResume, TailoredResume
from app.pdf.generator import PDFGenerator
from app.resume.manager import ResumeManager


class ApplicationAssistant:
    """Orchestrates application preview generation and approval-gated submission."""

    def __init__(
        self,
        settings: Settings,
        db: DatabaseRepository,
        resume_manager: ResumeManager,
        job_matcher: JobMatcher,
        resume_tailor: ResumeTailor,
        pdf_generator: PDFGenerator,
    ) -> None:
        self._settings = settings
        self._db = db
        self._resume_manager = resume_manager
        self._job_matcher = job_matcher
        self._resume_tailor = resume_tailor
        self._pdf_generator = pdf_generator

    async def ensure_master_resume_stored(self, resume: MasterResume) -> int:
        """Persist master resume snapshot if not already stored."""
        existing = await self._db.get_master_resume_id()
        if existing:
            return existing
        return await self._db.save_resume(
            resume,
            version_label="master",
            is_tailored=False,
            source_type="master",
        )

    async def prepare_application(
        self,
        job: Job,
        master_resume: Optional[MasterResume] = None,
        on_progress: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> ApplicationPreview:
        """Generate match score, tailored resume PDF, and application preview."""
        resume = master_resume or self._resume_manager.load_master_resume()
        master_resume_id = await self.ensure_master_resume_stored(resume)

        if on_progress:
            await on_progress("matching", f"Analyzing fit for {job.title}...")
        match_result = await self._job_matcher.match(resume, job)
        warnings: list[str] = []

        if match_result.match_score < self._settings.min_match_score:
            warnings.append(
                f"Match score {match_result.match_score} is below threshold "
                f"{self._settings.min_match_score}. Application will not be submitted."
            )

        if on_progress:
            await on_progress("tailoring", "Tailoring resume with Ollama...")
        tailored = await self._resume_tailor.tailor(resume, job)

        if on_progress:
            await on_progress("pdf", "Generating tailored resume PDF...")
        pdf_path = self._pdf_generator.generate(tailored, job)

        if on_progress:
            await on_progress("saving", "Saving application preview...")
        resume_id = await self._db.save_resume(
            tailored,
            job_id=job.id,
            pdf_path=str(pdf_path),
            is_tailored=True,
            version_label=f"tailored_{job.id}",
            parent_resume_id=master_resume_id,
            source_type="tailored",
        )

        await self._db.update_job_match(
            job.id,
            match_result.match_score,
            JobStatus.RECOMMENDED
            if match_result.match_score >= self._settings.min_match_score
            else JobStatus.MATCHED,
            match_result=match_result,
        )

        application_answers = self._generate_application_answers(tailored, job)
        match_analysis = match_result.model_dump()

        preview = ApplicationPreview(
            job_id=job.id,
            company=job.company,
            job_title=job.title,
            match_score=match_result.match_score,
            resume_path=str(pdf_path),
            resume_filename=pdf_path.name,
            missing_skills=match_result.missing_skills,
            relevant_experience=match_result.relevant_experience,
            application_answers=application_answers,
            tailored_summary=tailored.tailored_summary or tailored.summary,
            apply_url=job.apply_url,
            warnings=warnings,
        )

        if not await self._db.application_exists_for_job(job.id):
            await self._db.create_application(
                job_id=job.id,
                match_score=match_result.match_score,
                resume_id=resume_id,
                resume_pdf_path=str(pdf_path),
                application_answers=application_answers,
                missing_skills=match_result.missing_skills,
                relevant_experience=match_result.relevant_experience,
                match_analysis=match_analysis,
            )

        logger.bind(component="application_assistant").info(
            "Application preview ready for {} at {} (score: {})",
            job.title,
            job.company,
            match_result.match_score,
        )
        return preview

    def _generate_application_answers(
        self, resume: TailoredResume, job: Job
    ) -> dict[str, str]:
        """Generate draft answers for common application fields from existing resume data."""
        summary = resume.tailored_summary or resume.summary or ""
        years_exp = len(resume.work_experience)
        top_skills = ", ".join(s.name for s in resume.skills[:8])

        return {
            "Why are you interested in this role?": (
                f"I am excited about the {job.title} position at {job.company} because it "
                f"aligns with my background in {top_skills}. {summary[:300]}"
            ).strip(),
            "Years of relevant experience": str(max(years_exp, 1)),
            "Key skills": top_skills,
            "Authorized to work": "Please confirm based on your work authorization status.",
            "Require sponsorship": "Please confirm based on your visa status.",
        }

    async def approve_application(
        self, application_id: int, approved_by: str = "user"
    ) -> Application:
        """Approve an application for submission (does not auto-submit)."""
        application = await self._db.get_application(application_id)
        if not application:
            raise ValueError(f"Application {application_id} not found")

        if application.match_score < self._settings.min_match_score:
            raise ValueError(
                f"Cannot approve: match score {application.match_score} "
                f"below threshold {self._settings.min_match_score}"
            )

        await self._db.update_application_status(
            application_id, ApplicationStatus.APPROVED
        )
        await self._db.add_application_history(
            application_id,
            "approved",
            "User approved application for submission",
            performed_by=approved_by,
        )

        updated = await self._db.get_application(application_id)
        if not updated:
            raise RuntimeError("Failed to fetch updated application")
        return updated

    async def reject_application(
        self, application_id: int, reason: str = "", rejected_by: str = "user"
    ) -> Application:
        """Reject an application."""
        await self._db.update_application_status(
            application_id,
            ApplicationStatus.REJECTED,
            notes=reason,
        )
        await self._db.add_application_history(
            application_id,
            "rejected",
            reason or "User rejected application",
            performed_by=rejected_by,
        )
        application = await self._db.get_application(application_id)
        if not application:
            raise ValueError(f"Application {application_id} not found")
        return application

    async def mark_submitted(
        self,
        application_id: int,
        submitted_by: str = "user",
        notes: Optional[str] = None,
    ) -> Application:
        """
        Mark application as submitted after human has manually completed Easy Apply.

        The system never auto-submits; this records successful manual submission.
        """
        application = await self._db.get_application(application_id)
        if not application:
            raise ValueError(f"Application {application_id} not found")

        if application.status != ApplicationStatus.APPROVED:
            raise ValueError(
                f"Application must be approved before submission. "
                f"Current status: {application.status.value}"
            )

        if application.match_score < self._settings.min_match_score:
            raise ValueError("Cannot submit: match score below threshold")

        await self._db.update_application_status(
            application_id,
            ApplicationStatus.SUBMITTED,
            notes=notes,
            mark_submitted=True,
        )
        await self._db.update_job_status(application.job_id, JobStatus.APPLIED)
        await self._db.add_application_history(
            application_id,
            "submitted",
            notes or "Application submitted via LinkedIn Easy Apply",
            performed_by=submitted_by,
        )

        updated = await self._db.get_application(application_id)
        if not updated:
            raise RuntimeError("Failed to fetch updated application")
        return updated
