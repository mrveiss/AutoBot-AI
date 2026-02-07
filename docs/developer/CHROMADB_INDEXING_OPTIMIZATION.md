# ChromaDB Codebase Indexing Optimization

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
**Issue**: #539

This document describes the performance optimizations available for ChromaDB codebase indexing.

## Overview

The codebase indexing system scans the AutoBot codebase and stores code metadata (functions, classes, problems) in ChromaDB for semantic search and analysis. For large codebases (53K+ items), indexing can be resource-intensive.

This document covers the configurable optimizations introduced in Issue #539.

## Configuration Options

All configuration is done via environment variables. Set these in your `.env` file or export them before starting AutoBot.

### 1. Batch Size Configuration

**Environment Variable**: `CODEBASE_INDEX_BATCH_SIZE`
**Default**: `5000`
**Range**: `1000` - `10000` (recommended)

Controls how many items are stored to ChromaDB per batch operation.

```bash
# Smaller batches - less memory, more batches
export CODEBASE_INDEX_BATCH_SIZE=2500

# Larger batches - more memory, fewer batches (faster)
export CODEBASE_INDEX_BATCH_SIZE=7500
```

**Trade-offs**:
- **Higher values**: Fewer batch operations, faster overall, but more memory usage
- **Lower values**: More batch operations, slower overall, but less memory usage

### 2. Parallel Batch Processing

**Environment Variable**: `CODEBASE_INDEX_PARALLEL_BATCHES`
**Default**: `1` (sequential)
**Range**: `1` - `4` (recommended)

Controls how many batches are processed concurrently during the storage phase.

```bash
# Sequential processing (default - safest)
export CODEBASE_INDEX_PARALLEL_BATCHES=1

# Process 2 batches concurrently
export CODEBASE_INDEX_PARALLEL_BATCHES=2

# Process 4 batches concurrently (fastest, highest resource usage)
export CODEBASE_INDEX_PARALLEL_BATCHES=4
```

**Trade-offs**:
- **Higher values**: Faster storage, but higher CPU/memory usage
- **Lower values**: Slower storage, but lower resource usage

**Note**: ChromaDB may have limitations on concurrent writes. Start with `2` and increase if stable.

### 3. Incremental Indexing

**Environment Variable**: `CODEBASE_INDEX_INCREMENTAL`
**Default**: `false`
**Values**: `true` | `false`

When enabled, only re-indexes files that have changed since the last indexing run.

```bash
# Enable incremental indexing
export CODEBASE_INDEX_INCREMENTAL=true

# Disable (full re-index every time)
export CODEBASE_INDEX_INCREMENTAL=false
```

**How it works**:
1. Computes SHA-256 hash of each file
2. Compares with stored hash in Redis
3. Skips files with matching hashes (unchanged)
4. Stores new hashes after successful processing

**Requirements**:
- Redis must be available (uses `analytics` database)
- File hashes stored with prefix `codebase:file_hash:`

**Trade-offs**:
- **Enabled**: Much faster subsequent runs, but requires Redis
- **Disabled**: Full re-index every time, no Redis dependency

## Recommended Configurations

### Development Environment
```bash
# Fast indexing, acceptable resource usage
export CODEBASE_INDEX_BATCH_SIZE=5000
export CODEBASE_INDEX_PARALLEL_BATCHES=2
export CODEBASE_INDEX_INCREMENTAL=true
```

### Production Environment
```bash
# Balanced performance and stability
export CODEBASE_INDEX_BATCH_SIZE=5000
export CODEBASE_INDEX_PARALLEL_BATCHES=1
export CODEBASE_INDEX_INCREMENTAL=true
```

### Low-Memory Environment
```bash
# Minimize memory usage
export CODEBASE_INDEX_BATCH_SIZE=2000
export CODEBASE_INDEX_PARALLEL_BATCHES=1
export CODEBASE_INDEX_INCREMENTAL=true
```

### Maximum Performance
```bash
# Fastest possible indexing (high resource usage)
export CODEBASE_INDEX_BATCH_SIZE=7500
export CODEBASE_INDEX_PARALLEL_BATCHES=4
export CODEBASE_INDEX_INCREMENTAL=true
```

## Monitoring Progress

The indexing task exposes configuration in its status:

```json
{
  "config": {
    "batch_size": 5000,
    "parallel_batches": 2,
    "incremental_enabled": true
  },
  "stats": {
    "files_scanned": 1500,
    "files_skipped": 3200,
    "items_stored": 45000
  }
}
```

- `files_skipped`: Number of unchanged files skipped (incremental mode)
- `batch_size`: Current batch size in use
- `parallel_batches`: Current parallelism level

## Clearing Incremental Index Cache

To force a full re-index when incremental indexing is enabled:

```bash
# Clear all file hashes from Redis
redis-cli -h 172.16.168.23 -n 11 KEYS "codebase:file_hash:*" | xargs redis-cli -h 172.16.168.23 -n 11 DEL
```

Or temporarily disable incremental indexing:
```bash
export CODEBASE_INDEX_INCREMENTAL=false
# Run indexing
# Then re-enable
export CODEBASE_INDEX_INCREMENTAL=true
```

## Technical Details

### File Hashing

- Algorithm: SHA-256
- Chunk size: 64KB (memory-efficient for large files)
- Storage: Redis key `codebase:file_hash:{relative_path}`
- Database: Redis DB 11 (analytics)

### Batch Processing

- Default batch size: 5000 items
- ChromaDB embedding: Uses default `ONNXMiniLM_L6_V2` model
- Parallel execution: Uses `asyncio.gather()` for concurrent batches

### Related Files

- `autobot-user-backend/api/codebase_analytics/scanner.py` - Main indexing logic
- `autobot-user-backend/api/codebase_analytics/storage.py` - ChromaDB/Redis connections
- `autobot-user-backend/utils/chromadb_client.py` - ChromaDB client utilities

## Troubleshooting

### Indexing Too Slow
1. Enable incremental indexing
2. Increase batch size
3. Increase parallel batches (if stable)

### Memory Issues
1. Decrease batch size
2. Set parallel batches to 1

### Files Not Being Re-indexed
1. Clear file hash cache (see above)
2. Check Redis connectivity
3. Temporarily disable incremental indexing

### ChromaDB Errors During Parallel Processing
1. Reduce parallel batches to 1
2. Check ChromaDB logs for specific errors
