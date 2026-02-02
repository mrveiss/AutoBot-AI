# Agent LLM Configuration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement per-agent LLM configuration in SLM with WebSocket push updates to backend.

**Architecture:** SLM stores agents with LLM config in SQLite. Backend connects via HTTP for initial fetch and WebSocket for real-time updates. Encrypted API key storage using existing Fernet infrastructure.

**Tech Stack:** FastAPI, SQLAlchemy, WebSocket, aiohttp, Fernet encryption

---

## Task 1: Add Agent Model

**Files:**
- Modify: `slm-server/models/database.py`

**Step 1: Add Agent model after ServiceConflict class**

```python
class Agent(Base):
    """AI Agent with LLM configuration (Issue #760 Phase 2).

    Each agent can have its own LLM provider configuration.
    One agent with is_default=True serves as fallback.
    """

    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)

    # LLM Configuration
    llm_provider = Column(String(32), nullable=False)  # ollama, openai, anthropic
    llm_endpoint = Column(String(256), nullable=True)
    llm_model = Column(String(64), nullable=False)
    llm_api_key_encrypted = Column(Text, nullable=True)
    llm_timeout = Column(Integer, default=30)
    llm_temperature = Column(Float, default=0.7)
    llm_max_tokens = Column(Integer, nullable=True)

    # State
    is_default = Column(Boolean, default=False, index=True)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**Step 2: Verify import**

Run: `cd slm-server && python -c "from models.database import Agent; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add slm-server/models/database.py
git commit -m "feat(slm): add Agent model for LLM configuration (#760)"
```

---

## Task 2: Add Agent Pydantic Schemas

**Files:**
- Modify: `slm-server/models/schemas.py`

**Step 1: Add schemas at end of file**

```python
# =============================================================================
# Agent Schemas (Issue #760 Phase 2)
# =============================================================================


class AgentLLMConfig(BaseModel):
    """LLM configuration for an agent (excludes API key)."""

    llm_provider: str
    llm_endpoint: Optional[str] = None
    llm_model: str
    llm_timeout: int = 30
    llm_temperature: float = 0.7
    llm_max_tokens: Optional[int] = None


class AgentResponse(BaseModel):
    """Agent response with LLM config."""

    id: int
    agent_id: str
    name: str
    description: Optional[str] = None
    llm_provider: str
    llm_endpoint: Optional[str] = None
    llm_model: str
    llm_timeout: int = 30
    llm_temperature: float = 0.7
    llm_max_tokens: Optional[int] = None
    is_default: bool = False
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentCreateRequest(BaseModel):
    """Request to create an agent."""

    agent_id: str = Field(..., min_length=1, max_length=64, pattern="^[a-z0-9-]+$")
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    llm_provider: str = Field(..., pattern="^(ollama|openai|anthropic|vllm)$")
    llm_endpoint: Optional[str] = None
    llm_model: str = Field(..., min_length=1, max_length=64)
    llm_api_key: Optional[str] = None  # Will be encrypted before storage
    llm_timeout: int = Field(default=30, ge=1, le=300)
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    llm_max_tokens: Optional[int] = Field(default=None, ge=1, le=128000)
    is_default: bool = False
    is_active: bool = True


