"""Structured logging with Loguru."""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger

from app.config.settings import Settings


def setup_logging(settings: Optional[Settings] = None) -> None:
    """Configure structured application logging."""
    settings = settings or Settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stderr,
        format=log_format,
        level="DEBUG" if settings.debug else "INFO",
        enqueue=True,
    )

    logger.add(
        settings.log_dir / "agent_{time:YYYY-MM-DD}.log",
        format=log_format,
        level="DEBUG",
        rotation="1 day",
        retention="30 days",
        enqueue=True,
        serialize=False,
    )

    logger.add(
        settings.log_dir / "errors_{time:YYYY-MM-DD}.log",
        format=log_format,
        level="ERROR",
        rotation="1 week",
        retention="90 days",
        enqueue=True,
    )

    logger.bind(component="startup").info("Logging initialized")


def get_logger(component: str):
    """Return a logger bound to a component name."""
    return logger.bind(component=component)
