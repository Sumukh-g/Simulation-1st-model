# Base image for every GSIP Python service.
#
# Build context is the repository root, because the services import each other
# and the domain packs. Which service an instance becomes is decided by the
# command in docker-compose, not by the image.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Build tooling for the few packages without wheels for this platform. Removed
# in the same layer so it never reaches the final image.
COPY requirements-docker.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && pip install --upgrade pip \
    && pip install -r requirements-docker.txt \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

# Application code. Copied after dependencies so a code change does not
# invalidate the dependency layer.
COPY core/ ./core/
COPY libs/ ./libs/
COPY compute/ ./compute/
COPY services/ ./services/
COPY scripts/ ./scripts/
COPY configs/ ./configs/
COPY seed/ ./seed/
COPY pyproject.toml ./

# Runs as an unprivileged user. Domain packs are user-authored code, so nothing
# in this image should ever execute as root.
RUN useradd --create-home --uid 10001 gsip \
    && chown -R gsip:gsip /app
USER gsip

EXPOSE 8000

CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