class AgentUpdateRequest(BaseModel):
    """Request to update an agent."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    llm_provider: Optional[str] = Field(default=None, pattern="^(ollama|openai|anthropic|vllm)$")
    llm_endpoint: Optional[str] = None
    llm_model: Optional[str] = Field(default=None, min_length=1, max_length=64)
    llm_api_key: Optional[str] = None  # Will be encrypted before storage
    llm_timeout: Optional[int] = Field(default=None, ge=1, le=300)
    llm_temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    llm_max_tokens: Optional[int] = Field(default=None, ge=1, le=128000)
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class AgentListResponse(BaseModel):
    """List of agents."""

    agents: List[AgentResponse]
    total: int


class AgentLLMConfigWithKey(AgentLLMConfig):
    """LLM config including decrypted API key (for backend only)."""

    llm_api_key: Optional[str] = None
```

**Step 2: Verify import**

Run: `cd slm-server && python -c "from models.schemas import AgentResponse, AgentCreateRequest; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add slm-server/models/schemas.py
git commit -m "feat(slm): add Agent Pydantic schemas (#760)"
```

---

## Task 3: Create Migration Script

**Files:**
- Create: `slm-server/migrations/add_agents.py`

**Step 1: Create migration script**

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add agents table for per-agent LLM configuration.

Issue #760 Phase 2
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def run_migration(db_path: str = "slm.db") -> bool:
    """Run the agents table migration."""
    logger.info("Running agents migration...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
        )
        if cursor.fetchone():
            logger.info("agents table already exists, skipping creation")
            return True

        # Create agents table
        cursor.execute("""
            CREATE TABLE agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id VARCHAR(64) UNIQUE NOT NULL,
                name VARCHAR(128) NOT NULL,
                description TEXT,
                llm_provider VARCHAR(32) NOT NULL,
                llm_endpoint VARCHAR(256),
                llm_model VARCHAR(64) NOT NULL,
                llm_api_key_encrypted TEXT,
                llm_timeout INTEGER DEFAULT 30,
                llm_temperature REAL DEFAULT 0.7,
                llm_max_tokens INTEGER,
                is_default BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("Created agents table")

        # Create indexes
        cursor.execute("CREATE INDEX idx_agents_agent_id ON agents(agent_id)")
        cursor.execute("CREATE INDEX idx_agents_is_default ON agents(is_default)")
        logger.info("Created indexes")

        # Seed default agent
        cursor.execute("""
            INSERT INTO agents (agent_id, name, description, llm_provider, llm_model, is_default)
            VALUES ('default', 'Default Agent', 'Fallback agent for unconfigured requests',
                    'ollama', 'mistral:7b-instruct', TRUE)
        """)
        logger.info("Seeded default agent")

        conn.commit()
        logger.info("Migration complete")
        return True

    except Exception as e:
        logger.error("Migration failed: %s", e)
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Find database
    db_path = Path("slm.db")
    if not db_path.exists():
        db_path = Path("data/slm.db")

    if not db_path.exists():
        logger.error("Database not found")
        exit(1)

    success = run_migration(str(db_path))
    exit(0 if success else 1)
