# Redis Memory Graph Quick Reference

**Database:** DB 0 @ 172.16.168.23:6379
**Key Prefixes:** `memory:graph:entity:*`, `memory:graph:relations:*`
**Indexes:** `memory_graph_entity_idx`, `memory_graph_fulltext_idx`

---

## 🚀 Quick Commands

### Initialization

```bash
# Full setup (first time)
python scripts/utilities/init_memory_graph_redis.py --migrate --validate --benchmark

# Create indexes only
python scripts/utilities/init_memory_graph_redis.py

# Validate existing setup
python scripts/utilities/init_memory_graph_redis.py --validate

# Run performance tests
python scripts/utilities/init_memory_graph_redis.py --benchmark

# Rollback (drop indexes, keep data)
python scripts/utilities/init_memory_graph_redis.py --rollback
```

---

## 📊 Stats & Monitoring

```bash
# Count entities
redis-cli -h 172.16.168.23 KEYS "memory:graph:entity:*" | wc -l

# Count relations
redis-cli -h 172.16.168.23 KEYS "memory:graph:relations:*" | wc -l

# Index statistics
redis-cli -h 172.16.168.23 FT.INFO memory_graph_entity_idx | grep -E "num_docs|num_records"

# Memory usage
redis-cli -h 172.16.168.23 INFO memory | grep used_memory_human

# List all indexes
redis-cli -h 172.16.168.23 FT._LIST
```

---

## 🔍 Search Examples

### By Type

```bash
# All conversations
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx "@type:{conversation}" LIMIT 0 10

# All bug fixes
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx "@type:{bug_fix}" LIMIT 0 10
```

### By Status & Priority

```bash
# Active high-priority items
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx \
  "@status:{active} @priority:{high}" LIMIT 0 10

# Archived conversations
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx \
  "@type:{conversation} @status:{archived}" LIMIT 0 10
```

### By Topic/Tag

```bash
# Entities about Redis
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx "@tags:{redis}" LIMIT 0 10

# Multiple tags (OR)
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx "@tags:{redis|database}" LIMIT 0 10
```

### Full-Text Search

```bash
# Search in names and observations
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx "memory graph optimization" LIMIT 0 10

# Phonetic search (typo-tolerant)
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_fulltext_idx "performans" LIMIT 0 10
```

### Date Range

```bash
# Last 7 days
TIMESTAMP=$(date -d '7 days ago' +%s)000
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx \
  "@created_at:[$TIMESTAMP +inf]" SORTBY created_at DESC LIMIT 0 10

# Specific date range
START=1728000000000  # Unix timestamp ms
END=1728086400000
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx \
  "@created_at:[$START $END]" LIMIT 0 10
```

### Count Queries

```bash
# Count by type (fast)
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx "@type:{conversation}" LIMIT 0 0

# Count active tasks
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx \
  "@type:{task} @status:{active}" LIMIT 0 0
```

---

## 📝 CRUD Operations

### Create Entity

```python
import redis
import time

r = redis.Redis(host='172.16.168.23', port=6379, db=0)

entity = {
    "id": "new-entity-uuid",
    "type": "decision",
    "name": "Redis Memory Graph Implementation",
    "created_at": int(time.time() * 1000),
    "updated_at": int(time.time() * 1000),
    "observations": ["Initial design completed"],
    "metadata": {
        "priority": "high",
        "status": "active",
        "tags": ["redis", "architecture"]
    }
}

r.json().set(f"memory:graph:entity:{entity['id']}", '$', entity)
```

### Read Entity

```bash
# Get complete entity
redis-cli -h 172.16.168.23 JSON.GET "memory:graph:entity:267ab75b-8c44-46bb-b038-e5ee72096de4"

# Get specific fields
redis-cli -h 172.16.168.23 JSON.GET "memory:graph:entity:267ab75b-8c44-46bb-b038-e5ee72096de4" \
  $.name $.type $.metadata.topics
```

### Update Entity

```bash
# Update status
redis-cli -h 172.16.168.23 JSON.SET "memory:graph:entity:267ab75b-8c44-46bb-b038-e5ee72096de4" \
  '$.metadata.status' '"completed"'

# Add observation
redis-cli -h 172.16.168.23 JSON.ARRAPPEND "memory:graph:entity:267ab75b-8c44-46bb-b038-e5ee72096de4" \
  '$.observations' '"New observation added"'

# Update timestamp
redis-cli -h 172.16.168.23 JSON.SET "memory:graph:entity:267ab75b-8c44-46bb-b038-e5ee72096de4" \
  '$.updated_at' $(date +%s)000
```

### Delete Entity

```bash
# Delete entity (also delete relations!)
redis-cli -h 172.16.168.23 DEL "memory:graph:entity:entity-uuid"
redis-cli -h 172.16.168.23 DEL "memory:graph:relations:out:entity-uuid"
redis-cli -h 172.16.168.23 DEL "memory:graph:relations:in:entity-uuid"
```

---

## 🔗 Relations

### Create Relation

