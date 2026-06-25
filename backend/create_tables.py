"""
create_tables.py
────────────────
Standalone script that creates all database tables by running
Base.metadata.create_all() against the configured PostgreSQL database.

Run from the project root:
    python create_tables.py

The WindowsSelectorEventLoopPolicy guard is kept so this script works on
Windows (Python 3.10+ ProactorEventLoop is incompatible with psycopg async).
On Linux/macOS the policy call is a no-op.
"""

import asyncio
import sys

# Windows: use SelectorEventLoop — ProactorEventLoop is incompatible with
# psycopg's async driver. This must be set BEFORE any asyncio.run() call.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.db.base import Base      # noqa: E402 — must come after policy guard
from app.db.session import engine  # noqa: E402

# Import every model so SQLAlchemy registers its Table on Base.metadata
# before create_all() runs. Without these imports, the tables are invisible
# to metadata and will not be created.
from app.models.attendance import AttendanceRecord  # noqa: F401, E402
from app.models.embedding import FaceEmbedding      # noqa: F401, E402
from app.models.student import Student              # noqa: F401, E402
from app.models.user import User                    # noqa: F401, E402


async def create_tables() -> None:
    print("\n=== REGISTERED TABLES ===")
    print(list(Base.metadata.tables.keys()))
    print("=========================\n")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("\n=== TABLES AFTER create_all() ===")
    print(list(Base.metadata.tables.keys()))
    print("================================\n")
    print("Tables created successfully!")


if __name__ == "__main__":
    asyncio.run(create_tables())