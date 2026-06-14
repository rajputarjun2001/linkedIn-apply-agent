"""Tests for database migrations."""

from pathlib import Path

import pytest

from app.database.migrations import MigrationManager


@pytest.mark.asyncio
async def test_migrations_apply(tmp_path):
    db_path = tmp_path / "migrate.db"
    schema = Path(__file__).resolve().parents[1] / "app" / "database" / "schema.sql"
    migrator = MigrationManager(db_path, schema)
    version = await migrator.migrate()
    assert version >= 1

    status = await migrator.status()
    assert status["current_version"] >= 1


@pytest.mark.asyncio
async def test_migration_rollback_record(tmp_path):
    db_path = tmp_path / "rollback.db"
    schema = Path(__file__).resolve().parents[1] / "app" / "database" / "schema.sql"
    migrator = MigrationManager(db_path, schema)
    await migrator.migrate()
    await migrator.rollback_to(1)
    status = await migrator.status()
    assert status["current_version"] <= 4
