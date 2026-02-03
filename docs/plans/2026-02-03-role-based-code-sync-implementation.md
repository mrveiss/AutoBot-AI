# Role-Based Code Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement centralized, role-based code distribution with SLM as orchestrator, per-role version tracking, and auto-discovery.

**Architecture:** Hub-and-spoke model where code-source node (git-connected) notifies SLM of changes, SLM pulls and caches code, then distributes to fleet nodes based on their assigned roles.

**Tech Stack:** Python/FastAPI (backend), SQLAlchemy (database), Vue 3/TypeScript (frontend), rsync (sync), systemd (services)

**GitHub Issue:** #779

---

## Phase 1: Database Foundation

### Task 1.1: Add Role Model

**Files:**
- Modify: `slm-server/models/database.py`

**Step 1: Add RoleStatus enum and Role model**

Add after `CodeStatus` enum (~line 69):

```python
class RoleStatus(str, enum.Enum):
    """Role detection status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    NOT_INSTALLED = "not_installed"


class SyncType(str, enum.Enum):
    """Code sync type."""

    COMPONENT = "component"
    PACKAGE = "package"
```

Add after `UpdateSchedule` class (end of file):

```python
class Role(Base):
    """Role definition for code distribution (Issue #779)."""

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100), nullable=True)
    sync_type = Column(String(20), default=SyncType.COMPONENT.value)
    source_paths = Column(JSON, nullable=False, default=list)
    target_path = Column(String(255), nullable=False)
    systemd_service = Column(String(100), nullable=True)
    auto_restart = Column(Boolean, default=False)
    health_check_port = Column(Integer, nullable=True)
    health_check_path = Column(String(255), nullable=True)
    pre_sync_cmd = Column(Text, nullable=True)
    post_sync_cmd = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**Step 2: Commit**

```bash
git add slm-server/models/database.py
git commit -m "feat(#779): add Role model for code distribution"
```

---

### Task 1.2: Add NodeRole Model

**Files:**
- Modify: `slm-server/models/database.py`

**Step 1: Add NodeRole model**

Add after `Role` class:

```python
class NodeRole(Base):
    """Node-role assignment with version tracking (Issue #779)."""

    __tablename__ = "node_roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String(64), nullable=False, index=True)
    role_name = Column(String(50), nullable=False, index=True)
    assignment_type = Column(String(20), default="auto")  # auto | manual
    status = Column(String(20), default=RoleStatus.NOT_INSTALLED.value)
    current_version = Column(String(64), nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("node_id", "role_name", name="uq_node_role"),
    )
```

**Step 2: Commit**

```bash
git add slm-server/models/database.py
git commit -m "feat(#779): add NodeRole model for assignment tracking"
```

---

### Task 1.3: Add CodeSource Model

**Files:**
- Modify: `slm-server/models/database.py`

**Step 1: Add CodeSource model**

Add after `NodeRole` class:

```python
class CodeSource(Base):
    """Code source node configuration (Issue #779)."""

    __tablename__ = "code_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String(64), nullable=False, index=True)
    is_active = Column(Boolean, default=False)
    repo_path = Column(String(255), nullable=False)
    branch = Column(String(100), default="main")
    last_known_commit = Column(String(64), nullable=True)
    last_notified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**Step 2: Commit**

```bash
git add slm-server/models/database.py
git commit -m "feat(#779): add CodeSource model for git-connected nodes"
```

---

### Task 1.4: Extend Node Model

**Files:**
- Modify: `slm-server/models/database.py`

**Step 1: Add new columns to Node model**

Add after `code_status` field (~line 101):

```python
    # Role-based tracking (Issue #779)
    detected_roles = Column(JSON, default=list)
    listening_ports = Column(JSON, default=list)
    role_versions = Column(JSON, default=dict)
```

**Step 2: Commit**

```bash
git add slm-server/models/database.py
git commit -m "feat(#779): extend Node model with role tracking fields"
```

---

### Task 1.5: Create Database Migration

**Files:**
- Create: `slm-server/migrations/versions/xxxx_add_role_based_code_sync.py`

**Step 1: Generate migration**

```bash
cd slm-server && alembic revision --autogenerate -m "add_role_based_code_sync"
```

**Step 2: Apply migration**

```bash
cd slm-server && alembic upgrade head
```

**Step 3: Commit**

```bash
git add slm-server/migrations/
git commit -m "feat(#779): add database migration for role-based code sync"
```

---

## Phase 2: Role Registry Service

### Task 2.1: Create Role Registry Service

**Files:**
- Create: `slm-server/services/role_registry.py`