```

**Step 2: Verify syntax**

Run: `cd slm-server && python -c "import migrations.add_agents; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add slm-server/migrations/add_agents.py
git commit -m "feat(slm): add agents table migration (#760)"
```

---

## Task 4: Create Agents API Router

**Files:**
- Create: `slm-server/api/agents.py`

**Step 1: Create the API router**

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agents API - Per-agent LLM configuration management.

Issue #760 Phase 2
"""

import logging
from typing import Optional

from api.websocket import ws_manager
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from config import settings
from models.database import Agent
from models.schemas import (
    AgentCreateRequest,
    AgentListResponse,
    AgentLLMConfig,
    AgentLLMConfigWithKey,
    AgentResponse,
    AgentUpdateRequest,
)
from services.auth import get_current_user
from services.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

# Encryption key from settings (reuse existing infrastructure)
_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """Get Fernet instance for API key encryption."""
    global _fernet
    if _fernet is None:
        key = settings.encryption_key.encode() if settings.encryption_key else Fernet.generate_key()
        _fernet = Fernet(key)
    return _fernet


def _encrypt_api_key(api_key: Optional[str]) -> Optional[str]:
    """Encrypt API key for storage."""
    if not api_key:
        return None
    return _get_fernet().encrypt(api_key.encode()).decode()


def _decrypt_api_key(encrypted: Optional[str]) -> Optional[str]:
    """Decrypt API key from storage."""
    if not encrypted:
        return None
    try:
        return _get_fernet().decrypt(encrypted.encode()).decode()
    except Exception:
        logger.warning("Failed to decrypt API key")
        return None


@router.get("", response_model=AgentListResponse)
async def list_agents(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    active_only: bool = False,
) -> AgentListResponse:
    """List all agents."""
    query = select(Agent).order_by(Agent.name)
    if active_only:
        query = query.where(Agent.is_active.is_(True))

    result = await db.execute(query)
    agents = result.scalars().all()

    return AgentListResponse(
        agents=[AgentResponse.model_validate(a) for a in agents],
        total=len(agents),
    )


@router.get("/default", response_model=AgentResponse)
async def get_default_agent(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> AgentResponse:
    """Get the default agent."""
    result = await db.execute(
        select(Agent).where(Agent.is_default.is_(True))
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No default agent configured",
        )

    return AgentResponse.model_validate(agent)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> AgentResponse:
    """Get an agent by ID."""
    result = await db.execute(
        select(Agent).where(Agent.agent_id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    return AgentResponse.model_validate(agent)


@router.get("/{agent_id}/llm", response_model=AgentLLMConfigWithKey)
async def get_agent_llm_config(
    agent_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> AgentLLMConfigWithKey:
    """Get agent LLM config including decrypted API key (for backend use)."""
    result = await db.execute(
        select(Agent).where(Agent.agent_id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        # Fall back to default agent
        result = await db.execute(
            select(Agent).where(Agent.is_default.is_(True))
        )
        agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No agent or default found",
        )

    return AgentLLMConfigWithKey(
        llm_provider=agent.llm_provider,
        llm_endpoint=agent.llm_endpoint,
        llm_model=agent.llm_model,
        llm_timeout=agent.llm_timeout,
        llm_temperature=agent.llm_temperature,
        llm_max_tokens=agent.llm_max_tokens,
        llm_api_key=_decrypt_api_key(agent.llm_api_key_encrypted),
    )


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    request: AgentCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> AgentResponse:
    """Create a new agent."""
    # Check if agent_id already exists
    result = await db.execute(
        select(Agent).where(Agent.agent_id == request.agent_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent '{request.agent_id}' already exists",
        )

    # If setting as default, unset existing default
    if request.is_default:
        await db.execute(
            Agent.__table__.update().where(Agent.is_default.is_(True)).values(is_default=False)
        )

    agent = Agent(
        agent_id=request.agent_id,
        name=request.name,
        description=request.description,
        llm_provider=request.llm_provider,
        llm_endpoint=request.llm_endpoint,
        llm_model=request.llm_model,
        llm_api_key_encrypted=_encrypt_api_key(request.llm_api_key),
        llm_timeout=request.llm_timeout,
        llm_temperature=request.llm_temperature,
        llm_max_tokens=request.llm_max_tokens,
        is_default=request.is_default,
        is_active=request.is_active,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    logger.info("Created agent: %s (%s)", request.agent_id, request.llm_provider)

    # Broadcast creation via WebSocket
    await ws_manager.broadcast({
        "type": "agent_created",
        "agent_id": agent.agent_id,
        "config": AgentLLMConfig(
            llm_provider=agent.llm_provider,
            llm_endpoint=agent.llm_endpoint,
            llm_model=agent.llm_model,
            llm_timeout=agent.llm_timeout,
            llm_temperature=agent.llm_temperature,
            llm_max_tokens=agent.llm_max_tokens,
        ).model_dump(),
    })

    return AgentResponse.model_validate(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    request: AgentUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> AgentResponse:
    """Update an agent."""
    result = await db.execute(
        select(Agent).where(Agent.agent_id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    # If setting as default, unset existing default
    if request.is_default is True and not agent.is_default:
        await db.execute(
            Agent.__table__.update().where(Agent.is_default.is_(True)).values(is_default=False)
        )

    # Update fields
    update_data = request.model_dump(exclude_unset=True)
    if "llm_api_key" in update_data:
        agent.llm_api_key_encrypted = _encrypt_api_key(update_data.pop("llm_api_key"))

    for field, value in update_data.items():
        setattr(agent, field, value)

    await db.commit()
    await db.refresh(agent)

    logger.info("Updated agent: %s", agent_id)

    # Broadcast update via WebSocket
    await ws_manager.broadcast({
        "type": "agent_config_changed",
        "agent_id": agent.agent_id,
        "config": AgentLLMConfig(
            llm_provider=agent.llm_provider,
            llm_endpoint=agent.llm_endpoint,
            llm_model=agent.llm_model,
            llm_timeout=agent.llm_timeout,
            llm_temperature=agent.llm_temperature,
            llm_max_tokens=agent.llm_max_tokens,
        ).model_dump(),
    })

    return AgentResponse.model_validate(agent)


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Delete an agent."""
    result = await db.execute(
        select(Agent).where(Agent.agent_id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    if agent.is_default:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the default agent",
        )

    await db.delete(agent)
    await db.commit()

    logger.info("Deleted agent: %s", agent_id)

    # Broadcast deletion via WebSocket
    await ws_manager.broadcast({
        "type": "agent_deleted",
        "agent_id": agent_id,
    })

    return {"message": "Agent deleted", "agent_id": agent_id}
```

