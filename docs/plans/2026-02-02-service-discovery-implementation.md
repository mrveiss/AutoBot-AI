# Service Discovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add dynamic service discovery, per-node configuration, and service conflict tracking to SLM (#760)

**Architecture:** Extend existing Service model with discovery fields, add NodeConfig for key-value config with inheritance (node → global), add ServiceConflict for incompatible services. New API routers for discovery and config.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, Pydantic

---

## Task 1: Extend Service Model with Discovery Fields

**Files:**
- Modify: `slm-server/models/database.py:341-365`

**Step 1: Add discovery fields to Service model**

Add these columns after line 358 (after `extra_data`):

```python
    # Service Discovery Fields (Issue #760)
    port = Column(Integer, nullable=True)  # e.g., 8001, 6379
    protocol = Column(String(10), default="http")  # http, https, ws, wss, redis, tcp
    endpoint_path = Column(String(256), nullable=True)  # e.g., "/api/health"
    is_discoverable = Column(Boolean, default=True)  # Include in discovery responses
```

**Step 2: Verify syntax**

Run: `python -c "from slm_server.models.database import Service; print('OK')"`

**Step 3: Commit**

```bash
git add slm-server/models/database.py
git commit -m "feat(slm): add service discovery fields to Service model (#760)"
```

---

## Task 2: Add NodeConfig Model

**Files:**
- Modify: `slm-server/models/database.py` (add after Service model, ~line 366)

**Step 1: Add NodeConfig model**

```python
class NodeConfig(Base):
    """Per-node configuration with inheritance support (Issue #760).

    When node_id is NULL, the config is a global default.
    Resolution order: node-specific → global default → not found.
    """

    __tablename__ = "node_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String(64), nullable=True, index=True)  # NULL = global default
    config_key = Column(String(128), nullable=False, index=True)
    config_value = Column(Text, nullable=True)
    value_type = Column(String(20), default="string")  # string, int, bool, json

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("node_id", "config_key", name="uq_node_config"),
    )
```

**Step 2: Commit**

```bash
git add slm-server/models/database.py
git commit -m "feat(slm): add NodeConfig model for per-node configuration (#760)"
```

---

## Task 3: Add ServiceConflict Model

**Files:**
- Modify: `slm-server/models/database.py` (add after NodeConfig)

**Step 1: Add ServiceConflict model**

```python
class ServiceConflict(Base):
    """Tracks services that cannot coexist on the same node (Issue #760).

    Examples: redis-server vs redis-stack-server (port 6379),
    apache2 vs nginx (port 80/443).
    """

    __tablename__ = "service_conflicts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    service_name_a = Column(String(128), nullable=False, index=True)
    service_name_b = Column(String(128), nullable=False, index=True)
    reason = Column(Text, nullable=True)  # e.g., "Both bind to port 6379"
    conflict_type = Column(String(32), default="port")  # port, dependency, resource

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("service_name_a", "service_name_b", name="uq_service_conflict"),
    )
```

**Step 2: Commit**

```bash
git add slm-server/models/database.py
git commit -m "feat(slm): add ServiceConflict model for incompatible services (#760)"
```

---

## Task 4: Add Pydantic Schemas

**Files:**
- Modify: `slm-server/models/schemas.py` (add at end, before last blank line)

**Step 1: Add discovery and config schemas**

