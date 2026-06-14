"""SQLite database repository with async operations."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite
from loguru import logger

from app.config.settings import Settings
from app.database.migrations import MigrationManager
from app.models.application import Application, ApplicationHistory, ApplicationStatus
from app.models.job import Job, JobCreate, JobStatus
from app.models.match import JobMatchResult
from app.models.resume import MasterResume, TailoredResume


class DatabaseRepository:
    """Async SQLite repository for jobs, resumes, and applications."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db_path = settings.database_path
        self._schema_path = Path(__file__).parent / "schema.sql"

    async def initialize(self) -> None:
        """Create database directory and apply schema migrations."""
        migrator = MigrationManager(self._db_path, self._schema_path)
        version = await migrator.migrate()
        logger.bind(component="database").info(
            "Database initialized at {} (schema v{})", self._db_path, version
        )

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value.replace("Z", ""), fmt)
            except ValueError:
                continue
        return datetime.fromisoformat(value)

    @staticmethod
    def _row_value(row: aiosqlite.Row, key: str, default: Any = None) -> Any:
        if key in row.keys():
            return row[key]
        return default

    def _row_to_job(self, row: aiosqlite.Row) -> Job:
        return Job(
            id=row["id"],
            title=row["title"],
            company=row["company"],
            location=row["location"] or "",
            description=row["description"] or "",
            apply_url=row["apply_url"],
            posting_date=row["posting_date"],
            keyword=row["keyword"],
            search_location=row["search_location"],
            is_easy_apply=bool(row["is_easy_apply"]),
            linkedin_job_id=row["linkedin_job_id"],
            match_score=row["match_score"],
            missing_skills=json.loads(self._row_value(row, "missing_skills", "[]") or "[]"),
            relevant_skills=json.loads(self._row_value(row, "relevant_skills", "[]") or "[]"),
            relevant_experience=json.loads(
                self._row_value(row, "relevant_experience", "[]") or "[]"
            ),
            match_reasoning=self._row_value(row, "match_reasoning"),
            status=JobStatus(row["status"]),
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    async def job_exists(self, apply_url: str, linkedin_job_id: Optional[str] = None) -> bool:
        """Check if a job already exists to prevent duplicates."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if linkedin_job_id:
                cursor = await db.execute(
                    "SELECT 1 FROM jobs WHERE apply_url = ? OR linkedin_job_id = ? LIMIT 1",
                    (apply_url, linkedin_job_id),
                )
            else:
                cursor = await db.execute(
                    "SELECT 1 FROM jobs WHERE apply_url = ? LIMIT 1",
                    (apply_url,),
                )
            row = await cursor.fetchone()
            return row is not None

    async def create_job(self, job: JobCreate) -> Optional[Job]:
        """Insert a new job if not duplicate."""
        if await self.job_exists(job.apply_url, job.linkedin_job_id):
            logger.bind(component="database").debug(
                "Skipping duplicate job: {} at {}", job.title, job.company
            )
            return None

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                INSERT INTO jobs (
                    title, company, location, description, apply_url, posting_date,
                    keyword, search_location, is_easy_apply, linkedin_job_id, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.title,
                    job.company,
                    job.location,
                    job.description,
                    job.apply_url,
                    job.posting_date,
                    job.keyword,
                    job.search_location,
                    int(job.is_easy_apply),
                    job.linkedin_job_id,
                    JobStatus.DISCOVERED.value,
                ),
            )
            await db.commit()
            job_id = cursor.lastrowid

        return await self.get_job(job_id)

    async def get_job(self, job_id: int) -> Optional[Job]:
        """Fetch a job by ID."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = await cursor.fetchone()
            return self._row_to_job(row) if row else None

    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        min_match_score: Optional[int] = None,
        limit: int = 100,
    ) -> List[Job]:
        """List jobs with optional filters."""
        query = "SELECT * FROM jobs WHERE 1=1"
        params: List[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status.value)
        if min_match_score is not None:
            query += " AND match_score >= ?"
            params.append(min_match_score)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [self._row_to_job(row) for row in rows]

    async def update_job_match(
        self,
        job_id: int,
        match_score: int,
        status: JobStatus = JobStatus.MATCHED,
        match_result: Optional[JobMatchResult] = None,
    ) -> None:
        """Update job match score, analysis, and status."""
        missing_skills = json.dumps(match_result.missing_skills if match_result else [])
        relevant_skills = json.dumps(match_result.relevant_skills if match_result else [])
        relevant_experience = json.dumps(
            match_result.relevant_experience if match_result else []
        )
        reasoning = match_result.reasoning if match_result else ""

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                UPDATE jobs
                SET match_score = ?, status = ?, missing_skills = ?,
                    relevant_skills = ?, relevant_experience = ?,
                    match_reasoning = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    match_score,
                    status.value,
                    missing_skills,
                    relevant_skills,
                    relevant_experience,
                    reasoning,
                    job_id,
                ),
            )
            await db.commit()

    async def update_job_status(self, job_id: int, status: JobStatus) -> None:
        """Update job status."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "UPDATE jobs SET status = ?, updated_at = datetime('now') WHERE id = ?",
                (status.value, job_id),
            )
            await db.commit()

    async def save_resume(
        self,
        resume_data: MasterResume | TailoredResume,
        job_id: Optional[int] = None,
        pdf_path: Optional[str] = None,
        is_tailored: bool = False,
        version_label: str = "master",
        parent_resume_id: Optional[int] = None,
        source_type: str = "master",
    ) -> int:
        """Persist resume JSON and return resume ID."""
        resume_json = resume_data.model_dump_json()

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO resumes (
                    job_id, version_label, resume_json, pdf_path, is_tailored,
                    parent_resume_id, source_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    version_label,
                    resume_json,
                    pdf_path,
                    int(is_tailored),
                    parent_resume_id,
                    source_type,
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_master_resume_id(self) -> Optional[int]:
        """Return latest stored master resume ID."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id FROM resumes
                WHERE source_type = 'master' OR is_tailored = 0
                ORDER BY created_at DESC LIMIT 1
                """
            )
            row = await cursor.fetchone()
            return row["id"] if row else None

    async def get_resume(self, resume_id: int) -> Optional[Dict[str, Any]]:
        """Fetch resume record by ID."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "job_id": row["job_id"],
                "version_label": row["version_label"],
                "resume_json": json.loads(row["resume_json"]),
                "pdf_path": row["pdf_path"],
                "is_tailored": bool(row["is_tailored"]),
                "created_at": row["created_at"],
            }

    async def list_tailored_resumes(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List tailored resume records."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT r.*, j.title as job_title, j.company as job_company
                FROM resumes r
                LEFT JOIN jobs j ON r.job_id = j.id
                WHERE r.is_tailored = 1
                ORDER BY r.created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "job_id": row["job_id"],
                    "job_title": row["job_title"],
                    "job_company": row["job_company"],
                    "pdf_path": row["pdf_path"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    async def application_exists_for_job(self, job_id: int) -> bool:
        """Check if an application already exists for a job."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT 1 FROM applications WHERE job_id = ? LIMIT 1",
                (job_id,),
            )
            return await cursor.fetchone() is not None

    async def create_application(
        self,
        job_id: int,
        match_score: int,
        resume_id: Optional[int] = None,
        resume_pdf_path: Optional[str] = None,
        application_answers: Optional[Dict[str, str]] = None,
        missing_skills: Optional[List[str]] = None,
        relevant_experience: Optional[List[str]] = None,
        match_analysis: Optional[Dict[str, Any]] = None,
    ) -> Application:
        """Create a pending application requiring human approval."""
        if await self.application_exists_for_job(job_id):
            raise ValueError(f"Application already exists for job {job_id}")

        answers_json = json.dumps(application_answers or {})
        missing_json = json.dumps(missing_skills or [])
        relevant_json = json.dumps(relevant_experience or [])
        analysis_json = json.dumps(match_analysis or {})

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO applications (
                    job_id, resume_id, match_score, status,
                    resume_pdf_path, application_answers,
                    missing_skills, relevant_experience, match_analysis_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    resume_id,
                    match_score,
                    ApplicationStatus.PENDING_APPROVAL.value,
                    resume_pdf_path,
                    answers_json,
                    missing_json,
                    relevant_json,
                    analysis_json,
                ),
            )
            await db.commit()
            app_id = cursor.lastrowid

        application = await self.get_application(app_id)
        if not application:
            raise RuntimeError("Failed to create application")
        await self.add_application_history(
            app_id, "created", "Application preview generated, awaiting approval"
        )
        return application

    def _application_from_row(self, row: aiosqlite.Row) -> Application:
        return Application(
            id=row["id"],
            job_id=row["job_id"],
            resume_id=row["resume_id"],
            match_score=row["match_score"],
            status=ApplicationStatus(row["status"]),
            resume_pdf_path=row["resume_pdf_path"],
            application_answers=json.loads(row["application_answers"] or "{}"),
            missing_skills=json.loads(
                self._row_value(row, "missing_skills", "[]") or "[]"
            ),
            relevant_experience=json.loads(
                self._row_value(row, "relevant_experience", "[]") or "[]"
            ),
            match_analysis_json=json.loads(
                self._row_value(row, "match_analysis_json", "{}") or "{}"
            ),
            notes=row["notes"],
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
            submitted_at=self._parse_datetime(row["submitted_at"]),
        )

    async def get_application(self, application_id: int) -> Optional[Application]:
        """Fetch application by ID."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM applications WHERE id = ?",
                (application_id,),
            )
            row = await cursor.fetchone()
            return self._application_from_row(row) if row else None

    async def list_applications(
        self,
        status: Optional[ApplicationStatus] = None,
        limit: int = 100,
    ) -> List[Application]:
        """List applications with optional status filter."""
        query = "SELECT * FROM applications"
        params: List[Any] = []

        if status:
            query += " WHERE status = ?"
            params.append(status.value)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [self._application_from_row(row) for row in rows]

    async def update_application_status(
        self,
        application_id: int,
        status: ApplicationStatus,
        notes: Optional[str] = None,
        mark_submitted: bool = False,
    ) -> None:
        """Update application status."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if mark_submitted:
                await db.execute(
                    """
                    UPDATE applications
                    SET status = ?, notes = ?, updated_at = datetime('now'),
                        submitted_at = datetime('now')
                    WHERE id = ?
                    """,
                    (status.value, notes, application_id),
                )
            else:
                await db.execute(
                    """
                    UPDATE applications
                    SET status = ?, notes = ?, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (status.value, notes, application_id),
                )
            await db.commit()

    async def add_application_history(
        self,
        application_id: int,
        action: str,
        details: Optional[str] = None,
        performed_by: str = "system",
    ) -> None:
        """Record an application history event."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO application_history (application_id, action, details, performed_by)
                VALUES (?, ?, ?, ?)
                """,
                (application_id, action, details, performed_by),
            )
            await db.commit()

    async def get_application_history(
        self, application_id: int
    ) -> List[ApplicationHistory]:
        """Fetch history for an application."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM application_history
                WHERE application_id = ?
                ORDER BY created_at DESC
                """,
                (application_id,),
            )
            rows = await cursor.fetchall()
            return [
                ApplicationHistory(
                    id=row["id"],
                    application_id=row["application_id"],
                    action=row["action"],
                    details=row["details"],
                    performed_by=row["performed_by"],
                    created_at=self._parse_datetime(row["created_at"]),
                )
                for row in rows
            ]

    async def get_statistics(self) -> Dict[str, Any]:
        """Return dashboard statistics."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            stats: Dict[str, Any] = {}

            for query, key in [
                ("SELECT COUNT(*) FROM jobs", "total_jobs"),
                ("SELECT COUNT(*) FROM jobs WHERE status = 'recommended'", "recommended_jobs"),
                ("SELECT COUNT(*) FROM applications", "total_applications"),
                (
                    "SELECT COUNT(*) FROM applications WHERE status = 'pending_approval'",
                    "pending_approvals",
                ),
                (
                    "SELECT COUNT(*) FROM applications WHERE status = 'submitted'",
                    "submitted_applications",
                ),
                ("SELECT COUNT(*) FROM resumes WHERE is_tailored = 1", "tailored_resumes"),
                ("SELECT AVG(match_score) FROM jobs WHERE match_score IS NOT NULL", "avg_match_score"),
            ]:
                cursor = await db.execute(query)
                row = await cursor.fetchone()
                stats[key] = row[0] if row else 0

            return stats

    async def migration_status(self) -> Dict[str, Any]:
        """Return database migration status."""
        migrator = MigrationManager(self._db_path, self._schema_path)
        return await migrator.status()
