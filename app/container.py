"""Dependency injection container."""

from functools import lru_cache

from app.agents.application_assistant import ApplicationAssistant
from app.agents.job_matcher import JobMatcher
from app.agents.resume_tailor import ResumeTailor
from app.config.settings import Settings, get_settings
from app.database.repository import DatabaseRepository
from app.linkedin.browser import LinkedInBrowser
from app.linkedin.scraper import LinkedInScraper
from app.pdf.generator import PDFGenerator
from app.resume.manager import ResumeManager
from app.services.application_service import ApplicationService
from app.services.job_discovery_service import JobDiscoveryService
from app.services.linkedin_auth_service import LinkedInAuthService
from app.services.ollama_service import OllamaService
from app.services.scheduler_service import SchedulerService


class Container:
    """Application dependency injection container."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db = DatabaseRepository(self.settings)
        self.ollama = OllamaService(self.settings)
        self.resume_manager = ResumeManager(self.settings)
        self.pdf_generator = PDFGenerator(self.settings)
        self.job_matcher = JobMatcher(self.ollama)
        self.resume_tailor = ResumeTailor(self.ollama)
        self.application_assistant = ApplicationAssistant(
            settings=self.settings,
            db=self.db,
            resume_manager=self.resume_manager,
            job_matcher=self.job_matcher,
            resume_tailor=self.resume_tailor,
            pdf_generator=self.pdf_generator,
        )
        self.linkedin_browser = LinkedInBrowser(self.settings)
        self.linkedin_auth = LinkedInAuthService(self.settings, self.linkedin_browser)
        self.linkedin_scraper = LinkedInScraper(self.settings, self.linkedin_browser)
        self.job_discovery = JobDiscoveryService(
            settings=self.settings,
            db=self.db,
            scraper=self.linkedin_scraper,
            browser=self.linkedin_browser,
            job_matcher=self.job_matcher,
            application_assistant=self.application_assistant,
            resume_manager=self.resume_manager,
            ollama=self.ollama,
        )
        self.application_service = ApplicationService(
            db=self.db,
            assistant=self.application_assistant,
            settings=self.settings,
        )
        self.scheduler = SchedulerService(self.settings, self.job_discovery)


@lru_cache
def get_container() -> Container:
    """Return cached application container."""
    return Container()