```python
# =============================================================================
# Service Discovery Schemas (Issue #760)
# =============================================================================


class ServiceDiscoveryResponse(BaseModel):
    """Single service discovery response."""

    service_name: str
    host: str
    port: Optional[int] = None
    protocol: str = "http"
    endpoint_path: Optional[str] = None
    url: str  # Fully constructed URL
    healthy: bool
    node_id: str


class ServiceDiscoveryListResponse(BaseModel):
    """All discoverable services grouped by name."""

    services: Dict[str, List[ServiceDiscoveryResponse]]


# =============================================================================
# Node Configuration Schemas (Issue #760)
# =============================================================================


class NodeConfigResponse(BaseModel):
    """Node configuration response."""

    id: int
    node_id: Optional[str] = None  # None = global default
    config_key: str
    config_value: Optional[str] = None
    value_type: str = "string"
    is_global: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NodeConfigSetRequest(BaseModel):
    """Request to set a configuration value."""

    value: str
    value_type: str = Field(default="string", pattern="^(string|int|bool|json)$")


class NodeConfigBulkResponse(BaseModel):
    """Bulk config response with casted values."""

    node_id: str
    configs: Dict[str, Optional[str]]  # key -> value


# =============================================================================
# Service Conflict Schemas (Issue #760)
# =============================================================================


class ServiceConflictResponse(BaseModel):
    """Service conflict response."""

    id: int
    service_name_a: str
    service_name_b: str
    reason: Optional[str] = None
    conflict_type: str = "port"
    created_at: datetime

    model_config = {"from_attributes": True}


class ServiceConflictCreateRequest(BaseModel):
    """Request to create a service conflict."""

    service_a: str = Field(..., min_length=1, max_length=128)
    service_b: str = Field(..., min_length=1, max_length=128)
    reason: Optional[str] = None
    conflict_type: str = Field(default="port", pattern="^(port|dependency|resource)$")


class ServiceConflictListResponse(BaseModel):
    """List of service conflicts."""

    conflicts: List[ServiceConflictResponse]
    total: int
```

**Step 2: Update imports at top of file**

Add `Any` to the typing imports if not present.

**Step 3: Commit**

```bash
git add slm-server/models/schemas.py
git commit -m "feat(slm): add schemas for discovery, config, and conflicts (#760)"
```

---

## Task 5: Create Migration Script

**Files:**
- Create: `slm-server/migrations/add_service_discovery.py`

