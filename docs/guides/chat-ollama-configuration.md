# Chat Module: Ollama Configuration Guide

> Configure the AutoBot Chat module to use a local Ollama instance for processing
> natural language prompts.

**Applies to:** AutoBot Backend v2025.3+
**Last updated:** 2026-03-15
**Related issues:** #63, #380, #620, #708, #760, #964, #1070, #1193, #1214, #1325, #1433

---

## Table of Contents

1. [Chat Module Architecture](#1-chat-module-architecture)
2. [Ollama Configuration](#2-ollama-configuration)
3. [Endpoint Resolution Priority](#3-endpoint-resolution-priority)
4. [Model Selection](#4-model-selection)
5. [Chat API Endpoints](#5-chat-api-endpoints)
6. [Setting Up Ollama Locally](#6-setting-up-ollama-locally)
7. [Knowledge-Enhanced Chat (RAG)](#7-knowledge-enhanced-chat-rag)
8. [GPU Model Routing](#8-gpu-model-routing)
9. [SLM Service Discovery](#9-slm-service-discovery)
10. [Complete Configuration Example](#10-complete-configuration-example)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Chat Module Architecture

The chat system is built as a modular pipeline where each stage is encapsulated in a
mixin class composed into a single manager.

### Component Hierarchy

```
api/chat.py (FastAPI router, tags=["chat"])
  |
  +-- ChatWorkflowManager (chat_workflow/manager.py)
        |   Composes four mixins via multiple inheritance:
        |
        +-- ConversationHandlerMixin  (chat_workflow/conversation.py)
        |     Redis-backed history, file-based transcript persistence
        |
        +-- ToolHandlerMixin          (chat_workflow/tool_handler.py)
        |     Command execution, approval workflow
        |
        +-- LLMHandlerMixin           (chat_workflow/llm_handler.py)
        |     Ollama endpoint resolution, prompt building, streaming
        |
        +-- SessionHandlerMixin       (chat_workflow/session_handler.py)
              Session lifecycle, intent classification, safety guards
```

**Source files:**

| File | Purpose |
|------|---------|
| `autobot-backend/api/chat.py` | FastAPI endpoints (router prefix: `/api`) |
| `autobot-backend/chat_workflow/__init__.py` | Module entry, global singleton |
| `autobot-backend/chat_workflow/manager.py` | `ChatWorkflowManager` orchestrator |
| `autobot-backend/chat_workflow/llm_handler.py` | `LLMHandlerMixin` -- Ollama interaction |
| `autobot-backend/chat_workflow/conversation.py` | `ConversationHandlerMixin` -- history |
| `autobot-backend/chat_workflow/session_handler.py` | `SessionHandlerMixin` -- sessions |
| `autobot-backend/chat_workflow/models.py` | `WorkflowSession`, `StreamingMessage` |
| `autobot-backend/chat_workflow/graph.py` | LangGraph `StateGraph` (optional) |
| `autobot-backend/config/config.yaml` | Runtime config read by `ConfigManager` |
| `autobot-backend/config/model_config.py` | `ModelConfigMixin` -- model selection |
| `autobot-backend/config/service_config.py` | `ServiceConfigMixin` -- host/port resolution |

### Message Flow

A user message traverses these stages before reaching Ollama:

```
User sends message
       |
       v
[1] api/chat.py -- POST /api/chat/message or POST /api/chats/{chat_id}/message
       |
       v
[2] ChatWorkflowManager.process_message_stream(session_id, message, context)
       |
       v
[3] SessionHandlerMixin._initialize_chat_session()
       |   - get_or_create_session() loads conversation history from Redis/file
       |   - IntentClassifier.classify() determines intent (COMMAND, QUESTION, END, ...)
       |   - ConversationSafetyGuards.check() validates exit intent
       |   - Creates terminal session if needed
       |
       v
[4] LLMHandlerMixin._prepare_llm_request_params()
       |   - _get_selected_model()        -- resolve model name
       |   - _discover_ollama_from_slm()   -- try SLM service discovery
       |   - _get_ollama_endpoint_for_model() -- GPU routing fallback
       |   - _get_system_prompt()          -- personality + language
       |   - _retrieve_knowledge_context() -- RAG retrieval
       |   - _build_full_prompt()          -- assemble final prompt
       |
       v
[5] HTTP POST to Ollama /api/generate (streaming or non-streaming)
       |
       v
[6] StreamingMessage accumulates tokens, yields WorkflowMessage chunks
       |
       v
[7] ConversationHandlerMixin._persist_conversation()
       |   - Updates in-memory session history
       |   - Saves to Redis (24h TTL) and file transcript concurrently
       |
       v
[8] SSE stream ends; frontend receives all chunks
```

### Session Management

Sessions are managed in-memory with Redis-backed persistence:

```python
# chat_workflow/models.py
@dataclass
class WorkflowSession:
    session_id: str
    workflow: Any                    # AsyncChatWorkflow instance
    created_at: float               # time.time()
    last_activity: float            # Updated on every message
    message_count: int              # Incremented per message
    metadata: Dict[str, Any]        # RAG citations, query intent, etc.
    conversation_history: List[Dict[str, str]]  # Last 10 exchanges
```

Key behaviors:

- **Redis key format:** `chat:conversation:{session_id}` with 24-hour TTL
- **File transcripts:** `data/conversation_transcripts/{session_id}.json`
- **History window:** Last 10 exchanges are kept in memory; older entries are in file only
- **Inactive cleanup:** `cleanup_inactive_sessions(max_age_seconds=3600)` removes stale sessions
- **Thread safety:** All session operations use `asyncio.Lock`
- **Global singleton:** `get_chat_workflow_manager()` returns a thread-safe singleton

### AI Stack Integration

The chat API includes enhanced endpoints that route through the AI Stack (VM `.24`)
for additional capabilities such as multi-model orchestration:

| Endpoint | Description |
|----------|-------------|
| `POST /api/enhanced` | AI Stack enhanced chat (non-streaming) |
| `POST /api/stream-enhanced` | AI Stack enhanced chat (streaming) |
| `GET /api/health-enhanced` | AI Stack health check |
| `GET /api/capabilities` | List available AI Stack capabilities |

These endpoints use `services.ai_stack_client.get_ai_stack_client()` and fall back
to the standard Ollama path when the AI Stack is unavailable.

---

## 2. Ollama Configuration

AutoBot resolves the Ollama endpoint and model through a layered configuration
system. There are three configuration surfaces: `config.yaml`, environment variables,
and the SSOT config module.

### 2.1 config.yaml Setup

The primary configuration file lives at `autobot-backend/config/config.yaml`.
The `ConfigManager` reads it at startup via `config/loader.py`.

```yaml
# autobot-backend/config/config.yaml

# Backend LLM configuration
# Primary path for _get_ollama_endpoint() in chat_workflow/llm_handler.py
backend:
  llm:
    ollama:
      endpoint: http://127.0.0.1:11434
      # GPU endpoint for model-to-endpoint routing (#1070)
      # When set, models in gpu_models are routed here instead of the default.
      # gpu_endpoint: http://172.16.168.20:11434
      # gpu_models:
      #   - "qwen3.5:9b"
      #   - "mistral:7b-instruct"
      #   - "codellama:13b"

# Infrastructure host overrides
# Fallback path for _get_ollama_endpoint_fallback() via get_host("ollama")
infrastructure:
  hosts:
    ollama: 127.0.0.1
```

The `backend.llm.ollama.endpoint` key is the first place `LLMHandlerMixin._get_ollama_endpoint()`
checks. It must be a full URL with scheme (`http://` or `https://`). The
`/api/generate` suffix is appended automatically if missing.

### 2.2 Environment Variables

Environment variables override `config.yaml` values. The mapping is defined in
`config/loader.py` as `ENV_VAR_MAPPINGS`:

```bash
# Primary Ollama host (highest priority for get_host("ollama"))
# Sets: backend.llm.local.providers.ollama.host
export AUTOBOT_OLLAMA_HOST=127.0.0.1

# Default LLM model (used by _get_selected_model fallback)
# Sets: backend.llm.local.providers.ollama.selected_model
export AUTOBOT_DEFAULT_LLM_MODEL=llama3.2

# Full endpoint override (sets the endpoint URL directly)
# Sets: backend.llm.local.providers.ollama.endpoint
export AUTOBOT_OLLAMA_ENDPOINT=http://127.0.0.1:11434
```

**How env vars are applied:** `config/loader.py:apply_env_overrides()` reads each
`AUTOBOT_*` variable and deep-merges it into the loaded config dictionary at
startup. The conversion handles booleans and integers automatically.

### 2.3 SSOT Configuration

The SSOT (Single Source of Truth) config provides programmatic access and is the
recommended way to read configuration in shared code:

```python
from autobot_shared.ssot_config import config

# Access Ollama configuration via SSOT
ollama_host = config.vm.ollama           # Returns configured host
ollama_port = config.port.ollama         # Returns configured port (11434)
ollama_url = f"http://{ollama_host}:{ollama_port}"
```

The `ConfigManager` (instantiated as `global_config_manager` in `dependencies.py`)
wraps all three layers. Its `get_host()` and `get_port()` methods implement the
priority chain described below.

### 2.4 ConfigManager Host/Port Resolution

`ServiceConfigMixin.get_host(service)` (in `config/service_config.py`) resolves
the host for any service using this priority:

```python
def get_host(self, service: str) -> str:
    # 1. Environment variable AUTOBOT_{SERVICE}_HOST (highest priority)
    env_key = f"AUTOBOT_{service.upper()}_HOST"
    env_host = os.getenv(env_key)
    if env_host:
        return env_host

    # 2. Config file infrastructure.hosts.{service}
    host = self.get_nested(f"infrastructure.hosts.{service}")
    if host:
        return host

    # 3. Module-level cached fallback map
    return _HOST_SERVICE_MAP.get(service, "localhost")
```

For Ollama, the fallback map entry is:

```python
# config/service_config.py
_HOST_SERVICE_MAP = {
    "ollama": ConfigRegistry.get("vm.ollama", "127.0.0.1"),
    # ... other services
}
```

`get_port("ollama")` follows the same three-tier pattern and defaults to the
`NetworkConstants.OLLAMA_PORT` value (11434).

---

## 3. Endpoint Resolution Priority

When the chat module needs to send a prompt to Ollama, `LLMHandlerMixin` resolves
the endpoint through a five-step fallback chain. Each step is tried in order; the
first successful result is used.

### Resolution Chain

```
[1] SLM service discovery (_discover_ollama_from_slm)
     |  Calls: services/slm_client.py -> discover_service("ollama")
     |  Cached: 60s TTL
     |  Returns: base URL like "http://172.16.168.20:11434"
     |
     +-- If found -> append /api/generate -> DONE
     |
     v
[2] Per-model GPU routing (_get_ollama_endpoint_for_model)
     |  Reads: backend.llm.ollama.gpu_endpoint + gpu_models from config.yaml
     |  If model_name is in gpu_models -> return gpu_endpoint
     |
     +-- If matched -> append /api/generate -> DONE
     |
     v
[3] config.yaml endpoint (_get_ollama_endpoint)
     |  Reads: backend.llm.ollama.endpoint via global_config_manager.get_nested()
     |  Validates URL starts with http:// or https://
     |
     +-- If valid -> append /api/generate -> DONE
     |
     v
[4] ConfigManager fallback (_get_ollama_endpoint_fallback)
     |  Calls: ConfigManager().get_host("ollama") + get_port("ollama")
     |  This triggers the get_host three-tier chain:
     |    (a) AUTOBOT_OLLAMA_HOST env var
     |    (b) infrastructure.hosts.ollama in config.yaml
     |    (c) _HOST_SERVICE_MAP default (127.0.0.1)
     |
     +-- Builds: http://{host}:{port}/api/generate -> DONE
```

### Source Code Reference

```python
# chat_workflow/llm_handler.py

class LLMHandlerMixin:

    def _get_ollama_endpoint(self) -> str:
        """Get Ollama endpoint from config with fallbacks."""
        try:
            endpoint = global_config_manager.get_nested(
                "backend.llm.ollama.endpoint", None
            )
            if endpoint and endpoint.startswith(("http://", "https://")):
                if not endpoint.endswith("/api/generate"):
                    endpoint = endpoint.rstrip("/") + "/api/generate"
                return endpoint
            return self._get_ollama_endpoint_fallback()
        except Exception as e:
            logger.error("Failed to load Ollama endpoint from config: %s", e)
            return self._get_ollama_endpoint_fallback()

    def _get_ollama_endpoint_fallback(self) -> str:
        """Get Ollama endpoint from ConfigManager as fallback."""
        from config import ConfigManager

        config = ConfigManager()
        ollama_host = config.get_host("ollama")
        ollama_port = config.get_port("ollama")
        return f"http://{ollama_host}:{ollama_port}/api/generate"

    def _get_ollama_endpoint_for_model(self, model_name: str) -> str:
        """Get Ollama endpoint routed by model name (#1070)."""
        try:
            base_url = global_config_manager.get_ollama_endpoint_for_model(
                model_name
            )
            if base_url and base_url.startswith(("http://", "https://")):
                if not base_url.endswith("/api/generate"):
                    base_url = base_url.rstrip("/") + "/api/generate"
                return base_url
        except Exception as e:
            logger.warning("Model endpoint routing failed: %s", e)
        return self._get_ollama_endpoint()

    async def _discover_ollama_from_slm(self) -> str | None:
        """Try to discover Ollama endpoint from SLM service discovery (#1214)."""
        try:
            from services.slm_client import discover_service

            url = await discover_service("ollama")
            if url and url.startswith(("http://", "https://")):
                return url
        except Exception as e:
            logger.debug("SLM service discovery unavailable: %s", e)
        return None
```

The final assembly happens in `_prepare_llm_request_params()`:

```python
    async def _prepare_llm_request_params(self, session, message, ...):
        selected_model = self._get_selected_model()

        # Step 1: SLM discovery (fleet-managed endpoint)
        slm_base = await self._discover_ollama_from_slm()
        if slm_base:
            ollama_endpoint = slm_base.rstrip("/") + "/api/generate"
        else:
            # Steps 2-4: GPU routing -> config.yaml -> fallback
            ollama_endpoint = self._get_ollama_endpoint_for_model(selected_model)

        # ... build prompt, return params
        return {
            "endpoint": ollama_endpoint,
            "model": selected_model,
            "prompt": full_prompt,
        }
```

---

## 4. Model Selection

### Resolution Priority

Model selection follows its own priority chain, defined in
`config/model_config.py:ModelConfigMixin.get_selected_model()`:

```
[1] config.yaml: backend.llm.local.providers.ollama.selected_model
[2] Environment: AUTOBOT_DEFAULT_LLM_MODEL
[3] ModelConstants.DEFAULT_OLLAMA_MODEL (from ConfigRegistry -> "qwen3.5:9b")
```

### Source Code Reference

```python
# config/model_config.py

class ModelConfigMixin:

    def get_selected_model(self) -> str:
        """Get the currently selected model from config.yaml."""
        # 1. Config.yaml (primary)
        selected_model = self.get_nested(
            "backend.llm.local.providers.ollama.selected_model"
        )
        if selected_model:
            return selected_model

        # 2. Environment variable
        env_model = os.getenv("AUTOBOT_DEFAULT_LLM_MODEL")
        if env_model:
            return env_model

        # 3. Centralized fallback constant
        from constants.model_constants import ModelConstants
        return ModelConstants.DEFAULT_OLLAMA_MODEL
```

The `LLMHandlerMixin._get_selected_model()` in `chat_workflow/llm_handler.py` adds
one more fallback layer:

```python
    def _get_selected_model(self) -> str:
        """Get selected LLM model from config with fallback."""
        try:
            default_model = global_config_manager.get_default_llm_model()
            selected = global_config_manager.get_nested(
                "backend.llm.ollama.selected_model", default_model
            )
            if selected and isinstance(selected, str):
                return selected
            return default_model
        except Exception:
            return os.getenv(
                "AUTOBOT_DEFAULT_LLM_MODEL",
                ModelConstants.DEFAULT_OLLAMA_MODEL,
            )
```

This checks `backend.llm.ollama.selected_model` (the flat config.yaml key)
in addition to the nested legacy key.

### Configuration Methods

**Method 1: Environment variable**

```bash
export AUTOBOT_DEFAULT_LLM_MODEL=llama3.2:latest
```

**Method 2: config.yaml (flat key -- preferred)**

```yaml
# autobot-backend/config/config.yaml
backend:
  llm:
    ollama:
      endpoint: http://127.0.0.1:11434
      selected_model: "llama3.2:latest"
```

**Method 3: config.yaml (legacy nested key)**

```yaml
# autobot-backend/config/config.yaml
backend:
  llm:
    local:
      providers:
        ollama:
          selected_model: "llama3.2:latest"
```

**Method 4: Runtime API**

```bash
curl -sk -X POST https://localhost:8443/api/settings/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"backend": {"llm": {"local": {"providers": {"ollama": {"selected_model": "mistral:latest"}}}}}}'
```

**Method 5: Programmatic update**

```python
from dependencies import global_config_manager

global_config_manager.update_llm_model("llama3.2:latest")
# Writes to both settings.json and config.yaml
```

### Available Models

Check which models are installed on your Ollama instance:

```bash
curl -s http://localhost:11434/api/tags | python3 -c "
import json, sys
data = json.load(sys.stdin)
for m in data.get('models', []):
    size_gb = m.get('size', 0) / (1024**3)
    print(f\"  {m['name']:<35} {size_gb:.1f} GB\")
"
```

### ModelConstants Defaults

The system-wide model defaults are defined in `constants/model_constants.py`:

```python
from constants.model_constants import ModelConstants

ModelConstants.DEFAULT_OLLAMA_MODEL     # "qwen3.5:9b" (from ConfigRegistry)
ModelConstants.DEFAULT_OPENAI_MODEL     # "gpt-4"
ModelConstants.DEFAULT_ANTHROPIC_MODEL  # "claude-3-5-sonnet-20241022"
ModelConstants.EMBEDDING_MODEL          # "nomic-embed-text:latest"
ModelConstants.CURRENT_PROVIDER         # "ollama"
```

---

## 5. Chat API Endpoints

All endpoints are mounted under the `/api` prefix (see
`initialization/router_registry/core_routers.py` -- chat router has prefix `""`).
Authentication is required on all endpoints via `get_current_user`.

### Core Chat Endpoints

#### Send Message (non-streaming)

```http
POST /api/chat
POST /api/chat/message
Content-Type: application/json
Authorization: Bearer {token}

{
    "content": "What services are running on the network?",
    "session_id": "optional-session-uuid",
    "role": "user",
    "message_type": "text",
    "language": "en",
    "metadata": {}
}
```

Request model (`ChatMessage`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | `str` | Yes | Message text (1-50,000 chars) |
| `role` | `str` | No | `user`, `assistant`, or `system` (default: `user`) |
| `session_id` | `str` | No | Chat session ID; auto-generated if omitted |
| `message_type` | `str` | No | Message type (default: `text`) |
| `language` | `str` | No | Response language code (e.g., `en`, `es`, `de`) |
| `metadata` | `dict` | No | Additional key-value pairs |

Response:

```json
{
    "success": true,
    "data": {
        "content": "Based on the current network scan...",
        "role": "assistant",
        "session_id": "chat_abc123",
        "message_id": "msg_def456",
        "timestamp": "2026-03-15T10:30:00Z"
    },
    "message": "Message processed successfully",
    "request_id": "req_789"
}
```

#### Send Message to Chat by ID (streaming SSE)

```http
POST /api/chats/{chat_id}/message
Content-Type: application/json
Authorization: Bearer {token}

{
    "message": "What services are running on the network?",
    "context": {},
    "use_knowledge": true,
    "language": "en"
}
```

Response (Server-Sent Events):

```
data: {"type": "start", "session_id": "chat_abc123", "request_id": "req_789"}

data: {"type": "response", "content": "Based on", "metadata": {"message_id": "...", "version": 1, "operation": "stream", "streaming": true}}

data: {"type": "response", "content": " the current", "metadata": {"message_id": "...", "version": 2, "operation": "stream", "streaming": true}}

data: {"type": "response", "content": " network scan...", "metadata": {"message_id": "...", "version": 3, "operation": "stream", "streaming": true}}

data: {"type": "end", "request_id": "req_789"}
```

SSE message types:

| Type | Description |
|------|-------------|
| `start` | Stream opened, includes `session_id` and `request_id` |
| `response` | LLM-generated text token |
| `thought` | Internal reasoning (between `[THOUGHT]` tags) |
| `planning` | Plan formulation (between `[PLANNING]` tags) |
| `terminal_command` | Command to be executed |
| `terminal_output` | Command execution output |
| `approval_request` | Awaiting user approval for a command |
| `error` | Error during processing |
| `end` | Stream complete |

#### Stream Chat Response

```http
POST /api/chat/stream
Content-Type: application/json
Authorization: Bearer {token}

{
    "content": "Explain Docker networking",
    "session_id": "optional-session-id"
}
```

Returns a `StreamingResponse` with `media_type="text/event-stream"` and headers:
- `Cache-Control: no-cache`
- `Connection: keep-alive`
- `X-Accel-Buffering: no`

### Session Management Endpoints

```http
# Create a new chat session
POST /api/chat/sessions
Authorization: Bearer {token}

# List all sessions
GET /api/chat/sessions
Authorization: Bearer {token}

# Get session details
GET /api/chat/sessions/{session_id}
Authorization: Bearer {token}

# Update session metadata
PUT /api/chat/sessions/{session_id}
Authorization: Bearer {token}

# Delete session
DELETE /api/chat/sessions/{session_id}
Authorization: Bearer {token}

# Export session transcript
GET /api/chat/sessions/{session_id}/export
Authorization: Bearer {token}

# Reset all sessions
POST /api/chat/reset
Authorization: Bearer {token}
```

### Chat History Endpoints

```http
# List all chats (with session metadata)
GET /api/chats
GET /api/chat/chats
Authorization: Bearer {token}

# Resume a chat
POST /api/chats/{chat_id}/resume
Authorization: Bearer {token}

# Save chat to persistent storage
POST /api/chats/{chat_id}/save
Authorization: Bearer {token}

# Delete a chat
DELETE /api/chats/{chat_id}
Authorization: Bearer {token}
```

### Activity Tracking Endpoints

```http
# Log a session activity
POST /api/chat/sessions/{session_id}/activities
Authorization: Bearer {token}

# Batch log activities
POST /api/chat/sessions/{session_id}/activities/batch
Authorization: Bearer {token}

# Get session activities
GET /api/chat/sessions/{session_id}/activities
Authorization: Bearer {token}
```

### Health and Status

```http
# Chat service health check
GET /api/chat/health
Authorization: Bearer {token}

Response:
{
    "status": "healthy",
    "timestamp": "2026-03-15T10:30:00Z",
    "components": {
        "chat_history_manager": "healthy",
        "llm_service": "healthy"
    }
}

# Chat statistics
GET /api/chat/stats
Authorization: Bearer {token}
```

### AI Stack Enhanced Endpoints

```http
# Enhanced chat (AI Stack routing)
POST /api/enhanced
Authorization: Bearer {token}

# Enhanced streaming chat
POST /api/stream-enhanced
Authorization: Bearer {token}

# AI Stack health
GET /api/health-enhanced
Authorization: Bearer {token}

# List AI capabilities
GET /api/capabilities
Authorization: Bearer {token}

# Translate text
POST /api/translate
Authorization: Bearer {token}

# Detect language
POST /api/detect-language
Authorization: Bearer {token}
```

### Direct Response (Command Approval)

```http
POST /api/chat/direct
Authorization: Bearer {token}

{
    "chat_id": "session-uuid",
    "message": "yes",
    "remember_choice": false
}
```

Used when the chat workflow requests command approval and the user responds with
`yes`/`no`.

---

## 6. Setting Up Ollama Locally

### Prerequisites

- Linux x86_64 or ARM64 (WSL2 supported)
- Minimum 8 GB RAM (16 GB+ recommended for 7B+ models)
- NVIDIA GPU with CUDA 12+ for GPU acceleration (optional)

### Step 1: Install Ollama

```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

Verify installation:

```bash
ollama --version
```

### Step 2: Start the Ollama Service

```bash
# Start as a systemd service
sudo systemctl enable ollama
sudo systemctl start ollama

# Verify it is running
sudo systemctl status ollama --no-pager
```

Ollama listens on `http://127.0.0.1:11434` by default.

### Step 3: Pull a Model

```bash
# Pull the default model
ollama pull qwen3.5:9b

# Or pull a different model
ollama pull llama3.2

# Verify available models
ollama list
```

### Step 4: Verify Ollama Responds

```bash
# Check the API is alive
curl -s http://127.0.0.1:11434/api/tags | python3 -m json.tool

# Test generation
curl -s http://127.0.0.1:11434/api/generate \
  -d '{"model": "qwen3.5:9b", "prompt": "Hello", "stream": false}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('response','')[:200])"
```

### Step 5: Configure AutoBot

Option A -- Environment variables (quick, non-persistent):

```bash
export AUTOBOT_OLLAMA_HOST=127.0.0.1
export AUTOBOT_DEFAULT_LLM_MODEL=qwen3.5:9b
```

Option B -- config.yaml (persistent, recommended):

```yaml
# Edit autobot-backend/config/config.yaml
backend:
  llm:
    ollama:
      endpoint: http://127.0.0.1:11434
      selected_model: "qwen3.5:9b"

infrastructure:
  hosts:
    ollama: 127.0.0.1
```

### Step 6: Restart the AutoBot Backend

```bash
sudo systemctl restart autobot-backend

# Verify the backend is up (takes approximately 6 minutes to fully initialize)
curl -sk https://localhost:8443/api/health | python3 -m json.tool
```

### Step 7: Test the Chat Endpoint

```bash
# Get an auth token first
TOKEN=$(curl -sk https://localhost:8443/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"..."}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))")

# Send a test message
curl -sk https://localhost:8443/api/chat/message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"content": "Hello, what can you help me with?"}' \
  | python3 -m json.tool
```

---

## 7. Knowledge-Enhanced Chat (RAG)

The chat pipeline automatically retrieves relevant knowledge context before sending
prompts to Ollama. This is the Retrieval-Augmented Generation (RAG) flow.

### RAG Pipeline

```
User message
     |
     v
ChatKnowledgeService.conversation_aware_retrieve()
     |   - Analyzes query intent (FACTUAL, CONVERSATIONAL, COMMAND, ...)
     |   - Optionally enhances query using conversation context
     |   - Retrieves top_k=5 results above score_threshold=0.3
     |
     v
Returns: (knowledge_context, citations, query_intent, enhanced_query)
     |
     v
LLMHandlerMixin._build_full_prompt()
     |   system_prompt + knowledge_context + conversation_context + user_message
     |
     v
Sent to Ollama
```

### Source Code Reference

```python
# chat_workflow/llm_handler.py

async def _retrieve_knowledge_context(
    self, message: str, session: WorkflowSession
) -> tuple:
    """Retrieve knowledge context for RAG. Returns (context, citations)."""
    knowledge_context, citations, query_intent, enhanced_query = (
        await self.knowledge_service.conversation_aware_retrieve(
            query=message,
            conversation_history=session.conversation_history or [],
            top_k=5,
            score_threshold=0.3,
            force_retrieval=False,
        )
    )
    if knowledge_context:
        session.metadata["last_citations"] = citations
        session.metadata["used_knowledge"] = True
        session.metadata["query_intent"] = query_intent.intent.value
    return knowledge_context, citations

def _build_full_prompt(
    self,
    system_prompt: str,
    knowledge_context: str,
    conversation_context: str,
    message: str,
) -> str:
    """Build full prompt with optional knowledge context."""
    if knowledge_context:
        return (
            system_prompt + "\n\n"
            + knowledge_context + "\n"
            + conversation_context
            + f"\n**Current user message:** {message}\n\nAssistant:"
        )
    return (
        system_prompt
        + conversation_context
        + f"\n**Current user message:** {message}\n\nAssistant:"
    )
```

### RAG Configuration

RAG parameters are defined in `constants/model_constants.py:ModelConfig`:

| Parameter | Value | Description |
|-----------|-------|-------------|
| `RAG_DEFAULT_MAX_RESULTS` | 5 | Top-k retrieval results |
| `RAG_HYBRID_WEIGHT_SEMANTIC` | 0.7 | Semantic search weight |
| `RAG_HYBRID_WEIGHT_KEYWORD` | 0.3 | Keyword search weight |
| `RAG_DIVERSITY_THRESHOLD` | 0.85 | Deduplication similarity threshold |
| `RAG_DEFAULT_CONTEXT_LENGTH` | 2000 | Characters of context injected |
| `RAG_MAX_CONTEXT_LENGTH` | 5000 | Maximum context length |

### Disabling RAG

Pass `use_knowledge=false` in the request body or context to skip knowledge retrieval:

```json
{
    "message": "Just chat without knowledge base",
    "context": {},
    "use_knowledge": false
}
```

When `knowledge_service` is `None` (e.g., knowledge base failed to initialize),
RAG is automatically skipped and `session.metadata["used_knowledge"]` is set to
`False`.

---

## 8. GPU Model Routing

For models that benefit from GPU acceleration, AutoBot can route specific models
to a separate Ollama instance running on a GPU-equipped machine.

### Configuration

```yaml
# autobot-backend/config/config.yaml
backend:
  llm:
    ollama:
      endpoint: http://127.0.0.1:11434           # CPU endpoint (default)
      gpu_endpoint: http://172.16.168.20:11434    # GPU-accelerated endpoint
      gpu_models:
        - "qwen3.5:9b"
        - "mistral:7b-instruct"
        - "codellama:13b"
```

### How It Works

`ModelConfigMixin.get_ollama_endpoint_for_model()` in `config/model_config.py`
performs the routing:

```python
def get_ollama_endpoint_for_model(self, model_name: str) -> str:
    """Get Ollama endpoint routed by model name (#1070)."""
    ollama_cfg = self.get_nested("backend.llm.ollama", {})
    gpu_endpoint = ollama_cfg.get("gpu_endpoint", "")
    gpu_models = ollama_cfg.get("gpu_models", [])

    if gpu_endpoint and gpu_models:
        gpu_set = {m.strip().lower() for m in gpu_models}
        if model_name.strip().lower() in gpu_set:
            return gpu_endpoint

    # Fall back to default endpoint
    return self._resolve_default_ollama_endpoint()
```

Model names are compared case-insensitively. The returned URL is a base URL
(without `/api/generate`); the suffix is appended by the caller.

### Verifying Routing

Check the backend logs after sending a chat message:

```bash
journalctl -u autobot-backend --since "30 seconds ago" \
  | grep -i "ollama request\|Using model"
```

Expected output:

```
[ChatWorkflowManager] Making Ollama request to: http://172.16.168.20:11434/api/generate
[ChatWorkflowManager] Using model: qwen3.5:9b
```

---

## 9. SLM Service Discovery

In fleet-managed deployments, the SLM (Service Lifecycle Manager) on VM `.19`
maintains a registry of running services. The chat module queries this registry
before falling back to local configuration.

### Discovery Flow

```python
# chat_workflow/llm_handler.py

async def _discover_ollama_from_slm(self) -> str | None:
    """Try to discover Ollama endpoint from SLM service discovery (#1214).

    Uses the SLM /api/discover/ollama endpoint (cached with 60s TTL).
    Returns base URL (no /api/generate suffix) or None if unavailable.
    """
    try:
        from services.slm_client import discover_service

        url = await discover_service("ollama")
        if url and url.startswith(("http://", "https://")):
            logger.info("Ollama endpoint from SLM discovery: %s", url)
            return url
    except Exception as e:
        logger.debug("SLM service discovery unavailable: %s", e)
    return None
```

### SLM Client Fallback Chain

The `discover_service()` function in `services/slm_client.py` has its own
fallback chain:

```
[1] In-memory cache (60s TTL)
[2] HTTP GET to SLM: {SLM_URL}/api/discover/{service_name}
[3] Environment variable fallback
[4] ServiceNotConfiguredError
```

### Configuring SLM URL

```bash
export SLM_URL=https://172.16.168.19:8443
```

Without `SLM_URL`, the SLM client is unavailable and discovery silently returns
`None`, falling through to local configuration.

### Ultimate Fallback Config

When the SLM is unreachable, `slm_client.py` uses these defaults:

```python
ULTIMATE_FALLBACK_CONFIG = {
    "llm_provider": os.getenv("AUTOBOT_LLM_PROVIDER", "ollama"),
    "llm_endpoint": os.getenv(
        "OLLAMA_URL",
        os.getenv("OLLAMA_HOST", "http://localhost:11434"),
    ),
    "llm_model": os.getenv("AUTOBOT_DEFAULT_LLM_MODEL", "qwen3.5:9b"),
    "llm_timeout": 30,
    "llm_temperature": 0.7,
}
```

---

## 10. Complete Configuration Example

The following script performs end-to-end verification: checks Ollama availability,
configures the backend, and sends a test chat message.

```python
#!/usr/bin/env python3
"""
Configure and verify AutoBot Chat Module with local Ollama.

Usage:
    python3 docs/guides/configure_chat_ollama.py

Prerequisites:
    - Ollama running on localhost:11434 with at least one model pulled
    - AutoBot backend running on https://localhost:8443
    - pip install aiohttp
"""

import asyncio
import json
import logging
import ssl
import sys

import aiohttp

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
BACKEND_URL = "https://172.16.168.20:8443"


async def check_ollama() -> list[str]:
    """Verify Ollama is running and list available models.

    Returns:
        List of model names available in the Ollama instance.

    Raises:
        SystemExit: If Ollama is not reachable.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{OLLAMA_BASE_URL}/api/tags", timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                data = await resp.json()
                models = [m["name"] for m in data.get("models", [])]
                logger.info("Ollama is running. Available models: %s", models)
                return models
    except aiohttp.ClientError as exc:
        logger.error("Cannot reach Ollama at %s: %s", OLLAMA_BASE_URL, exc)
        logger.error("Start Ollama with: sudo systemctl start ollama")
        sys.exit(1)


async def get_auth_token(
    session: aiohttp.ClientSession, ssl_ctx: ssl.SSLContext
) -> str:
    """Authenticate and return a Bearer token.

    Args:
        session: aiohttp client session.
        ssl_ctx: SSL context (unverified for local dev).

    Returns:
        JWT access token string.

    Raises:
        SystemExit: If authentication fails.
    """
    async with session.post(
        f"{BACKEND_URL}/api/auth/login",
        json={"username": "admin", "password": "changeme"},
        ssl=ssl_ctx,
    ) as resp:
        if resp.status != 200:
            logger.error("Authentication failed (status %d)", resp.status)
            sys.exit(1)
        data = await resp.json()
        token = data.get("access_token", "")
        logger.info("Authenticated successfully")
        return token


async def update_backend_config(
    session: aiohttp.ClientSession,
    ssl_ctx: ssl.SSLContext,
    token: str,
    model_name: str,
) -> None:
    """Push Ollama configuration to the AutoBot backend.

    Args:
        session: aiohttp client session.
        ssl_ctx: SSL context.
        token: Bearer token.
        model_name: Ollama model to configure as default.
    """
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "backend": {
            "llm": {
                "ollama": {
                    "endpoint": OLLAMA_BASE_URL,
                    "selected_model": model_name,
                },
                "local": {
                    "providers": {
                        "ollama": {
                            "selected_model": model_name,
                        }
                    }
                },
            }
        }
    }
    async with session.post(
        f"{BACKEND_URL}/api/settings/",
        json=payload,
        headers=headers,
        ssl=ssl_ctx,
    ) as resp:
        if resp.status == 200:
            logger.info("Backend config updated: model=%s", model_name)
        else:
            text = await resp.text()
            logger.warning("Config update returned %d: %s", resp.status, text[:200])


async def test_chat(
    session: aiohttp.ClientSession,
    ssl_ctx: ssl.SSLContext,
    token: str,
) -> None:
    """Send a test chat message and print the response.

    Args:
        session: aiohttp client session.
        ssl_ctx: SSL context.
        token: Bearer token.
    """
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"content": "Hello, what can you help me with?"}

    async with session.post(
        f"{BACKEND_URL}/api/chat/message",
        json=payload,
        headers=headers,
        ssl=ssl_ctx,
    ) as resp:
        data = await resp.json()
        if data.get("success"):
            content = data.get("data", {}).get("content", "")
            logger.info("Chat response: %s", content[:300])
        else:
            logger.error("Chat failed: %s", json.dumps(data, indent=2)[:500])


async def main() -> None:
    """Run the full configuration and verification sequence."""
    # Step 1: Verify Ollama
    models = await check_ollama()
    if not models:
        logger.error("No models found. Pull one with: ollama pull qwen3.5:9b")
        sys.exit(1)

    model_name = models[0]  # Use the first available model
    logger.info("Using model: %s", model_name)

    # Step 2: Configure and test backend
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async with aiohttp.ClientSession() as session:
        token = await get_auth_token(session, ssl_ctx)
        await update_backend_config(session, ssl_ctx, token, model_name)
        await test_chat(session, ssl_ctx, token)

    logger.info("Configuration complete. Ollama is ready for chat.")


if __name__ == "__main__":
    asyncio.run(main())
```

### Quick Setup Checklist

```bash
# 1. Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# 2. Start the service
sudo systemctl enable --now ollama

# 3. Pull a model
ollama pull qwen3.5:9b

# 4. Verify
curl -s http://127.0.0.1:11434/api/tags | python3 -m json.tool

# 5. Set environment (or edit config.yaml)
export AUTOBOT_OLLAMA_HOST=127.0.0.1
export AUTOBOT_DEFAULT_LLM_MODEL=qwen3.5:9b

# 6. Restart backend
sudo systemctl restart autobot-backend

# 7. Wait for initialization (~6 minutes), then test
curl -sk https://localhost:8443/api/health | python3 -m json.tool

# 8. Test chat (replace TOKEN with actual Bearer token)
curl -sk https://localhost:8443/api/chat/message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"content": "Hello"}' | python3 -m json.tool
```

---

## 11. Troubleshooting

### Ollama Connection Refused

**Symptom:** Backend logs show `ConnectionRefusedError` when trying to reach Ollama.

**Diagnosis:**

```bash
# Check Ollama service status
sudo systemctl status ollama --no-pager

# Check if port 11434 is listening
ss -tlnp | grep 11434

# Test connectivity directly
curl -s http://127.0.0.1:11434/api/tags
```

**Fixes:**

- Start Ollama: `sudo systemctl start ollama`
- If binding to a different interface, set `OLLAMA_HOST=0.0.0.0` in
  `/etc/systemd/system/ollama.service.d/override.conf` and reload
- WSL2: Ensure Windows Firewall is not blocking port 11434

### Model Not Found

**Symptom:** Ollama returns `{"error": "model 'xyz' not found"}`.

**Diagnosis:**

```bash
# List installed models
ollama list

# Check what the backend is requesting
journalctl -u autobot-backend --since "1 minute ago" | grep "Using model"
```

**Fixes:**

- Pull the model: `ollama pull <model_name>`
- Verify the model name matches exactly (including tag): `qwen3.5:9b` vs `mistral:latest`
- Update config to use an installed model

### Slow Responses

**Symptom:** Chat responses take 30+ seconds for short prompts.

**Diagnosis:**

```bash
# Check GPU availability
nvidia-smi 2>/dev/null || echo "No NVIDIA GPU detected"

# Check model size vs available RAM
ollama list  # Note model sizes
free -h      # Check available memory
```

**Fixes:**

- Use a smaller model (e.g., `qwen3.5:9b` instead of `llama3.2:70b`)
- Enable GPU acceleration if available (Ollama auto-detects CUDA GPUs)
- Configure GPU routing in `config.yaml` (see [GPU Model Routing](#8-gpu-model-routing))
- Increase system RAM or GPU VRAM

### Config Not Loading After Edit

**Symptom:** Changed `config.yaml` but the backend still uses old values.

**Diagnosis:**

```bash
# Check if the backend read the config
journalctl -u autobot-backend --since "5 minutes ago" | grep -i "config\|ollama"

# Verify the config file on disk
cat autobot-backend/config/config.yaml | grep -A5 "ollama"
```

**Fixes:**

- Restart the backend: `sudo systemctl restart autobot-backend`
- Use the hot-reload API: `POST /api/system/reload_config`
  (Note: this reloads `global_config_manager` but not all consumers --
  see CLAUDE.md note about `global_config_manager` vs `config` divergence)
- Verify env vars are not overriding config.yaml (env vars take precedence)

### SLM Discovery Overriding Local Config

**Symptom:** Backend connects to a different Ollama instance than configured locally.

**Diagnosis:**

```bash
journalctl -u autobot-backend --since "1 minute ago" | grep "SLM discovery\|Ollama endpoint"
```

**Fix:** SLM discovery has highest priority. To force local config:

- Unset `SLM_URL`: `unset SLM_URL` (disables SLM client entirely)
- Or ensure the SLM returns the desired Ollama URL

### Backend Returns 502 After Restart

**Symptom:** `502 Bad Gateway` immediately after restarting the backend.

This is expected. The backend takes approximately 6 minutes to fully initialize
(loading models, knowledge base, Redis connections). Wait and retry:

```bash
# Poll until healthy
for i in $(seq 1 30); do
    status=$(curl -sk -o /dev/null -w '%{http_code}' https://localhost:8443/api/health)
    if [ "$status" = "200" ]; then
        echo "Backend is ready"
        break
    fi
    echo "Waiting... (attempt $i, status=$status)"
    sleep 15
done
```

### Conversation History Not Persisting

**Symptom:** Starting a new session loses previous conversation context.

**Diagnosis:**

```bash
# Check Redis connectivity
redis-cli -h 172.16.168.23 ping

# Check for conversation keys
redis-cli -h 172.16.168.23 keys "chat:conversation:*" | head -5

# Check file transcripts
ls -la autobot-backend/data/conversation_transcripts/ | head -5
```

**Fixes:**

- Ensure Redis is running on VM `.23`
- Check Redis timeout logs: `journalctl -u autobot-backend | grep "Redis.*timeout"`
- Verify the `session_id` is being passed correctly in subsequent requests

---

## Appendix: Configuration Quick Reference

| Setting | config.yaml Key | Environment Variable | Default |
|---------|----------------|---------------------|---------|
| Ollama endpoint | `backend.llm.ollama.endpoint` | `AUTOBOT_OLLAMA_ENDPOINT` | `http://127.0.0.1:11434` |
| Ollama host | `infrastructure.hosts.ollama` | `AUTOBOT_OLLAMA_HOST` | `127.0.0.1` |
| Selected model | `backend.llm.ollama.selected_model` | `AUTOBOT_DEFAULT_LLM_MODEL` | `qwen3.5:9b` |
| GPU endpoint | `backend.llm.ollama.gpu_endpoint` | -- | (none) |
| GPU models | `backend.llm.ollama.gpu_models` | -- | `[]` |
| LLM provider | `backend.llm.active_provider` | `AUTOBOT_LLM_PROVIDER` | `ollama` |
| LLM timeout | -- | `AUTOBOT_LLM_TIMEOUT` | `30` (seconds) |
| LLM temperature | -- | `AUTOBOT_LLM_TEMPERATURE` | `0.7` |
| SLM URL | -- | `SLM_URL` | (none) |
| Redis host | -- | `AUTOBOT_REDIS_HOST` | `172.16.168.23` |

---

## Related Documentation

- [Configuration Guide](CONFIGURATION_GUIDE.md) -- Full backend configuration reference
- [LLM Interface Migration Guide](LLM_Interface_Migration_Guide.md) -- Multi-provider setup
- [VLLM Setup Guide](VLLM_SETUP_GUIDE.md) -- Alternative inference backend
- [Getting Started](GETTING_STARTED_COMPLETE.md) -- Initial setup walkthrough
- [Developer Reference](../developer/AUTOBOT_REFERENCE.md) -- IPs, commands, playbooks