**Step 2: Verify syntax**

Run: `cd slm-server && python -c "from api.agents import router; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add slm-server/api/agents.py
git commit -m "feat(slm): add agents API router (#760)"
```

---

## Task 5: Register Agents Router

**Files:**
- Modify: `slm-server/api/__init__.py`
- Modify: `slm-server/main.py`

**Step 1: Add to api/__init__.py**

Add import:
```python
from .agents import router as agents_router
```

Add to `__all__`:
```python
    "agents_router",
```

**Step 2: Add to main.py**

Add import:
```python
    agents_router,
```

Add router registration after discovery_router:
```python
app.include_router(agents_router, prefix="/api")
```

**Step 3: Verify app loads**

Run: `cd slm-server && python -c "from main import app; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add slm-server/api/__init__.py slm-server/main.py
git commit -m "feat(slm): register agents router (#760)"
```

---

## Task 6: Run Migration and Test API

**Step 1: Run migration**

Run: `cd slm-server && python -m migrations.add_agents`
Expected: Migration complete, default agent seeded

**Step 2: Verify table exists**

Run: `cd slm-server && sqlite3 slm.db "SELECT agent_id, name, llm_provider, llm_model, is_default FROM agents;"`
Expected: `default|Default Agent|ollama|mistral:7b-instruct|1`

**Step 3: Test API endpoint (manual or curl)**

Run: `curl -s http://localhost:8000/api/agents | python -m json.tool`
Expected: JSON with agents list containing default agent

**Step 4: Commit any fixes**

---

## Task 7: Create SLM Client for Backend

**Files:**
- Create: `backend/services/slm_client.py`

**Step 1: Create the SLM client**

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Client - HTTP + WebSocket client for SLM server.

