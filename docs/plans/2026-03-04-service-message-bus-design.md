# Service Message Bus + Workflow State Machine Design

> **Issues:** #1377, #1379, #1380
> **Date:** 2026-03-04
> **Status:** Approved

## Problem

AutoBot's 8-VM fleet communicates via ad-hoc per-endpoint API schemas. There is no:
- Unified message envelope for cross-service communication
- Cross-service audit trail (each service logs independently)
- Crash-recoverable workflow state (in-memory only)
- Correlation ID for tracing request chains across VMs

## Inspiration

ACP (Agent Communication Protocol) pattern from MarkTechPost article on LangGraph structured message bus. Adapted for AutoBot's distributed multi-VM architecture (not single-process).

## Architecture

Three layers, each building on the previous:

```
Layer 3: WorkflowStateMachine (autobot-backend)
         ├── WorkflowState model (Redis-persisted)
         ├── route_next() routing
         └── publishes transitions to ↓

Layer 2: ServiceMessageBus (autobot-shared)
         ├── publish() → Redis Stream
         ├── subscribe() → async iterator
         ├── get_correlation_chain() → trace requests
         └── stores messages as ↓

Layer 1: ServiceMessage (autobot-shared)
         └── Pydantic model: msg_id, sender, receiver, msg_type, content, correlation_id, meta
```

## Layer 1: ServiceMessage Schema

**File:** `autobot-shared/models/service_message.py`

```python
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
import uuid

ServiceName = Literal[
    "main-backend",
    "slm-backend",
    "ai-stack",
    "browser-worker",
    "npu-worker",
    "llm-cpu",
    "frontend",
    "system",
    "user",
]

MessageType = Literal[
    "task",           # Request to perform work
    "result",         # Successful completion
    "error",          # Failure
    "health",         # Health check/status
    "deploy",         # Deployment operation
    "workflow_step",  # Workflow state transition
    "notification",   # Informational
]

class ServiceMessage(BaseModel):
    """Unified envelope for cross-service communication."""

    msg_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ts: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    sender: str          # ServiceName or custom identifier
    receiver: str        # ServiceName or custom identifier
    msg_type: str        # MessageType or custom
    content: str         # Payload (JSON string or plain text)
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )
    meta: Dict[str, Any] = Field(default_factory=dict)
```

### Design Decisions

- **Pydantic (not dataclass):** Validation + `model_dump_json()` for serialization across services. Existing `AgentEvent` uses dataclass — that stays backend-internal.
- **String-based sender/receiver:** Literals for known services, but strings accepted for extensibility (new VMs, external services).
- **`correlation_id` defaults to new UUID:** Callers pass an existing one to chain related messages. This is the key field for tracing across VMs.
- **`content` is string:** JSON-serialized payload. Keeps the envelope generic — each service interprets content based on `msg_type`.

## Layer 2: ServiceMessageBus

**File:** `autobot-shared/message_bus.py`

Wraps Redis Streams for cross-service publish/subscribe.

```python
class ServiceMessageBusConfig:
    stream_key: str = "autobot:service:messages"
    message_hash_prefix: str = "autobot:service:msg:"
    correlation_prefix: str = "autobot:service:corr:"
    pubsub_channel: str = "autobot:service:live"
    max_stream_length: int = 50000
    message_data_ttl: int = 86400 * 14  # 14 days
    correlation_ttl: int = 86400 * 7    # 7 days

class ServiceMessageBus:
    async def publish(self, msg: ServiceMessage) -> None
    async def subscribe(self, sender=None, receiver=None, msg_type=None) -> AsyncIterator[ServiceMessage]
    async def get_correlation_chain(self, correlation_id: str) -> list[ServiceMessage]
    async def get_latest(self, count=50, sender=None, receiver=None) -> list[ServiceMessage]
    async def close(self) -> None
```

### Storage Strategy (mirrors existing EventStreamManager pattern)

1. **Main stream:** `autobot:service:messages` — ordered log, trimmed to 50k
2. **Message hash:** `autobot:service:msg:{msg_id}` — full message JSON, 14d TTL
3. **Correlation set:** `autobot:service:corr:{correlation_id}` — set of msg_ids, 7d TTL
4. **Pub/Sub channel:** `autobot:service:live` — real-time subscribers

