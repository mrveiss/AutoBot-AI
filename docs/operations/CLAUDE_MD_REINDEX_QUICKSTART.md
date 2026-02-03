# CLAUDE.md Re-indexing Quick Start

## 🚨 Problem
CLAUDE.md vector database is **15+ hours OUT OF SYNC**
- Current file: 2025-10-05 09:38:36 (TODAY)
- Vector DB: 2025-10-04 18:48:15 (YESTERDAY)
- **120 outdated chunks** need updating

## ⚡ Quick Solution

### One-Command Fix
```bash
bash /home/kali/Desktop/AutoBot/scripts/database/reindex_claude_md.sh
```

**Time:** ~10 minutes | **Risk:** Low (auto-backup)

## 📋 What It Does
1. Backs up 120 old chunks to `backups/database/`
2. Deletes outdated CLAUDE.md chunks from Redis
3. Rebuilds search index
4. Re-indexes current CLAUDE.md (43.8 KB)
5. Verifies new chunks created

## ✅ Verification
```bash
# Check stats
curl http://172.16.168.20:8001/api/knowledge_base/stats | jq

# Test search for new content
curl "http://172.16.168.20:8001/api/knowledge_base/search?q=MANDATORY+WORKFLOW&limit=1"
```

## 📚 Full Documentation
- **Complete Report:** `docs/database/CLAUDE_MD_REINDEX_REPORT.md`
- **Summary:** `docs/database/VECTOR_DB_RESEARCH_SUMMARY.md`

---
*Run the script above to fix immediately*
