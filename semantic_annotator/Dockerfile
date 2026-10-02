# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so they're cached independently of source changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY src ./src
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM python:3.12-slim AS runtime

RUN useradd --create-home --shell /usr/sbin/nologin annotator
WORKDIR /app
COPY --from=base --chown=annotator:annotator /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER annotator

ENTRYPOINT ["semantic-annotator"]
