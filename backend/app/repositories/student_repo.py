"""
app/repositories/student_repo.py
───────────────────────────────────────────────────────────────────────────────
Repository for Student CRUD operations.

Provides a session-scoped data access layer for the `students` table.
Hard-delete is used for student removal. Attendance records are preserved
via ON DELETE SET NULL on the FK; face embeddings are cascade-deleted.

There is no `is_active` column on `students` — every row in the table is
a live record by definition. `list_active` and `count_active` are provided
as semantic aliases so that the service layer can use intent-revealing names
without caring about the underlying storage strategy.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.student import Student

log = get_logger(__name__)


class StudentRepository:
    """Data-access layer for the `students` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Read ──────────────────────────────────────────────────────────────

    async def get_by_id(self, student_id: int, *, load_embeddings: bool = False) -> Student | None:
        """
        Fetch a Student by primary key.

        Args:
            student_id:      PK to look up.
            load_embeddings: If True, eagerly load the `embeddings`
                             relationship in the same query.
        """
        if load_embeddings:
            stmt = (
                select(Student)
                .where(Student.id == student_id)
                .options(selectinload(Student.embeddings))
            )
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()

        return await self._session.get(Student, student_id)

    async def get_by_code(self, student_code: str) -> Student | None:
        """Return a Student by their unique institutional code, or None."""
        stmt = select(Student).where(Student.student_code == student_code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Student | None:
        """Return a Student by email, or None."""
        stmt = select(Student).where(Student.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        department: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Student]:
        """
        Return all students, optionally filtered by department.

        Under hard-delete every row in `students` is a live student —
        there is no is_active flag to filter on.

        Args:
            department: Optional filter by department name.
            skip:       Pagination offset.
            limit:      Maximum rows returned.
        """
        stmt = select(Student)
        if department:
            stmt = stmt.where(Student.department == department)
        stmt = stmt.offset(skip).limit(limit).order_by(Student.name)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_active(
        self,
        *,
        department: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Student]:
        """
        Semantic alias for `list()`.

        Because students use hard-delete there is no is_active flag — every
        row is implicitly active. This alias lets the service layer use an
        intent-revealing name without the repository needing to know (or
        care) that the underlying strategy is hard-delete rather than
        soft-delete.

        Args:
            department: Optional filter by department name.
            skip:       Pagination offset.
            limit:      Maximum rows returned.
        """
        return await self.list(department=department, skip=skip, limit=limit)

    async def count(self) -> int:
        """Return the total number of students (for dashboard summary cards)."""
        stmt = select(func.count()).select_from(Student)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_active(self) -> int:
        """
        Semantic alias for `count()`.

        Under hard-delete all stored students are active; this alias mirrors
        `list_active` so the service layer can call both without caring about
        the underlying storage strategy.
        """
        return await self.count()

    async def search_by_name(
        self,
        name_fragment: str,
        *,
        limit: int = 20,
    ) -> Sequence[Student]:
        """
        Case-insensitive prefix/substring search on `name`.

        Useful for the admin "quick search" UI widget.
        """
        stmt = (
            select(Student)
            .where(Student.name.ilike(f"%{name_fragment}%"))
            .limit(limit)
            .order_by(Student.name)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ── Write ─────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        name: str,
        student_code: str,
        email: str | None = None,
        department: str | None = None,
        photo_path: str | None = None,
    ) -> Student:
        """Persist a new Student record and return it with a populated PK."""
        student = Student(
            name=name,
            student_code=student_code,
            email=email,
            department=department,
            photo_path=photo_path,
        )
        self._session.add(student)
        await self._session.flush()
        log.info(
            "Student created",
            extra={"ctx_student_id": student.id, "ctx_student_code": student_code},
        )
        return student

    async def update(self, student: Student, **fields) -> Student:
        """
        Apply arbitrary field updates to a Student row.

        Only non-None values in `fields` are applied, enabling partial
        updates (PUT /students/{id} with optional fields).

        Example:
            await repo.update(student, name="Bob", department="CS")
        """
        allowed = {"name", "email", "department", "photo_path"}
        for key, value in fields.items():
            if key in allowed and value is not None:
                setattr(student, key, value)
        self._session.add(student)
        await self._session.flush()
        log.info("Student updated", extra={"ctx_student_id": student.id, "ctx_fields": list(fields.keys())})
        return student

    async def delete(self, student: Student) -> None:
        """
        Permanently remove a student row.

        Face embeddings are cascade-deleted by the ORM (cascade="all,
        delete-orphan" on Student.embeddings). Attendance records are
        preserved — the DB sets their student_id FK to NULL via
        ON DELETE SET NULL while student_name / student_code on each row
        remain intact for historical display.
        """
        await self._session.delete(student)
        await self._session.flush()
        log.info("Student deleted", extra={"ctx_student_id": student.id})