**Step 1: Write migration script**

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add service discovery, node config, and service conflicts (Issue #760)

Adds:
- Discovery fields to services table (port, protocol, endpoint_path, is_discoverable)
- node_configs table for per-node configuration
- service_conflicts table for incompatible services

Run: python migrations/add_service_discovery.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Known service conflicts to seed
KNOWN_CONFLICTS = [
    ("redis-server", "redis-stack-server", "Both bind to port 6379", "port"),
    ("apache2", "nginx", "Both bind to port 80/443", "port"),
    ("mysql-server", "mariadb-server", "Both bind to port 3306", "port"),
    ("postgresql-14", "postgresql-15", "Data directory conflicts", "resource"),
    ("docker", "podman", "Container runtime conflicts", "dependency"),
]

# Default service ports for auto-population
SERVICE_DEFAULTS = {
    "autobot-backend": {"port": 8001, "protocol": "http", "endpoint_path": "/api"},
    "autobot-frontend": {"port": 5173, "protocol": "http", "endpoint_path": "/"},
    "redis-server": {"port": 6379, "protocol": "redis", "endpoint_path": None},
    "redis-stack-server": {"port": 6379, "protocol": "redis", "endpoint_path": None},
    "slm-agent": {"port": 8000, "protocol": "http", "endpoint_path": "/api"},
    "slm-backend": {"port": 8000, "protocol": "http", "endpoint_path": "/api"},
    "ollama": {"port": 11434, "protocol": "http", "endpoint_path": "/api"},
    "playwright-server": {"port": 3000, "protocol": "http", "endpoint_path": None},
    "grafana-server": {"port": 3000, "protocol": "http", "endpoint_path": "/"},
    "prometheus": {"port": 9090, "protocol": "http", "endpoint_path": "/"},
}


def add_column_if_not_exists(
    cursor: sqlite3.Cursor, table: str, column: str, column_def: str
) -> bool:
    """Add column if it doesn't exist. Returns True if added."""
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [col[1] for col in cursor.fetchall()]
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")
        return True
    return False


def migrate(db_path: str) -> None:
    """Run the migration."""
    logger.info("Running service discovery migration on: %s", db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Add discovery columns to services table
    logger.info("Adding discovery columns to services table...")
    added = []
    if add_column_if_not_exists(cursor, "services", "port", "INTEGER"):
        added.append("port")
    if add_column_if_not_exists(cursor, "services", "protocol", "VARCHAR(10) DEFAULT 'http'"):
        added.append("protocol")
    if add_column_if_not_exists(cursor, "services", "endpoint_path", "VARCHAR(256)"):
        added.append("endpoint_path")
    if add_column_if_not_exists(cursor, "services", "is_discoverable", "BOOLEAN DEFAULT 1"):
        added.append("is_discoverable")

    if added:
        logger.info("  Added columns: %s", ", ".join(added))
    else:
        logger.info("  All columns already exist")

    # 2. Create node_configs table
    logger.info("Creating node_configs table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS node_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id VARCHAR(64),
            config_key VARCHAR(128) NOT NULL,
            config_value TEXT,
            value_type VARCHAR(20) DEFAULT 'string',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(node_id, config_key)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_node_configs_node_id ON node_configs(node_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_node_configs_key ON node_configs(config_key)"
    )

    # 3. Create service_conflicts table
    logger.info("Creating service_conflicts table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS service_conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name_a VARCHAR(128) NOT NULL,
            service_name_b VARCHAR(128) NOT NULL,
            reason TEXT,
            conflict_type VARCHAR(32) DEFAULT 'port',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(service_name_a, service_name_b)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_service_conflicts_a ON service_conflicts(service_name_a)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_service_conflicts_b ON service_conflicts(service_name_b)"
    )

    # 4. Seed known conflicts
    logger.info("Seeding known service conflicts...")
    conflict_count = 0
    for service_a, service_b, reason, conflict_type in KNOWN_CONFLICTS:
        try:
            cursor.execute(
                """INSERT INTO service_conflicts
                   (service_name_a, service_name_b, reason, conflict_type)
                   VALUES (?, ?, ?, ?)""",
                (service_a, service_b, reason, conflict_type),
            )
            conflict_count += 1
        except sqlite3.IntegrityError:
            pass  # Already exists

    logger.info("  Seeded %d conflicts", conflict_count)

    # 5. Auto-populate service discovery fields for known services
    logger.info("Auto-populating discovery fields for known services...")
    updated_count = 0
    for service_name, defaults in SERVICE_DEFAULTS.items():
        cursor.execute(
            """UPDATE services
               SET port = COALESCE(port, ?),
                   protocol = COALESCE(protocol, ?),
                   endpoint_path = COALESCE(endpoint_path, ?)
               WHERE service_name = ? AND port IS NULL""",
            (
                defaults["port"],
                defaults["protocol"],
                defaults["endpoint_path"],
                service_name,
            ),
        )
        updated_count += cursor.rowcount

    logger.info("  Updated %d service records", updated_count)

    conn.commit()
    conn.close()

    logger.info("Migration complete!")


if __name__ == "__main__":
    db_path = Path(__file__).parent.parent / "data" / "slm.db"

    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])

    if not db_path.exists():
        logger.error("Database not found: %s", db_path)
        sys.exit(1)

    migrate(str(db_path))
```

**Step 2: Commit**

```bash
git add slm-server/migrations/add_service_discovery.py
git commit -m "feat(slm): add migration for service discovery tables (#760)"
```

---

## Task 6: Create Discovery API

**Files:**
- Create: `slm-server/api/discovery.py`

**Step 1: Write discovery API**

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Service Discovery API Routes (Issue #760)

Endpoints for discovering service locations dynamically.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import Node, Service, ServiceStatus
from models.schemas import ServiceDiscoveryListResponse, ServiceDiscoveryResponse
from services.auth import get_current_user
from services.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discover", tags=["discovery"])


def _build_service_url(node: Node, service: Service) -> str:
    """Build full URL for a service."""
    protocol = service.protocol or "http"
    host = node.ip_address
    port = service.port

    if port:
        base = f"{protocol}://{host}:{port}"
    else:
        base = f"{protocol}://{host}"

    if service.endpoint_path:
        return f"{base}{service.endpoint_path}"
    return base


@router.get("/{service_name}", response_model=ServiceDiscoveryResponse)
async def discover_service(
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    prefer_healthy: bool = Query(True, description="Prefer healthy instances"),
) -> ServiceDiscoveryResponse:
    """
    Discover a service by name.

    Returns the first available (preferably healthy) instance of the service.
    """
    # Find services with this name that are discoverable
    query = (
        select(Service, Node)
        .join(Node, Service.node_id == Node.node_id)
        .where(
            Service.service_name == service_name,
            Service.is_discoverable.is_(True),
        )
    )

    if prefer_healthy:
        # Order by running status first
        query = query.order_by(
            (Service.status == ServiceStatus.RUNNING.value).desc(),
            Node.hostname,
        )

    result = await db.execute(query)
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_name}' not found or not discoverable",
        )

    service, node = row
    is_healthy = service.status == ServiceStatus.RUNNING.value

    return ServiceDiscoveryResponse(
        service_name=service.service_name,
        host=node.ip_address,
        port=service.port,
        protocol=service.protocol or "http",
        endpoint_path=service.endpoint_path,
        url=_build_service_url(node, service),
        healthy=is_healthy,
        node_id=node.node_id,
    )


@router.get("/{service_name}/all")
async def discover_service_all(
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """
    Discover all instances of a service.

    Returns all instances for load balancing or failover scenarios.
    """
    query = (
        select(Service, Node)
        .join(Node, Service.node_id == Node.node_id)
        .where(
            Service.service_name == service_name,
            Service.is_discoverable.is_(True),
        )
        .order_by(Node.hostname)
    )

    result = await db.execute(query)
    rows = result.all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_name}' not found or not discoverable",
        )

    instances = []
    for service, node in rows:
        is_healthy = service.status == ServiceStatus.RUNNING.value
        instances.append(
            ServiceDiscoveryResponse(
                service_name=service.service_name,
                host=node.ip_address,
                port=service.port,
                protocol=service.protocol or "http",
                endpoint_path=service.endpoint_path,
                url=_build_service_url(node, service),
                healthy=is_healthy,
                node_id=node.node_id,
            )
        )

    return {"instances": instances, "total": len(instances)}


@router.get("", response_model=ServiceDiscoveryListResponse)
async def discover_all_services(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    healthy_only: bool = Query(False, description="Only return healthy services"),
) -> ServiceDiscoveryListResponse:
    """
    Discover all services.

    Returns all discoverable services grouped by service name.
    """
    query = (
        select(Service, Node)
        .join(Node, Service.node_id == Node.node_id)
        .where(Service.is_discoverable.is_(True))
    )

    if healthy_only:
        query = query.where(Service.status == ServiceStatus.RUNNING.value)

    query = query.order_by(Service.service_name, Node.hostname)

    result = await db.execute(query)
    rows = result.all()

    # Group by service name
    services_map: dict = {}
    for service, node in rows:
        if service.service_name not in services_map:
            services_map[service.service_name] = []

        is_healthy = service.status == ServiceStatus.RUNNING.value
        services_map[service.service_name].append(
            ServiceDiscoveryResponse(
                service_name=service.service_name,
                host=node.ip_address,
                port=service.port,
                protocol=service.protocol or "http",
                endpoint_path=service.endpoint_path,
                url=_build_service_url(node, service),
                healthy=is_healthy,
                node_id=node.node_id,
            )
        )

    return ServiceDiscoveryListResponse(services=services_map)
```

**Step 2: Commit**

```bash
git add slm-server/api/discovery.py
git commit -m "feat(slm): add service discovery API endpoints (#760)"
```

---

## Task 7: Create Node Config API

**Files:**
- Create: `slm-server/api/config.py`

**Step 1: Write config API**

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Configuration API Routes (Issue #760)

Endpoints for managing per-node and global configuration.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import Node, NodeConfig
from models.schemas import (
    NodeConfigBulkResponse,
    NodeConfigResponse,
    NodeConfigSetRequest,
)
from services.auth import get_current_user
from services.database import get_db

logger = logging.getLogger(__name__)

# Router for global defaults
router = APIRouter(prefix="/config", tags=["configuration"])

# Router for node-specific config (added to nodes router separately)
node_config_router = APIRouter(tags=["node-configuration"])


def _cast_config_value(value: Optional[str], value_type: str):
    """Cast config value to appropriate type."""
    if value is None:
        return None

    if value_type == "int":
        return int(value)
    elif value_type == "bool":
        return value.lower() in ("true", "1", "yes")
    elif value_type == "json":
        return json.loads(value)
    return value


async def _get_config_with_fallback(
    db: AsyncSession, node_id: str, key: str
) -> Optional[NodeConfig]:
    """Get config for node, falling back to global default."""
    # Check node-specific first
    result = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id == node_id,
            NodeConfig.config_key == key,
        )
    )
    config = result.scalar_one_or_none()
    if config:
        return config

    # Fall back to global
    result = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id.is_(None),
            NodeConfig.config_key == key,
        )
    )
    return result.scalar_one_or_none()


