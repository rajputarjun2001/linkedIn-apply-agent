"""Database schema migrations."""

import json
from pathlib import Path

import aiosqlite
from loguru import logger

MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "initial_schema",
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """,
    ),
    (
        2,
        "add_job_match_analysis",
        """
        ALTER TABLE jobs ADD COLUMN missing_skills TEXT DEFAULT '[]';
        ALTER TABLE jobs ADD COLUMN relevant_skills TEXT DEFAULT '[]';
        ALTER TABLE jobs ADD COLUMN relevant_experience TEXT DEFAULT '[]';
        ALTER TABLE jobs ADD COLUMN match_reasoning TEXT DEFAULT '';
        """,
    ),
    (
        3,
        "add_application_match_fields",
        """
        ALTER TABLE applications ADD COLUMN missing_skills TEXT DEFAULT '[]';
        ALTER TABLE applications ADD COLUMN relevant_experience TEXT DEFAULT '[]';
        ALTER TABLE applications ADD COLUMN match_analysis_json TEXT DEFAULT '{}';
        """,
    ),
    (
        4,
        "add_resume_versioning",
        """
        ALTER TABLE resumes ADD COLUMN parent_resume_id INTEGER;
        ALTER TABLE resumes ADD COLUMN source_type TEXT NOT NULL DEFAULT 'master';
        """,
    ),
]


class MigrationManager:
    """Applies versioned SQLite schema migrations with rollback metadata."""

    def __init__(self, db_path: Path, schema_sql_path: Path) -> None:
        self._db_path = db_path
        self._schema_sql_path = schema_sql_path

    async def _current_version(self, db: aiosqlite.Connection) -> int:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        )
        if not await cursor.fetchone():
            return 0
        cursor = await db.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def migrate(self) -> int:
        """Apply pending migrations. Returns final schema version."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self._db_path) as db:
            base_schema = self._schema_sql_path.read_text(encoding="utf-8")
            await db.executescript(base_schema)
            await db.commit()

            current = await self._current_version(db)
            applied = current

            for version, name, sql in MIGRATIONS:
                if version <= current:
                    continue
                logger.bind(component="migrations").info(
                    "Applying migration v{}: {}", version, name
                )
                try:
                    await db.executescript(sql)
                    await db.execute(
                        "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                        (version, name),
                    )
                    await db.commit()
                    applied = version
                except Exception as exc:
                    if "duplicate column name" in str(exc).lower():
                        await db.execute(
                            "INSERT OR IGNORE INTO schema_migrations (version, name) VALUES (?, ?)",
                            (version, name),
                        )
                        await db.commit()
                        applied = version
                        logger.bind(component="migrations").warning(
                            "Migration v{} already partially applied: {}", version, exc
                        )
                    else:
                        raise

            logger.bind(component="migrations").info(
                "Database at schema version {}", applied
            )
            return applied

    async def rollback_to(self, target_version: int) -> None:
        """Rollback is limited to recording downgrade intent for SQLite."""
        async with aiosqlite.connect(self._db_path) as db:
            current = await self._current_version(db)
            if target_version >= current:
                return
            await db.execute(
                "DELETE FROM schema_migrations WHERE version > ?",
                (target_version,),
            )
            await db.commit()
            logger.bind(component="migrations").warning(
                "Rolled back migration records to v{}. "
                "SQLite columns are not dropped automatically.",
                target_version,
            )

    async def status(self) -> dict:
        async with aiosqlite.connect(self._db_path) as db:
            current = await self._current_version(db)
            pending = [m[1] for m in MIGRATIONS if m[0] > current]
            return {
                "current_version": current,
                "latest_version": MIGRATIONS[-1][0] if MIGRATIONS else 0,
                "pending": pending,
            }
