# Redis Database Schema Documentation

**Last Updated**: 2025-12-13
**Related Issue**: [#251](https://github.com/mrveiss/AutoBot-AI/issues/251)
**Related ADR**: [ADR-002: Redis Database Separation](../adr/002-redis-database-separation.md)

This document describes the data structures and key patterns used in AutoBot's Redis databases.

---

## Database Overview

AutoBot uses Redis Stack on VM3 (`172.16.168.23:6379`) with named database abstraction:

| Database | Name | Purpose | Key Count (Typical) |
|----------|------|---------|---------------------|
| DB 0 | `main` | Sessions, cache, queues | 500-2,000 |
| DB 1 | `knowledge` | Vectors, documents, facts | 10,000-50,000 |
| DB 2 | `prompts` | LLM prompts, templates | 50-200 |
| DB 3 | `analytics` | Metrics, usage, errors | 1,000-10,000 |

---

## Database 0: Main

### Sessions

```
Key Pattern: session:{session_id}
Type: HASH
TTL: 24 hours (86400 seconds)

Fields:
  - user_id: string
  - created_at: ISO8601 timestamp
  - last_activity: ISO8601 timestamp
  - conversation_id: string
  - metadata: JSON string
```

**Example:**
```redis
HGETALL session:abc123-def456
1) "user_id"
2) "user_001"
3) "created_at"
4) "2025-01-15T10:30:00Z"
5) "last_activity"
6) "2025-01-15T11:45:00Z"
7) "conversation_id"
8) "conv_789"
9) "metadata"
10) "{\"browser\":\"Chrome\",\"ip\":\"192.168.1.1\"}"
```

### Conversation History

```
Key Pattern: conversation:{conversation_id}:messages
Type: LIST
TTL: 7 days (604800 seconds)

Elements: JSON-encoded message objects
  - role: "user" | "assistant" | "system"
  - content: string
  - timestamp: ISO8601
  - tokens: number (optional)
```

**Example:**
```redis
LRANGE conversation:conv_789:messages 0 -1
1) "{\"role\":\"user\",\"content\":\"Hello\",\"timestamp\":\"2025-01-15T10:30:00Z\"}"
2) "{\"role\":\"assistant\",\"content\":\"Hi! How can I help?\",\"timestamp\":\"2025-01-15T10:30:05Z\",\"tokens\":15}"
```

### API Cache

```
Key Pattern: cache:api:{endpoint_hash}:{params_hash}
Type: STRING (JSON)
TTL: 5 minutes (300 seconds) default, configurable

Value: JSON response body
```

**Example:**
```redis
GET cache:api:health:default
"{\"status\":\"healthy\",\"timestamp\":\"2025-01-15T10:30:00Z\"}"
```

### Task Queues

```
Key Pattern: queue:{queue_name}
Type: LIST (FIFO)
TTL: None

Elements: JSON-encoded task objects
  - task_id: string
  - task_type: string
  - payload: object
  - created_at: ISO8601
  - priority: number (1-10)
```

**Example:**
```redis
LPUSH queue:workflows "{\"task_id\":\"task_001\",\"task_type\":\"browser_automation\",\"payload\":{\"url\":\"https://example.com\"},\"created_at\":\"2025-01-15T10:30:00Z\",\"priority\":5}"
```

### Rate Limiting

```
Key Pattern: ratelimit:{client_id}:{endpoint}
Type: STRING (counter)
TTL: 1 minute (60 seconds)

Value: Request count
```

---

## Database 1: Knowledge

### Vector Embeddings (LlamaIndex)

```
Key Pattern: llama_index/vector_store/{collection}/{doc_id}
Type: HASH

Fields:
  - embedding: Binary (float32 array)
  - text: string (chunk content)
  - metadata: JSON string
  - doc_id: string
  - node_id: string
```

**Example:**
```redis
HGETALL llama_index/vector_store/default/doc_001_chunk_0
1) "embedding"
2) <binary float32 array, 384 or 768 dimensions>
3) "text"
4) "AutoBot is an AI-powered automation platform..."
5) "metadata"
6) "{\"source\":\"docs/README.md\",\"chunk_index\":0}"
7) "doc_id"
8) "doc_001"
9) "node_id"
10) "node_abc123"
```

### Document Metadata

```
Key Pattern: doc:{doc_id}:metadata
Type: HASH

Fields:
  - title: string
  - source: string (file path or URL)
  - content_type: string (markdown, html, pdf, etc.)
  - created_at: ISO8601
  - updated_at: ISO8601
  - chunk_count: number
  - word_count: number
  - hash: string (content hash for deduplication)
```

### Facts Store

```
Key Pattern: fact:{fact_id}
Type: HASH

Fields:
  - content: string
  - category: string
  - confidence: float (0.0-1.0)
  - source: string
  - created_at: ISO8601
  - verified: boolean
```

**Example:**
```redis
HGETALL fact:f001
1) "content"
2) "AutoBot uses Redis Stack for data persistence"
3) "category"
4) "architecture"
5) "confidence"
6) "0.95"
7) "source"
8) "docs/architecture/README.md"
9) "created_at"
10) "2025-01-15T10:30:00Z"
11) "verified"
12) "true"
```

### Document Index

```
Key Pattern: index:documents
Type: SORTED SET

Score: Last updated timestamp (Unix epoch)
Member: doc_id
```

---

## Database 2: Prompts

### System Prompts

```
Key Pattern: prompt:system:{prompt_name}
Type: HASH

Fields:
  - content: string (prompt text)
  - version: string
  - description: string
  - variables: JSON array of variable names
  - created_at: ISO8601
  - updated_at: ISO8601
```

**Example:**
```redis
HGETALL prompt:system:chat_default
1) "content"
2) "You are AutoBot, an AI assistant. Current date: {{date}}. User: {{user_name}}"
3) "version"
4) "1.2.0"
5) "description"
6) "Default chat system prompt"
7) "variables"
8) "[\"date\",\"user_name\"]"
```

### Prompt Templates

```
Key Pattern: prompt:template:{template_name}
Type: HASH

Fields:
  - template: string (Jinja2 template)
  - category: string
  - examples: JSON array
  - required_variables: JSON array
```

### Custom User Prompts

```
Key Pattern: prompt:user:{user_id}:{prompt_name}
Type: HASH

Fields:
  - content: string
  - is_private: boolean
  - created_at: ISO8601
```

---

## Database 3: Analytics

### Performance Metrics

```
Key Pattern: metrics:{service}:{metric_name}:{timestamp_bucket}
Type: HASH

Fields:
  - count: number
  - sum: number
  - min: number
  - max: number
  - avg: number
```

**Example:**
```redis
HGETALL metrics:api:response_time:2025-01-15-10
1) "count"
2) "1542"
3) "sum"
4) "45260"
5) "min"
6) "12"
7) "max"
8) "1250"
9) "avg"
10) "29.35"
```

### Usage Statistics

```
Key Pattern: usage:{date}:{user_id}
Type: HASH

Fields:
  - requests: number
  - tokens_in: number
  - tokens_out: number
  - llm_calls: number
  - kb_queries: number
```

### Error Logs

```
Key Pattern: errors:{date}:{error_type}
Type: LIST
TTL: 30 days

Elements: JSON error objects
  - timestamp: ISO8601
  - message: string
  - stack_trace: string (optional)
  - context: object
```

### Real-time Counters

```
Key Pattern: counter:{metric}:{window}
Type: STRING (atomic counter)
TTL: Varies by window (1min, 1hour, 1day)

Value: Integer count
```

---

## Access Patterns

### Reading Data

```python
from src.utils.redis_client import get_redis_client

# Get client for specific database
redis = get_redis_client(async_client=False, database="knowledge")

# Read session
session = redis.hgetall("session:abc123")

# Read conversation history
messages = redis.lrange("conversation:conv_001:messages", 0, -1)

# Search vectors (via LlamaIndex)
# Handled by LlamaIndex's RedisVectorStore
```

### Writing Data

```python
from src.utils.redis_client import get_redis_client

redis = get_redis_client(async_client=False, database="main")

# Create session with TTL
redis.hset("session:new_id", mapping={
    "user_id": "user_001",
    "created_at": datetime.now().isoformat()
})
redis.expire("session:new_id", 86400)  # 24 hours

# Append to conversation
redis.rpush("conversation:conv_001:messages", json.dumps(message))
```

---

## Maintenance Operations

### Backup

```bash
# Full backup
redis-cli -h 172.16.168.23 BGSAVE

# Database-specific backup
redis-cli -h 172.16.168.23 -n 1 --rdb knowledge_backup.rdb
```

### Key Analysis

```bash
# Count keys by pattern
redis-cli -h 172.16.168.23 -n 0 KEYS "session:*" | wc -l

# Memory usage
redis-cli -h 172.16.168.23 INFO memory

# Key distribution
redis-cli -h 172.16.168.23 DBSIZE
```

### Cleanup

```bash
# Flush cache only (DB 0 cache keys)
redis-cli -h 172.16.168.23 -n 0 KEYS "cache:*" | xargs redis-cli -h 172.16.168.23 -n 0 DEL

# Expire old analytics
redis-cli -h 172.16.168.23 -n 3 KEYS "metrics:*:2024-*" | xargs redis-cli -h 172.16.168.23 -n 3 DEL
```

---

## Related Documentation

- [ADR-002: Redis Database Separation](../adr/002-redis-database-separation.md)
- [Data Flow Diagrams](data-flows.md)
- [Redis Client Usage](../developer/REDIS_CLIENT_USAGE.md)

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
