"""CLI commands for AI Job Application Agent."""

import argparse
import asyncio
import sys

from loguru import logger

from app.container import Container
from app.utils.logger import setup_logging


async def cmd_init(container: Container) -> None:
    """Initialize database and sample resume."""
    await container.db.initialize()
    container.resume_manager.ensure_data_dir()
    if not container.settings.master_resume_path.exists():
        container.resume_manager.create_sample_resume()
        logger.info("Created sample master resume")
    logger.info("Initialization complete")


async def cmd_discover(container: Container) -> None:
    """Run job discovery pipeline."""
    result = await container.job_discovery.run_full_pipeline()
    logger.info(
        "Discovery complete: {} new jobs, {} recommended",
        result["discovered_count"],
        result["recommended_count"],
    )


async def cmd_serve(container: Container) -> None:
    """Start web server."""
    import uvicorn

    settings = container.settings
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="AI Job Application Agent CLI")
    parser.add_argument(
        "command",
        choices=["init", "discover", "serve"],
        help="Command to run",
    )
    args = parser.parse_args()

    setup_logging()
    container = Container()

    commands = {
        "init": cmd_init,
        "discover": cmd_discover,
        "serve": cmd_serve,
    }

    if args.command == "serve":
        asyncio.run(cmd_init(container))
        cmd_serve(container)
    else:
        asyncio.run(commands[args.command](container))


if __name__ == "__main__":
    main()
