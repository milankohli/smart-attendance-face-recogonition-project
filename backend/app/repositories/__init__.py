"""
app/repositories/__init__.py
───────────────────────────────────────────────────────────────────────────────
Convenience re-exports for the repository layer.

Usage:
    from app.repositories import StudentRepository, AttendanceRepository
───────────────────────────────────────────────────────────────────────────────
"""

from app.repositories.user_repo import UserRepository
from app.repositories.student_repo import StudentRepository
from app.repositories.embedding_repo import EmbeddingRepository
from app.repositories.attendance_repo import AttendanceRepository

__all__ = [
    "UserRepository",
    "StudentRepository",
    "EmbeddingRepository",
    "AttendanceRepository",
]