**Step 1: Create role_registry.py**

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Role Registry Service (Issue #779).

Manages role definitions and provides default roles for code distribution.
"""

import logging
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Role, SyncType

logger = logging.getLogger(__name__)

DEFAULT_ROLES = [
    {
        "name": "code-source",
        "display_name": "Code Source",
        "sync_type": None,
        "source_paths": [],
        "target_path": "",
        "auto_restart": False,
    },
    {
        "name": "backend",
        "display_name": "Backend API",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["backend/", "src/"],
        "target_path": "/home/autobot/AutoBot",
        "systemd_service": "autobot-backend",
        "auto_restart": False,
        "health_check_port": 8001,
        "health_check_path": "/api/health",
    },
    {
        "name": "frontend",
        "display_name": "Frontend UI",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-vue/"],
        "target_path": "/home/autobot/autobot-vue",
        "systemd_service": "autobot-frontend",
        "auto_restart": True,
        "health_check_port": 5173,
        "post_sync_cmd": "cd /home/autobot/autobot-vue && npm install",
    },
    {
        "name": "slm-server",
        "display_name": "SLM Server",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["slm-server/", "slm-admin/"],
        "target_path": "/home/autobot/AutoBot",
        "systemd_service": "slm-backend",
        "auto_restart": False,
        "health_check_port": 8000,
        "health_check_path": "/api/health",
    },
    {
        "name": "slm-agent",
        "display_name": "SLM Agent",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["src/slm/agent/"],
        "target_path": "/opt/slm-agent",
        "systemd_service": "slm-agent",
        "auto_restart": True,
    },
    {
        "name": "npu-worker",
        "display_name": "NPU Worker",
        "sync_type": SyncType.PACKAGE.value,
        "source_paths": ["resources/windows-npu-worker/"],
        "target_path": "C:\\AutoBot\\npu-worker",
        "auto_restart": False,
        "health_check_port": 8081,
    },
    {
        "name": "browser-service",
        "display_name": "Browser Automation",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["browser-service/"],
        "target_path": "/home/autobot/browser-service",
        "systemd_service": "autobot-browser",
        "auto_restart": True,
        "health_check_port": 3000,
    },
]


async def seed_default_roles(db: AsyncSession) -> int:
    """Seed default roles if they don't exist."""
    created = 0
    for role_data in DEFAULT_ROLES:
        result = await db.execute(
            select(Role).where(Role.name == role_data["name"])
        )
        if not result.scalar_one_or_none():
            role = Role(**role_data)
            db.add(role)
            created += 1
            logger.info("Created default role: %s", role_data["name"])

    if created > 0:
        await db.commit()

    return created


async def get_role(db: AsyncSession, role_name: str) -> Optional[Role]:
    """Get role by name."""
    result = await db.execute(select(Role).where(Role.name == role_name))
    return result.scalar_one_or_none()


async def list_roles(db: AsyncSession) -> List[Role]:
    """List all roles."""
    result = await db.execute(select(Role).order_by(Role.name))
    return list(result.scalars().all())


async def get_role_definitions() -> List[Dict]:
    """Get lightweight role definitions for agents."""
    return [
        {
            "name": r["name"],
            "target_path": r["target_path"],
            "systemd_service": r.get("systemd_service"),
            "health_check_port": r.get("health_check_port"),
        }
        for r in DEFAULT_ROLES
        if r.get("target_path")
    ]
```

**Step 2: Commit**

```bash
git add slm-server/services/role_registry.py
git commit -m "feat(#779): add role registry service with defaults"
```

---

### Task 2.2: Create Roles API

**Files:**
- Create: `slm-server/api/roles.py`

**Step 1: Create roles.py**

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Roles API Routes (Issue #779).

CRUD endpoints for role definitions.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import Role, SyncType
from services.auth import get_current_user
from services.database import get_db
from services.role_registry import get_role_definitions, list_roles

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/roles", tags=["roles"])


class RoleResponse(BaseModel):
    """Role response schema."""

    name: str
    display_name: str | None
    sync_type: str | None
    source_paths: list
    target_path: str
    systemd_service: str | None
    auto_restart: bool
    health_check_port: int | None
    health_check_path: str | None
    pre_sync_cmd: str | None
    post_sync_cmd: str | None

    class Config:
        from_attributes = True


class RoleCreate(BaseModel):
    """Role creation schema."""

    name: str = Field(..., min_length=1, max_length=50)
    display_name: str | None = None
    sync_type: str = SyncType.COMPONENT.value
    source_paths: list = Field(default_factory=list)
    target_path: str = Field(..., min_length=1)
    systemd_service: str | None = None
    auto_restart: bool = False
    health_check_port: int | None = None
    health_check_path: str | None = None
    pre_sync_cmd: str | None = None
    post_sync_cmd: str | None = None


class RoleUpdate(BaseModel):
    """Role update schema."""

    display_name: str | None = None
    sync_type: str | None = None
    source_paths: list | None = None
    target_path: str | None = None
    systemd_service: str | None = None
    auto_restart: bool | None = None
    health_check_port: int | None = None
    health_check_path: str | None = None
    pre_sync_cmd: str | None = None
    post_sync_cmd: str | None = None


@router.get("", response_model=List[RoleResponse])
async def get_roles(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> List[RoleResponse]:
    """List all role definitions."""
    roles = await list_roles(db)
    return [RoleResponse.model_validate(r) for r in roles]


@router.get("/definitions")
async def get_definitions_for_agents() -> List[dict]:
    """
    Get lightweight role definitions for agents.

    No authentication required - agents use this to know what to detect.
    """
    return await get_role_definitions()


@router.get("/{role_name}", response_model=RoleResponse)
async def get_role_by_name(
    role_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> RoleResponse:
    """Get a specific role by name."""
    result = await db.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role not found: {role_name}",
        )

    return RoleResponse.model_validate(role)


@router.post("", response_model=RoleResponse)
async def create_role(
    role_data: RoleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> RoleResponse:
    """Create a new role definition."""
    # Check if exists
    result = await db.execute(select(Role).where(Role.name == role_data.name))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Role already exists: {role_data.name}",
        )

    role = Role(**role_data.model_dump())
    db.add(role)
    await db.commit()
    await db.refresh(role)

    logger.info("Created role: %s", role.name)
    return RoleResponse.model_validate(role)


@router.put("/{role_name}", response_model=RoleResponse)
async def update_role(
    role_name: str,
    role_data: RoleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> RoleResponse:
    """Update a role definition."""
    result = await db.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role not found: {role_name}",
        )

    for field, value in role_data.model_dump(exclude_unset=True).items():
        setattr(role, field, value)

    await db.commit()
    await db.refresh(role)

    logger.info("Updated role: %s", role.name)
    return RoleResponse.model_validate(role)


@router.delete("/{role_name}")
async def delete_role(
    role_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Delete a role definition."""
    result = await db.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role not found: {role_name}",
        )

    await db.delete(role)
    await db.commit()

    logger.info("Deleted role: %s", role_name)
    return {"success": True, "message": f"Role '{role_name}' deleted"}
```

**Step 2: Commit**

```bash
git add slm-server/api/roles.py
git commit -m "feat(#779): add roles API endpoints"
```

---

### Task 2.3: Register Roles Router

**Files:**
- Modify: `slm-server/main.py`

**Step 1: Import and register router**

Add import:

```python
from api.roles import router as roles_router
```

Add registration (after other routers):

```python
app.include_router(roles_router, prefix="/api")
```

**Step 2: Add role seeding to startup**

In the lifespan function, add after database initialization:

```python
    # Seed default roles (Issue #779)
    from services.role_registry import seed_default_roles
    async with db_service.session() as db:
        created = await seed_default_roles(db)
        if created > 0:
            logger.info("Seeded %d default roles", created)
```

**Step 3: Commit**

```bash
git add slm-server/main.py
git commit -m "feat(#779): register roles router and seed defaults on startup"
```

---

## Phase 3: Code Source Management

### Task 3.1: Create Code Source API

**Files:**
- Create: `slm-server/api/code_source.py`

**Step 1: Create code_source.py**

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Source API Routes (Issue #779).

Manages the code-source node assignment and git notifications.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import CodeSource, Node, NodeRole, RoleStatus
from services.auth import get_current_user
from services.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/code-source", tags=["code-source"])


class CodeSourceResponse(BaseModel):
    """Code source configuration response."""

    node_id: str
    hostname: str | None
    ip_address: str | None
    repo_path: str
    branch: str
    last_known_commit: str | None
    last_notified_at: datetime | None
    is_active: bool

    class Config:
        from_attributes = True


class CodeSourceAssign(BaseModel):
    """Assign code-source to a node."""

    node_id: str
    repo_path: str = "/home/kali/Desktop/AutoBot"
    branch: str = "main"


class CodeNotification(BaseModel):
    """Git commit notification from code-source."""

    node_id: str
    commit: str
    branch: str = "main"
    message: str | None = None
    is_code_source: bool = True


class CodeNotificationResponse(BaseModel):
    """Response to code notification."""

    success: bool
    message: str
    commit: str
    outdated_nodes: int = 0


@router.get("", response_model=Optional[CodeSourceResponse])
async def get_active_code_source(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> Optional[CodeSourceResponse]:
    """Get the active code source configuration."""
    result = await db.execute(
        select(CodeSource).where(CodeSource.is_active == True)  # noqa: E712
    )
    source = result.scalar_one_or_none()

    if not source:
        return None

    # Get node info
    node_result = await db.execute(
        select(Node).where(Node.node_id == source.node_id)
    )
    node = node_result.scalar_one_or_none()

    return CodeSourceResponse(
        node_id=source.node_id,
        hostname=node.hostname if node else None,
        ip_address=node.ip_address if node else None,
        repo_path=source.repo_path,
        branch=source.branch,
        last_known_commit=source.last_known_commit,
        last_notified_at=source.last_notified_at,
        is_active=source.is_active,
    )


@router.post("/assign", response_model=CodeSourceResponse)
async def assign_code_source(
    data: CodeSourceAssign,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> CodeSourceResponse:
    """Assign a node as code-source."""
    # Verify node exists
    node_result = await db.execute(
        select(Node).where(Node.node_id == data.node_id)
    )
    node = node_result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node not found: {data.node_id}",
        )

    # Deactivate any existing code-source
    existing_result = await db.execute(
        select(CodeSource).where(CodeSource.is_active == True)  # noqa: E712
    )
    for existing in existing_result.scalars().all():
        existing.is_active = False

    # Check if this node already has a code-source record
    source_result = await db.execute(
        select(CodeSource).where(CodeSource.node_id == data.node_id)
    )
    source = source_result.scalar_one_or_none()

    if source:
        source.is_active = True
        source.repo_path = data.repo_path
        source.branch = data.branch
    else:
        source = CodeSource(
            node_id=data.node_id,
            repo_path=data.repo_path,
            branch=data.branch,
            is_active=True,
        )
        db.add(source)

    # Add code-source role to node
    role_result = await db.execute(
        select(NodeRole).where(
            NodeRole.node_id == data.node_id,
            NodeRole.role_name == "code-source",
        )
    )
    node_role = role_result.scalar_one_or_none()

    if not node_role:
        node_role = NodeRole(
            node_id=data.node_id,
            role_name="code-source",
            assignment_type="manual",
            status=RoleStatus.ACTIVE.value,
        )
        db.add(node_role)

    await db.commit()
    await db.refresh(source)

    logger.info("Assigned code-source to node: %s", data.node_id)

    return CodeSourceResponse(
        node_id=source.node_id,
        hostname=node.hostname,
        ip_address=node.ip_address,
        repo_path=source.repo_path,
        branch=source.branch,
        last_known_commit=source.last_known_commit,
        last_notified_at=source.last_notified_at,
        is_active=source.is_active,
    )


@router.delete("/assign")
async def remove_code_source(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Remove the active code-source assignment."""
    result = await db.execute(
        select(CodeSource).where(CodeSource.is_active == True)  # noqa: E712
    )
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active code-source",
        )

    source.is_active = False
    await db.commit()

    logger.info("Removed code-source from node: %s", source.node_id)
    return {"success": True, "message": "Code-source removed"}


@router.post("/notify", response_model=CodeNotificationResponse)
async def notify_new_commit(
    notification: CodeNotification,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CodeNotificationResponse:
    """
    Receive notification of new commit from code-source.

    Called by git post-commit hook. No authentication - uses node_id.
    """
    # Verify this is from an active code-source
    source_result = await db.execute(
        select(CodeSource).where(
            CodeSource.node_id == notification.node_id,
            CodeSource.is_active == True,  # noqa: E712
        )
    )
    source = source_result.scalar_one_or_none()

    if not source:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Node is not an active code-source",
        )

    # Update source with new commit
    source.last_known_commit = notification.commit
    source.last_notified_at = datetime.utcnow()

    # Update node's code_version
    node_result = await db.execute(
        select(Node).where(Node.node_id == notification.node_id)
    )
    node = node_result.scalar_one_or_none()
    if node:
        node.code_version = notification.commit

    # Mark other nodes as potentially outdated
    # (They'll be marked outdated when their heartbeat shows different version)

    await db.commit()

    logger.info(
        "Code notification received: commit=%s from node=%s",
        notification.commit[:12],
        notification.node_id,
    )

    # Broadcast via WebSocket
    try:
        from api.websocket import ws_manager

        await ws_manager.broadcast(
            {
                "type": "code_source.new_commit",
                "data": {
                    "commit": notification.commit,
                    "branch": notification.branch,
                    "message": notification.message,
                    "node_id": notification.node_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            }
        )
    except Exception as e:
        logger.debug("Failed to broadcast commit notification: %s", e)

    return CodeNotificationResponse(
        success=True,
        message=f"Commit {notification.commit[:12]} recorded",
        commit=notification.commit,
        outdated_nodes=0,
    )
```

**Step 2: Commit**

```bash
git add slm-server/api/code_source.py
git commit -m "feat(#779): add code-source API for git notifications"
```

---

### Task 3.2: Register Code Source Router

**Files:**
- Modify: `slm-server/main.py`

**Step 1: Import and register router**

Add import:

```python
from api.code_source import router as code_source_router
```

Add registration:

```python
app.include_router(code_source_router, prefix="/api")
```

**Step 2: Commit**

```bash
git add slm-server/main.py
git commit -m "feat(#779): register code-source router"
```

---

## Phase 4: Agent Role Detection

### Task 4.1: Create Port Scanner Module

**Files:**
- Create: `src/slm/agent/port_scanner.py`

**Step 1: Create port_scanner.py**

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Port Scanner Module (Issue #779).

Detects listening TCP ports on the local system.
"""

import logging
import subprocess
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PortInfo:
    """Information about a listening port."""

    port: int
    process: Optional[str] = None
    pid: Optional[int] = None


def get_listening_ports() -> List[PortInfo]:
    """
    Get all listening TCP ports.

    Uses `ss` command on Linux.
    """
    ports = []

    try:
        # ss -tlnp: TCP, listening, numeric, show process
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            logger.warning("ss command failed: %s", result.stderr)
            return ports

        for line in result.stdout.splitlines()[1:]:  # Skip header
            parts = line.split()
            if len(parts) < 5:
                continue

            # Parse local address (format: *:port or 0.0.0.0:port or :::port)
            local_addr = parts[3]
            if ":" not in local_addr:
                continue

            port_str = local_addr.rsplit(":", 1)[-1]
            try:
                port = int(port_str)
            except ValueError:
                continue

            # Parse process info if available (format: users:(("process",pid,fd)))
            process = None
            pid = None
            if len(parts) >= 6:
                proc_info = parts[5] if "users:" in parts[5] else ""
                if proc_info:
                    # Extract process name
                    if '(("' in proc_info:
                        try:
                            process = proc_info.split('(("')[1].split('"')[0]
                            pid_str = proc_info.split(",")[1]
                            pid = int(pid_str.replace("pid=", ""))
                        except (IndexError, ValueError):
                            pass

            ports.append(PortInfo(port=port, process=process, pid=pid))

    except subprocess.TimeoutExpired:
        logger.warning("Port scan timed out")
    except FileNotFoundError:
        logger.warning("ss command not found, trying netstat")
        ports = _get_ports_netstat()
    except Exception as e:
        logger.error("Port scan failed: %s", e)

    # Deduplicate by port
    seen = set()
    unique_ports = []
    for p in ports:
        if p.port not in seen:
            seen.add(p.port)
            unique_ports.append(p)

    return unique_ports


def _get_ports_netstat() -> List[PortInfo]:
    """Fallback using netstat."""
    ports = []

    try:
        result = subprocess.run(
            ["netstat", "-tlnp"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        for line in result.stdout.splitlines():
            if "LISTEN" not in line:
                continue

            parts = line.split()
            if len(parts) < 4:
                continue

            local_addr = parts[3]
            port_str = local_addr.rsplit(":", 1)[-1]

            try:
                port = int(port_str)
                ports.append(PortInfo(port=port))
            except ValueError:
                continue

    except Exception as e:
        logger.error("netstat fallback failed: %s", e)

    return ports
```

**Step 2: Commit**

```bash
git add src/slm/agent/port_scanner.py
git commit -m "feat(#779): add port scanner module for role detection"
```

---

### Task 4.2: Create Role Detector Module

**Files:**
- Create: `src/slm/agent/role_detector.py`

**Step 1: Create role_detector.py**

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Role Detector Module (Issue #779).

Detects installed roles on the local system based on:
- Path existence
- Service status
- Port availability
"""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .port_scanner import get_listening_ports

logger = logging.getLogger(__name__)


@dataclass
class RoleDefinition:
    """Definition of a role for detection."""

    name: str
    target_path: str
    systemd_service: Optional[str] = None
    health_check_port: Optional[int] = None


@dataclass
class RoleStatus:
    """Detection status for a role."""

    path_exists: bool = False
    path: Optional[str] = None
    service_running: bool = False
    service_name: Optional[str] = None
    ports: List[int] = field(default_factory=list)
    version: Optional[str] = None

    @property
    def status(self) -> str:
        """Determine overall status."""
        if self.path_exists and self.service_running:
            return "active"
        elif self.path_exists:
            return "inactive"
        else:
            return "not_installed"


class RoleDetector:
    """Detects installed roles on this node."""

    def __init__(self, role_definitions: Optional[List[Dict]] = None):
        """
        Initialize role detector.

        Args:
            role_definitions: List of role definitions from SLM server.
                             If None, uses empty list until fetched.
        """
        self.roles: Dict[str, RoleDefinition] = {}
        if role_definitions:
            self.load_definitions(role_definitions)

    def load_definitions(self, definitions: List[Dict]) -> None:
        """Load role definitions from SLM server response."""
        self.roles = {}
        for defn in definitions:
            if not defn.get("target_path"):
                continue  # Skip roles without target path (e.g., code-source)

            self.roles[defn["name"]] = RoleDefinition(
                name=defn["name"],
                target_path=defn["target_path"],
                systemd_service=defn.get("systemd_service"),
                health_check_port=defn.get("health_check_port"),
            )

        logger.debug("Loaded %d role definitions", len(self.roles))

    def detect_all(self) -> Dict[str, RoleStatus]:
        """Detect all known roles on this system."""
        results = {}
        listening_ports = {p.port for p in get_listening_ports()}

        for name, role in self.roles.items():
            results[name] = self._detect_role(role, listening_ports)

        return results

    def _detect_role(
        self, role: RoleDefinition, listening_ports: set
    ) -> RoleStatus:
        """Detect a single role."""
        status = RoleStatus()

        # Check path
        target_path = Path(role.target_path)
        status.path_exists = target_path.exists()
        status.path = str(target_path) if status.path_exists else None

        # Check service
        if role.systemd_service:
            status.service_name = role.systemd_service
            status.service_running = self._check_service(role.systemd_service)

        # Check port
        if role.health_check_port:
            if role.health_check_port in listening_ports:
                status.ports.append(role.health_check_port)

        # Read version if path exists
        if status.path_exists:
            status.version = self._read_version(target_path)

        return status

    def _check_service(self, service_name: str) -> bool:
        """Check if a systemd service is running."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() == "active"
        except Exception as e:
            logger.debug("Service check failed for %s: %s", service_name, e)
            return False

    def _read_version(self, target_path: Path) -> Optional[str]:
        """Read version from version.json if present."""
        version_file = target_path / "version.json"

        # Also check parent's version.json for nested paths
        if not version_file.exists():
            version_file = target_path.parent / "version.json"

        # Check /var/lib/slm-agent for slm-agent
        if not version_file.exists() and "slm-agent" in str(target_path):
            version_file = Path("/var/lib/slm-agent/version.json")

        if not version_file.exists():
            return None

        try:
            data = json.loads(version_file.read_text(encoding="utf-8"))
            return data.get("commit") or data.get("version")
        except Exception as e:
            logger.debug("Failed to read version from %s: %s", version_file, e)
            return None
```

**Step 2: Commit**

```bash
git add src/slm/agent/role_detector.py
git commit -m "feat(#779): add role detector module"
```

---

### Task 4.3: Enhance Agent Heartbeat

**Files:**
- Modify: `src/slm/agent/agent.py`

**Step 1: Add imports at top of file**

```python
from .port_scanner import get_listening_ports
from .role_detector import RoleDetector
```

**Step 2: Add role_detector to __init__**

In `SLMAgent.__init__`, after `self.collector = HealthCollector(...)`:

```python
        # Role detection (Issue #779)
        self.role_detector = RoleDetector()
        self._role_definitions_loaded = False
```

**Step 3: Add method to fetch role definitions**

Add new method after `__init__`:

```python
    async def _fetch_role_definitions(self) -> bool:
        """Fetch role definitions from SLM server."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.admin_url}/api/roles/definitions"
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False,
                ) as response:
                    if response.status == 200:
                        definitions = await response.json()
                        self.role_detector.load_definitions(definitions)
                        self._role_definitions_loaded = True
                        logger.info("Loaded %d role definitions", len(definitions))
                        return True
        except Exception as e:
            logger.debug("Failed to fetch role definitions: %s", e)
        return False
```

**Step 4: Update send_heartbeat to include role report**

In `send_heartbeat`, replace the payload construction with:

```python
        # Fetch role definitions if not loaded
        if not self._role_definitions_loaded:
            await self._fetch_role_definitions()

        # Collect health data
        health = self.collector.collect()

        # Detect roles (Issue #779)
        role_report = {}
        if self._role_definitions_loaded:
            role_statuses = self.role_detector.detect_all()
            role_report = {
                name: {
                    "path_exists": status.path_exists,
                    "path": status.path,
                    "service_running": status.service_running,
                    "service_name": status.service_name,
                    "ports": status.ports,
                    "version": status.version,
                    "status": status.status,
                }
                for name, status in role_statuses.items()
            }

        # Get listening ports
        listening_ports = [
            {"port": p.port, "process": p.process, "pid": p.pid}
            for p in get_listening_ports()
        ]

        # Build payload
        code_version = self.version_manager.get_version()
        payload = {
            "cpu_percent": health.get("cpu_percent", 0.0),
            "memory_percent": health.get("memory_percent", 0.0),
            "disk_percent": health.get("disk_percent", 0.0),
            "agent_version": "1.0.0",
            "os_info": f"{platform.system()} {platform.release()}",
            "code_version": code_version,
            "role_report": role_report,  # Issue #779
            "listening_ports": listening_ports,  # Issue #779
            "extra_data": {
                "services": health.get("services", {}),
                "discovered_services": health.get("discovered_services", []),
                "load_avg": health.get("load_avg", []),
                "uptime_seconds": health.get("uptime_seconds", 0),
                "hostname": health.get("hostname"),
            },
        }
```

**Step 5: Commit**

```bash
git add src/slm/agent/agent.py
git commit -m "feat(#779): enhance agent heartbeat with role detection"
```

---

## Phase 5: Extended Node API

### Task 5.1: Update Heartbeat to Process Role Report

**Files:**
- Modify: `slm-server/api/nodes.py`

**Step 1: Update HeartbeatRequest schema in schemas.py**

Add to `slm-server/models/schemas.py`:

```python
class RoleReportItem(BaseModel):
    """Single role detection report."""

    path_exists: bool = False
    path: Optional[str] = None
    service_running: bool = False
    service_name: Optional[str] = None
    ports: List[int] = Field(default_factory=list)
    version: Optional[str] = None
    status: str = "not_installed"


class PortInfo(BaseModel):
    """Listening port info."""

    port: int
    process: Optional[str] = None
    pid: Optional[int] = None
```

Update HeartbeatRequest:

```python
class HeartbeatRequest(BaseModel):
    """Agent heartbeat request."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    agent_version: Optional[str] = None
    os_info: Optional[str] = None
    code_version: Optional[str] = None
    role_report: Dict[str, RoleReportItem] = Field(default_factory=dict)  # Issue #779
    listening_ports: List[PortInfo] = Field(default_factory=list)  # Issue #779
    extra_data: Dict = Field(default_factory=dict)
```

**Step 2: Update heartbeat endpoint in nodes.py**

After updating health metrics, add role processing:

```python
    # Process role report (Issue #779)
    if request.role_report:
        detected_roles = []
        role_versions = {}

        for role_name, report in request.role_report.items():
            if report.status in ("active", "inactive"):
                detected_roles.append(role_name)
            if report.version:
                role_versions[role_name] = report.version

        node.detected_roles = detected_roles
        node.role_versions = role_versions

    # Store listening ports (Issue #779)
    if request.listening_ports:
        node.listening_ports = [p.model_dump() for p in request.listening_ports]
```

**Step 3: Commit**

```bash
git add slm-server/models/schemas.py slm-server/api/nodes.py
git commit -m "feat(#779): process role report in heartbeat endpoint"
```

---

### Task 5.2: Add Node Role Management Endpoints

**Files:**
- Modify: `slm-server/api/nodes.py`

**Step 1: Add role management endpoints**

Add at end of nodes.py:

```python
@router.get("/{node_id}/roles")
async def get_node_roles(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Get roles for a specific node (Issue #779)."""
    # Get node
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Get manual role assignments
    from models.database import NodeRole

    roles_result = await db.execute(
        select(NodeRole).where(NodeRole.node_id == node_id)
    )
    assignments = roles_result.scalars().all()

    manual_roles = [
        {
            "role_name": a.role_name,
            "status": a.status,
            "current_version": a.current_version,
            "last_synced_at": a.last_synced_at.isoformat() if a.last_synced_at else None,
        }
        for a in assignments
        if a.assignment_type == "manual"
    ]

    return {
        "node_id": node_id,
        "detected_roles": node.detected_roles or [],
        "manual_roles": manual_roles,
        "role_versions": node.role_versions or {},
        "listening_ports": node.listening_ports or [],
    }


@router.put("/{node_id}/roles")
async def set_node_roles(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    assigned_roles: List[str] = [],
) -> dict:
    """Set manual role assignments for a node (Issue #779)."""
    from models.database import NodeRole, RoleStatus

    # Verify node exists
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Remove existing manual assignments not in new list
    existing_result = await db.execute(
        select(NodeRole).where(
            NodeRole.node_id == node_id,
            NodeRole.assignment_type == "manual",
        )
    )
    for existing in existing_result.scalars().all():
        if existing.role_name not in assigned_roles:
            await db.delete(existing)

    # Add new assignments
    for role_name in assigned_roles:
        role_result = await db.execute(
            select(NodeRole).where(
                NodeRole.node_id == node_id,
                NodeRole.role_name == role_name,
            )
        )
        if not role_result.scalar_one_or_none():
            node_role = NodeRole(
                node_id=node_id,
                role_name=role_name,
                assignment_type="manual",
                status=RoleStatus.NOT_INSTALLED.value,
            )
            db.add(node_role)

    await db.commit()

    logger.info("Updated roles for node %s: %s", node_id, assigned_roles)

    return {"success": True, "assigned_roles": assigned_roles}
```

**Step 2: Commit**

```bash
git add slm-server/api/nodes.py
git commit -m "feat(#779): add node role management endpoints"
```

---

## Phase 6: Code Sync Orchestrator

### Task 6.1: Create Sync Orchestrator Service

**Files:**
- Create: `slm-server/services/sync_orchestrator.py`

**Step 1: Create sync_orchestrator.py**

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Sync Orchestrator Service (Issue #779).

Orchestrates code distribution from code-source through SLM to fleet nodes.
"""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import CodeSource, Node, NodeRole, Role, RoleStatus
from services.code_distributor import get_code_distributor
from services.database import db_service

logger = logging.getLogger(__name__)

# Code cache directory
CODE_CACHE_DIR = Path(os.environ.get("SLM_CODE_CACHE", "/var/lib/slm/code-cache"))
SSH_KEY_PATH = os.environ.get("SLM_SSH_KEY", "/home/autobot/.ssh/autobot_key")


class SyncOrchestrator:
    """Orchestrates role-based code distribution."""

    def __init__(self):
        self.cache_dir = CODE_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def pull_from_source(self) -> Tuple[bool, str, Optional[str]]:
        """
        Pull code from code-source node to SLM cache.

        Returns:
            Tuple of (success, message, commit_hash)
        """
        async with db_service.session() as db:
            # Get active code source
            result = await db.execute(
                select(CodeSource).where(CodeSource.is_active == True)  # noqa
            )
            source = result.scalar_one_or_none()

            if not source:
                return False, "No active code-source configured", None

            # Get source node info
            node_result = await db.execute(
                select(Node).where(Node.node_id == source.node_id)
            )
            node = node_result.scalar_one_or_none()

            if not node:
                return False, f"Code-source node not found: {source.node_id}", None

        # Pull using rsync
        commit = source.last_known_commit or "latest"
        cache_path = self.cache_dir / commit

        ssh_opts = (
            f"ssh -o StrictHostKeyChecking=no "
            f"-o UserKnownHostsFile=/dev/null "
            f"-o ConnectTimeout=30"
        )
        if Path(SSH_KEY_PATH).exists():
            ssh_opts += f" -i {SSH_KEY_PATH}"

        rsync_cmd = [
            "rsync",
            "-avz",
            "--delete",
            "--exclude", ".git",
            "--exclude", "__pycache__",
            "--exclude", "*.pyc",
            "--exclude", "node_modules",
            "--exclude", "venv",
            "--exclude", ".venv",
            "-e", ssh_opts,
            f"{node.ssh_user}@{node.ip_address}:{source.repo_path}/",
            f"{cache_path}/",
        ]

        try:
            logger.info("Pulling code from %s to cache", node.ip_address)
            proc = await asyncio.create_subprocess_exec(
                *rsync_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)

            if proc.returncode != 0:
                output = stdout.decode("utf-8", errors="replace")
                logger.error("Pull failed: %s", output[:500])
                return False, f"Pull failed: {output[:200]}", None

            logger.info("Code pulled to cache: %s", cache_path)
            return True, f"Code cached at {commit}", commit

        except asyncio.TimeoutError:
            return False, "Pull timed out", None
        except Exception as e:
            logger.error("Pull error: %s", e)
            return False, str(e), None

    async def sync_node_role(
        self,
        node_id: str,
        role_name: str,
        commit: str,
        restart: bool = True,
    ) -> Tuple[bool, str]:
        """
        Sync a specific role to a node.

        Args:
            node_id: Target node ID
            role_name: Role to sync
            commit: Commit hash to sync
            restart: Whether to restart service after sync

        Returns:
            Tuple of (success, message)
        """
        async with db_service.session() as db:
            # Get node
            node_result = await db.execute(
                select(Node).where(Node.node_id == node_id)
            )
            node = node_result.scalar_one_or_none()

            if not node:
                return False, f"Node not found: {node_id}"

            # Get role
            role_result = await db.execute(
                select(Role).where(Role.name == role_name)
            )
            role = role_result.scalar_one_or_none()

            if not role:
                return False, f"Role not found: {role_name}"

            if not role.source_paths:
                return False, f"Role has no source paths: {role_name}"

        # Check cache exists
        cache_path = self.cache_dir / commit
        if not cache_path.exists():
            return False, f"Commit not cached: {commit}"

        # Sync each source path
        ssh_opts = (
            f"ssh -o StrictHostKeyChecking=no "
            f"-o UserKnownHostsFile=/dev/null "
            f"-o ConnectTimeout=30 "
            f"-p {node.ssh_port}"
        )
        if Path(SSH_KEY_PATH).exists():
            ssh_opts += f" -i {SSH_KEY_PATH}"

        for source_path in role.source_paths:
            src = cache_path / source_path.rstrip("/")
            if not src.exists():
                logger.warning("Source path not found in cache: %s", src)
                continue

            # Determine target
            target = role.target_path
            if source_path.endswith("/"):
                # Sync contents of directory
                rsync_src = f"{src}/"
            else:
                rsync_src = str(src)

            rsync_cmd = [
                "rsync",
                "-avz",
                "--delete",
                "--exclude", "__pycache__",
                "--exclude", "*.pyc",
                "-e", ssh_opts,
                rsync_src,
                f"{node.ssh_user}@{node.ip_address}:{target}/",
            ]

            try:
                proc = await asyncio.create_subprocess_exec(
                    *rsync_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)

                if proc.returncode != 0:
                    output = stdout.decode("utf-8", errors="replace")
                    return False, f"Sync failed for {source_path}: {output[:200]}"

            except asyncio.TimeoutError:
                return False, f"Sync timed out for {source_path}"
            except Exception as e:
                return False, f"Sync error: {e}"

        # Run post-sync command if defined
        if role.post_sync_cmd:
            try:
                ssh_cmd = [
                    "ssh",
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null",
                    "-p", str(node.ssh_port),
                ]
                if Path(SSH_KEY_PATH).exists():
                    ssh_cmd.extend(["-i", SSH_KEY_PATH])
                ssh_cmd.extend([
                    f"{node.ssh_user}@{node.ip_address}",
                    role.post_sync_cmd,
                ])

                proc = await asyncio.create_subprocess_exec(
                    *ssh_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                await asyncio.wait_for(proc.communicate(), timeout=300)

            except Exception as e:
                logger.warning("Post-sync command failed: %s", e)

        # Restart service if requested
        if restart and role.auto_restart and role.systemd_service:
            try:
                ssh_cmd = [
                    "ssh",
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null",
                    "-p", str(node.ssh_port),
                ]
                if Path(SSH_KEY_PATH).exists():
                    ssh_cmd.extend(["-i", SSH_KEY_PATH])
                ssh_cmd.extend([
                    f"{node.ssh_user}@{node.ip_address}",
                    f"sudo systemctl restart {role.systemd_service}",
                ])

                proc = await asyncio.create_subprocess_exec(
                    *ssh_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                await asyncio.wait_for(proc.communicate(), timeout=60)
                logger.info("Restarted %s on %s", role.systemd_service, node_id)

            except Exception as e:
                logger.warning("Service restart failed: %s", e)

        # Update node role record
        async with db_service.session() as db:
            role_result = await db.execute(
                select(NodeRole).where(
                    NodeRole.node_id == node_id,
                    NodeRole.role_name == role_name,
                )
            )
            node_role = role_result.scalar_one_or_none()

            if node_role:
                node_role.current_version = commit
                node_role.last_synced_at = datetime.utcnow()
                node_role.status = RoleStatus.ACTIVE.value
            else:
                node_role = NodeRole(
                    node_id=node_id,
                    role_name=role_name,
                    assignment_type="auto",
                    status=RoleStatus.ACTIVE.value,
                    current_version=commit,
                    last_synced_at=datetime.utcnow(),
                )
                db.add(node_role)

            await db.commit()

        logger.info("Synced %s to %s (commit: %s)", role_name, node_id, commit[:12])
        return True, f"Synced {role_name} to {node_id}"


# Singleton
_orchestrator: Optional[SyncOrchestrator] = None


def get_sync_orchestrator() -> SyncOrchestrator:
    """Get or create sync orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SyncOrchestrator()
    return _orchestrator
```

**Step 2: Commit**

```bash
git add slm-server/services/sync_orchestrator.py
git commit -m "feat(#779): add sync orchestrator service"
```

---

### Task 6.2: Extend Code Sync API

**Files:**
- Modify: `slm-server/api/code_sync.py`

**Step 1: Add pull endpoint**

Add after existing endpoints:

```python
from services.sync_orchestrator import get_sync_orchestrator


@router.post("/pull")
async def pull_from_source(
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """
    Pull code from code-source to SLM cache (Issue #779).
    """
    orchestrator = get_sync_orchestrator()
    success, message, commit = await orchestrator.pull_from_source()

    return {
        "success": success,
        "message": message,
        "commit": commit,
    }


@router.post("/roles/{role_name}/sync")
async def sync_role(
    role_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_ids: Optional[List[str]] = None,
    restart: bool = True,
) -> dict:
    """
    Sync a role to all nodes that have it (Issue #779).

    Args:
        role_name: Role to sync
        node_ids: Optional filter - only sync to these nodes
        restart: Whether to restart services
    """
    # Get latest commit from code source
    result = await db.execute(
        select(CodeSource).where(CodeSource.is_active == True)  # noqa
    )
    source = result.scalar_one_or_none()

    if not source or not source.last_known_commit:
        raise HTTPException(
            status_code=400,
            detail="No code version available. Pull from source first.",
        )

    commit = source.last_known_commit

    # Get nodes with this role
    if node_ids:
        nodes_result = await db.execute(
            select(Node).where(Node.node_id.in_(node_ids))
        )
    else:
        # Find nodes with this role detected or assigned
        nodes_result = await db.execute(select(Node))

    nodes = nodes_result.scalars().all()

    # Filter to nodes with this role
    target_nodes = []
    for node in nodes:
        detected = node.detected_roles or []
        if role_name in detected:
            target_nodes.append(node)
            continue

        # Check manual assignments
        role_result = await db.execute(
            select(NodeRole).where(
                NodeRole.node_id == node.node_id,
                NodeRole.role_name == role_name,
                NodeRole.assignment_type == "manual",
            )
        )
        if role_result.scalar_one_or_none():
            target_nodes.append(node)

    if not target_nodes:
        return {
            "success": True,
            "message": f"No nodes have role '{role_name}'",
            "synced": 0,
            "failed": 0,
        }

    # Sync to each node
    orchestrator = get_sync_orchestrator()
    synced = 0
    failed = 0
    errors = []

    for node in target_nodes:
        success, msg = await orchestrator.sync_node_role(
            node.node_id, role_name, commit, restart
        )
        if success:
            synced += 1
        else:
            failed += 1
            errors.append(f"{node.hostname}: {msg}")

    return {
        "success": failed == 0,
        "message": f"Synced {synced}/{len(target_nodes)} nodes",
        "synced": synced,
        "failed": failed,
        "errors": errors if errors else None,
    }
```

**Step 2: Commit**

```bash
git add slm-server/api/code_sync.py
git commit -m "feat(#779): add pull and role-based sync endpoints"
```

---

## Phase 7: Frontend Dashboard

### Task 7.1: Create useRoles Composable

**Files:**
- Create: `slm-admin/src/composables/useRoles.ts`

**Step 1: Create useRoles.ts**

```typescript
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Roles Composable (Issue #779)
 *
 * Provides API integration for role management.
 */

import { ref } from 'vue'
import axios from 'axios'
import { getBackendUrl } from '@/config/ssot-config'

export interface Role {
  name: string
  display_name: string | null
  sync_type: string | null
  source_paths: string[]
  target_path: string
  systemd_service: string | null
  auto_restart: boolean
  health_check_port: number | null
  health_check_path: string | null
  pre_sync_cmd: string | null
  post_sync_cmd: string | null
}

export interface NodeRoleInfo {
  node_id: string
  detected_roles: string[]
  manual_roles: Array<{
    role_name: string
    status: string
    current_version: string | null
    last_synced_at: string | null
  }>
  role_versions: Record<string, string>
  listening_ports: Array<{
    port: number
    process: string | null
    pid: number | null
  }>
}

export function useRoles() {
  const roles = ref<Role[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const API_BASE = getBackendUrl()

  async function fetchRoles(): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const response = await axios.get<Role[]>(`${API_BASE}/api/roles`)
      roles.value = response.data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      isLoading.value = false
    }
  }

  async function getNodeRoles(nodeId: string): Promise<NodeRoleInfo | null> {
    try {
      const response = await axios.get<NodeRoleInfo>(
        `${API_BASE}/api/nodes/${nodeId}/roles`
      )
      return response.data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
      return null
    }
  }

  async function setNodeRoles(
    nodeId: string,
    assignedRoles: string[]
  ): Promise<boolean> {
    try {
      await axios.put(`${API_BASE}/api/nodes/${nodeId}/roles`, null, {
        params: { assigned_roles: assignedRoles },
      })
      return true
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
      return false
    }
  }

  async function syncRole(
    roleName: string,
    nodeIds?: string[],
    restart: boolean = true
  ): Promise<{ success: boolean; message: string; synced: number; failed: number }> {
    try {
      const response = await axios.post(
        `${API_BASE}/api/code-sync/roles/${roleName}/sync`,
        null,
        { params: { node_ids: nodeIds, restart } }
      )
      return response.data
    } catch (e: any) {
      return {
        success: false,
        message: e.response?.data?.detail || e.message,
        synced: 0,
        failed: 0,
      }
    }
  }

  return {
    roles,
    isLoading,
    error,
    fetchRoles,
    getNodeRoles,
    setNodeRoles,
    syncRole,
  }
}
```

**Step 2: Commit**

```bash
git add slm-admin/src/composables/useRoles.ts
git commit -m "feat(#779): add useRoles composable"
```

---

### Task 7.2: Extend useCodeSync Composable

**Files:**
- Modify: `slm-admin/src/composables/useCodeSync.ts`

**Step 1: Add code-source and pull methods**

Add interfaces:

```typescript
export interface CodeSource {
  node_id: string
  hostname: string | null
  ip_address: string | null
  repo_path: string
  branch: string
  last_known_commit: string | null
  last_notified_at: string | null
  is_active: boolean
}
```

Add to composable:

```typescript
  const codeSource = ref<CodeSource | null>(null)
  const isPulling = ref(false)

  async function fetchCodeSource(): Promise<void> {
    try {
      const response = await axios.get<CodeSource | null>(
        `${API_BASE}/api/code-source`
      )
      codeSource.value = response.data
    } catch (e: any) {
      // May be null if not configured
      codeSource.value = null
    }
  }

  async function pullFromSource(): Promise<{ success: boolean; message: string; commit: string | null }> {
    isPulling.value = true
    error.value = null

    try {
      const response = await axios.post(`${API_BASE}/api/code-sync/pull`)
      await fetchStatus()
      return response.data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
      return { success: false, message: error.value || 'Pull failed', commit: null }
    } finally {
      isPulling.value = false
    }
  }

  // Return these new values
  return {
    // ... existing
    codeSource,
    isPulling,
    fetchCodeSource,
    pullFromSource,
  }
```

**Step 2: Commit**

```bash
git add slm-admin/src/composables/useCodeSync.ts
git commit -m "feat(#779): extend useCodeSync with code-source support"
```

---

### Task 7.3: Create RoleManagementModal Component

**Files:**
- Create: `slm-admin/src/components/RoleManagementModal.vue`

**Step 1: Create RoleManagementModal.vue**

```vue
<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Role Management Modal (Issue #779)
 *
 * Allows viewing and assigning roles to a node.
 */

import { ref, computed, onMounted } from 'vue'
import { useRoles, type NodeRoleInfo, type Role } from '@/composables/useRoles'

const props = defineProps<{
  nodeId: string
  hostname: string
}>()

const emit = defineEmits<{
  close: []
  saved: []
}>()

const { roles, fetchRoles, getNodeRoles, setNodeRoles } = useRoles()

const nodeRoles = ref<NodeRoleInfo | null>(null)
const selectedRoles = ref<string[]>([])
const isSaving = ref(false)
const isLoading = ref(true)

const availableRoles = computed(() =>
  roles.value.filter(r => r.name !== 'code-source' && r.target_path)
)

onMounted(async () => {
  await Promise.all([fetchRoles(), loadNodeRoles()])
  isLoading.value = false
})

async function loadNodeRoles() {
  nodeRoles.value = await getNodeRoles(props.nodeId)
  if (nodeRoles.value) {
    selectedRoles.value = nodeRoles.value.manual_roles.map(r => r.role_name)
  }
}

function isRoleDetected(roleName: string): boolean {
  return nodeRoles.value?.detected_roles.includes(roleName) ?? false
}

function getRoleVersion(roleName: string): string | null {
  return nodeRoles.value?.role_versions[roleName] ?? null
}

async function handleSave() {
  isSaving.value = true
  const success = await setNodeRoles(props.nodeId, selectedRoles.value)
  isSaving.value = false

  if (success) {
    emit('saved')
    emit('close')
  }
}
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal-content">
      <div class="modal-header">
        <h3>Manage Roles - {{ hostname }}</h3>
        <button class="close-btn" @click="emit('close')">&times;</button>
      </div>

      <div v-if="isLoading" class="loading">Loading...</div>

      <div v-else class="modal-body">
        <section class="detected-section">
          <h4>Detected Roles (auto-discovered)</h4>
          <div v-if="nodeRoles?.detected_roles.length" class="role-list">
            <div
              v-for="role in nodeRoles.detected_roles"
              :key="role"
              class="role-item detected"
            >
              <span class="role-name">{{ role }}</span>
              <span class="role-version" v-if="getRoleVersion(role)">
                v{{ getRoleVersion(role)?.slice(0, 8) }}
              </span>
              <span class="badge badge-success">Active</span>
            </div>
          </div>
          <p v-else class="empty">No roles detected</p>
        </section>

        <section class="manual-section">
          <h4>Manual Role Assignment</h4>
          <div class="role-checkboxes">
            <label
              v-for="role in availableRoles"
              :key="role.name"
              class="role-checkbox"
              :class="{ detected: isRoleDetected(role.name) }"
            >
              <input
                type="checkbox"
                v-model="selectedRoles"
                :value="role.name"
                :disabled="isRoleDetected(role.name)"
              />
              <span class="role-info">
                <span class="name">{{ role.display_name || role.name }}</span>
                <span class="path">{{ role.target_path }}</span>
              </span>
            </label>
          </div>
        </section>

        <section class="ports-section" v-if="nodeRoles?.listening_ports.length">
          <h4>Listening Ports</h4>
          <div class="ports-list">
            <span
              v-for="port in nodeRoles.listening_ports"
              :key="port.port"
              class="port-badge"
            >
              {{ port.port }}
              <small v-if="port.process">({{ port.process }})</small>
            </span>
          </div>
        </section>
      </div>

      <div class="modal-footer">
        <button class="btn btn-secondary" @click="emit('close')">Cancel</button>
        <button
          class="btn btn-primary"
          @click="handleSave"
          :disabled="isSaving"
        >
          {{ isSaving ? 'Saving...' : 'Save Assignments' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg-primary, #1a1a2e);
  border-radius: 8px;
  width: 500px;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid var(--border, #333);
}

.modal-header h3 {
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: var(--text-secondary, #888);
}

.modal-body {
  padding: 1rem;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  padding: 1rem;
  border-top: 1px solid var(--border, #333);
}

section {
  margin-bottom: 1.5rem;
}

section h4 {
  margin: 0 0 0.75rem 0;
  font-size: 0.875rem;
  color: var(--text-secondary, #888);
}

.role-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.role-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: var(--bg-secondary, #252540);
  border-radius: 4px;
}

.role-name {
  font-weight: 500;
}

.role-version {
  font-family: monospace;
  font-size: 0.75rem;
  color: var(--text-secondary, #888);
}

.role-checkboxes {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.role-checkbox {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.5rem;
  border-radius: 4px;
  cursor: pointer;
}

.role-checkbox:hover {
  background: var(--bg-secondary, #252540);
}

.role-checkbox.detected {
  opacity: 0.6;
  cursor: not-allowed;
}

.role-info {
  display: flex;
  flex-direction: column;
}

.role-info .name {
  font-weight: 500;
}

.role-info .path {
  font-size: 0.75rem;
  color: var(--text-secondary, #888);
  font-family: monospace;
}

.ports-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.port-badge {
  padding: 0.25rem 0.5rem;
  background: var(--bg-secondary, #252540);
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.875rem;
}

.badge {
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  font-size: 0.75rem;
}

.badge-success {
  background: var(--success-bg, #1a4d1a);
  color: var(--success, #4ade80);
}

.empty {
  color: var(--text-secondary, #888);
  font-style: italic;
}

.loading {
  padding: 2rem;
  text-align: center;
  color: var(--text-secondary, #888);
}

.btn {
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
}

.btn-primary {
  background: var(--primary, #6366f1);
  color: white;
  border: none;
}

.btn-secondary {
  background: transparent;
  border: 1px solid var(--border, #333);
  color: var(--text-primary, #fff);
}
</style>
```

**Step 2: Commit**

```bash
git add slm-admin/src/components/RoleManagementModal.vue
git commit -m "feat(#779): add RoleManagementModal component"
```

---

### Task 7.4: Update CodeSyncView

**Files:**
- Modify: `slm-admin/src/views/CodeSyncView.vue`

This task involves significant changes to the existing view. The implementation should:

1. Add code-source status banner
2. Add role columns to the node table
3. Add "Manage Roles" button per node
4. Add "Sync by Role" dropdown
5. Integrate RoleManagementModal

Due to the size, this should be implemented incrementally during execution.

**Step 1: Plan the changes**

- Import and use `useRoles` composable
- Add code-source display section
- Modify node table to show roles and role versions
- Add role management modal integration
- Add role-based sync actions

**Step 2: Commit after implementation**

```bash
git add slm-admin/src/views/CodeSyncView.vue
git commit -m "feat(#779): enhance CodeSyncView with role-based features"
```

---

## Phase 8: Testing & Documentation

### Task 8.1: Add Integration Tests

**Files:**
- Create: `tests/services/slm/test_role_sync.py`

**Step 1: Create test file with key tests**

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for role-based code sync (Issue #779)."""

import pytest


class TestRoleRegistry:
    """Test role registry service."""

    @pytest.mark.asyncio
    async def test_seed_default_roles(self, db_session):
        """Should seed default roles."""
        from services.role_registry import seed_default_roles, list_roles

        created = await seed_default_roles(db_session)
        assert created >= 5

        roles = await list_roles(db_session)
        role_names = [r.name for r in roles]
        assert "frontend" in role_names
        assert "backend" in role_names
        assert "slm-agent" in role_names


class TestCodeSourceAPI:
    """Test code source API."""

    @pytest.mark.asyncio
    async def test_assign_code_source(self, client, auth_headers, db_session):
        """Should assign code-source to a node."""
        from models.database import Node

        # Create test node
        node = Node(
            node_id="test-source-node",
            hostname="source-host",
            ip_address="192.168.1.100",
        )
        db_session.add(node)
        await db_session.commit()

        response = await client.post(
            "/api/code-source/assign",
            json={
                "node_id": "test-source-node",
                "repo_path": "/home/test/repo",
                "branch": "main",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True


class TestRolesAPI:
    """Test roles API."""

    @pytest.mark.asyncio
    async def test_list_roles(self, client, auth_headers):
        """Should list all roles."""
        response = await client.get("/api/roles", headers=auth_headers)
        assert response.status_code == 200
        roles = response.json()
        assert len(roles) > 0

    @pytest.mark.asyncio
    async def test_get_role_definitions_no_auth(self, client):
        """Definitions endpoint should work without auth."""
        response = await client.get("/api/roles/definitions")
        assert response.status_code == 200
```

**Step 2: Commit**

```bash
git add tests/services/slm/test_role_sync.py
git commit -m "test(#779): add integration tests for role-based sync"
```

---

### Task 8.2: Update Documentation

**Files:**
- Modify: `docs/system-state.md`

**Step 1: Add Issue #779 section**

Add to RECENT UPDATES:

```markdown
### Issue #779: Role-Based Code Sync

**Status:** ✅ Complete (2026-02-03)
**GitHub Issue:** #779 - Role-based code sync with centralized version dashboard

**Summary:**
Implemented centralized code distribution with role-based targeting:
- Single git-connected code-source node
- SLM pulls and caches code from source
- Role-based distribution to fleet nodes
- Auto-discovery of roles via path + service + port detection
- Per-role version tracking

**Key Components:**
- `slm-server/api/roles.py` - Role definitions CRUD
- `slm-server/api/code_source.py` - Code source management
- `slm-server/services/sync_orchestrator.py` - Distribution orchestration
- `src/slm/agent/role_detector.py` - Agent role detection
- `slm-admin/src/views/CodeSyncView.vue` - Enhanced dashboard

**Default Roles:**
- `code-source` - Git-connected source node
- `backend` - Backend API server
- `frontend` - Frontend UI
- `slm-server` - SLM management server
- `slm-agent` - SLM node agent
- `npu-worker` - NPU acceleration worker
- `browser-service` - Browser automation
```

**Step 2: Commit**

```bash
git add docs/system-state.md
git commit -m "docs(#779): document role-based code sync implementation"
```

---

## Summary

This plan covers 8 phases with 20+ tasks:

1. **Phase 1**: Database foundation (Role, NodeRole, CodeSource models)
2. **Phase 2**: Role registry service with default roles
3. **Phase 3**: Code source management API
4. **Phase 4**: Agent role detection modules
5. **Phase 5**: Extended node API with role tracking
6. **Phase 6**: Sync orchestrator for hub-and-spoke distribution
7. **Phase 7**: Frontend dashboard enhancements
8. **Phase 8**: Testing and documentation

Each task follows TDD principles with explicit file paths and commit messages.
