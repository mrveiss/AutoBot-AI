# Knowledge Base Service Dockerfile
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

# Install additional dependencies for knowledge base
RUN pip install --no-cache-dir \
    chromadb \
    sentence-transformers \
    faiss-cpu \
    tiktoken

# Copy source code
COPY src/ ./src/
COPY data/ ./data/
COPY prompts/ ./prompts/

# Create non-root user
RUN useradd -m -u 1000 autobot && \
    chown -R autobot:autobot /app
USER autobot

# Expose port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Start knowledge base service
CMD ["python", "-m", "src.knowledge_base_service"]
