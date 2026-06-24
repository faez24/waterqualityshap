# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile – Water Quality SHAP API
# Base image: python:3.11-slim
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Metadata
LABEL maintainer="Faiz"
LABEL description="FastAPI + SHAP Water Quality Analysis"

# Env vars
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Working directory di dalam container
WORKDIR /workspace

# Install dependencies OS yang diperlukan
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements lebih dulu (layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy seluruh project
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Jalankan Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
