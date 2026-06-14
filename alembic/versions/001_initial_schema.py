"""Initial schema via Alembic."""

from pathlib import Path

from alembic import op

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = Path(__file__).resolve().parents[1] / "app" / "database" / "schema.sql"
    sql = schema.read_text(encoding="utf-8")
    op.execute(sql)

    migrations = Path(__file__).resolve().parents[1] / "app" / "database" / "migrations.py"
    # Additional columns applied by runtime MigrationManager on app startup.
    _ = migrations


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS application_history")
    op.execute("DROP TABLE IF EXISTS applications")
    op.execute("DROP TABLE IF EXISTS resumes")
    op.execute("DROP TABLE IF EXISTS jobs")
    op.execute("DROP TABLE IF EXISTS schema_migrations")
