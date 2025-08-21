#!/bin/bash
# Setup centralized Docker volumes for AutoBot
# This script creates the proper directory structure and copies necessary files

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VOLUMES_DIR="$PROJECT_ROOT/docker/volumes"

echo "🚀 Setting up centralized Docker volumes for AutoBot..."

# Create volume directories
echo "📁 Creating volume directories..."
mkdir -p "$VOLUMES_DIR"/{prompts,knowledge_base,models,config}

# Copy prompts to centralized location
echo "📝 Copying prompts to centralized location..."
if [ -d "$PROJECT_ROOT/prompts" ]; then
    cp -r "$PROJECT_ROOT/prompts/"* "$VOLUMES_DIR/prompts/" 2>/dev/null || true
    echo "   ✅ Prompts copied successfully"
else
    echo "   ⚠️  No prompts directory found at $PROJECT_ROOT/prompts"
fi

# Set up knowledge base with system documentation
echo "📚 Setting up knowledge base..."
mkdir -p "$VOLUMES_DIR/knowledge_base"/{system_docs,user_guides,api_docs,architecture}

# Copy documentation to knowledge base
echo "   📄 Copying system documentation..."
if [ -d "$PROJECT_ROOT/docs" ]; then
    # Copy specific documentation categories
    [ -d "$PROJECT_ROOT/docs/api" ] && cp -r "$PROJECT_ROOT/docs/api/"* "$VOLUMES_DIR/knowledge_base/api_docs/" 2>/dev/null || true
    [ -d "$PROJECT_ROOT/docs/architecture" ] && cp -r "$PROJECT_ROOT/docs/architecture/"* "$VOLUMES_DIR/knowledge_base/architecture/" 2>/dev/null || true
    [ -d "$PROJECT_ROOT/docs/agents" ] && cp -r "$PROJECT_ROOT/docs/agents/"* "$VOLUMES_DIR/knowledge_base/system_docs/" 2>/dev/null || true
    [ -d "$PROJECT_ROOT/docs/testing" ] && cp -r "$PROJECT_ROOT/docs/testing/"* "$VOLUMES_DIR/knowledge_base/system_docs/" 2>/dev/null || true

    # Copy main documentation files
    cp "$PROJECT_ROOT/docs/"*.md "$VOLUMES_DIR/knowledge_base/system_docs/" 2>/dev/null || true

    # Copy README files
    cp "$PROJECT_ROOT/README.md" "$VOLUMES_DIR/knowledge_base/user_guides/README.md" 2>/dev/null || true
    cp "$PROJECT_ROOT/docs/README.md" "$VOLUMES_DIR/knowledge_base/system_docs/docs_index.md" 2>/dev/null || true

    echo "   ✅ Documentation copied to knowledge base"
else
    echo "   ⚠️  No docs directory found"
fi

# Create knowledge base index
echo "   📑 Creating knowledge base index..."
cat > "$VOLUMES_DIR/knowledge_base/index.json" << 'EOF'
{
  "version": "1.0",
  "last_updated": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "categories": {
    "system_docs": {
      "name": "System Documentation",
      "description": "Core system documentation including agent guides, testing frameworks, and implementation details",
      "path": "/app/knowledge_base/system_docs"
    },
    "user_guides": {
      "name": "User Guides",
      "description": "End-user documentation and tutorials",
      "path": "/app/knowledge_base/user_guides"
    },
    "api_docs": {
      "name": "API Documentation",
      "description": "API endpoints, request/response formats, and integration guides",
      "path": "/app/knowledge_base/api_docs"
    },
    "architecture": {
      "name": "Architecture Documents",
      "description": "System architecture, design patterns, and technical decisions",
      "path": "/app/knowledge_base/architecture"
    }
  },
  "auto_index_patterns": [
    "*.md",
    "*.txt",
    "*.json",
    "*.yaml",
    "*.yml"
  ]
}
EOF

# Copy configuration files
echo "⚙️  Setting up shared configuration..."
mkdir -p "$VOLUMES_DIR/config"
if [ -d "$PROJECT_ROOT/config" ]; then
    cp -r "$PROJECT_ROOT/config/"* "$VOLUMES_DIR/config/" 2>/dev/null || true
    echo "   ✅ Configuration files copied"
fi

# Create models directory structure
echo "🤖 Setting up models directory..."
mkdir -p "$VOLUMES_DIR/models"/{embedding,llm,specialized}