### Key Differences from EventStreamManager

| Aspect | EventStreamManager | ServiceMessageBus |
|--------|-------------------|-------------------|
| Scope | Backend-internal | Cross-service (all VMs) |
| Model | `AgentEvent` (dataclass) | `ServiceMessage` (Pydantic) |
| Database | `main` | `logs` |
| Stream | `autobot:events:stream` | `autobot:service:messages` |
| Correlation | Optional field | First-class with index |
| TTL | 7 days | 14 days |
| Location | `autobot-backend/events/` | `autobot-shared/` |

### Redis Database Choice

Uses `logs` database (already allocated in redis_client.py). The `main` database is for the existing event stream — keeping them separate avoids namespace collisions and allows independent scaling.

## Layer 3: WorkflowStateMachine

**File:** `autobot-backend/api/workflow_state.py`

Replaces in-memory `active_workflows` dict with Redis-persisted state.

```python
class WorkflowState(BaseModel):
    """Persistent workflow state with explicit routing."""

    workflow_id: str
    goal: str
    current_step: str = "planning"  # planning, executing, validating, complete, failed
    active_service: str = "main-backend"
    steps_completed: list[str] = Field(default_factory=list)
    steps_remaining: list[dict] = Field(default_factory=list)
    mailbox: list[ServiceMessage] = Field(default_factory=list)
    done: bool = False
    errors: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = Field(default_factory=dict)

class WorkflowStateMachine:
    """Redis-persisted workflow state with routing logic."""

    async def create(self, workflow_id: str, goal: str, steps: list[dict]) -> WorkflowState
    async def get(self, workflow_id: str) -> Optional[WorkflowState]
    async def transition(self, workflow_id: str, new_step: str, result: str = "") -> WorkflowState
    async def fail(self, workflow_id: str, error: str) -> WorkflowState
    async def complete(self, workflow_id: str) -> WorkflowState
    async def list_active(self) -> list[WorkflowState]

def route_next(state: WorkflowState) -> str:
    """Determine next service based on current state."""
    if state.done:
        return "complete"
    routing = {
        "planning": "main-backend",
        "executing": state.metadata.get("executor_service", "main-backend"),
        "validating": "main-backend",
    }
    return routing.get(state.current_step, "complete")
```

### Redis Storage

- Key pattern: `autobot:workflow:{workflow_id}` in `workflows` database
- Active set: `autobot:workflow:active` (Redis Set of active workflow IDs)
- TTL: 7 days for completed workflows, no TTL for active
- Serialization: `WorkflowState.model_dump_json()` stored as string value

### Integration with existing workflow.py

```python
# BEFORE (in-memory):
active_workflows: Dict[str, Metadata] = {}
active_workflows[workflow_id] = {...}

# AFTER (Redis-persisted):
workflow_sm = WorkflowStateMachine()
state = await workflow_sm.create(workflow_id, goal, steps)
state = await workflow_sm.transition(workflow_id, "executing", result)
```

The existing `event_manager.publish()` calls remain — they feed the frontend WebSocket. `WorkflowStateMachine.transition()` additionally publishes a `ServiceMessage` to the bus for cross-service audit.

## What Does NOT Change

- `AgentEvent` + `RedisEventStreamManager` — unchanged, backend-internal
- `event_manager.publish()` calls in workflow.py — still feed frontend WebSocket
- `ServiceHTTPClient` with HMAC auth — still used for HTTP calls
- All existing API endpoints — unchanged
- Frontend WebSocket message format — unchanged

## File Plan

```
NEW:  autobot-shared/models/__init__.py
NEW:  autobot-shared/models/service_message.py     # ServiceMessage + types
NEW:  autobot-shared/message_bus.py                 # ServiceMessageBus
NEW:  autobot-backend/api/workflow_state.py          # WorkflowState + WorkflowStateMachine + route_next
EDIT: autobot-backend/api/workflow.py                # Replace in-memory dict with WorkflowStateMachine
EDIT: autobot-shared/__init__.py                     # Export new models
```

## Future Integration Points (not in this PR)

- SLM backend publishes deploy/health messages to bus
- AI Stack client wraps requests in ServiceMessage
- Frontend dashboard widget for message timeline
- Alerting on error message patterns
