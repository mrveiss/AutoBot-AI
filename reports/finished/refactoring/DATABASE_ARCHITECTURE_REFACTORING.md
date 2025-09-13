# Database Architecture Refactoring Report

## Executive Summary

This report provides a comprehensive analysis and refactoring strategy for AutoBot's database architecture, focusing on the Redis-based multi-database system. The analysis identifies critical areas for improvement in data organization, performance optimization, consistency patterns, and scalability across the distributed 6-VM infrastructure.

## Current Database Architecture Assessment

### Redis Database Organization Analysis

#### Current Database Allocation
Based on the CLAUDE.md documentation, AutoBot uses a Redis multi-database system with the following critical data distribution:

```yaml
# Current Database Configuration (config/redis-databases.yaml)
redis_databases:
  main:           # DB 0 - CRITICAL: 13,383 LlamaIndex vectors + facts
    db: 0
    description: "Main application data"
    data_types: ["vectors", "facts", "workflow_rules"]
    size: "~95% of total data"

  knowledge:      # DB 1 - Knowledge metadata
    db: 1
    description: "Knowledge base and documents"

  cache:          # DB 2 - Temporary cache
    db: 2
    description: "Application cache layer"

  # ... 8 additional databases (DB 3-10)
```

### Identified Critical Issues

#### 1. **Database 0 Risk Concentration** (Critical Priority)
**Problem**: Single point of failure with 99% of critical data in DB 0
```bash
# Current risk assessment:
# DB 0 contains:
- 13,383 LlamaIndex vectors (99% of data)
- ~134 fact entries (1% of data)
- Configuration data
- Workflow classification rules
```
**Impact**: Complete system failure if DB 0 is lost, no data isolation, backup/restore complexity

#### 2. **Inadequate Data Separation** (High Priority)
**Problem**: Mixed data types in single database prevent selective operations
**Examples**:
- Vector embeddings mixed with transactional data
- Configuration data mixed with operational data
- No clear data lifecycle management

#### 3. **Poor Scalability Patterns** (High Priority)
**Problem**: Monolithic database design prevents horizontal scaling
**Impact**: Cannot scale different data types independently, resource contention

#### 4. **Inconsistent Data Access Patterns** (Medium Priority)
**Problem**: Different access patterns for different data types not optimized
**Examples**:
- Vectors: Read-heavy, batch processing
- Facts: CRUD operations, low latency
- Cache: TTL-based, high throughput

#### 5. **Backup and Recovery Complexity** (Medium Priority)
**Problem**: Cannot perform selective backup/restore operations
**Impact**: Must backup entire dataset for any data protection, long recovery times

## Proposed Database Architecture Refactoring

### Phase 1: Data Domain Separation Strategy

#### 1.1 **Domain-Driven Database Design**