```python
import redis

r = redis.Redis(host='172.16.168.23', port=6379, db=0)

relation = {
    "to": "target-entity-uuid",
    "type": "relates_to",
    "created_at": int(time.time() * 1000),
    "metadata": {"strength": 0.9}
}

# Outgoing relation
out_key = "memory:graph:relations:out:source-entity-uuid"
r.json().set(out_key, '$', {"entity_id": "source-entity-uuid", "relations": []}, nx=True)
r.json().arrappend(out_key, '$.relations', relation)

# Incoming relation (reverse)
in_key = "memory:graph:relations:in:target-entity-uuid"
reverse_rel = {"from": "source-entity-uuid", "type": "relates_to", "created_at": relation['created_at']}
r.json().set(in_key, '$', {"entity_id": "target-entity-uuid", "relations": []}, nx=True)
r.json().arrappend(in_key, '$.relations', reverse_rel)
```

### Get Relations

```bash
# Get outgoing relations
redis-cli -h 172.16.168.23 JSON.GET "memory:graph:relations:out:267ab75b-8c44-46bb-b038-e5ee72096de4"

# Get incoming relations
redis-cli -h 172.16.168.23 JSON.GET "memory:graph:relations:in:267ab75b-8c44-46bb-b038-e5ee72096de4"
```

### Traverse Graph

```python
def traverse_relations(entity_id, relation_type="relates_to", max_depth=3):
    """BFS traversal of entity graph"""
    r = redis.Redis(host='172.16.168.23', port=6379, db=0)

    visited = set()
    queue = [(entity_id, 0)]
    chain = []

    while queue:
        current_id, depth = queue.pop(0)

        if current_id in visited or depth > max_depth:
            continue

        visited.add(current_id)

        # Get entity
        entity = r.json().get(f'memory:graph:entity:{current_id}')
        if entity:
            chain.append(entity)

        # Get relations
        relations = r.json().get(f'memory:graph:relations:out:{current_id}')
        if relations:
            for rel in relations['relations']:
                if rel['type'] == relation_type:
                    queue.append((rel['to'], depth + 1))

    return chain

# Usage
related = traverse_relations('267ab75b-8c44-46bb-b038-e5ee72096de4', max_depth=2)
print(f"Found {len(related)} related entities")
```

---

## 🐛 Troubleshooting

### Check Connection

```bash
redis-cli -h 172.16.168.23 -p 6379 PING
# Expected: PONG
```

### Verify Modules

```bash
redis-cli -h 172.16.168.23 MODULE LIST
# Must include: search, ReJSON
```

### Check Index Status

```bash
# List indexes
redis-cli -h 172.16.168.23 FT._LIST

# Get detailed index info
redis-cli -h 172.16.168.23 FT.INFO memory_graph_entity_idx
```

### View Logs

```bash
# Recent logs
tail -50 /home/kali/Desktop/AutoBot/logs/database/memory_graph_init.log

# Follow logs
tail -f /home/kali/Desktop/AutoBot/logs/database/memory_graph_init.log

# Search for errors
grep -i error /home/kali/Desktop/AutoBot/logs/database/memory_graph_init.log
```

### Rebuild Indexes

```bash
# Drop indexes (keeps data)
redis-cli -h 172.16.168.23 FT.DROPINDEX memory_graph_entity_idx
redis-cli -h 172.16.168.23 FT.DROPINDEX memory_graph_fulltext_idx

# Recreate
python scripts/utilities/init_memory_graph_redis.py
```

---

## 💡 Common Patterns

### Recent Activity

```bash
# Last 20 updates
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx "*" \
  SORTBY updated_at DESC LIMIT 0 20 \
  RETURN 4 $.name $.type $.updated_at $.metadata.status
```

### High Priority Tasks

```bash
# Active high-priority tasks
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx \
  "@type:{task} @status:{active} @priority:{high}" \
  SORTBY created_at DESC LIMIT 0 10
```

### Topic Analysis

```bash
# Group by topic (manual aggregation needed)
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx "@tags:{redis}" LIMIT 0 0
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx "@tags:{database}" LIMIT 0 0
redis-cli -h 172.16.168.23 FT.SEARCH memory_graph_entity_idx "@tags:{frontend}" LIMIT 0 0
```

---

## 📦 Backup & Restore

### Backup

```bash
# Export all Memory Graph data
redis-cli -h 172.16.168.23 --scan --pattern "memory:graph:*" | \
  xargs redis-cli -h 172.16.168.23 DUMP | \
  gzip > memory_graph_backup_$(date +%Y%m%d).json.gz
```

### Restore

```bash
# Import from backup (use appropriate restore tool)
# Note: RedisSearch indexes will need to be recreated
python scripts/utilities/init_memory_graph_redis.py
```

---

## 🔧 Performance Tips

1. **Use pipelines** for batch operations
2. **Limit result sets** (use LIMIT wisely)
3. **Cache frequently accessed entities**
4. **Use specific queries** over wildcards
5. **Monitor query performance** (log slow queries >50ms)
6. **Regular index maintenance** (check fragmentation monthly)

---

## 📚 Quick Links

- **Full Guide**: `/home/kali/Desktop/AutoBot/docs/database/MEMORY_GRAPH_INITIALIZATION_GUIDE.md`
- **Specification**: `/home/kali/Desktop/AutoBot/docs/database/REDIS_MEMORY_GRAPH_SPECIFICATION.md`
- **Script**: `/home/kali/Desktop/AutoBot/scripts/utilities/init_memory_graph_redis.py`
- **Logs**: `/home/kali/Desktop/AutoBot/logs/database/memory_graph_init.log`

---

**Last Updated:** 2025-10-03