# =============================================================================
# Global Defaults Endpoints
# =============================================================================


@router.get("/defaults")
async def get_global_defaults(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    prefix: Optional[str] = Query(None, description="Filter by key prefix"),
) -> dict:
    """Get all global default configurations."""
    query = select(NodeConfig).where(NodeConfig.node_id.is_(None))

    if prefix:
        query = query.where(NodeConfig.config_key.startswith(prefix))

    query = query.order_by(NodeConfig.config_key)
    result = await db.execute(query)
    configs = result.scalars().all()

    return {
        "configs": [
            NodeConfigResponse(
                id=c.id,
                node_id=None,
                config_key=c.config_key,
                config_value=c.config_value,
                value_type=c.value_type,
                is_global=True,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in configs
        ],
        "total": len(configs),
    }


@router.get("/defaults/{key}")
async def get_global_default(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeConfigResponse:
    """Get a specific global default configuration."""
    result = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id.is_(None),
            NodeConfig.config_key == key,
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Global config '{key}' not found",
        )

    return NodeConfigResponse(
        id=config.id,
        node_id=None,
        config_key=config.config_key,
        config_value=config.config_value,
        value_type=config.value_type,
        is_global=True,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.put("/defaults/{key}")
async def set_global_default(
    key: str,
    request: NodeConfigSetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeConfigResponse:
    """Set a global default configuration."""
    result = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id.is_(None),
            NodeConfig.config_key == key,
        )
    )
    config = result.scalar_one_or_none()

    if config:
        config.config_value = request.value
        config.value_type = request.value_type
        config.updated_at = datetime.utcnow()
    else:
        config = NodeConfig(
            node_id=None,
            config_key=key,
            config_value=request.value,
            value_type=request.value_type,
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)

    logger.info("Global config '%s' set to '%s'", key, request.value)

    return NodeConfigResponse(
        id=config.id,
        node_id=None,
        config_key=config.config_key,
        config_value=config.config_value,
        value_type=config.value_type,
        is_global=True,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.delete("/defaults/{key}")
async def delete_global_default(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Delete a global default configuration."""
    result = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id.is_(None),
            NodeConfig.config_key == key,
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Global config '{key}' not found",
        )

    await db.delete(config)
    await db.commit()

    logger.info("Global config '%s' deleted", key)

    return {"message": f"Global config '{key}' deleted", "key": key}


# =============================================================================
# Node-Specific Config Endpoints (to be added to nodes router)
# =============================================================================


@node_config_router.get("/{node_id}/config")
async def get_node_config(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    prefix: Optional[str] = Query(None, description="Filter by key prefix"),
    include_globals: bool = Query(True, description="Include global defaults"),
) -> NodeConfigBulkResponse:
    """
    Get all configuration for a node.

    Returns node-specific configs merged with global defaults.
    """
    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    if not node_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    configs: dict = {}

    # Get global defaults first (if requested)
    if include_globals:
        query = select(NodeConfig).where(NodeConfig.node_id.is_(None))
        if prefix:
            query = query.where(NodeConfig.config_key.startswith(prefix))
        result = await db.execute(query)
        for config in result.scalars().all():
            configs[config.config_key] = config.config_value

    # Get node-specific configs (overwrite globals)
    query = select(NodeConfig).where(NodeConfig.node_id == node_id)
    if prefix:
        query = query.where(NodeConfig.config_key.startswith(prefix))
    result = await db.execute(query)
    for config in result.scalars().all():
        configs[config.config_key] = config.config_value

    return NodeConfigBulkResponse(node_id=node_id, configs=configs)


@node_config_router.get("/{node_id}/config/{key}")
async def get_node_config_key(
    node_id: str,
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeConfigResponse:
    """Get a specific config for a node (with fallback to global)."""
    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    if not node_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    config = await _get_config_with_fallback(db, node_id, key)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Config '{key}' not found for node or globally",
        )

    return NodeConfigResponse(
        id=config.id,
        node_id=config.node_id,
        config_key=config.config_key,
        config_value=config.config_value,
        value_type=config.value_type,
        is_global=config.node_id is None,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@node_config_router.put("/{node_id}/config/{key}")
async def set_node_config_key(
    node_id: str,
    key: str,
    request: NodeConfigSetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeConfigResponse:
    """Set a config for a specific node."""
    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    if not node_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Check for existing node-specific config
    result = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id == node_id,
            NodeConfig.config_key == key,
        )
    )
    config = result.scalar_one_or_none()

    if config:
        config.config_value = request.value
        config.value_type = request.value_type
        config.updated_at = datetime.utcnow()
    else:
        config = NodeConfig(
            node_id=node_id,
            config_key=key,
            config_value=request.value,
            value_type=request.value_type,
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)

    logger.info("Node %s config '%s' set to '%s'", node_id, key, request.value)

    return NodeConfigResponse(
        id=config.id,
        node_id=config.node_id,
        config_key=config.config_key,
        config_value=config.config_value,
        value_type=config.value_type,
        is_global=False,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@node_config_router.delete("/{node_id}/config/{key}")
async def delete_node_config_key(
    node_id: str,
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Delete node-specific config (falls back to global if exists)."""
    result = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id == node_id,
            NodeConfig.config_key == key,
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node-specific config '{key}' not found",
        )

    await db.delete(config)
    await db.commit()

    logger.info("Node %s config '%s' deleted", node_id, key)

    return {
        "message": f"Node config '{key}' deleted (will use global default if exists)",
        "node_id": node_id,
        "key": key,
    }
```

**Step 2: Commit**

```bash
git add slm-server/api/config.py
git commit -m "feat(slm): add node and global config API endpoints (#760)"
```

---

## Task 8: Add Service Conflicts Endpoints

**Files:**
- Modify: `slm-server/api/services.py` (add at end of file before fleet_router section)

**Step 1: Add conflict endpoints to services router**

Add after the `restart_all_node_services` endpoint (around line 691), before the fleet_router section:

```python
# =============================================================================
# Service Conflicts endpoints (Issue #760)
# =============================================================================


from models.database import ServiceConflict
from models.schemas import (
    ServiceConflictCreateRequest,
    ServiceConflictListResponse,
    ServiceConflictResponse,
)


@router.get("/conflicts", response_model=ServiceConflictListResponse)
async def list_service_conflicts(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceConflictListResponse:
    """List all known service conflicts."""
    result = await db.execute(
        select(ServiceConflict).order_by(ServiceConflict.service_name_a)
    )
    conflicts = result.scalars().all()

    return ServiceConflictListResponse(
        conflicts=[ServiceConflictResponse.model_validate(c) for c in conflicts],
        total=len(conflicts),
    )


@router.post("/conflicts", response_model=ServiceConflictResponse, status_code=201)
async def create_service_conflict(
    request: ServiceConflictCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceConflictResponse:
    """Create a new service conflict."""
    # Normalize order (alphabetical) to prevent duplicates
    service_a, service_b = sorted([request.service_a, request.service_b])

    # Check if already exists
    result = await db.execute(
        select(ServiceConflict).where(
            ServiceConflict.service_name_a == service_a,
            ServiceConflict.service_name_b == service_b,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict already exists",
        )

    conflict = ServiceConflict(
        service_name_a=service_a,
        service_name_b=service_b,
        reason=request.reason,
        conflict_type=request.conflict_type,
    )
    db.add(conflict)
    await db.commit()
    await db.refresh(conflict)

    logger.info(
        "Created service conflict: %s <-> %s (%s)",
        service_a,
        service_b,
        request.conflict_type,
    )

    return ServiceConflictResponse.model_validate(conflict)


@router.delete("/conflicts/{conflict_id}")
async def delete_service_conflict(
    conflict_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Delete a service conflict."""
    result = await db.execute(
        select(ServiceConflict).where(ServiceConflict.id == conflict_id)
    )
    conflict = result.scalar_one_or_none()

    if not conflict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conflict not found",
        )

    await db.delete(conflict)
    await db.commit()

    logger.info(
        "Deleted service conflict: %s <-> %s",
        conflict.service_name_a,
        conflict.service_name_b,
    )

    return {"message": "Conflict deleted", "id": conflict_id}


@router.get("/{service_name}/conflicts")
async def get_service_conflicts(
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceConflictListResponse:
    """Get all conflicts for a specific service."""
    result = await db.execute(
        select(ServiceConflict).where(
            (ServiceConflict.service_name_a == service_name)
            | (ServiceConflict.service_name_b == service_name)
        )
    )
    conflicts = result.scalars().all()

    return ServiceConflictListResponse(
        conflicts=[ServiceConflictResponse.model_validate(c) for c in conflicts],
        total=len(conflicts),
    )
```

**Step 2: Add imports at top of services.py**

Add `ServiceConflict` to the imports from models.database, and add the new schema imports.

**Step 3: Commit**

```bash
git add slm-server/api/services.py
git commit -m "feat(slm): add service conflicts API endpoints (#760)"
```

---

## Task 9: Register New Routers

**Files:**
- Modify: `slm-server/api/__init__.py`
- Modify: `slm-server/main.py`

**Step 1: Update api/__init__.py**

Add after line 12:

```python
from .config import node_config_router, router as config_router
from .discovery import router as discovery_router
```

Add to `__all__` list:

```python
    "config_router",
    "node_config_router",
    "discovery_router",
```

**Step 2: Update main.py imports**

Add to the imports (around line 18):

```python
    config_router,
    discovery_router,
    node_config_router,
```

**Step 3: Register routers in main.py**

Add after line 146:

```python
app.include_router(discovery_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(node_config_router, prefix="/api/nodes")
```

**Step 4: Commit**

```bash
git add slm-server/api/__init__.py slm-server/main.py
git commit -m "feat(slm): register discovery and config routers (#760)"
```

---

## Task 10: Update ServiceResponse Schema

**Files:**
- Modify: `slm-server/models/schemas.py:547-565`

**Step 1: Add discovery fields to ServiceResponse**

Add after line 561 (after `memory_bytes`):

```python
    # Discovery fields (Issue #760)
    port: Optional[int] = None
    protocol: str = "http"
    endpoint_path: Optional[str] = None
    is_discoverable: bool = True
```

**Step 2: Commit**

```bash
git add slm-server/models/schemas.py
git commit -m "feat(slm): add discovery fields to ServiceResponse schema (#760)"
```

---

## Task 11: Run Migration and Test

**Step 1: Run migration**

```bash
cd slm-server && python migrations/add_service_discovery.py
```

Expected output: Migration complete with columns added and conflicts seeded.

**Step 2: Start SLM server**

```bash
cd slm-server && python main.py
```

Expected: Server starts without errors.

**Step 3: Test discovery endpoint**

```bash
curl -X GET http://localhost:8000/api/discover -H "Authorization: Bearer <token>"
```

Expected: Returns discoverable services.

**Step 4: Test config endpoint**

```bash
curl -X PUT http://localhost:8000/api/config/defaults/llm.provider \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"value": "ollama", "value_type": "string"}'
```

Expected: 200 OK with config response.

**Step 5: Test conflicts endpoint**

```bash
curl -X GET http://localhost:8000/api/nodes/conflicts -H "Authorization: Bearer <token>"
```

Expected: Returns seeded conflicts.

---

## Task 12: Final Commit and Update Issue

**Step 1: Final verification commit**

```bash
git add -A
git status
```

Ensure all changes are staged properly.

**Step 2: Update GitHub issue with progress**

Add comment to issue #760 with Phase 1 completion status.