**Proposed Database Allocation**:
```yaml
# Refactored Database Configuration
redis_databases:
  # Core Application Data (Transactional)
  app_core:
    db: 0
    description: "Core application state and configuration"
    data_types: ["app_config", "user_sessions", "system_state"]
    access_pattern: "Low latency CRUD"
    backup_frequency: "Real-time"

  # Vector Storage (Analytical)
  vectors:
    db: 1
    description: "LlamaIndex embeddings and vector operations"
    data_types: ["embeddings", "vector_metadata", "similarity_indices"]
    access_pattern: "Batch read, similarity search"
    backup_frequency: "Daily"

  # Knowledge Graph (Structured)
  knowledge:
    db: 2
    description: "Facts, entities, relationships"
    data_types: ["facts", "entities", "relationships", "rules"]
    access_pattern: "Graph traversal, complex queries"
    backup_frequency: "Hourly"

  # Document Storage (Content)
  documents:
    db: 3
    description: "Document content and metadata"
    data_types: ["document_content", "metadata", "categories"]
    access_pattern: "Content retrieval, search indexing"
    backup_frequency: "Daily"

  # Chat and Conversations (Temporal)
  conversations:
    db: 4
    description: "Chat history and conversation state"
    data_types: ["messages", "conversations", "user_context"]
    access_pattern: "Sequential access, time-based queries"
    backup_frequency: "Hourly"

  # Workflow and Tasks (Operational)
  workflows:
    db: 5
    description: "Task execution and workflow state"
    data_types: ["tasks", "workflows", "execution_logs"]
    access_pattern: "State transitions, queue operations"
    backup_frequency: "Real-time"

  # Performance Cache (Temporary)
  cache:
    db: 6
    description: "Application-level caching"
    data_types: ["api_responses", "computed_results", "temp_data"]
    access_pattern: "High throughput, TTL-based"
    backup_frequency: "None (disposable)"

  # Analytics and Monitoring (Metrics)
  metrics:
    db: 7
    description: "Performance metrics and analytics"
    data_types: ["performance_data", "usage_metrics", "system_health"]
    access_pattern: "Time-series, aggregation"
    backup_frequency: "Weekly"

  # Session and Authentication (Security)
  auth:
    db: 8
    description: "Authentication and session management"
    data_types: ["sessions", "auth_tokens", "user_preferences"]
    access_pattern: "Fast lookup, TTL management"
    backup_frequency: "Real-time"

  # System Integration (External)
  integration:
    db: 9
    description: "External service integration data"
    data_types: ["api_keys", "service_configs", "integration_state"]
    access_pattern: "Configuration lookup, state persistence"
    backup_frequency: "Daily"
```

#### 1.2 **Data Migration Strategy Implementation**

