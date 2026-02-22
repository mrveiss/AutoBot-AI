# Dynamic Service Discovery and Per-Node Configuration Design

> **Issue:** [#760](https://github.com/mrveiss/AutoBot-AI/issues/760)
> **Date:** 2026-02-02
> **Status:** Approved

## Overview

Add dynamic service discovery and per-node configuration to SLM, eliminating 506+ hardcoded IP references across the codebase. This is Phase 1 of a larger initiative.

## Database Models

### Extended Service Model

Adding to existing `Service` table in `models/database.py`:

```python
# Service Discovery Fields
port = Column(Integer, nullable=True)  # e.g., 8001, 6379
protocol = Column(String(10), default="http")  # http, https, ws, wss, redis, tcp
endpoint_path = Column(String(256), nullable=True)  # e.g., "/api/health"
is_discoverable = Column(Boolean, default=True)  # Include in discovery responses
```

### New NodeConfig Model

Key-value configuration per node with inheritance:

```python
class NodeConfig(Base):
    __tablename__ = "node_configs"

    id = Column(Integer, primary_key=True)
    node_id = Column(String(64), ForeignKey("nodes.node_id"), nullable=True)  # NULL = global default
    config_key = Column(String(128), index=True)  # e.g., "llm.provider", "llm.endpoint"
    config_value = Column(Text)
    value_type = Column(String(20), default="string")  # string, int, bool, json

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("node_id", "config_key", name="uq_node_config"),
        Index("ix_node_config_lookup", "node_id", "config_key"),
    )
```

**Key decision:** `node_id = NULL` represents global defaults.

### New ServiceConflict Model

Tracks services that can't coexist on the same node:

```python
class ServiceConflict(Base):
    __tablename__ = "service_conflicts"

    id = Column(Integer, primary_key=True)
    service_name_a = Column(String(128), index=True)  # e.g., "redis-server"
    service_name_b = Column(String(128), index=True)  # e.g., "redis-stack-server"
    reason = Column(Text)  # e.g., "Both bind to port 6379"
    conflict_type = Column(String(32), default="port")  # port, dependency, resource

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("service_name_a", "service_name_b", name="uq_service_conflict"),
    )
```

**Key decision:** Uses service names (not IDs) since conflicts are inherent to service types, not instances.

## API Endpoints

### Service Discovery Endpoints

New file `api/discovery.py`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/discover/{service_name}` | Returns first healthy instance |
| GET | `/api/discover` | Returns all discoverable services grouped by name |
| GET | `/api/discover/{service_name}/all` | Returns all instances (for load balancing) |

**Response example for `/api/discover/{service_name}`:**
```json
{
    "service_name": "autobot-backend",
    "host": "172.16.168.20",
    "port": 8001,
    "protocol": "http",
    "endpoint_path": "/api",
    "url": "https://172.16.168.20:8443/api",
    "healthy": true,
    "node_id": "node-main"
}
```

### Node Configuration Endpoints

Added to `api/nodes.py`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/nodes/{node_id}/config` | All config for node (merged with global) |
| GET | `/api/nodes/{node_id}/config/{key}` | Single config value |
| PUT | `/api/nodes/{node_id}/config/{key}` | Set config for node |
| DELETE | `/api/nodes/{node_id}/config/{key}` | Remove node override |

### Global Defaults Endpoints

New file `api/config.py`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config/defaults` | All global defaults |
| PUT | `/api/config/defaults/{key}` | Set global default |
| DELETE | `/api/config/defaults/{key}` | Remove global default |

### Service Conflicts Endpoints

Added to `api/services.py`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/services/conflicts` | List all conflicts |
| POST | `/api/services/conflicts` | Create conflict |
| DELETE | `/api/services/conflicts/{id}` | Delete conflict |
| GET | `/api/services/{service_name}/conflicts` | Conflicts for service |

## Configuration Resolution

### Resolution Order

1. Node-specific config (`node_id = given node`)
2. Global default (`node_id = NULL`)
3. Not configured (`None`)

```python
async def get_config(node_id: str, key: str) -> Optional[str]:
    # Check node-specific first
    node_config = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id == node_id,
            NodeConfig.config_key == key
        )
    )
    if result := node_config.scalar_one_or_none():
        return cast_value(result.config_value, result.value_type)

    # Fall back to global
    global_config = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id.is_(None),
            NodeConfig.config_key == key
        )
    )
    if result := global_config.scalar_one_or_none():
        return cast_value(result.config_value, result.value_type)

    return None
```

### LLM Config Keys (Standardized)

| Key | Example Values | Description |
|-----|---------------|-------------|
| `llm.provider` | `ollama`, `openai`, `anthropic` | Provider type |
| `llm.endpoint` | `http://127.0.0.1:11434` | API base URL |
| `llm.model` | `mistral:7b-instruct`, `gpt-4` | Default model |
| `llm.api_key` | `sk-...` | API key (encrypted at rest) |
| `llm.timeout` | `30` | Request timeout seconds |

### Bulk Config Fetch

```
GET /api/nodes/{node_id}/config?prefix=llm.
```

Returns all configs matching prefix in one call.

## Migration

### Migration Script

New file `migrations/add_service_discovery.py`:

1. Add columns to `services` table: `port`, `protocol`, `endpoint_path`, `is_discoverable`
2. Create `node_configs` table
3. Create `service_conflicts` table
4. Create indexes

### Seed Data: Known Service Conflicts

```python
KNOWN_CONFLICTS = [
    ("redis-server", "redis-stack-server", "Both bind to port 6379", "port"),
    ("apache2", "nginx", "Both bind to port 80/443", "port"),
    ("mysql-server", "mariadb-server", "Both bind to port 3306", "port"),
    ("postgresql-14", "postgresql-15", "Data directory conflicts", "resource"),
    ("docker", "podman", "Container runtime conflicts", "dependency"),
]
```

### Seed Data: Default Service Ports

```python
SERVICE_DEFAULTS = {
    "autobot-backend": {"port": 8001, "protocol": "http", "endpoint_path": "/api"},
    "autobot-frontend": {"port": 5173, "protocol": "http", "endpoint_path": "/"},
    "redis-server": {"port": 6379, "protocol": "redis"},
    "redis-stack-server": {"port": 6379, "protocol": "redis"},
    "slm-agent": {"port": 8000, "protocol": "http", "endpoint_path": "/api"},
    "ollama": {"port": 11434, "protocol": "http", "endpoint_path": "/api"},
    "playwright-server": {"port": 3000, "protocol": "http"},
}
```

## Pydantic Schemas

### Service Discovery

```python
class ServiceDiscoveryResponse(BaseModel):
    service_name: str
    host: str
    port: Optional[int]
    protocol: str
    endpoint_path: Optional[str]
    url: str
    healthy: bool
    node_id: str

class ServiceDiscoveryListResponse(BaseModel):
    services: Dict[str, List[ServiceDiscoveryResponse]]
```

### Node Configuration

```python
class NodeConfigResponse(BaseModel):
    node_id: Optional[str]
    config_key: str
    config_value: Any
    value_type: str
    is_global: bool

class NodeConfigSetRequest(BaseModel):
    value: Any
    value_type: str = "string"

class NodeConfigBulkResponse(BaseModel):
    node_id: str
    configs: Dict[str, Any]
```

### Service Conflicts

```python
class ServiceConflictResponse(BaseModel):
    id: int
    service_name_a: str
    service_name_b: str
    reason: Optional[str]
    conflict_type: str

class ServiceConflictCreateRequest(BaseModel):
    service_a: str
    service_b: str
    reason: Optional[str] = None
    conflict_type: str = "port"
```

## Implementation Summary

| Component | File | Changes |
|-----------|------|---------|
| **Models** | `models/database.py` | Add `NodeConfig`, `ServiceConflict` models; extend `Service` |
| **Schemas** | `models/schemas.py` | Add discovery/config/conflict schemas |
| **Discovery API** | `api/discovery.py` | New file with `/api/discover/*` endpoints |
| **Node Config API** | `api/nodes.py` | Add `/config` endpoints to existing router |
| **Global Config API** | `api/config.py` | New file with `/api/config/defaults/*` endpoints |
| **Conflicts API** | `api/services.py` | Add conflict endpoints to existing router |
| **Migration** | `migrations/add_service_discovery.py` | New migration script |
| **Main** | `main.py` | Register new routers |

## Acceptance Criteria

From issue #760:

- [ ] Moving backend to a different host requires only updating SLM, not code changes
- [ ] Each node can have different LLM provider configured via SLM UI
- [ ] Services discover each other via SLM API, not hardcoded IPs
- [ ] Frontend can query SLM to find backend URL dynamically
- [ ] Configuration changes propagate without service restarts (with reasonable TTL)
