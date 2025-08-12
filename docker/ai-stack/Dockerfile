# AutoBot AI Stack Container
# Contains LangChain + LlamaIndex + Vector DB to resolve dependency conflicts

FROM python:3.10.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create directories
RUN mkdir -p /app/src /app/data /app/models /app/logs

# Copy requirements for AI stack
COPY docker/ai-stack/requirements-ai.txt /app/
RUN pip install --no-cache-dir -r requirements-ai.txt

# Copy AI-related source code
COPY src/agents/ /app/src/agents/
COPY src/config.py /app/src/
COPY src/llm_interface.py /app/src/
COPY src/knowledge_base.py /app/src/
COPY src/autobot_types.py /app/src/
COPY src/utils/ /app/src/utils/
COPY src/workflow_classifier.py /app/src/
COPY src/chat_history_manager.py /app/src/

# Copy AI container-specific code
COPY docker/ai-stack/ai_container_main.py /app/
COPY docker/ai-stack/ai_api_server.py /app/

# Set Python path
ENV PYTHONPATH=/app

# Expose port for AI services
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the AI service
CMD ["python", "ai_container_main.py"]