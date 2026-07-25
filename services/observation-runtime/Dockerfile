# SensOS Observation Runtime — production image
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml README.md ./
COPY sensos ./sensos

RUN pip install --upgrade pip \
 && pip install --prefix=/install .


FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="SensOS Observation Runtime" \
      org.opencontainers.image.description="SensOS Observation-Centered Runtime" \
      org.opencontainers.image.version="0.3.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    SENSOS_HOST=0.0.0.0 \
    SENSOS_PORT=8090 \
    SENSOS_RUNTIME_BACKEND=mock \
    SENSOS_LOG_LEVEL=info

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

RUN groupadd --gid 1002 sensos \
 && useradd --uid 1002 --gid sensos --no-create-home --shell /bin/false sensos

WORKDIR /app
COPY sensos ./sensos
COPY pyproject.toml README.md ./

RUN mkdir -p /app/logs && chown -R sensos:sensos /app

USER sensos

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${SENSOS_PORT}/health || exit 1

CMD ["sh", "-c", "uvicorn sensos.api.app:create_app --factory --host ${SENSOS_HOST} --port ${SENSOS_PORT} --log-level ${SENSOS_LOG_LEVEL}"]
