# ADR-004: Chat Workflow and Message Processing Architecture

## Status

**Status**: Accepted

## Date

**Date**: 2025-01-01

## Context

AutoBot's primary interface is a chat-based interaction where users can:
- Ask questions and get AI-powered responses
- Execute workflows and automations
- Query the knowledge base
- Interact with multi-modal content (images, voice)

The chat system must handle:
1. **Streaming responses**: Real-time token-by-token output
2. **Context management**: Maintaining conversation history
3. **Tool execution**: Running workflows triggered by chat
4. **Multi-LLM routing**: Choosing appropriate model for each task
5. **Session persistence**: Saving and resuming conversations

## Decision

We implement a layered chat workflow architecture:

```
User Message
    │
    ▼
┌──────────────────┐
│  Message Router  │ ─── Determines intent and routing
└────────┬─────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌───────────┐
│ Chat  │ │ Workflow  │
│ Flow  │ │ Executor  │
└───┬───┘ └─────┬─────┘
    │           │
    ▼           ▼
┌──────────────────┐
│   LLM Interface  │ ─── Unified LLM abstraction
└────────┬─────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌───────┐
│ Cloud │ │ Local │
│ (API) │ │ (NPU) │
└───────┘ └───────┘
```

### Key Components

1. **Message Router**: Analyzes intent, routes to appropriate handler
2. **Chat Flow**: Standard conversational responses
3. **Workflow Executor**: Runs automations triggered by commands
4. **LLM Interface**: Unified API for multiple LLM providers
5. **Session Manager**: Handles conversation state and history

### Alternatives Considered

1. **Direct LLM Calls**
   - Pros: Simple, low latency
   - Cons: No routing, no workflow integration, single provider lock-in

2. **LangChain/LangGraph**
   - Pros: Feature-rich, community support
   - Cons: Heavy abstraction, version instability, opinionated design

3. **Custom Layered Architecture (Chosen)**
   - Pros: Full control, tailored to needs, clear separation
   - Cons: More code to maintain, no community plugins

## Consequences

### Positive

- **Flexibility**: Easy to add new LLM providers
- **Streaming**: Native support for real-time responses
- **Context Control**: Fine-grained conversation management
- **Testability**: Each layer can be tested independently
- **Observability**: Clear points for logging and monitoring

### Negative

- **Maintenance**: Custom code requires ongoing maintenance
- **Learning Curve**: New developers must understand architecture
- **No Plugins**: Can't use LangChain community integrations

### Neutral

- WebSocket for streaming, REST for non-streaming
- Session state stored in Redis

## Implementation Notes

### Key Files

- `src/llm_interface.py` - Unified LLM abstraction layer
- `backend/api/chat.py` - Chat API endpoints
- `backend/services/chat_service.py` - Chat business logic
- `backend/services/session_manager.py` - Session state management
- `src/enhanced_orchestrator.py` - Workflow orchestration

### Message Flow

```python
# 1. Receive message via WebSocket
async def handle_message(message: ChatMessage, session: Session):
    # 2. Route based on intent
    if message.is_workflow_trigger():
        return await workflow_executor.execute(message)

    # 3. Standard chat flow
    context = await session_manager.get_context(session.id)

    # 4. Stream response
    async for token in llm_interface.stream(message, context):
        await websocket.send(token)

    # 5. Update session
    await session_manager.append_message(session.id, message)
```

### LLM Interface Pattern

```python
from src.llm_interface import LLMInterface

llm = LLMInterface()

# Synchronous completion
response = await llm.complete(prompt, model="gpt-4")

# Streaming completion
async for token in llm.stream(prompt, model="claude-3"):
    yield token

# Embedding (routes to NPU when available)
embedding = await llm.embed(text)
```

### Session Management

```python
from backend.services.session_manager import SessionManager

session_mgr = SessionManager()

# Create session
session = await session_mgr.create(user_id="user123")

# Get conversation context
context = await session_mgr.get_context(session.id, limit=10)

# Persist message
await session_mgr.append_message(session.id, message)
```

### WebSocket Streaming

```typescript
// Frontend WebSocket handler
const ws = new WebSocket('ws://localhost:8001/ws/chat');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'token') {
        appendToken(data.content);
    } else if (data.type === 'complete') {
        finishMessage();
    }
};
```

## Related ADRs

- [ADR-001](001-distributed-vm-architecture.md) - Chat API runs on main backend
- [ADR-003](003-npu-integration-strategy.md) - Local embedding via NPU

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
