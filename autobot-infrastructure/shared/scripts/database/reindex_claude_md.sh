#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# CLAUDE.md Vector Database Re-indexing Script
# Deletes outdated CLAUDE.md chunks and re-indexes current version
# Location: autobot-infrastructure/shared/scripts/database/reindex_claude_md.sh

set -e  # Exit on error

# #13149: this defaulted to the deployed install, so running it from a checkout
# read or wrote the LIVE install instead of this tree. The shared helper resolves
# the root from this file's own location; AUTOBOT_PROJECT_ROOT still overrides.
# shellcheck source=scripts/lib/project_root.sh
source "$(dirname "${BASH_SOURCE[0]}")/../../../../scripts/lib/project_root.sh"

# Load SSOT configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/../lib/ssot-config.sh" || {
    echo "FATAL: ${SCRIPT_DIR}/../lib/ssot-config.sh could not be sourced -- refusing to run on hardcoded config fallbacks (#14172)" >&2
    return 1 2>/dev/null || exit 1
}

# Import root for the inline Python below. PROJECT_ROOT is resolved above from
# this file's own location (database/ -> scripts/ -> shared/ ->
# autobot-infrastructure/ -> repo root, four levels); the knowledge package
# lives under autobot-backend and autobot_shared.* at the repo root. Exported so
# the quoted heredoc below can read it - inside a quoted heredoc ${PROJECT_ROOT}
# is a literal string, never a substitution (#14867).
export PROJECT_ROOT
export PYTHONPATH="${PROJECT_ROOT}/autobot-backend:${PROJECT_ROOT}:${PYTHONPATH:-}"

if [ ! -d "${PROJECT_ROOT}/autobot-backend" ]; then
    echo "ERROR: backend package root not found at ${PROJECT_ROOT}/autobot-backend;" >&2
    echo "       CLAUDE.md was NOT re-indexed (#14867)." >&2
    exit 1
fi

echo "=== CLAUDE.md Vector Database Re-indexing ==="
echo "Starting: $(date)"
echo ""

# Step 1: Create backup directory
echo "Step 1: Creating backup directory..."
mkdir -p ${PROJECT_ROOT}/backups/database/
mkdir -p ${PROJECT_ROOT}/logs/database/

# Step 2: Find and backup CLAUDE.md chunks
echo "Step 2: Finding CLAUDE.md chunks..."
redis-cli -h "${AUTOBOT_REDIS_HOST:-localhost}" --scan --pattern "doc:*" > /tmp/all_docs.txt

# Count CLAUDE.md chunks
claude_count=0
> /tmp/claude_docs_to_delete.txt
while IFS= read -r key; do
    title=$(redis-cli -h "${AUTOBOT_REDIS_HOST:-localhost}" HGET "$key" title 2>/dev/null)
    if [ "$title" = "AutoBot Development Instructions & Project Reference" ]; then
        echo "$key" >> /tmp/claude_docs_to_delete.txt
        claude_count=$((claude_count + 1))
    fi
done < /tmp/all_docs.txt

echo "Found $claude_count CLAUDE.md chunks to delete"
echo ""

# Step 3: Backup chunks
echo "Step 3: Creating backup..."
timestamp=$(date +%Y%m%d_%H%M%S)
backup_file="${PROJECT_ROOT}/backups/database/claude_chunks_backup_$timestamp.json"

echo "[" > "$backup_file"
first=true
backup_count=0
while read key; do
    if [ "$first" = true ]; then
        first=false
    else
        echo "," >> "$backup_file"
    fi
    redis-cli -h "${AUTOBOT_REDIS_HOST:-localhost}" HGETALL "$key" 2>/dev/null | \
    python3 -c "
import sys, json
data = {}
lines = [line.strip() for line in sys.stdin.readlines()]
for i in range(0, len(lines), 2):
    if i+1 < len(lines):
        data[lines[i]] = lines[i+1]
data['redis_key'] = '$key'
print(json.dumps(data, indent=2))
    " >> "$backup_file"
    backup_count=$((backup_count + 1))
    if [ $((backup_count % 20)) -eq 0 ]; then
        echo "  Backed up $backup_count/$claude_count chunks..."
    fi
done < /tmp/claude_docs_to_delete.txt
echo "]" >> "$backup_file"

echo "Backup created: $backup_file"
echo ""

# Step 4: Delete old chunks
echo "Step 4: Deleting $claude_count old CLAUDE.md chunks..."
deleted_count=0
while read key; do
    redis-cli -h "${AUTOBOT_REDIS_HOST:-localhost}" DEL "$key" >/dev/null 2>&1
    deleted_count=$((deleted_count + 1))
    if [ $((deleted_count % 20)) -eq 0 ]; then
        echo "  Deleted $deleted_count/$claude_count chunks..."
    fi
