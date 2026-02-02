# Agent LLM Configuration Design (Issue #760 Phase 2)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable per-agent LLM configuration via SLM with real-time push updates.

**Architecture:** SLM stores agent definitions with embedded LLM config. Backend fetches on startup, caches locally, and subscribes to WebSocket for instant config updates.

**Tech Stack:** FastAPI, SQLAlchemy, WebSocket, aiohttp

---

## 1. Agent Model (SLM)

```python
class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True)
    agent_id = Column(String(64), unique=True, index=True)  # "code-assistant"
    name = Column(String(128))
    description = Column(Text, nullable=True)

    # LLM Configuration
    llm_provider = Column(String(32))  # ollama, openai, anthropic
    llm_endpoint = Column(String(256), nullable=True)
    llm_model = Column(String(64))
    llm_api_key_encrypted = Column(Text, nullable=True)  # Fernet encrypted
    llm_timeout = Column(Integer, default=30)
    llm_temperature = Column(Float, default=0.7)
    llm_max_tokens = Column(Integer, nullable=True)

    # State
    is_default = Column(Boolean, default=False)  # Fallback agent
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

## 2. API Endpoints (SLM)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/agents` | List all agents |
| GET | `/api/agents/{agent_id}` | Get agent with config |
| POST | `/api/agents` | Create new agent |
| PUT | `/api/agents/{agent_id}` | Update agent config |
| DELETE | `/api/agents/{agent_id}` | Delete agent |
| GET | `/api/agents/{agent_id}/llm` | Get just LLM config (for backend) |
| GET | `/api/agents/default` | Get default agent config |

## 3. WebSocket Push (SLM)

When agent config changes, SLM broadcasts to subscribed clients:

```json
{
    "type": "agent_config_changed",
    "agent_id": "code-assistant",
    "config": {
        "llm_provider": "openai",
        "llm_model": "gpt-4",
        "llm_endpoint": "https://api.openai.com/v1",
        "llm_timeout": 30,
        "llm_temperature": 0.7
    }
}
```

Message types:
- `agent_config_changed` - Agent updated
- `agent_created` - New agent registered
- `agent_deleted` - Agent removed

## 4. Backend Integration

### SLM Client

```python
class SLMClient:
    def __init__(self, slm_url: str):
        self.slm_url = slm_url
        self._ws = None
        self._cache = AgentConfigCache()

    async def connect(self):
        """Connect and subscribe to agent_config channel."""
        self._ws = await websockets.connect(f"{self.slm_url}/ws")
        await self._ws.send(json.dumps({"subscribe": "agent_config"}))
        asyncio.create_task(self._listen())

    async def get_agent_config(self, agent_id: str) -> dict:
        """Get config from cache, fallback to HTTP if not found."""
        config = self._cache.get(agent_id)
        if config:
            return config

        # Fetch from SLM
        config = await self._fetch_agent_config(agent_id)
        if config:
            self._cache.set(agent_id, config)
            return config

        # Return default agent config
        return await self.get_default_agent_config()
```

### Cache with TTL Fallback

```python
class AgentConfigCache:
    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl_seconds

    def get(self, agent_id: str) -> Optional[dict]:
        entry = self._cache.get(agent_id)
        if entry and not entry.is_expired():
            return entry.config
        return None

    def set(self, agent_id: str, config: dict):
        self._cache[agent_id] = CacheEntry(config, time.time() + self._ttl)

    def update(self, agent_id: str, config: dict):
        """Update from WebSocket push - reset TTL."""
        self.set(agent_id, config)

    def remove(self, agent_id: str):
        self._cache.pop(agent_id, None)
```

## 5. Data Flow

```
1. Backend starts
   → Fetches all agents from SLM via HTTP
   → Caches locally
   → Connects WebSocket, subscribes to agent_config

2. Agent makes LLM request
   → Checks cache for agent config
   → Uses config (provider, model, endpoint)
   → Makes LLM API call

3. Admin changes config in SLM
   → SLM updates database
   → SLM broadcasts via WebSocket
   → Backend receives, updates cache immediately

4. Next LLM request uses new config (no delay)
```

## 6. Fallback Chain

```
Agent-specific config (SLM)
    ↓ not found
Default agent config (SLM, is_default=True)
    ↓ SLM unavailable
Environment variables (AUTOBOT_LLM_*)
    ↓ not set
Hardcoded defaults (ollama, localhost:11434)
```

## 7. Security

- API key stored encrypted (Fernet) in SLM database
- API key decrypted only when sending to backend
- WebSocket messages don't include API keys
- Backend fetches decrypted key via HTTPS only

## 8. Migration

```sql
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
);

CREATE INDEX idx_agents_agent_id ON agents(agent_id);
CREATE INDEX idx_agents_is_default ON agents(is_default);

-- Seed default agent
INSERT INTO agents (agent_id, name, llm_provider, llm_model, is_default)
VALUES ('default', 'Default Agent', 'ollama', 'mistral:7b-instruct', TRUE);
```

## 9. Phase 2 Scope

**SLM Server:**
- [ ] Agent model in database.py
- [ ] Pydantic schemas in schemas.py
- [ ] Migration script
- [ ] API router (api/agents.py)
- [ ] WebSocket broadcast on agent changes

**Backend:**
- [ ] SLMClient class (HTTP + WebSocket)
- [ ] AgentConfigCache class
- [ ] Integration with LLMInterface
- [ ] Startup hook for SLM connection

**NOT in Phase 2:**
- Frontend UI for agent management (Phase 3)
- Full migration of existing agents (Phase 4)
