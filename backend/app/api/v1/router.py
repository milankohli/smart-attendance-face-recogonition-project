"""
app/api/v1/router.py
───────────────────────────────────────────────────────────────────────────────
Aggregated v1 API router.

All sub-routers for /api/v1/* are registered here. main.py mounts this
single router under `settings.API_V1_PREFIX` (typically "/api/v1"), so
the effective paths become:

  /api/v1/auth/*   — authentication (login, refresh, me, register)
  /api/v1/users/*  — user management CRUD (admin-only)
  … (add future sub-routers here, not in main.py)
───────────────────────────────────────────────────────────────────────────────
"""

from fastapi import APIRouter

from app.api.v1 import analytics, attendance, auth, export, recognition, students, users

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(students.router)
api_router.include_router(attendance.router)
api_router.include_router(recognition.router)
api_router.include_router(analytics.router)
api_router.include_router(export.router)
