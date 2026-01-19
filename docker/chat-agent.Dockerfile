# Chat Agent Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY prompts/ ./prompts/

# Create non-root user
RUN useradd -m -u 1000 autobot && \
    chown -R autobot:autobot /app
USER autobot

# Expose port
EXPOSE 8004

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8004/health || exit 1

# Start chat agent service
CMD ["python", "-m", "src.agents.chat_agent"]
