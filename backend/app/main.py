"""
app/main.py
───────────────────────────────────────────────────────────────────────────────
FastAPI application entrypoint.

Responsibilities
────────────────
  • Create the FastAPI app instance.
  • Configure structured logging on startup.
  • Configure CORS for the React frontend.
  • Register the aggregated v1 API router (includes auth, users, and all
    other sub-routers registered in app/api/v1/router.py).
  • Define startup/shutdown lifecycle hooks:
      - startup : configure logging, create DB tables, (future:
                   load ML models — FaceNet / Haar Cascade — once as
                   singletons via app.state)
      - shutdown: dispose of the DB engine's connection pool cleanly,
                   (future: release ML resources / GPU memory)
  • Expose a `/health` endpoint for load balancers / container orchestrators.

Router registration note
────────────────────────
The /api/v1/users router is included via app/api/v1/router.py (the
aggregated api_router), NOT directly in this file. Adding it directly here
with prefix="/api/v1" would produce the correct URL paths but bypasses the
aggregator pattern used by every other sub-router in this project. If you
need to register it here directly for a special reason, use:

    from app.api.v1 import users
    app.include_router(users.router, prefix=settings.API_V1_PREFIX)

This file deliberately contains NO business logic — only application
bootstrapping and wiring.
───────────────────────────────────────────────────────────────────────────────
"""

import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models.attendance import AttendanceRecord  # noqa: F401
from app.models.embedding import FaceEmbedding  # noqa: F401
from app.models.student import Student        # noqa: F401
from app.models.user import User              # noqa: F401
from app.services.attendance_service import AttendanceService
from app.websocket.recognition_ws import router as ws_router

log = get_logger(__name__)


def _next_absent_generation_run(now: datetime) -> datetime:
    """Return the next configured attendance close datetime."""
    close_time = AttendanceService._plain_time(settings.CHECKIN_CLOSE)
    run_at = datetime.combine(now.date(), close_time, tzinfo=now.tzinfo)
    if run_at <= now:
        run_at += timedelta(days=1)
    return run_at


async def _generate_previous_day_absences() -> None:
    """Generate ABSENT rows for the attendance date that just closed."""
    now = AttendanceService._attendance_now()
    target_date = (now - timedelta(seconds=1)).date()

    async with AsyncSessionLocal() as session:
        try:
            service = AttendanceService(session)
            created = await service.generate_absent_records_for_date(target_date)
            await session.commit()
            log.info(
                "Scheduled absent generation complete",
                extra={"ctx_date": str(target_date), "ctx_created": len(created)},
            )
        except Exception as exc:
            await session.rollback()
            log.exception(
                "Scheduled absent generation failed",
                extra={"ctx_date": str(target_date), "ctx_error": str(exc)},
            )


async def _absent_generation_loop() -> None:
    """Run automatic absent generation at CHECKIN_CLOSE every day."""
    while True:
        now = AttendanceService._attendance_now()
        run_at = _next_absent_generation_run(now)
        sleep_seconds = max((run_at - now).total_seconds(), 0)
        log.info(
            "Scheduled next absent generation",
            extra={"ctx_run_at": run_at.isoformat()},
        )
        await asyncio.sleep(sleep_seconds)
        await _generate_previous_day_absences()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    STARTUP:
      1. Configure structured logging (console or JSON, per settings).
      2. Run Base.metadata.create_all to create any missing tables
         (users, students, attendance, embeddings) without dropping
         existing data.
      3. (Future phase) Load and cache ML models — Haar Cascade detector
         and FaceNet embedder — on `app.state` so they are initialised
         once per process, not per request.

    SHUTDOWN:
      1. Dispose of the SQLAlchemy engine's connection pool.
      2. (Future phase) Release any ML model resources / GPU memory.
    """
    # ── Startup ──────────────────────────────────────────────────────────
    configure_logging()
    log.info(f"Starting {settings.PROJECT_NAME} ({settings.ENVIRONMENT})")

    try:
        print("\n=== REGISTERED TABLES ===")
        print(list(Base.metadata.tables.keys()))
        print("=========================\n")

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        print("\n=== TABLES AFTER create_all() ===")
        print(list(Base.metadata.tables.keys()))
        print("================================\n")

        log.info("Database tables verified / created.")
    except Exception as exc:
        import traceback
        log.error("Database initialisation failed!")
        traceback.print_exc()
        # Intentionally not raising here in early development so the API
        # can still boot (e.g. to serve /health) even if the DB is not yet
        # provisioned. Tighten this (re-raise) once migrations are in place.

    # Placeholder for future ML model loading:
    #   app.state.face_detector = HaarFaceDetector()
    #   app.state.embedder      = FaceNetEmbedder()
    absent_generation_task = asyncio.create_task(_absent_generation_loop())
    app.state.absent_generation_task = absent_generation_task
    log.info("Startup complete.")

    yield

    absent_generation_task.cancel()
    with suppress(asyncio.CancelledError):
        await absent_generation_task

    # ── Shutdown ─────────────────────────────────────────────────────────
    log.info("Shutting down — disposing database engine.")
    await engine.dispose()

    # Placeholder for future ML resource cleanup:
    #   del app.state.embedder
    #   del app.state.face_detector
    log.info("Shutdown complete.")


def create_app() -> FastAPI:
    """
    Application factory.

    Using a factory (rather than a bare module-level `app = FastAPI()`)
    keeps test setup flexible — tests can call `create_app()` with
    overridden settings/dependencies without import-time side effects.
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.1.0",
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────
    # Hardcoded localhost origins are always included for local development.
    # BACKEND_CORS_ORIGINS (set via env var on Render) adds the deployed
    # frontend URL, e.g. https://smart-attendance-face-recogonition.vercel.app
    allow_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        *settings.cors_origins,   # parsed from BACKEND_CORS_ORIGINS env var
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ──────────────────────────────────────────────────────────
    # api_router (app/api/v1/router.py) aggregates all v1 sub-routers,
    # including the new /users router registered there.
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    app.include_router(ws_router)  # WebSocket: /ws/recognition

    # ── Health check ─────────────────────────────────────────────────────
    @app.get("/health", tags=["Health"])
    def health_check() -> dict[str, str]:
        """Basic liveness probe for load balancers / orchestrators."""
        return {"status": "ok", "environment": settings.ENVIRONMENT}

    return app


app = create_app()
