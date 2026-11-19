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

Only the chunks in the `knowledge` Redis database whose key starts with `doc:`, whose `title` field is
`AutoBot Development Instructions & Project Reference` and whose `source` field is `autobot_docs` (what `--reindex`
writes). A document with the same title from another source is not touched. The backend recomputes that list when
the approval runs and refuses (deleting nothing, auditing the refusal) when more chunks match than the count the
approver saw; re-run `--request` to refresh the count of a pending proposal. Fewer is fine.

## Retry after a partial failure

If the delete fails partway, the failure audit entry records how many chunks were already removed. Run
`--request` again for a new proposal (the count is recomputed), have an admin approve it, then `--reindex`.

## Why the search index is not dropped, and why there is no backup

- The search index is left alone: RediSearch drops a hash's entry when its key is deleted, so no index rebuild is
  needed and KB search keeps working throughout.
- No file backup is taken: CLAUDE.md in the repository is the system of record and the chunks are a rebuildable
  projection of it, so deleting them loses no data. `--reindex` regenerates them.

## Verification

```bash
curl https://<backend-host>:8443/api/knowledge_base/stats | jq
curl "https://<backend-host>:8443/api/knowledge_base/search?q=MANDATORY+WORKFLOW&limit=1"
```
