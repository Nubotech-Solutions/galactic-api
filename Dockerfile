# Galactic Logistics API — demo target for NTS-Buddy MCP integration.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py .
COPY site ./site

# Run as non-root.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Cloud Run injects PORT; default to 8080 for local runs.
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
