"""Job discovery and matching orchestration service."""

from typing import List, Optional

from loguru import logger

from app.agents.application_assistant import ApplicationAssistant
from app.agents.job_matcher import JobMatcher
from app.config.settings import Settings
from app.database.repository import DatabaseRepository
from app.linkedin.browser import LinkedInBrowser
from app.linkedin.errors import LinkedInAuthError
from app.linkedin.scraper import LinkedInScraper
from app.models.discovery import DiscoveryProgress
from app.models.job import Job, JobStatus
from app.resume.manager import ResumeManager
from app.services.ollama_service import OllamaService, OllamaUnavailableError


class JobDiscoveryService:
    """Orchestrates LinkedIn job discovery, storage, and matching."""

    def __init__(
        self,
        settings: Settings,
        db: DatabaseRepository,
        scraper: LinkedInScraper,
        browser: LinkedInBrowser,
        job_matcher: JobMatcher,
        application_assistant: ApplicationAssistant,
        resume_manager: ResumeManager,
        ollama: OllamaService,
    ) -> None:
        self._settings = settings
        self._db = db
        self._scraper = scraper
        self._browser = browser
        self._job_matcher = job_matcher
        self._application_assistant = application_assistant
        self._resume_manager = resume_manager
        self._ollama = ollama
        self.progress = DiscoveryProgress()

    def _set_progress(
        self,
        phase: str,
        message: str,
        current: int = 0,
        total: int = 0,
    ) -> None:
        self.progress = DiscoveryProgress(
            phase=phase,
            message=message,
            current=current,
            total=total,
        )

    async def discover_jobs(self, max_per_search: int = 15) -> List[Job]:
        """Search LinkedIn and store new Easy Apply jobs."""
        self._set_progress("scraping", "Searching LinkedIn for Easy Apply jobs...")
        await self._browser.start(headless=True)

        try:
            await self._browser.ensure_authenticated()
            scraped = await self._scraper.search_all_configured(max_per_search)
            stored: List[Job] = []

            for job_create in scraped:
                if not job_create.is_easy_apply:
                    logger.bind(component="job_discovery").info(
                        "Skipped non-Easy Apply: {} at {}", job_create.title, job_create.company
                    )
                    continue
                created = await self._db.create_job(job_create)
                if created:
                    stored.append(created)

            logger.bind(component="job_discovery").info(
                "Discovered {} new Easy Apply jobs", len(stored)
            )
            self._set_progress(
                "scraping",
                f"Found {len(stored)} new jobs on LinkedIn.",
                current=len(stored),
                total=len(stored),
            )
            return stored
        finally:
            await self._browser.close()

    async def match_and_recommend_jobs(
        self,
        job_ids: Optional[List[int]] = None,
    ) -> List[Job]:
        """Match discovered jobs and mark recommendations above threshold."""
        await self._ollama.ensure_ready()

        resume = self._resume_manager.load_master_resume()
        await self._application_assistant.ensure_master_resume_stored(resume)

        jobs: List[Job] = []
        if job_ids:
            for job_id in job_ids[: self._settings.discovery_match_limit]:
                job = await self._db.get_job(job_id)
                if job:
                    jobs.append(job)
        else:
            jobs = await self._db.list_jobs(
                status=JobStatus.DISCOVERED,
                limit=self._settings.discovery_match_limit,
            )

        recommended: List[Job] = []
        total = len(jobs)
        self._set_progress(
            "matching",
            f"Matching {total} jobs with Ollama (this may take a few minutes)...",
            current=0,
            total=total,
        )

        for index, job in enumerate(jobs, start=1):
            self._set_progress(
                "matching",
                f"Matching job {index} of {total}: {job.title}",
                current=index,
                total=total,
            )
            try:
                match = await self._job_matcher.match(resume, job)
                status = (
                    JobStatus.RECOMMENDED
                    if match.match_score >= self._settings.min_match_score
                    else JobStatus.MATCHED
                )
                await self._db.update_job_match(
                    job.id, match.match_score, status, match_result=match
                )

                if match.match_score >= self._settings.min_match_score:
                    updated = await self._db.get_job(job.id)
                    if updated:
                        recommended.append(updated)

            except Exception as exc:
                logger.bind(component="job_discovery").error(
                    "Failed to match job {}: {}", job.id, exc
                )
                continue

        logger.bind(component="job_discovery").info(
            "Recommended {} jobs above threshold {}",
            len(recommended),
            self._settings.min_match_score,
        )
        self._set_progress(
            "complete",
            f"Matched {total} jobs. Recommended {len(recommended)}.",
            current=total,
            total=total,
        )
        return recommended

    async def run_full_pipeline(self) -> dict:
        """Execute full discovery, matching, and recommendation pipeline."""
        try:
            self._set_progress("starting", "Starting job discovery pipeline...")
            discovered = await self.discover_jobs()
            recommended = await self.match_and_recommend_jobs(
                job_ids=[job.id for job in discovered]
            )
            return {
                "success": True,
                "discovered_count": len(discovered),
                "recommended_count": len(recommended),
                "discovered": discovered,
                "recommended": recommended,
                "error": None,
            }
        except LinkedInAuthError as exc:
            self._set_progress("error", str(exc))
            logger.bind(component="job_discovery").error("LinkedIn auth required: {}", exc)
            return {
                "success": False,
                "discovered_count": 0,
                "recommended_count": 0,
                "discovered": [],
                "recommended": [],
                "error": str(exc),
            }
        except OllamaUnavailableError as exc:
            self._set_progress("error", str(exc))
            logger.bind(component="job_discovery").error("Ollama unavailable: {}", exc)
            return {
                "success": False,
                "discovered_count": 0,
                "recommended_count": 0,
                "discovered": [],
                "recommended": [],
                "error": str(exc),
            }
        except Exception as exc:
            self._set_progress("error", str(exc))
            logger.bind(component="job_discovery").error(
                "Discovery pipeline failed: {}", exc
            )
            return {
                "success": False,
                "discovered_count": 0,
                "recommended_count": 0,
                "discovered": [],
                "recommended": [],
                "error": str(exc),
            }