# Set proper permissions
echo "🔐 Setting permissions..."
# Make prompts and knowledge base read-only for containers
chmod -R 755 "$VOLUMES_DIR/prompts" "$VOLUMES_DIR/knowledge_base"
# Models and config can be writable
chmod -R 755 "$VOLUMES_DIR/models" "$VOLUMES_DIR/config"

# Create docker-compose override for volumes
echo "🐳 Creating docker-compose volume override..."
cat > "$PROJECT_ROOT/docker-compose.volumes.yml" << 'EOF'
# Docker Compose override for centralized volumes
# Use with: docker-compose -f docker-compose.yml -f docker-compose.volumes.yml up

version: '3.8'

x-shared-volumes: &shared-volumes
  - ./docker/volumes/prompts:/app/prompts:ro
  - ./docker/volumes/knowledge_base:/app/knowledge_base:ro
  - ./docker/volumes/models:/app/models
  - ./docker/volumes/config:/app/config:ro

services:
  autobot-backend:
    volumes:
      <<: *shared-volumes
      - ./data:/app/data
      - ./logs:/app/logs
      - ./reports:/app/reports

  autobot-ai-stack:
    volumes:
      <<: *shared-volumes
      - autobot_ai_data:/app/data
      - autobot_ai_logs:/app/logs

  autobot-npu-worker:
    volumes:
      <<: *shared-volumes
      - autobot_npu_logs:/app/logs
EOF

# Update hybrid compose file
echo "🔄 Updating hybrid compose file..."
# Create a backup first
cp "$PROJECT_ROOT/docker/compose/docker-compose.hybrid.yml" "$PROJECT_ROOT/docker/compose/docker-compose.hybrid.yml.backup"

# Create knowledge base loader script
echo "📥 Creating knowledge base loader..."
cat > "$VOLUMES_DIR/knowledge_base/load_to_db.py" << 'EOF'
#!/usr/bin/env python3
"""
Load documentation into AutoBot knowledge base
This script indexes all documentation for vector search and RAG capabilities
"""

import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict

async def load_documents_to_knowledge_base(kb_path: str = "/app/knowledge_base"):
    """Load all documents from knowledge base directory into vector DB"""

    # Import after environment is set up
    from src.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()

    # Load index
    index_path = Path(kb_path) / "index.json"
    if index_path.exists():
        with open(index_path) as f:
            index = json.load(f)
    else:
        print(f"Warning: No index.json found at {index_path}")
        index = {"categories": {}}

    documents_loaded = 0

    # Process each category
    for category_id, category_info in index.get("categories", {}).items():
        category_path = Path(kb_path) / category_id
        if not category_path.exists():
            continue

        print(f"\n📁 Processing category: {category_info['name']}")

        # Find all documents
        for pattern in index.get("auto_index_patterns", ["*.md", "*.txt"]):
            for doc_path in category_path.rglob(pattern):
                if doc_path.is_file():
                    try:
                        print(f"  📄 Loading: {doc_path.name}")

                        # Read document content
                        content = doc_path.read_text(encoding='utf-8')

                        # Create metadata
                        metadata = {
                            "source": str(doc_path),
                            "category": category_id,
                            "category_name": category_info['name'],
                            "filename": doc_path.name,
                            "file_type": doc_path.suffix
                        }

                        # Add to knowledge base
                        await kb.add_document(
                            content=content,
                            metadata=metadata,
                            doc_id=f"{category_id}/{doc_path.name}"
                        )

                        documents_loaded += 1

                    except Exception as e:
                        print(f"  ❌ Error loading {doc_path}: {e}")

    print(f"\n✅ Loaded {documents_loaded} documents into knowledge base")

    # Create search index
    print("\n🔍 Creating search index...")
    await kb.create_search_index()

    print("\n🎉 Knowledge base setup complete!")

if __name__ == "__main__":
    # Set up environment
    import sys
    sys.path.insert(0, '/app')
    sys.path.insert(0, '/app/src')

    # Run loader
    asyncio.run(load_documents_to_knowledge_base())
EOF

chmod +x "$VOLUMES_DIR/knowledge_base/load_to_db.py"

echo ""
echo "✅ Docker volumes setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Use docker-compose with volume override:"
echo "   docker-compose -f docker-compose.yml -f docker-compose.volumes.yml up"
echo ""
echo "2. Or for hybrid deployment:"
echo "   docker-compose -f docker/compose/docker-compose.hybrid.yml up"
echo ""
echo "3. To load documentation into knowledge base, run inside container:"
echo "   docker exec -it autobot-ai-stack python /app/knowledge_base/load_to_db.py"
echo ""
echo "📁 Volume structure created at: $VOLUMES_DIR"
