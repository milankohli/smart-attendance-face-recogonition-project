"""add student_name and student_code to attendance_records

Revision ID: a1b2c3d4e5f6
Revises: <replace_with_your_current_head>
Create Date: 2024-01-01 00:00:00.000000

Context
───────
The student-deletion workflow was changed from soft-delete (deactivate) to
hard-delete.  To preserve attendance history after a student row is removed,
the AttendanceRecord model was updated to carry two denormalised identity
columns:

  student_name  VARCHAR(150) NULL  — copied from students.name at record creation
  student_code  VARCHAR(50)  NULL  — copied from students.student_code at creation

When a student is hard-deleted, the DB sets attendance_records.student_id to
NULL (ON DELETE SET NULL), but student_name and student_code remain, keeping
every historical row human-readable.

This migration:
  1. Adds both columns as nullable (no default required — existing rows are
     backfilled in step 2).
  2. Backfills all existing records whose student_id is still non-NULL by
     joining to the students table.  Records where student_id is already NULL
     (student was deleted before this migration) cannot be backfilled and will
     retain NULL in both new columns — this is the correct, intended behaviour.
  3. Creates the index on student_code that mirrors the ORM model definition
     (ix_attendance_records_student_code).

Rollback:
  Drops the index, then drops both columns.  No data recovery is needed
  because the source of truth (students.name / students.student_code) still
  exists.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "<replace_with_your_current_head>"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ── Step 1: Add the two nullable columns ──────────────────────────────
    #
    # Both are nullable so the ALTER TABLE succeeds instantly even on a large
    # table — PostgreSQL does not rewrite the table for nullable additions.
    # The ORM model declares them nullable=True, matching exactly.

    op.add_column(
        "attendance_records",
        sa.Column("student_name", sa.String(150), nullable=True),
    )
    op.add_column(
        "attendance_records",
        sa.Column("student_code", sa.String(50), nullable=True),
    )

    # ── Step 2: Backfill existing rows from the students table ────────────
    #
    # Use a single UPDATE … FROM … JOIN so Postgres resolves all lookups in
    # one pass.  Records whose student_id is already NULL are not touched —
    # the WHERE clause naturally excludes them, leaving their new columns NULL.
    #
    # Raw SQL is intentional: Alembic migrations must never import ORM models
    # because the models may have diverged from the DB state being migrated.

    op.execute(
        """
        UPDATE attendance_records AS ar
        SET
            student_name = s.name,
            student_code = s.student_code
        FROM students AS s
        WHERE ar.student_id = s.id
          AND ar.student_id IS NOT NULL
        """
    )

    # ── Step 3: Create the index on student_code ──────────────────────────
    #
    # Mirrors the ORM declaration:
    #   student_code: Mapped[str | None] = mapped_column(..., index=True)
    # Alembic auto-generates this index name from the table + column name.

    op.create_index(
        "ix_attendance_records_student_code",
        "attendance_records",
        ["student_code"],
        unique=False,
    )


def downgrade() -> None:
    # Drop in reverse order: index first, then columns.

    op.drop_index(
        "ix_attendance_records_student_code",
        table_name="attendance_records",
    )
    op.drop_column("attendance_records", "student_code")
    op.drop_column("attendance_records", "student_name")