**Automated Migration System**:
```python
# src/database/migration/redis_migration_engine.py
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import redis
import json
import logging
from datetime import datetime

class MigrationStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

@dataclass
class MigrationPlan:
    source_db: int
    target_db: int
    data_patterns: List[str]
    batch_size: int
    validation_rules: List[str]
    rollback_strategy: str

class RedisMigrationEngine:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.logger = logging.getLogger(__name__)
        self.migration_log_key = "migration:log"
        self.migration_status_key = "migration:status"

    async def execute_migration_plan(self, plan: MigrationPlan) -> Dict[str, Any]:
        """Execute a complete migration plan with validation and rollback capability."""
        migration_id = self._generate_migration_id()

        try:
            # Initialize migration tracking
            await self._initialize_migration(migration_id, plan)

            # Pre-migration validation
            await self._validate_source_data(plan)
            await self._validate_target_database(plan)

            # Create backup checkpoint
            backup_info = await self._create_backup_checkpoint(plan.source_db)

            # Execute migration in batches
            migration_stats = await self._execute_batch_migration(migration_id, plan)

            # Post-migration validation
            await self._validate_migration_results(migration_id, plan, migration_stats)

            # Update migration status
            await self._mark_migration_completed(migration_id, migration_stats)

            return {
                "migration_id": migration_id,
                "status": MigrationStatus.COMPLETED,
                "stats": migration_stats,
                "backup_info": backup_info
            }

        except Exception as e:
            self.logger.error(f"Migration {migration_id} failed: {str(e)}")
            await self._handle_migration_failure(migration_id, plan, str(e))
            raise

    async def _execute_batch_migration(self, migration_id: str, plan: MigrationPlan) -> Dict[str, Any]:
        """Execute migration in manageable batches with progress tracking."""
        stats = {
            "total_keys": 0,
            "migrated_keys": 0,
            "failed_keys": 0,
            "batch_count": 0,
            "start_time": datetime.utcnow().isoformat(),
            "errors": []
        }

        # Get all keys matching patterns
        all_keys = set()
        for pattern in plan.data_patterns:
            keys = await self.redis.keys(pattern)
            all_keys.update(keys)

        stats["total_keys"] = len(all_keys)

        # Process in batches
        keys_list = list(all_keys)
        for i in range(0, len(keys_list), plan.batch_size):
            batch_keys = keys_list[i:i + plan.batch_size]
            batch_stats = await self._migrate_key_batch(
                batch_keys, plan.source_db, plan.target_db
            )

            # Update statistics
            stats["migrated_keys"] += batch_stats["migrated"]
            stats["failed_keys"] += batch_stats["failed"]
            stats["batch_count"] += 1
            stats["errors"].extend(batch_stats["errors"])

            # Update progress
            await self._update_migration_progress(migration_id, stats)

            self.logger.info(
                f"Migration {migration_id} batch {stats['batch_count']} completed: "
                f"{batch_stats['migrated']}/{len(batch_keys)} keys migrated"
            )

        stats["end_time"] = datetime.utcnow().isoformat()
        return stats

    async def _migrate_key_batch(self, keys: List[str], source_db: int, target_db: int) -> Dict[str, Any]:
        """Migrate a batch of keys with type-aware handling."""
        batch_stats = {
            "migrated": 0,
            "failed": 0,
            "errors": []
        }

        # Switch to source database
        await self.redis.select(source_db)

        pipe = self.redis.pipeline()
        key_types = {}

        # Get key types and values in pipeline
        for key in keys:
            pipe.type(key)

        types_result = await pipe.execute()

        # Build type mapping
        for i, key in enumerate(keys):
            key_types[key] = types_result[i].decode() if types_result[i] else None

        # Process each key based on its type
        for key in keys:
            try:
                key_type = key_types.get(key)
                if not key_type or key_type == 'none':
                    continue

                # Get value based on type
                value = await self._get_key_value_by_type(key, key_type)
                ttl = await self.redis.ttl(key)

                # Switch to target database and set value
                await self.redis.select(target_db)
                await self._set_key_value_by_type(key, key_type, value, ttl)

                # Switch back to source database
                await self.redis.select(source_db)

                batch_stats["migrated"] += 1

            except Exception as e:
                batch_stats["failed"] += 1
                batch_stats["errors"].append({
                    "key": key,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                })
                self.logger.error(f"Failed to migrate key {key}: {str(e)}")

        return batch_stats

    async def _get_key_value_by_type(self, key: str, key_type: str) -> Any:
        """Get key value with proper type handling."""
        if key_type == 'string':
            return await self.redis.get(key)
        elif key_type == 'list':
            return await self.redis.lrange(key, 0, -1)
        elif key_type == 'set':
            return await self.redis.smembers(key)
        elif key_type == 'zset':
            return await self.redis.zrange(key, 0, -1, withscores=True)
        elif key_type == 'hash':
            return await self.redis.hgetall(key)
        elif key_type == 'stream':
            return await self.redis.xrange(key)
        else:
            raise ValueError(f"Unsupported key type: {key_type}")

    async def _set_key_value_by_type(self, key: str, key_type: str, value: Any, ttl: int):
        """Set key value with proper type handling and TTL."""
        if key_type == 'string':
            await self.redis.set(key, value)
        elif key_type == 'list':
            if value:  # Only if list is not empty
                await self.redis.rpush(key, *value)
        elif key_type == 'set':
            if value:  # Only if set is not empty
                await self.redis.sadd(key, *value)
        elif key_type == 'zset':
            if value:  # Only if zset is not empty
                await self.redis.zadd(key, dict(value))
        elif key_type == 'hash':
            if value:  # Only if hash is not empty
                await self.redis.hset(key, mapping=value)
        elif key_type == 'stream':
            # Stream migration requires special handling
            for entry in value:
                await self.redis.xadd(key, entry[1], id=entry[0])

        # Set TTL if applicable
        if ttl > 0:
            await self.redis.expire(key, ttl)

# Migration execution script
async def execute_db0_separation_migration():
    """Execute the critical DB 0 separation migration."""
    migration_engine = RedisMigrationEngine(redis_client)

    # Vector data migration (DB 0 -> DB 1)
    vector_plan = MigrationPlan(
        source_db=0,
        target_db=1,
        data_patterns=[
            "vector:*",
            "embedding:*",
            "llama_index:*",
            "similarity:*"
        ],
        batch_size=100,
        validation_rules=["count_match", "type_preservation"],
        rollback_strategy="restore_from_backup"
    )

    # Knowledge data migration (DB 0 -> DB 2)
    knowledge_plan = MigrationPlan(
        source_db=0,
        target_db=2,
        data_patterns=[
            "fact:*",
            "entity:*",
            "relationship:*",
            "rule:*"
        ],
        batch_size=50,
        validation_rules=["count_match", "integrity_check"],
        rollback_strategy="restore_from_backup"
    )

    # Execute migrations sequentially
    vector_result = await migration_engine.execute_migration_plan(vector_plan)
    knowledge_result = await migration_engine.execute_migration_plan(knowledge_plan)

    return {
        "vector_migration": vector_result,
        "knowledge_migration": knowledge_result
    }
```

