# DEPRECATED (Phase5) — prefer docker/Dockerfile.runtime on Active compose.
# Deprecation Date: 2026-07-25 | Archive ETA: 2027-07-25
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

COPY runtime/requirements.txt ./runtime/requirements.txt
RUN pip install --no-cache-dir -r runtime/requirements.txt

COPY runtime/ ./runtime/
COPY migrations/ ./migrations/

EXPOSE 8020

CMD ["uvicorn", "runtime.main:app", "--host", "0.0.0.0", "--port", "8020"]
