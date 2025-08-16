# RAG Agent Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install RAG-specific dependencies
RUN pip install --no-cache-dir \
    langchain \
    llama-index \
    transformers

# Copy source code
COPY src/ ./src/
COPY prompts/ ./prompts/

# Create non-root user
RUN useradd -m -u 1000 autobot && \
    chown -R autobot:autobot /app
USER autobot

# Expose port
EXPOSE 8003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

# Start RAG agent service
CMD ["python", "-m", "src.agents.rag_agent"]
