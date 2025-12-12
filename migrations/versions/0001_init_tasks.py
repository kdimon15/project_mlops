"""Initial tasks table (includes zoom in tasksource enum).

Revision ID: 0001_init
Revises:
Create Date: 2025-12-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Создаем/обновляем enum-типы
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'taskstatus') THEN
                CREATE TYPE taskstatus AS ENUM ('queued', 'processing', 'completed', 'failed');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tasksource') THEN
                CREATE TYPE tasksource AS ENUM ('upload', 'kontur_talk', 'zoom');
            ELSIF NOT EXISTS (
                SELECT 1 FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                WHERE t.typname = 'tasksource' AND e.enumlabel = 'zoom'
            ) THEN
                ALTER TYPE tasksource ADD VALUE 'zoom';
            END IF;
        END$$;
        """
    )

    if "tasks" not in inspector.get_table_names():
        status_enum = postgresql.ENUM(
            "queued",
            "processing",
            "completed",
            "failed",
            name="taskstatus",
            create_type=False,
        )
        source_enum = postgresql.ENUM(
            "upload",
            "kontur_talk",
            "zoom",
            name="tasksource",
            create_type=False,
        )

        op.create_table(
            "tasks",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("status", status_enum, nullable=True),
            sa.Column("source", source_enum, nullable=True),
            sa.Column("progress", sa.Integer(), nullable=True),
            sa.Column("meeting_id", sa.String(length=255), nullable=True),
            sa.Column("recording_id", sa.String(length=255), nullable=True),
            sa.Column("filename", sa.String(length=255), nullable=True),
            sa.Column("file_path", sa.String(length=500), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column("language", sa.String(length=10), nullable=True),
            sa.Column("transcription", sa.Text(), nullable=True),
            sa.Column("transcription_segments", sa.Text(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("key_points", sa.Text(), nullable=True),
            sa.Column("action_items", sa.Text(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
    else:
        # таблица уже существует — ничего не делаем
        pass


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "tasks" in inspector.get_table_names():
        op.drop_table("tasks")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'taskstatus') THEN
                DROP TYPE taskstatus;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tasksource') THEN
                DROP TYPE tasksource;
            END IF;
        END$$;
        """
    )