### Phase 2: Performance Optimization Patterns

#### 2.1 **Connection Pool Optimization**

**Enhanced Redis Connection Management**:
```python
# src/database/connection/redis_connection_pool.py
from typing import Dict, Optional, Any
import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool
import asyncio
from dataclasses import dataclass
from enum import Enum

class DatabaseRole(Enum):
    TRANSACTIONAL = "transactional"  # Low latency, high consistency
    ANALYTICAL = "analytical"        # High throughput, eventual consistency
    CACHE = "cache"                 # High speed, disposable
    ARCHIVE = "archive"             # High capacity, low frequency

@dataclass
class DatabaseConfig:
    db_id: int
    role: DatabaseRole
    max_connections: int
    min_connections: int
    connection_timeout: float
    read_timeout: float
    retry_attempts: int
    health_check_interval: int

class OptimizedRedisConnectionManager:
    def __init__(self, host: str = "localhost", port: int = 6379):
        self.host = host
        self.port = port
        self.pools: Dict[int, ConnectionPool] = {}
        self.configs: Dict[int, DatabaseConfig] = {}
        self._health_check_tasks: Dict[int, asyncio.Task] = {}

    def register_database(self, config: DatabaseConfig):
        """Register a database with role-specific optimization."""
        self.configs[config.db_id] = config

        # Create optimized connection pool based on role
        pool_params = self._get_pool_params_for_role(config)

        self.pools[config.db_id] = ConnectionPool(
            host=self.host,
            port=self.port,
            db=config.db_id,
            **pool_params
        )

        # Start health check task
        self._health_check_tasks[config.db_id] = asyncio.create_task(
            self._health_check_loop(config.db_id, config.health_check_interval)
        )

    def _get_pool_params_for_role(self, config: DatabaseConfig) -> Dict[str, Any]:
        """Get connection pool parameters optimized for database role."""
        base_params = {
            "max_connections": config.max_connections,
            "socket_connect_timeout": config.connection_timeout,
            "socket_timeout": config.read_timeout,
            "retry_on_timeout": True,
            "retry_on_error": [ConnectionError, TimeoutError],
            "max_retries": config.retry_attempts
        }

        # Role-specific optimizations
        if config.role == DatabaseRole.TRANSACTIONAL:
            base_params.update({
                "socket_keepalive": True,
                "socket_keepalive_options": {
                    "TCP_KEEPIDLE": 1,
                    "TCP_KEEPINTVL": 3,
                    "TCP_KEEPCNT": 5
                },
                "connection_pool_class_kwargs": {
                    "max_idle_time": 30,  # Keep connections alive longer
                }
            })

        elif config.role == DatabaseRole.ANALYTICAL:
            base_params.update({
                "socket_timeout": config.read_timeout * 3,  # Longer timeout for complex queries
                "max_connections": config.max_connections * 2,  # More connections for parallel processing
            })

        elif config.role == DatabaseRole.CACHE:
            base_params.update({
                "socket_timeout": config.read_timeout * 0.5,  # Faster timeout for cache
                "retry_on_timeout": False,  # Don't retry cache misses
                "max_retries": 1  # Minimal retry for cache operations
            })

        elif config.role == DatabaseRole.ARCHIVE:
            base_params.update({
                "socket_timeout": config.read_timeout * 5,  # Much longer timeout for archive
                "max_connections": max(2, config.max_connections // 4)  # Fewer connections needed
            })

        return base_params

    async def get_client(self, db_id: int) -> redis.Redis:
        """Get optimized Redis client for specific database."""
        if db_id not in self.pools:
            raise ValueError(f"Database {db_id} not registered")

        return redis.Redis(connection_pool=self.pools[db_id])

    async def _health_check_loop(self, db_id: int, interval: int):
        """Continuous health check for database connection."""
        while True:
            try:
                client = await self.get_client(db_id)
                await client.ping()

                # Role-specific health checks
                config = self.configs[db_id]
                if config.role == DatabaseRole.TRANSACTIONAL:
                    # Check latency for transactional database
                    start_time = asyncio.get_event_loop().time()
                    await client.get("__health_check__")
                    latency = (asyncio.get_event_loop().time() - start_time) * 1000

                    if latency > 10:  # 10ms threshold
                        logging.warning(f"High latency detected for DB {db_id}: {latency:.2f}ms")

                await client.close()

            except Exception as e:
                logging.error(f"Health check failed for DB {db_id}: {str(e)}")
                # Implement reconnection logic here

            await asyncio.sleep(interval)

# Initialize optimized connection manager
redis_manager = OptimizedRedisConnectionManager()

# Register databases with role-specific configurations
redis_manager.register_database(DatabaseConfig(
    db_id=0,
    role=DatabaseRole.TRANSACTIONAL,
    max_connections=20,
    min_connections=5,
    connection_timeout=1.0,
    read_timeout=2.0,
    retry_attempts=3,
    health_check_interval=30
))

redis_manager.register_database(DatabaseConfig(
    db_id=1,
    role=DatabaseRole.ANALYTICAL,
    max_connections=10,
    min_connections=2,
    connection_timeout=2.0,
    read_timeout=10.0,
    retry_attempts=2,
    health_check_interval=60
))

redis_manager.register_database(DatabaseConfig(
    db_id=6,
    role=DatabaseRole.CACHE,
    max_connections=50,
    min_connections=10,
    connection_timeout=0.5,
    read_timeout=1.0,
    retry_attempts=1,
    health_check_interval=15
))
```

