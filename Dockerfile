# AutoBot Production Dockerfile
# Multi-stage build for optimized production deployment

# Build stage
FROM node:18-alpine AS frontend-builder

WORKDIR /app/frontend
COPY autobot-vue/package*.json ./
RUN npm ci --only=production

COPY autobot-vue/ ./
RUN npm run build

# Python backend stage
FROM python:3.11-slim AS backend-builder

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim AS production

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    redis-tools \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r autobot && useradd -r -g autobot autobot

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=backend-builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=backend-builder /usr/local/bin/ /usr/local/bin/

# Copy frontend build
COPY --from=frontend-builder /app/frontend/dist/ ./static/

# Copy backend source
COPY src/ ./src/
COPY backend/ ./backend/
COPY main.py ./
COPY config/ ./config/
COPY prompts/ ./prompts/

# Create required directories
RUN mkdir -p data logs reports/monitoring && \
    chown -R autobot:autobot /app

# Security: Switch to non-root user
USER autobot

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/api/system/health || exit 1

# Expose ports
EXPOSE 8001

# Environment variables
ENV PYTHONPATH=/app
ENV AUTOBOT_ENVIRONMENT=production
ENV AUTOBOT_LOG_LEVEL=INFO

# Start command
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
