"""APScheduler background job scheduler."""

import asyncio
from typing import Any, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from app.config.settings import Settings
from app.services.job_discovery_service import JobDiscoveryService


class SchedulerService:
    """Schedules periodic job discovery runs."""

    def __init__(self, settings: Settings, job_discovery: JobDiscoveryService) -> None:
        self._settings = settings
        self._job_discovery = job_discovery
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._discovery_task: Optional[asyncio.Task] = None
        self._discovery_result: Optional[dict] = None
        self._discovery_error: Optional[str] = None

    async def _run_discovery_job(self) -> None:
        """Scheduled task: run full job discovery pipeline."""
        logger.bind(component="scheduler").info("Starting scheduled job discovery")
        try:
            result = await self._job_discovery.run_full_pipeline()
            if result.get("success"):
                logger.bind(component="scheduler").info(
                    "Scheduled run complete: {} discovered, {} recommended",
                    result["discovered_count"],
                    result["recommended_count"],
                )
            else:
                logger.bind(component="scheduler").error(
                    "Scheduled discovery failed: {}", result.get("error")
                )
        except Exception as exc:
            logger.bind(component="scheduler").error("Scheduled discovery failed: {}", exc)

    def start(self) -> None:
        """Start the background scheduler."""
        if not self._settings.scheduler_enabled:
            logger.bind(component="scheduler").info("Scheduler disabled in settings")
            return

        if self._scheduler and self._scheduler.running:
            return

        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._run_discovery_job,
            trigger=IntervalTrigger(hours=self._settings.scheduler_interval_hours),
            id="job_discovery",
            name="LinkedIn Job Discovery",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.bind(component="scheduler").info(
            "Scheduler started: every {} hour(s)",
            self._settings.scheduler_interval_hours,
        )

    def stop(self) -> None:
        """Stop the background scheduler."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.bind(component="scheduler").info("Scheduler stopped")

    async def run_now(self) -> dict:
        """Trigger immediate discovery run."""
        return await self._job_discovery.run_full_pipeline()

    def start_discovery_background(self) -> Dict[str, Any]:
        """Start discovery pipeline without blocking the HTTP request."""
        if self._discovery_task and not self._discovery_task.done():
            return {
                "started": False,
                "in_progress": True,
                "message": "Job discovery is already running.",
            }

        self._discovery_result = None
        self._discovery_error = None
        self._discovery_task = asyncio.create_task(
            self._run_discovery_background(),
            name="job_discovery_manual",
        )
        return {
            "started": True,
            "in_progress": True,
            "message": "Job discovery started. This may take several minutes.",
        }

    async def _run_discovery_background(self) -> None:
        try:
            self._discovery_result = await self._job_discovery.run_full_pipeline()
            if not self._discovery_result.get("success"):
                self._discovery_error = (
                    self._discovery_result.get("error") or "Job discovery failed"
                )
                logger.bind(component="scheduler").error(
                    "Manual discovery failed: {}", self._discovery_error
                )
            else:
                logger.bind(component="scheduler").info(
                    "Manual discovery complete: {} discovered, {} recommended",
                    self._discovery_result.get("discovered_count", 0),
                    self._discovery_result.get("recommended_count", 0),
                )
        except Exception as exc:
            self._discovery_error = str(exc)
            logger.bind(component="scheduler").error("Manual discovery failed: {}", exc)

    def discovery_progress(self) -> Dict[str, Any]:
        """Return background discovery task state for polling."""
        if self._discovery_task is None:
            return {
                "in_progress": False,
                "completed": False,
                "success": False,
                "error": self._discovery_error,
                "result": self._discovery_result,
            }

        if not self._discovery_task.done():
            progress = self._job_discovery.progress.to_dict()
            return {
                "in_progress": True,
                "completed": False,
                "success": False,
                "error": None,
                "result": None,
                "progress": progress,
            }

        success = self._discovery_task.exception() is None and not self._discovery_error
        if not success and self._discovery_error is None and self._discovery_task.exception():
            self._discovery_error = str(self._discovery_task.exception())

        return {
            "in_progress": False,
            "completed": True,
            "success": success,
            "error": self._discovery_error,
            "result": self._discovery_result,
            "progress": self._job_discovery.progress.to_dict(),
        }
