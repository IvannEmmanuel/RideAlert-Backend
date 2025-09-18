FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for scientific stack & pyproj (PROJ / GDAL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    proj-bin proj-data libproj-dev \
    gdal-bin \
    && rm -rf /var/lib/apt/lists/*

# Faster pip & no cache
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Copy only requirements first for better layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Ensure model directory exists (models are downloaded lazily by code)
RUN mkdir -p app/ml

# Default port for Koyeb (falls back to 8000 locally)
ENV PORT=8080
EXPOSE 8080

# Optional: basic container health check hitting lightweight status route
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD curl -fsSL http://127.0.0.1:${PORT:-8080}/predict/status || exit 1

# Start uvicorn (single worker since background model loader + WebSockets)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --timeout-keep-alive 30"]
