# CLAUDE.md Re-indexing Quick Start

The knowledge base keeps CLAUDE.md as chunks. When the file changes, the stale chunks are deleted and the current
file is indexed again. The deletion is a data deletion, so the script only **proposes** it: an admin approves it
in the Approvals inbox, the backend deletes exactly the stale chunks and writes a durable audit entry, and only
then does the script re-index (#21383, #17038). The script deletes nothing itself.

## Steps

```bash
S=autobot-infrastructure/shared/scripts/database/reindex_claude_md.sh
bash "$S"              # 1. preview: how many stale chunks the deletion would remove (deletes nothing)
bash "$S" --request    # 2. raise the approval proposal (deletes nothing)
# 3. an admin approves "Delete the stale CLAUDE.md knowledge chunks, then re-index" in the Approvals inbox
bash "$S" --reindex    # 4. index the current CLAUDE.md; it refuses while stale chunks remain
```

## What the approval deletes

Only the chunks in the `knowledge` Redis database whose key starts with `doc:` and whose `title` field is
`AutoBot Development Instructions & Project Reference`. The backend recomputes that list when the approval runs;
nothing else is touched, and the search index is not dropped. CLAUDE.md is the source, so no chunk backup is
needed to restore it.

## Verification

```bash
curl https://<backend-host>:8443/api/knowledge_base/stats | jq
curl "https://<backend-host>:8443/api/knowledge_base/search?q=MANDATORY+WORKFLOW&limit=1"
```
