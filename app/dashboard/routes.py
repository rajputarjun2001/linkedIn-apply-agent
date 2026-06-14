"""Dashboard API and web routes."""

from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from loguru import logger

from app.container import get_container
from app.models.application import ApplicationStatus
from app.models.job import JobStatus
from app.linkedin.errors import LinkedInAuthError, LinkedInConnectTimeoutError
from app.models.linkedin import LinkedInSessionStatus
from app.services.ollama_service import OllamaUnavailableError

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request, error: Optional[str] = None, success: Optional[str] = None):
    """Dashboard statistics overview."""
    container = get_container()
    stats = await container.db.get_statistics()
    pending = await container.db.list_applications(
        status=ApplicationStatus.PENDING_APPROVAL, limit=5
    )
    ollama_status = await container.ollama.status()
    linkedin_status = await container.linkedin_auth.status(verify=False)
    return _templates(request).TemplateResponse(
        request,
        "index.html",
        {
            "stats": stats,
            "pending": pending,
            "error": error,
            "success": success,
            "ollama_status": ollama_status,
            "linkedin_status": linkedin_status,
        },
    )


@router.get("/jobs", response_class=HTMLResponse)
async def jobs_found(request: Request, status: Optional[str] = None):
    """List discovered jobs."""
    container = get_container()
    job_status = JobStatus(status) if status else None
    jobs = await container.db.list_jobs(status=job_status, limit=100)
    return _templates(request).TemplateResponse(
        request,
        "jobs.html",
        {"jobs": jobs, "current_status": status},
    )


@router.get("/recommended", response_class=HTMLResponse)
async def recommended_jobs(request: Request):
    """List recommended jobs above match threshold."""
    container = get_container()
    jobs = await container.db.list_jobs(
        status=JobStatus.RECOMMENDED,
        min_match_score=container.settings.min_match_score,
        limit=100,
    )
    return _templates(request).TemplateResponse(
        request,
        "recommended.html",
        {"jobs": jobs, "min_score": container.settings.min_match_score},
    )


@router.get("/resumes", response_class=HTMLResponse)
async def tailored_resumes(request: Request):
    """List tailored resume PDFs."""
    container = get_container()
    resumes = await container.db.list_tailored_resumes(limit=50)
    return _templates(request).TemplateResponse(
        request,
        "resumes.html",
        {"resumes": resumes},
    )


@router.get("/applications", response_class=HTMLResponse)
async def applications_list(request: Request, status: Optional[str] = None):
    """List all applications."""
    container = get_container()
    app_status = ApplicationStatus(status) if status else None
    applications = await container.db.list_applications(status=app_status, limit=100)

    jobs_map = {}
    for app in applications:
        job = await container.db.get_job(app.job_id)
        if job:
            jobs_map[app.job_id] = job

    return _templates(request).TemplateResponse(
        request,
        "applications.html",
        {
            "applications": applications,
            "jobs_map": jobs_map,
            "current_status": status,
        },
    )


@router.get("/applications/{application_id}", response_class=HTMLResponse)
async def application_detail(request: Request, application_id: int):
    """Application detail with approval controls."""
    container = get_container()
    data = await container.application_service.get_application_with_job(application_id)
    if not data:
        raise HTTPException(status_code=404, detail="Application not found")

    return _templates(request).TemplateResponse(
        request,
        "application_detail.html",
        {
            "application": data["application"],
            "job": data["job"],
            "history": data["history"],
            "min_score": container.settings.min_match_score,
        },
    )