Issue #760 Phase 2
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with TTL."""

    config: dict
    expires_at: float

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class AgentConfigCache:
    """In-memory cache for agent configurations."""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl_seconds
        self._default_config: Optional[dict] = None

    def get(self, agent_id: str) -> Optional[dict]:
        """Get config from cache if not expired."""
        entry = self._cache.get(agent_id)
        if entry and not entry.is_expired():
            return entry.config
        return None

    def set(self, agent_id: str, config: dict):
        """Set config with TTL."""
        self._cache[agent_id] = CacheEntry(
            config=config,
            expires_at=time.time() + self._ttl,
        )

    def update(self, agent_id: str, config: dict):
        """Update from WebSocket push - reset TTL."""
        self.set(agent_id, config)
        logger.debug("Cache updated for agent: %s", agent_id)

    def remove(self, agent_id: str):
        """Remove agent from cache."""
        self._cache.pop(agent_id, None)
        logger.debug("Cache removed for agent: %s", agent_id)

    def set_default(self, config: dict):
        """Set default agent config."""
        self._default_config = config

    def get_default(self) -> Optional[dict]:
        """Get default agent config."""
        return self._default_config

    def clear(self):
        """Clear all cached entries."""
        self._cache.clear()
        self._default_config = None


class SLMClient:
    """Client for SLM server communication."""

    def __init__(
        self,
        slm_url: str,
        auth_token: Optional[str] = None,
        cache_ttl: int = 300,
    ):
        self.slm_url = slm_url.rstrip("/")
        self.ws_url = self.slm_url.replace("http://", "ws://").replace("https://", "wss://")
        self.auth_token = auth_token
        self._cache = AgentConfigCache(ttl_seconds=cache_ttl)
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._connected = False
        self._on_config_change: Optional[Callable] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _headers(self) -> dict:
        """Get HTTP headers with auth."""
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    async def connect(self):
        """Connect to SLM and subscribe to agent config updates."""
        try:
            # Fetch all agents initially
            await self._fetch_all_agents()

            # Connect WebSocket
            self._ws_task = asyncio.create_task(self._ws_listen())
            self._connected = True
            logger.info("Connected to SLM: %s", self.slm_url)
        except Exception as e:
            logger.warning("Failed to connect to SLM: %s", e)
            self._connected = False

    async def disconnect(self):
        """Disconnect from SLM."""
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
        self._connected = False
        logger.info("Disconnected from SLM")

    async def _fetch_all_agents(self):
        """Fetch all agents and populate cache."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.slm_url}/api/agents",
                    headers=self._headers(),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for agent in data.get("agents", []):
                            config = {
                                "llm_provider": agent["llm_provider"],
                                "llm_endpoint": agent.get("llm_endpoint"),
                                "llm_model": agent["llm_model"],
                                "llm_timeout": agent.get("llm_timeout", 30),
                                "llm_temperature": agent.get("llm_temperature", 0.7),
                                "llm_max_tokens": agent.get("llm_max_tokens"),
                            }
                            self._cache.set(agent["agent_id"], config)
                            if agent.get("is_default"):
                                self._cache.set_default(config)
                        logger.info("Loaded %d agents from SLM", len(data.get("agents", [])))
        except Exception as e:
            logger.warning("Failed to fetch agents: %s", e)

    async def _ws_listen(self):
        """Listen for WebSocket messages."""
        reconnect_delay = 1
        max_delay = 60

        while True:
            try:
                async with websockets.connect(f"{self.ws_url}/api/ws") as ws:
                    self._ws = ws
                    reconnect_delay = 1  # Reset on successful connection
                    logger.info("WebSocket connected to SLM")

                    async for message in ws:
                        try:
                            data = json.loads(message)
                            await self._handle_ws_message(data)
                        except json.JSONDecodeError:
                            logger.warning("Invalid WebSocket message")

            except ConnectionClosed:
                logger.warning("WebSocket closed, reconnecting in %ds", reconnect_delay)
            except Exception as e:
                logger.warning("WebSocket error: %s, reconnecting in %ds", e, reconnect_delay)

            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_delay)

    async def _handle_ws_message(self, data: dict):
        """Handle incoming WebSocket message."""
        msg_type = data.get("type")
        agent_id = data.get("agent_id")

        if msg_type == "agent_config_changed":
            config = data.get("config", {})
            self._cache.update(agent_id, config)
            if self._on_config_change:
                await self._on_config_change(agent_id, config)
            logger.info("Agent config updated: %s", agent_id)

        elif msg_type == "agent_created":
            config = data.get("config", {})
            self._cache.set(agent_id, config)
            logger.info("Agent created: %s", agent_id)

        elif msg_type == "agent_deleted":
            self._cache.remove(agent_id)
            logger.info("Agent deleted: %s", agent_id)

    async def get_agent_config(self, agent_id: str) -> dict:
        """Get agent LLM config from cache or SLM."""
        # Check cache first
        config = self._cache.get(agent_id)
        if config:
            return config

        # Fetch from SLM
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.slm_url}/api/agents/{agent_id}/llm",
                    headers=self._headers(),
                ) as resp:
                    if resp.status == 200:
                        config = await resp.json()
                        self._cache.set(agent_id, config)
                        return config
        except Exception as e:
            logger.warning("Failed to fetch agent config: %s", e)

        # Fall back to default
        default = self._cache.get_default()
        if default:
            return default

        # Ultimate fallback
        return {
            "llm_provider": "ollama",
            "llm_endpoint": "http://127.0.0.1:11434",
            "llm_model": "mistral:7b-instruct",
            "llm_timeout": 30,
            "llm_temperature": 0.7,
            "llm_max_tokens": None,
        }

    def on_config_change(self, callback: Callable):
        """Register callback for config changes."""
        self._on_config_change = callback


