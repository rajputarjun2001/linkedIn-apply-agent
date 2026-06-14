"""Application management service."""

import asyncio
from typing import Any, Callable, Coroutine, Dict, List, Optional

from loguru import logger

from app.agents.application_assistant import ApplicationAssistant
from app.config.settings import Settings
from app.database.repository import DatabaseRepository
from app.models.application import Application, ApplicationPreview, ApplicationStatus
from app.models.discovery import DiscoveryProgress
from app.models.job import Job
from app.services.ollama_service import OllamaUnavailableError

ProgressCallback = Callable[[str, str], Coroutine[Any, Any, None]]


class ApplicationService:
    """High-level application workflow service."""

    def __init__(
        self,
        db: DatabaseRepository,
        assistant: ApplicationAssistant,
        settings: Settings,
    ) -> None:
        self._db = db
        self._assistant = assistant
        self._settings = settings
        self._prepare_task: Optional[asyncio.Task] = None
        self._prepare_job_id: Optional[int] = None
        self._prepare_error: Optional[str] = None
        self._prepare_application_id: Optional[int] = None
        self.progress = DiscoveryProgress()

    def _set_progress(self, phase: str, message: str) -> None:
        self.progress = DiscoveryProgress(phase=phase, message=message)

    async def _report_progress(self, phase: str, message: str) -> None:
        self._set_progress(phase, message)

    async def get_pending_approvals(self) -> List[Application]:
        """List applications awaiting human approval."""
        return await self._db.list_applications(status=ApplicationStatus.PENDING_APPROVAL)

    async def prepare_for_job(self, job: Job) -> ApplicationPreview:
        """Prepare application preview for a specific job."""
        return await self._assistant.prepare_application(
            job,
            on_progress=self._report_progress,
        )

    def start_prepare_background(self, job_id: int) -> Dict[str, Any]:
        """Start prepare workflow without blocking the HTTP request."""
        if self._prepare_task and not self._prepare_task.done():
            return {
                "started": False,
                "in_progress": True,
                "job_id": self._prepare_job_id,
                "message": "Another prepare task is already running.",
            }

        self._prepare_error = None
        self._prepare_application_id = None
        self._prepare_job_id = job_id
        self._set_progress("starting", "Starting application preparation...")
        self._prepare_task = asyncio.create_task(
            self._run_prepare_background(job_id),
            name=f"prepare_job_{job_id}",
        )
        return {
            "started": True,
            "in_progress": True,
            "job_id": job_id,
            "message": "Preparing tailored resume and application preview...",
        }

    async def _run_prepare_background(self, job_id: int) -> None:
        try:
            job = await self._db.get_job(job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found")

            preview = await self.prepare_for_job(job)
            self._set_progress("complete", "Application preview ready.")

            applications = await self._db.list_applications(limit=100)
            for app in applications:
                if app.job_id == job_id:
                    self._prepare_application_id = app.id
                    break

            logger.bind(component="application_service").info(
                "Prepare complete for job {} ({})", job_id, preview.job_title
            )
        except OllamaUnavailableError as exc:
            self._prepare_error = str(exc)
            self._set_progress("error", str(exc))
            logger.bind(component="application_service").error(
                "Prepare failed for job {}: {}", job_id, exc
            )
        except Exception as exc:
            self._prepare_error = str(exc)
            self._set_progress("error", str(exc))
            logger.bind(component="application_service").error(
                "Prepare failed for job {}: {}", job_id, exc
            )

    def prepare_progress(self, job_id: int) -> Dict[str, Any]:
        """Return background prepare task state for polling."""
        if self._prepare_task is None or self._prepare_job_id != job_id:
            return {
                "in_progress": False,
                "completed": False,
                "success": False,
                "error": self._prepare_error,
                "application_id": self._prepare_application_id,
                "progress": self.progress.to_dict(),
            }

        if not self._prepare_task.done():
            return {
                "in_progress": True,
                "completed": False,
                "success": False,
                "error": None,
                "application_id": None,
                "progress": self.progress.to_dict(),
            }

        success = self._prepare_task.exception() is None and not self._prepare_error
        if not success and self._prepare_error is None and self._prepare_task.exception():
            self._prepare_error = str(self._prepare_task.exception())

        return {
            "in_progress": False,
            "completed": True,
            "success": success,
            "error": self._prepare_error,
            "application_id": self._prepare_application_id,
            "progress": self.progress.to_dict(),
        }

    async def approve(self, application_id: int, approved_by: str = "user") -> Application:
        """Approve application for submission."""
        return await self._assistant.approve_application(application_id, approved_by)

    async def reject(
        self, application_id: int, reason: str = "", rejected_by: str = "user"
    ) -> Application:
        """Reject an application."""
        return await self._assistant.reject_application(application_id, reason, rejected_by)

    async def submit(
        self,
        application_id: int,
        submitted_by: str = "user",
        notes: Optional[str] = None,
    ) -> Application:
        """
        Record submission after user manually completes LinkedIn Easy Apply.

        SAFETY: This does NOT auto-submit to LinkedIn. User must apply manually.
        """
        logger.bind(component="application_service").info(
            "Recording manual submission for application {}", application_id
        )
        return await self._assistant.mark_submitted(application_id, submitted_by, notes)

    async def get_application_with_job(
        self, application_id: int
    ) -> Optional[dict]:
        """Fetch application with associated job details."""
        application = await self._db.get_application(application_id)
        if not application:
            return None
        job = await self._db.get_job(application.job_id)
        history = await self._db.get_application_history(application_id)
        return {
            "application": application,
            "job": job,
            "history": history,
        }
