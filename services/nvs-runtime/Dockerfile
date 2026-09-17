# SensOS NVS Runtime — agents, sessions, MCP
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# meaning-mapper, meaning-space-runtime, and categorical-lift-engine are
# private, unpublished (not on PyPI) sibling repos supplied as Compose
# `additional_contexts` (see ../../compose/docker-compose.yml's
# `nvs-runtime` service) -- not vendored into this repo, not fetched from
# any index. Only pyproject.toml + src/ are copied (not each repo's full
# tree: no .venv/, tests/, or experiments/), matching each repo's own
# `[tool.setuptools.packages.find] include = ["<pkg>*"]` layout.
COPY --from=meaning-mapper pyproject.toml /deps/meaning-mapper/pyproject.toml
COPY --from=meaning-mapper src /deps/meaning-mapper/src
COPY --from=meaning-space-runtime pyproject.toml /deps/meaning-space-runtime/pyproject.toml
COPY --from=meaning-space-runtime src /deps/meaning-space-runtime/src
COPY --from=categorical-lift-engine pyproject.toml /deps/categorical-lift-engine/pyproject.toml
COPY --from=categorical-lift-engine src /deps/categorical-lift-engine/src
RUN pip install --no-cache-dir \
    /deps/meaning-mapper \
    /deps/meaning-space-runtime \
    /deps/categorical-lift-engine

COPY runtime/ ./runtime/
COPY migrations/ ./migrations/
COPY config/ ./config/

EXPOSE 8020

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8020/health || exit 1

CMD ["uvicorn", "runtime.main:app", "--host", "0.0.0.0", "--port", "8020"]
