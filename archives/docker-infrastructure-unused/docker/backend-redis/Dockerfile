FROM python:3.10-slim

# Install Redis server and required system dependencies
RUN apt-get update && apt-get install -y \
    redis-server \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install async architecture dependencies
RUN pip install --no-cache-dir aioredis pydantic-settings tenacity aiofiles

# Copy application code
COPY . .

# Create supervisor configuration
COPY docker/backend-redis/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create Redis configuration
COPY docker/backend-redis/redis.conf /etc/redis/redis.conf

# Expose ports
EXPOSE 6379 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/api/system/health || exit 1

# Start supervisor to manage both Redis and backend
CMD ["/usr/bin/supervisord", "-n"]