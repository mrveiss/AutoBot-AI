#!/bin/bash
# Backup Ollama models before using shared model configuration

set -e

BACKUP_DIR="$HOME/ollama-backups/$(date +%Y%m%d_%H%M%S)"
OLLAMA_DIR="$HOME/.ollama"

echo "🔒 Backing up Ollama models..."

if [[ -d "$OLLAMA_DIR/models" ]]; then
    mkdir -p "$BACKUP_DIR"

    # Calculate size
    SIZE=$(du -sh "$OLLAMA_DIR/models" | cut -f1)
    echo "📦 Model directory size: $SIZE"

    # Create backup
    echo "📂 Creating backup in: $BACKUP_DIR"
    cp -r "$OLLAMA_DIR/models" "$BACKUP_DIR/"

    # Create manifest
    echo "📝 Creating model manifest..."
    ollama list > "$BACKUP_DIR/model_manifest.txt" 2>/dev/null || true

    echo "✅ Backup complete!"
    echo "   Location: $BACKUP_DIR"
    echo ""
    echo "🔧 To restore:"
    echo "   rm -rf $OLLAMA_DIR/models"
    echo "   cp -r $BACKUP_DIR/models $OLLAMA_DIR/"
else
    echo "⚠️  No Ollama models directory found at $OLLAMA_DIR/models"
fi
