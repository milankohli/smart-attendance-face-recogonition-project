    # ─────────────────────────────────────────────────────────────────────────────
# Stage 1: builder
#   Installs all Python dependencies (including heavy ML libs) into a virtual
#   environment that is copied into the lean runtime stage.  Using a separate
#   builder keeps the final image free of build tools and pip cache.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# System libraries required to build / run:
#   libpq-dev        → psycopg (PostgreSQL driver)
#   libgl1            → OpenCV (headless) needs libGL
#   libglib2.0-0     → OpenCV runtime dep
#   build-essential  → compiling C-extension wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Create an isolated virtual environment so only its /build/venv directory
# needs to be copied to the runtime stage.
RUN python -m venv /build/venv
ENV PATH="/build/venv/bin:$PATH"

# Upgrade pip / wheel before installing heavy packages.
RUN pip install --upgrade pip wheel

# Copy only the dependency manifest first so Docker layer-caching avoids
# re-installing packages when only application code changes.
COPY requirements.txt .

# Install PyTorch CPU-only variant first (avoids pulling the CUDA wheel which
# is ~2 GB).  Then install the rest of the requirements.
# CPU torch wheel index keeps the image under 2 GB total.
RUN pip install --no-cache-dir \
        torch>=2.0.0 torchvision>=0.15.0 \
        --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

# FastAPI stack (not in requirements.txt — backend-specific web deps)
RUN pip install --no-cache-dir \
        fastapi>=0.111.0 \
        "uvicorn[standard]>=0.30.0" \
        pydantic>=2.7.0 \
        pydantic-settings>=2.3.0 \
        python-jose[cryptography]>=3.3.0 \
        passlib[bcrypt]>=1.7.4 \
        python-multipart>=0.0.9 \
        sqlalchemy>=2.0.0 \
        psycopg[binary]>=3.1.0 \
        pgvector>=0.2.5 \
        alembic>=1.13.0

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: runtime
#   Minimal image — only the virtual environment, system runtime libs, and
#   the application source.  No build tools, no pip, no cache.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="smart-attendance" \
      description="Smart Attendance System — FastAPI backend" \
      version="0.1.0"

# Runtime-only system libraries (no -dev packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy the pre-built virtual environment from the builder stage
COPY --from=builder /build/venv /app/venv
ENV PATH="/app/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy application source (preserving package layout)
COPY --chown=appuser:appuser . /app

# Create directories that the app writes to at runtime
RUN mkdir -p /app/media/exports \
    && chown -R appuser:appuser /app/media

USER appuser

EXPOSE 8000

# Health check — give the app 30 s to start, then poll every 15 s.
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

# Uvicorn: single worker per container; scale out by running more containers.
# --forwarded-allow-ips='*' trusts X-Forwarded-* headers from the reverse proxy.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--forwarded-allow-ips", "*", \
     "--log-level", "info"]
