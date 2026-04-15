FROM python:3.11-slim AS base

WORKDIR /app

# System dependencies (uncomment if needed for specific ML packages)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY src/ src/

# Non-root user (security best practice)
RUN useradd -m -u 1000 appuser
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

# Single worker — K8s HPA manages horizontal scaling
# NEVER use --workers N in K8s (causes CPU thrashing under pod limits)
CMD ["uvicorn", "app.main:app", "--host=0.0.0.0", "--port=8000"]
