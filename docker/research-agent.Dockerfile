# Research Agent with Playwright Dockerfile
FROM python:3.10-slim

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    xvfb \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and browsers
RUN pip install --no-cache-dir playwright
RUN playwright install-deps
RUN playwright install chromium firefox webkit

# Copy source code
COPY src/ ./src/
COPY prompts/ ./prompts/

# Create non-root user
RUN useradd -m -u 1000 autobot && \
    chown -R autobot:autobot /app
USER autobot

# Expose port
EXPOSE 8005

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8005/health || exit 1

# Start research agent service with virtual display
CMD ["sh", "-c", "Xvfb :99 -screen 0 1024x768x24 & export DISPLAY=:99 && python -m src.agents.research_agent"]