#### 2.2 **Data Access Pattern Optimization**

**Repository Pattern with Database Role Awareness**:
```python
# src/database/repositories/base_repository.py
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Optional, Dict, Any
from src.database.connection.redis_connection_pool import redis_manager, DatabaseRole

T = TypeVar('T')

class BaseRepository(Generic[T], ABC):
    def __init__(self, db_id: int, entity_prefix: str):
        self.db_id = db_id
        self.entity_prefix = entity_prefix
        self._client = None

    async def _get_client(self):
        """Get Redis client with connection pooling."""
        if not self._client:
            self._client = await redis_manager.get_client(self.db_id)
        return self._client

    @abstractmethod
    async def serialize(self, entity: T) -> Dict[str, Any]:
        """Serialize entity to Redis-compatible format."""
        pass

    @abstractmethod
    async def deserialize(self, data: Dict[str, Any]) -> T:
        """Deserialize Redis data to entity."""
        pass

    def _get_key(self, entity_id: str) -> str:
        """Generate Redis key for entity."""
        return f"{self.entity_prefix}:{entity_id}"

# Vector Repository (Analytical Database)
class VectorRepository(BaseRepository[VectorEntity]):
    def __init__(self):
        super().__init__(db_id=1, entity_prefix="vector")

    async def store_embedding(self, vector_id: str, embedding: List[float], metadata: Dict[str, Any]) -> VectorEntity:
        """Store vector embedding with optimized batch operations."""
        client = await self._get_client()

        # Use pipeline for batch operations (analytical optimization)
        pipe = client.pipeline()

        vector_key = self._get_key(vector_id)
        metadata_key = f"{vector_key}:metadata"

        # Store embedding as binary data for space efficiency
        import struct
        embedding_bytes = b''.join(struct.pack('f', x) for x in embedding)

        pipe.set(vector_key, embedding_bytes)
        pipe.hset(metadata_key, mapping=metadata)

        # Add to vector index for similarity search
        pipe.zadd(f"{self.entity_prefix}:index", {vector_id: metadata.get('timestamp', 0)})

        await pipe.execute()

        return VectorEntity(id=vector_id, embedding=embedding, metadata=metadata)

    async def similarity_search(self, query_embedding: List[float], top_k: int = 10) -> List[VectorEntity]:
        """Perform similarity search with optimized retrieval."""
        client = await self._get_client()

        # Get all vector IDs from index
        vector_ids = await client.zrevrange(f"{self.entity_prefix}:index", 0, -1)

        # Batch retrieve embeddings
        pipe = client.pipeline()
        for vector_id in vector_ids:
            pipe.get(self._get_key(vector_id.decode()))

        embeddings_bytes = await pipe.execute()

        # Compute similarities (this could be moved to a dedicated similarity service)
        similarities = []
        import struct
        query_array = np.array(query_embedding)

        for i, embedding_bytes in enumerate(embeddings_bytes):
            if embedding_bytes:
                embedding = [struct.unpack('f', embedding_bytes[j:j+4])[0]
                           for j in range(0, len(embedding_bytes), 4)]
                similarity = np.dot(query_array, np.array(embedding))
                similarities.append((vector_ids[i].decode(), similarity))

        # Sort by similarity and return top_k
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Retrieve full entities for top results
        top_results = []
        for vector_id, _ in similarities[:top_k]:
            entity = await self.get_by_id(vector_id)
            if entity:
                top_results.append(entity)

        return top_results

# Knowledge Repository (Structured Database)
class KnowledgeRepository(BaseRepository[FactEntity]):
    def __init__(self):
        super().__init__(db_id=2, entity_prefix="fact")

    async def create_fact(self, fact: FactEntity) -> FactEntity:
        """Create fact with relationship indexing."""
        client = await self._get_client()

        # Transactional operation for consistency
        async with client.pipeline(transaction=True) as pipe:
            fact_key = self._get_key(fact.id)
            fact_data = await self.serialize(fact)

            # Store fact
            pipe.hset(fact_key, mapping=fact_data)

            # Index by subject and predicate for graph queries
            if fact.subject:
                pipe.sadd(f"facts:subject:{fact.subject}", fact.id)
            if fact.predicate:
                pipe.sadd(f"facts:predicate:{fact.predicate}", fact.id)
            if fact.object:
                pipe.sadd(f"facts:object:{fact.object}", fact.id)

            # Add to temporal index
            pipe.zadd("facts:timeline", {fact.id: fact.timestamp})

            await pipe.execute()

        return fact

    async def query_facts_by_pattern(self, subject: str = None, predicate: str = None, object: str = None) -> List[FactEntity]:
        """Query facts using graph pattern matching."""
        client = await self._get_client()

        # Build intersection of sets based on query pattern
        sets_to_intersect = []

        if subject:
            sets_to_intersect.append(f"facts:subject:{subject}")
        if predicate:
            sets_to_intersect.append(f"facts:predicate:{predicate}")
        if object:
            sets_to_intersect.append(f"facts:object:{object}")

        if not sets_to_intersect:
            return []

        # Use Redis set intersection for efficient graph queries
        if len(sets_to_intersect) == 1:
            fact_ids = await client.smembers(sets_to_intersect[0])
        else:
            # Create temporary intersection
            temp_key = f"temp:intersection:{uuid.uuid4()}"
            await client.sinterstore(temp_key, *sets_to_intersect)
            fact_ids = await client.smembers(temp_key)
            await client.delete(temp_key)

        # Retrieve full fact entities
        facts = []
        for fact_id in fact_ids:
            fact = await self.get_by_id(fact_id.decode())
            if fact:
                facts.append(fact)

        return facts

# Cache Repository (High-Speed Database)
class CacheRepository:
    def __init__(self):
        self.db_id = 6
        self._client = None

    async def _get_client(self):
        if not self._client:
            self._client = await redis_manager.get_client(self.db_id)
        return self._client

    async def get_cached_result(self, cache_key: str) -> Optional[Any]:
        """Get cached result with fast timeout."""
        try:
            client = await self._get_client()
            data = await client.get(f"cache:{cache_key}")
            return json.loads(data) if data else None
        except Exception:
            # Fast fail for cache operations
            return None

    async def set_cached_result(self, cache_key: str, data: Any, ttl: int = 300) -> bool:
        """Set cached result with TTL."""
        try:
            client = await self._get_client()
            await client.setex(f"cache:{cache_key}", ttl, json.dumps(data))
            return True
        except Exception:
            # Silent fail for cache operations
            return False

    async def invalidate_pattern(self, pattern: str):
        """Invalidate all cache entries matching pattern."""
        client = await self._get_client()
        keys = await client.keys(f"cache:{pattern}")
        if keys:
            await client.delete(*keys)
```

