# Knowledge Base Maintenance Guide

## Overview

The AutoBot knowledge base contains all project documentation and enables semantic search across the codebase. This document outlines maintenance procedures and answers critical questions about keeping the knowledge base current.

## Current Knowledge Base Status

- **Total Facts**: 35+ documentation files indexed
- **Storage Type**: Fact-based storage (fallback from vector store)
- **Search Capability**: Both simple keywords and natural language queries
- **Coverage**: README, CLAUDE.md, docs/*, prompts/*, and root markdown files

## Critical Questions & Solutions

### 1. What happens when documentation gets updated?

**Current Behavior**: The knowledge base does NOT automatically update when documentation files change. This creates a critical maintenance gap.

**Problems**:
- New documentation changes won't be searchable until manually re-indexed
- Outdated information may persist in search results
- Users may get incorrect answers from stale documentation

**Solutions Needed**:

#### A. Automatic Documentation Sync (Recommended)
```python
# File: src/knowledge_base_sync.py
class KnowledgeBaseSync:
    def __init__(self):
        self.watched_paths = ["docs/", "*.md", "prompts/"]
        self.kb = KnowledgeBase()

    async def sync_documentation(self):
        """Automatically sync documentation changes to KB"""
        for doc_file in self.get_modified_docs():
            await self.update_document_in_kb(doc_file)

    def get_modified_docs(self):
        """Find docs modified since last sync"""
        # Check file modification times vs last sync timestamp
        pass
```

#### B. Git Hook Integration
```bash
# .git/hooks/post-merge
#!/bin/bash
# Auto-sync KB after git operations
python scripts/sync_kb_docs.py

# .git/hooks/post-commit
#!/bin/bash
# Sync KB after commits that modify docs
if git diff --name-only HEAD~1 | grep -E '\.(md|txt)$'; then
    python scripts/sync_kb_docs.py
fi
```

#### C. Scheduled Sync Task
```python
# Add to main application loop
async def scheduled_kb_sync():
    """Run every 6 hours to sync documentation"""
    while True:
        try:
            await sync_documentation_changes()
            logging.info("KB documentation sync completed")
        except Exception as e:
            logging.error(f"KB sync failed: {e}")
        await asyncio.sleep(6 * 3600)  # 6 hours
```

### 2. How to detect documentation changes?

**Current Gap**: No change detection mechanism exists.

**Detection Strategies**:

#### File Modification Time Tracking
```python
import os
from datetime import datetime

class DocumentChangeDetector:
    def __init__(self, sync_state_file="data/kb_sync_state.json"):
        self.sync_state_file = sync_state_file
        self.last_sync_times = self.load_sync_state()

    def get_modified_files(self, watch_patterns):
        modified_files = []
        for pattern in watch_patterns:
            for file_path in glob.glob(pattern, recursive=True):
                file_mtime = os.path.getmtime(file_path)
                last_sync = self.last_sync_times.get(file_path, 0)

                if file_mtime > last_sync:
                    modified_files.append(file_path)

        return modified_files
```

#### Git-based Change Detection
```bash
# Detect changed docs since last KB sync
git log --since="2025-01-01" --name-only --pretty=format: -- "*.md" "docs/" | sort -u
```

### 3. Knowledge Base Update Procedures

#### Manual Update (Current Method)
```bash
# Re-run population script
python scripts/direct_kb_populate.py

# Or use API approach
python scripts/fix_search.py
```

#### Automated Update Workflow
```python
async def update_knowledge_base():
    """Complete KB update workflow"""

    # 1. Detect changed files
    detector = DocumentChangeDetector()
    changed_files = detector.get_modified_files([
        "docs/**/*.md", "*.md", "prompts/**/*.md"
    ])

    if not changed_files:
        return "No changes detected"

    # 2. Remove outdated entries
    kb = KnowledgeBase()
    for file_path in changed_files:
        await kb.remove_document_by_path(file_path)

    # 3. Add updated documents
    success_count = 0
    for file_path in changed_files:
        result = await kb.add_file(
            file_path=file_path,
            file_type="txt",
            metadata={"source": "updated-docs", "sync_time": datetime.now().isoformat()}
        )
        if result["status"] == "success":
            success_count += 1

    # 4. Update sync state
    detector.update_sync_state(changed_files)

    return f"Updated {success_count}/{len(changed_files)} documents"
```

## Implementation Priority

### Phase 1: Immediate (Manual Process)
1. **Document Current State**: ✅ This document
2. **Create sync script**: Manual re-sync when docs change
3. **Add monitoring**: Log when KB becomes stale

### Phase 2: Semi-Automatic (Hooks)
1. **Git hooks**: Auto-sync after commits
2. **API endpoint**: `/api/knowledge_base/sync` for manual triggers
3. **Admin interface**: Show KB freshness status

### Phase 3: Fully Automatic (Background Process)
1. **File watchers**: Real-time sync on file changes
2. **Scheduled sync**: Regular background updates
3. **Conflict resolution**: Handle concurrent updates

## Recommended Immediate Actions

### 1. Create Sync Script
```python
# scripts/sync_kb_docs.py
#!/usr/bin/env python3
"""Sync documentation changes to knowledge base"""