@router.post("/applications/{application_id}/approve")
async def approve_application(request: Request, application_id: int):
    """Approve application for manual submission."""
    container = get_container()
    try:
        await container.application_service.approve(application_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/applications/{application_id}", status_code=303)


@router.post("/applications/{application_id}/reject")
async def reject_application(
    request: Request,
    application_id: int,
    reason: str = Form(default=""),
):
    """Reject an application."""
    container = get_container()
    await container.application_service.reject(application_id, reason)
    return RedirectResponse("/applications", status_code=303)


@router.post("/applications/{application_id}/submit")
async def submit_application(
    request: Request,
    application_id: int,
    notes: str = Form(default=""),
):
    """Record manual LinkedIn submission (does not auto-submit)."""
    container = get_container()
    try:
        await container.application_service.submit(application_id, notes=notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/applications/{application_id}", status_code=303)


@router.post("/jobs/{job_id}/prepare")
async def prepare_job_application(request: Request, job_id: int):
    """Start application prepare in the background."""
    container = get_container()
    job = await container.db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    container.application_service.start_prepare_background(job_id)
    return RedirectResponse(f"/jobs/{job_id}/prepare/running", status_code=303)


@router.get("/jobs/{job_id}/prepare/running", response_class=HTMLResponse)
async def prepare_running(request: Request, job_id: int):
    """Show prepare progress while Ollama tailors the resume."""
    container = get_container()
    job = await container.db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _templates(request).TemplateResponse(
        request,
        "prepare_running.html",
        {"job": job},
    )


@router.get("/jobs/{job_id}/prepare/status")
async def prepare_status(job_id: int):
    """Poll background prepare progress."""
    container = get_container()
    return container.application_service.prepare_progress(job_id)


@router.post("/jobs/{job_id}/prepare/wait")
async def prepare_job_application_blocking(request: Request, job_id: int):
    """Blocking prepare endpoint kept for scripts — not used by dashboard."""
    container = get_container()
    job = await container.db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        await container.ollama.ensure_ready()
        await container.application_service.prepare_for_job(job)
    except OllamaUnavailableError as exc:
        return RedirectResponse(f"/?error={quote(str(exc))}", status_code=303)
    except Exception as exc:
        logger.bind(component="dashboard").error("Prepare failed for job {}: {}", job_id, exc)
        return RedirectResponse(f"/?error={quote(str(exc))}", status_code=303)
    return RedirectResponse("/jobs?success=Application+prepared", status_code=303)


@router.post("/discover")
async def trigger_discovery(request: Request):
    """Start job discovery in the background and show progress page."""
    container = get_container()
    container.scheduler.start_discovery_background()
    return RedirectResponse("/discover/running", status_code=303)


@router.get("/discover/running", response_class=HTMLResponse)
async def discovery_running(request: Request):
    """Show discovery progress while pipeline runs in background."""
    return _templates(request).TemplateResponse(request, "discover_running.html", {})


@router.get("/discover/status")
async def discovery_status():
    """Poll background job discovery progress."""
    container = get_container()
    return container.scheduler.discovery_progress()


@router.post("/discover/wait")
async def trigger_discovery_blocking(request: Request):
    """Blocking discovery endpoint kept for scripts — not used by dashboard."""
    container = get_container()
    result = await container.scheduler.run_now()
    if not result.get("success"):
        error = result.get("error") or "Job discovery failed"
        logger.bind(component="dashboard").error("Discovery failed: {}", error)
        return RedirectResponse(f"/?error={quote(error)}", status_code=303)
    msg = (
        f"Discovered {result['discovered_count']} jobs, "
        f"recommended {result['recommended_count']}"
    )
    return RedirectResponse(f"/?success={quote(msg)}", status_code=303)


@router.get("/resumes/download/{resume_id}")
async def download_resume(resume_id: int):
    """Download tailored resume PDF."""
    container = get_container()
    resume = await container.db.get_resume(resume_id)
    if not resume or not resume.get("pdf_path"):
        raise HTTPException(status_code=404, detail="Resume PDF not found")

    pdf_path = Path(resume["pdf_path"])
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file missing on disk")

    return FileResponse(pdf_path, filename=pdf_path.name, media_type="application/pdf")


@router.get("/linkedin/status")
async def linkedin_status(verify: bool = True):
    """Return LinkedIn session status."""
    container = get_container()
    return await container.linkedin_auth.status(verify=verify)


@router.get("/linkedin/connect", response_class=HTMLResponse)
async def linkedin_connect(request: Request):
    """Launch headed browser for manual LinkedIn login (non-blocking)."""
    container = get_container()
    progress = container.linkedin_auth.start_connect_background()
    return _templates(request).TemplateResponse(
        request,
        "linkedin_connect.html",
        {"progress": progress},
    )


@router.get("/linkedin/connect/status")
async def linkedin_connect_status():
    """Poll background LinkedIn connect progress."""
    container = get_container()
    progress = container.linkedin_auth.connect_progress()
    if progress["completed"] and progress["success"]:
        status = await container.linkedin_auth.status(verify=False)
        progress["linkedin_status"] = status
    return progress


@router.post("/linkedin/connect")
async def linkedin_connect_api():
    """API-friendly connect start (returns JSON)."""
    container = get_container()
    return container.linkedin_auth.start_connect_background()


@router.get("/linkedin/connect/wait")
async def linkedin_connect_wait(request: Request):
    """Blocking connect endpoint kept for scripts — not used by dashboard."""
    container = get_container()
    try:
        await container.linkedin_auth.connect()
        return RedirectResponse("/?success=LinkedIn+connected+successfully", status_code=303)
    except LinkedInConnectTimeoutError as exc:
        return RedirectResponse(f"/?error={quote(str(exc))}", status_code=303)
    except Exception as exc:
        logger.bind(component="dashboard").error("LinkedIn connect failed: {}", exc)
        return RedirectResponse(f"/?error={quote(str(exc))}", status_code=303)


@router.post("/linkedin/disconnect")
async def linkedin_disconnect(request: Request):
    """Clear saved LinkedIn session."""
    container = get_container()
    await container.linkedin_auth.disconnect()
    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return {"status": LinkedInSessionStatus.DISCONNECTED.value, "label": "Disconnected"}
    return RedirectResponse("/?success=LinkedIn+disconnected", status_code=303)


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    container = get_container()
    ollama_status = await container.ollama.status()
    migration_status = await container.db.migration_status()
    return {
        "status": "ok",
        "ollama": ollama_status,
        "migrations": migration_status,
        "version": "1.0.0",
    }
