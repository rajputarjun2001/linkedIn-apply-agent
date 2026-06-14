"""FastAPI dashboard application."""

from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.dashboard.routes import router


def create_app(
    lifespan: Optional[Callable[..., AbstractAsyncContextManager]] = None,
) -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="AI Job Application Agent",
        description="AI-powered LinkedIn Easy Apply job application assistant",
        version="1.0.0",
        lifespan=lifespan,
    )

    templates_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)

    app.state.templates = Jinja2Templates(directory=str(templates_dir))
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(router)

    return app