done < /tmp/claude_docs_to_delete.txt

echo "Deleted $deleted_count chunks"
echo ""

# Step 5: Drop and rebuild search index
echo "Step 5: Rebuilding search index..."
redis-cli -h "${AUTOBOT_REDIS_HOST:-localhost}" FT.DROPINDEX llama_index 2>/dev/null && echo "Index dropped successfully" || echo "Index already dropped or doesn't exist"
echo ""

# Step 6: Re-index CLAUDE.md via Python
echo "Step 6: Re-indexing current CLAUDE.md..."
cd ${PROJECT_ROOT}

python3 << 'PYTHON_SCRIPT'
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

# (#14867) This heredoc is quoted, so '${PROJECT_ROOT}' was inserted verbatim
# and every path built from it pointed at a directory that cannot exist. The
# shell exports PROJECT_ROOT instead.
PROJECT_ROOT = os.environ["PROJECT_ROOT"]
sys.path.insert(0, PROJECT_ROOT)

# (#14867) There is no src package. KnowledgeBase is exported by the knowledge
# package under autobot-backend (knowledge/_composed.py).
from knowledge import KnowledgeBase
from llama_index.core import Document

async def reindex_claude_md():
    try:
        kb = KnowledgeBase()
        await kb._ensure_redis_initialized()

        claude_path = Path(PROJECT_ROOT) / "CLAUDE.md"
        if not claude_path.exists():
            # (#14867) This used to return normally, so a re-index that never
            # touched a single document still exited 0.
            print(f"ERROR: CLAUDE.md not found at {claude_path}!", file=sys.stderr)
            return 1

        content = claude_path.read_text(encoding='utf-8')
        print(f"Read CLAUDE.md: {len(content)} bytes")

        metadata = {
            "title": "AutoBot Development Instructions & Project Reference",
            "source": "autobot_docs",
            "category": "autobot_documentation",
            "file_path": str(claude_path),
            "file_size": len(content),
            "indexed_at": datetime.now().isoformat()
        }

        result = await kb.add_document(
            content=content,
            metadata=metadata,
            doc_id=None
        )

        print(f"Re-indexing result: {result}")

        stats = await kb.get_stats()
        print(f"New document count: {stats.get('total_documents', 0)}")
        print(f"Indexed documents: {stats.get('indexed_documents', 0)}")
        return 0

    except Exception as e:
        # (#14867) The traceback used to be printed and then discarded, leaving
        # the script to run its "verification" steps and exit 0.
        print(f"ERROR during re-indexing: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

sys.exit(asyncio.run(reindex_claude_md()))
PYTHON_SCRIPT

echo ""

# Step 7: Verification
echo "Step 7: Verification"
echo "===================="
echo ""

echo "Checking new stats..."
curl -s "http://${AUTOBOT_BACKEND_HOST:-localhost}:${AUTOBOT_BACKEND_PORT:-8001}/api/knowledge_base/stats" 2>/dev/null | jq '{total_documents, indexed_documents, total_facts}' 2>/dev/null || echo "API not responding or jq not available"

echo ""
echo "Testing search for new workflow content..."
curl -s "http://${AUTOBOT_BACKEND_HOST:-localhost}:${AUTOBOT_BACKEND_PORT:-8001}/api/knowledge_base/search?q=MANDATORY+WORKFLOW&limit=1" 2>/dev/null | \
  jq -r '.results[0].content' 2>/dev/null | head -10 || echo "Search test failed or jq not available"

echo ""
echo "Checking new CLAUDE.md chunk timestamps..."
redis-cli -h "${AUTOBOT_REDIS_HOST:-localhost}" --scan --pattern "doc:*" 2>/dev/null | head -50 | \
while IFS= read -r key; do
    title=$(redis-cli -h "${AUTOBOT_REDIS_HOST:-localhost}" HGET "$key" title 2>/dev/null)
    if [ "$title" = "AutoBot Development Instructions & Project Reference" ]; then
        stored_at=$(redis-cli -h "${AUTOBOT_REDIS_HOST:-localhost}" HGET "$key" stored_at 2>/dev/null)
        echo "$key : $stored_at"
    fi
done | head -5

echo ""
echo "=== Re-indexing Complete ==="
echo "Finished: $(date)"
echo "Backup saved to: $backup_file"
echo ""
echo "Summary:"
echo "  - Deleted: $deleted_count old chunks"
echo "  - Backup: $backup_file"
echo "  - Status: Re-indexing completed (verify above)"
echo ""
echo "Next steps:"
echo "  1. Verify search returns new workflow content"
echo "  2. Check knowledge base stats show updated count"
echo "  3. Test chat system retrieval of workflow guidelines"