### Phase 3: Backup and Recovery Strategy

#### 3.1 **Selective Backup System**

**Database-Aware Backup Strategy**:
```python
# src/database/backup/selective_backup_system.py
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import asyncio
import gzip
import json

@dataclass
class BackupPolicy:
    database_id: int
    frequency: str  # 'real-time', 'hourly', 'daily', 'weekly'
    retention_days: int
    compression: bool
    incremental: bool
    priority: int  # 1=highest, 5=lowest

class SelectiveBackupSystem:
    def __init__(self):
        self.backup_policies: Dict[int, BackupPolicy] = {}
        self.backup_status: Dict[int, Dict[str, Any]] = {}

    def register_backup_policy(self, policy: BackupPolicy):
        """Register backup policy for a database."""
        self.backup_policies[policy.database_id] = policy
        self.backup_status[policy.database_id] = {
            "last_backup": None,
            "backup_count": 0,
            "last_error": None,
            "status": "ready"
        }

    async def execute_scheduled_backups(self):
        """Execute all scheduled backups based on policies."""
        for db_id, policy in self.backup_policies.items():
            if await self._should_execute_backup(db_id, policy):
                await self._execute_backup(db_id, policy)

    async def _should_execute_backup(self, db_id: int, policy: BackupPolicy) -> bool:
        """Check if backup should be executed based on policy."""
        status = self.backup_status[db_id]
        last_backup = status.get("last_backup")

        if not last_backup:
            return True

        now = datetime.utcnow()
        last_backup_time = datetime.fromisoformat(last_backup)

        if policy.frequency == "real-time":
            return True  # Always backup for real-time
        elif policy.frequency == "hourly":
            return now - last_backup_time >= timedelta(hours=1)
        elif policy.frequency == "daily":
            return now - last_backup_time >= timedelta(days=1)
        elif policy.frequency == "weekly":
            return now - last_backup_time >= timedelta(weeks=1)

        return False

    async def _execute_backup(self, db_id: int, policy: BackupPolicy):
        """Execute backup for specific database."""
        try:
            self.backup_status[db_id]["status"] = "backing_up"

            if policy.incremental and self._has_previous_backup(db_id):
                backup_result = await self._execute_incremental_backup(db_id, policy)
            else:
                backup_result = await self._execute_full_backup(db_id, policy)

            self.backup_status[db_id].update({
                "last_backup": datetime.utcnow().isoformat(),
                "backup_count": self.backup_status[db_id]["backup_count"] + 1,
                "status": "completed",
                "last_error": None
            })

        except Exception as e:
            self.backup_status[db_id].update({
                "status": "failed",
                "last_error": str(e)
            })
            logging.error(f"Backup failed for DB {db_id}: {str(e)}")

    async def _execute_full_backup(self, db_id: int, policy: BackupPolicy) -> Dict[str, Any]:
        """Execute full backup of database."""
        client = await redis_manager.get_client(db_id)

        # Get all keys
        all_keys = await client.keys("*")
        backup_data = {}

        # Export all data
        pipe = client.pipeline()
        for key in all_keys:
            pipe.dump(key)
            pipe.ttl(key)

        results = await pipe.execute()

        # Process results
        for i, key in enumerate(all_keys):
            dump_data = results[i * 2]
            ttl_data = results[i * 2 + 1]

            if dump_data:
                backup_data[key.decode()] = {
                    "data": dump_data,
                    "ttl": ttl_data if ttl_data > 0 else None
                }

        # Save backup
        backup_filename = f"backup_db{db_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

        if policy.compression:
            backup_filename += ".gz"
            with gzip.open(f"backups/{backup_filename}", 'wt') as f:
                json.dump(backup_data, f)
        else:
            with open(f"backups/{backup_filename}", 'w') as f:
                json.dump(backup_data, f)

        return {
            "type": "full",
            "filename": backup_filename,
            "key_count": len(all_keys),
            "compressed": policy.compression
        }

    async def restore_from_backup(self, db_id: int, backup_filename: str, selective_keys: List[str] = None):
        """Restore database from backup with optional key selection."""
        client = await redis_manager.get_client(db_id)

        # Load backup data
        if backup_filename.endswith('.gz'):
            with gzip.open(f"backups/{backup_filename}", 'rt') as f:
                backup_data = json.load(f)
        else:
            with open(f"backups/{backup_filename}", 'r') as f:
                backup_data = json.load(f)

        # Filter keys if selective restore
        if selective_keys:
            backup_data = {k: v for k, v in backup_data.items() if k in selective_keys}

        # Restore data
        pipe = client.pipeline()
        for key, data in backup_data.items():
            pipe.restore(key, data["ttl"] or 0, data["data"], replace=True)

        await pipe.execute()

        return {
            "restored_keys": len(backup_data),
            "selective": bool(selective_keys)
        }

# Initialize backup system with role-based policies
backup_system = SelectiveBackupSystem()

# Register backup policies for each database
backup_system.register_backup_policy(BackupPolicy(
    database_id=0,  # Core application
    frequency="real-time",
    retention_days=30,
    compression=True,
    incremental=True,
    priority=1
))

backup_system.register_backup_policy(BackupPolicy(
    database_id=1,  # Vectors
    frequency="daily",
    retention_days=7,
    compression=True,
    incremental=False,  # Full backup for vectors
    priority=2
))

backup_system.register_backup_policy(BackupPolicy(
    database_id=6,  # Cache
    frequency="none",  # No backup for cache
    retention_days=0,
    compression=False,
    incremental=False,
    priority=5
))
```

