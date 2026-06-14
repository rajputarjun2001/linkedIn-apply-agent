"""Main application entry point."""

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from loguru import logger

from app.config.settings import get_settings
from app.container import get_container
from app.dashboard.app import create_app
from app.resume.manager import ResumeManager
from app.utils.logger import setup_logging


@asynccontextmanager
async def lifespan(app):
    """Application startup and shutdown lifecycle."""
    settings = get_settings()
    setup_logging(settings)
    container = get_container()

    await container.db.initialize()

    resume_manager = ResumeManager(settings)
    resume_manager.ensure_data_dir()
    if not settings.master_resume_path.exists():
        logger.info("Creating sample master resume at {}", settings.master_resume_path)
        resume_manager.create_sample_resume()

    settings.output_resumes_dir.mkdir(parents=True, exist_ok=True)

    container.scheduler.start()
    logger.info("AI Job Application Agent started")

    yield

    container.scheduler.stop()
    logger.info("AI Job Application Agent stopped")


app = create_app(lifespan=lifespan)


def main() -> None:
    """Run the application server."""
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