import os
import sys
import asyncio
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge_base import KnowledgeBase

async def sync_docs():
    """Re-sync all documentation to ensure KB is current"""

    print("=== Knowledge Base Documentation Sync ===")

    # Clear existing project docs
    kb = KnowledgeBase()
    await kb.ainit()

    # Get all current facts
    all_facts = await kb.get_all_facts()
    removed_count = 0

    # Remove old project documentation facts
    for fact in all_facts:
        metadata = fact.get("metadata", {})
        if metadata.get("source") in ["project-docs", "project-documentation"]:
            await kb.delete_fact(fact["id"])
            removed_count += 1

    print(f"Removed {removed_count} outdated documentation entries")

    # Re-add all current documentation
    from scripts.direct_kb_populate import populate_directly
    success = await populate_directly()

    if success:
        # Save sync timestamp
        sync_data = {
            "last_sync": datetime.now().isoformat(),
            "documents_synced": "all",
            "method": "full-resync"
        }

        with open("data/kb_sync_state.json", "w") as f:
            json.dump(sync_data, f, indent=2)

        print("✅ Knowledge base documentation sync completed")
        return True
    else:
        print("❌ Knowledge base documentation sync failed")
        return False

if __name__ == "__main__":
    success = asyncio.run(sync_docs())
    sys.exit(0 if success else 1)
```

### 2. Add KB Status Endpoint
```python
# autobot-user-backend/api/knowledge_base.py - add new endpoint
@router.get("/sync-status")
async def get_kb_sync_status():
    """Get knowledge base synchronization status"""
    try:
        # Check if sync state file exists
        sync_state_path = "data/kb_sync_state.json"
        if os.path.exists(sync_state_path):
            with open(sync_state_path, "r") as f:
                sync_data = json.load(f)

            last_sync = datetime.fromisoformat(sync_data["last_sync"])
            hours_since_sync = (datetime.now() - last_sync).total_seconds() / 3600

            return {
                "last_sync": sync_data["last_sync"],
                "hours_since_sync": round(hours_since_sync, 1),
                "status": "fresh" if hours_since_sync < 24 else "stale",
                "documents_synced": sync_data.get("documents_synced", "unknown"),
                "sync_method": sync_data.get("method", "manual")
            }
        else:
            return {
                "status": "never_synced",
                "message": "Knowledge base has never been synced"
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get sync status: {e}")

@router.post("/sync")
async def sync_knowledge_base():
    """Manually trigger knowledge base documentation sync"""
    try:
        # Run sync script
        import subprocess
        result = subprocess.run([
            sys.executable, "scripts/sync_kb_docs.py"
        ], capture_output=True, text=True, timeout=300)

        if result.returncode == 0:
            return {"status": "success", "message": "KB sync completed"}
        else:
            return {"status": "error", "message": f"Sync failed: {result.stderr}"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync operation failed: {e}")
```

### 3. Update CLAUDE.md Instructions
Add to the AutoBot CLAUDE.md file:

```markdown
## Knowledge Base Maintenance

### When Documentation Changes
**CRITICAL**: The knowledge base does NOT automatically update when documentation files change.

After modifying any documentation files (*.md), you MUST run:
```bash
python scripts/sync_kb_docs.py
```

### KB Sync Status
Check if KB is current:
```bash
curl http://localhost:8001/api/knowledge_base/sync-status
```

### Manual Sync Trigger
Force KB refresh via API:
```bash
curl -X POST http://localhost:8001/api/knowledge_base/sync
```
```

## Monitoring and Alerts

### KB Freshness Check
```python
def check_kb_freshness():
    """Alert if KB is stale"""
    sync_status = get_kb_sync_status()
    if sync_status["hours_since_sync"] > 48:
        logging.warning(f"Knowledge base is stale: {sync_status['hours_since_sync']} hours since last sync")
        return False
    return True
```

### Dashboard Integration
Add KB sync status to system health dashboard:
- ✅ Fresh (< 24 hours)
- ⚠️ Stale (24-48 hours)
- ❌ Very stale (> 48 hours)
- ⛔ Never synced

## Best Practices

1. **Sync after major documentation changes**
2. **Regular weekly syncs** even if no changes detected
3. **Test search after sync** to verify functionality
4. **Monitor sync failures** and fix promptly
5. **Version sync state** for rollback capability

## Future Enhancements

1. **Incremental sync**: Only update changed files
2. **Conflict detection**: Handle concurrent documentation edits
3. **Multi-source KB**: Integrate external documentation
4. **Semantic versioning**: Track KB schema versions
5. **A/B testing**: Compare old vs new KB versions

---

**Next Steps**: Implement sync script and API endpoints to address the critical documentation update gap.