# Singleton instance
_slm_client: Optional[SLMClient] = None


def get_slm_client() -> Optional[SLMClient]:
    """Get the SLM client singleton."""
    return _slm_client


async def init_slm_client(slm_url: str, auth_token: Optional[str] = None):
    """Initialize and connect the SLM client."""
    global _slm_client
    _slm_client = SLMClient(slm_url, auth_token)
    await _slm_client.connect()
    return _slm_client


async def shutdown_slm_client():
    """Shutdown the SLM client."""
    global _slm_client
    if _slm_client:
        await _slm_client.disconnect()
        _slm_client = None
```

**Step 2: Verify syntax**

Run: `cd backend && python -c "from services.slm_client import SLMClient; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/services/slm_client.py
git commit -m "feat(backend): add SLM client for agent config (#760)"
```

---

## Task 8: Integrate SLM Client with Backend Startup

**Files:**
- Modify: `backend/main.py` (or equivalent startup file)

**Step 1: Add SLM client initialization to lifespan**

Add imports:
```python
from services.slm_client import init_slm_client, shutdown_slm_client
```

In lifespan startup:
```python
# Initialize SLM client for agent config (Issue #760)
slm_url = os.getenv("SLM_URL", "http://172.16.168.19:8000")
slm_token = os.getenv("SLM_AUTH_TOKEN")
await init_slm_client(slm_url, slm_token)
logger.info("SLM client initialized")
```

In lifespan shutdown:
```python
await shutdown_slm_client()
logger.info("SLM client shutdown")
```

**Step 2: Verify app loads**

Run: `cd backend && python -c "from main import app; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat(backend): integrate SLM client with startup (#760)"
```

---

## Task 9: Update GitHub Issue

**Step 1: Add comment to issue #760**

Add completion comment with Phase 2 checklist:

```markdown
## Phase 2 Implementation Complete ✅

**SLM Server:**
- [x] Agent model in database.py
- [x] Pydantic schemas in schemas.py
- [x] Migration script (add_agents.py)
- [x] API router (api/agents.py)
- [x] WebSocket broadcast on agent changes

**Backend:**
- [x] SLMClient class (HTTP + WebSocket)
- [x] AgentConfigCache class
- [x] Startup hook for SLM connection

**API Endpoints:**
- GET /api/agents - List all agents
- GET /api/agents/default - Get default agent
- GET /api/agents/{agent_id} - Get agent
- GET /api/agents/{agent_id}/llm - Get LLM config with decrypted key
- POST /api/agents - Create agent
- PUT /api/agents/{agent_id} - Update agent
- DELETE /api/agents/{agent_id} - Delete agent

**WebSocket Messages:**
- agent_config_changed
- agent_created
- agent_deleted

Ready for Phase 3: LLM Interface Integration
```

---

## Summary

| Task | Component | Description |
|------|-----------|-------------|
| 1 | SLM Model | Agent table in database.py |
| 2 | SLM Schemas | Pydantic schemas for agents |
| 3 | SLM Migration | Create agents table, seed default |
| 4 | SLM API | CRUD endpoints + WebSocket broadcast |
| 5 | SLM Router | Register agents router |
| 6 | SLM Test | Run migration, verify API |
| 7 | Backend Client | SLMClient with cache + WebSocket |
| 8 | Backend Startup | Initialize SLM client |
| 9 | GitHub | Update issue with completion |