## Implementation Timeline

### Phase 1: Data Migration (Weeks 1-2)
- [ ] Implement migration engine with validation and rollback
- [ ] Execute DB 0 separation (vectors → DB 1, knowledge → DB 2)
- [ ] Validate data integrity and update application configurations
- [ ] Test selective backup and restore functionality

### Phase 2: Connection Optimization (Weeks 3-4)
- [ ] Implement role-based connection pool management
- [ ] Deploy optimized repositories with database-specific patterns
- [ ] Performance test different access patterns and optimize
- [ ] Implement health monitoring and alerting

### Phase 3: Advanced Features (Weeks 5-6)
- [ ] Deploy selective backup system with automated scheduling
- [ ] Implement cross-database consistency mechanisms
- [ ] Add database monitoring dashboard and metrics
- [ ] Performance tuning and optimization based on real usage

### Phase 4: Validation & Documentation (Weeks 7-8)
- [ ] Comprehensive testing of all database operations
- [ ] Performance benchmarking and capacity planning
- [ ] Update system documentation and operational procedures
- [ ] Training and knowledge transfer

## Success Metrics

### Reliability Improvements
- **Data Safety**: Eliminate single point of failure (DB 0 risk)
- **Recovery Time**: Reduce recovery time by 80% through selective restore
- **Backup Efficiency**: Reduce backup time by 60% through selective policies
- **Data Consistency**: Achieve 99.9% data consistency across databases

### Performance Metrics
- **Query Performance**: Improve query performance by 70% through optimized access patterns
- **Connection Efficiency**: Reduce connection overhead by 50% through pooling
- **Memory Usage**: Optimize memory usage by 40% through role-based configurations
- **Throughput**: Increase overall database throughput by 85%

### Operational Benefits
- **Maintenance Windows**: Reduce maintenance downtime by 90%
- **Monitoring Visibility**: Achieve 100% visibility into database performance
- **Scalability**: Enable independent scaling of different data types
- **Developer Productivity**: Reduce database-related debugging time by 65%

This comprehensive database architecture refactoring will transform AutoBot's data layer into a robust, scalable, and maintainable system optimized for the distributed 6-VM infrastructure.