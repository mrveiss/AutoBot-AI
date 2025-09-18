#!/bin/bash
# AI Stack container startup script
# Ensures prompts and knowledge base are properly initialized

set -e

echo "🚀 Starting AutoBot AI Stack..."

# Check if prompts are available
if [ ! -d "/app/prompts" ] || [ -z "$(ls -A /app/prompts 2>/dev/null)" ]; then
    echo "❌ ERROR: Prompts directory is missing or empty!"
    echo "   Please run: ./scripts/setup_docker_volumes.sh"
    exit 1
fi

echo "✅ Prompts directory found"

# Check if knowledge base is available
if [ ! -d "/app/knowledge_base" ] || [ ! -f "/app/knowledge_base/index.json" ]; then
    echo "⚠️  WARNING: Knowledge base not properly initialized"
    echo "   Run: ./scripts/setup_docker_volumes.sh to set up knowledge base"
else
    echo "✅ Knowledge base directory found"

    # Check if knowledge base needs to be loaded into vector DB
    if [ -f "/app/knowledge_base/load_to_db.py" ] && [ "${LOAD_KNOWLEDGE_BASE:-true}" = "true" ]; then
        echo "📚 Loading knowledge base into vector database..."
        python /app/knowledge_base/load_to_db.py || {
            echo "⚠️  Warning: Failed to load knowledge base, continuing anyway..."
        }
    fi
fi

# Initialize prompt manager cache
echo "📝 Initializing prompt manager..."
python -c "
import sys
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/src')

try:
    from src.prompt_manager import PromptManager
    pm = PromptManager()
    print(f'✅ Loaded {len(pm.list_prompts())} prompts')
except Exception as e:
    print(f'⚠️  Warning: Failed to initialize prompt manager: {e}')
"

# Start the AI server
echo "🌐 Starting AI API server..."
exec python /app/ai_container_main.py
