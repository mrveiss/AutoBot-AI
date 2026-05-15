# LLM Middleware and Telemetry Integration Guide


## Quick Answer

**How do you implement a custom middleware in AutoBot to intercept and modify LLM prompts based on real-time infrastructure telemetry?**

Subclass `ChatWorkflowManager` and override `_prepare_llm_request_params()` to
inject telemetry data into the prompt. This is the recommended approach because it
gives you full access to the session, RAG context, and conversation history. Here
is a complete end-to-end example:

```python
#!/usr/bin/env python3
"""Custom LLM middleware that injects infrastructure telemetry into prompts."""

import logging
import time
from typing import Any, Dict

from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.models import WorkflowSession

from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config

logger = logging.getLogger(__name__)


class TelemetryAwareChatManager(ChatWorkflowManager):
    """Chat manager that injects real-time infrastructure metrics into LLM prompts."""

    def __init__(self):
        super().__init__()
        self._telemetry_redis = None
        self._cache = None
        self._cache_ts = 0

    async def _gather_telemetry(self) -> str:
        """Collect fleet metrics from Redis and format as markdown."""
        now = time.time()
        if self._cache and (now - self._cache_ts) < 30:
            return self._cache

        if self._telemetry_redis is None:
            self._telemetry_redis = await get_redis_client(async_client=True, database="main")

        cpu = await self._telemetry_redis.get("metrics:cpu:current")
        mem = await self._telemetry_redis.get("metrics:memory:current")
        disk = await self._telemetry_redis.get("metrics:disk:current")

        lines = ["\n## Infrastructure Status"]
        lines.append(f"- CPU: {cpu.decode() if cpu else 'N/A'}%")
        lines.append(f"- Memory: {mem.decode() if mem else 'N/A'}%")
        lines.append(f"- Disk: {disk.decode() if disk else 'N/A'}%")

        health_keys = await self._telemetry_redis.keys("service:*:health")
        for key in health_keys:
            svc = key.decode().split(":")[1]
            data = await self._telemetry_redis.hgetall(key)
            status = data.get(b"status", b"unknown").decode()
            lines.append(f"- {svc}: {status}")

        context = "\n".join(lines)
        self._cache = context
        self._cache_ts = now
        return context

    async def _prepare_llm_request_params(
        self,
        session: WorkflowSession,
        message: str,
        use_knowledge: bool = True,
        language: str = None,
    ) -> Dict[str, Any]:
        """Override to inject telemetry between system prompt and conversation."""
        params = await super()._prepare_llm_request_params(
            session, message, use_knowledge, language
        )
        try:
            telemetry = await self._gather_telemetry()
            system_prompt = params["system_prompt"]
            original = params["prompt"]
            if original.startswith(system_prompt):
                remainder = original[len(system_prompt):]
                params["prompt"] = system_prompt + telemetry + remainder
            else:
                params["prompt"] = original + "\n" + telemetry
        except Exception as exc:
            logger.warning("Telemetry injection failed (non-fatal): %s", exc)
        return params
```

**Wire it up** in `chat_workflow/__init__.py`:

```python
from .telemetry_manager import TelemetryAwareChatManager

def get_chat_workflow_manager():
    global _workflow_manager
    if _workflow_manager is None:
        with _workflow_manager_lock:
            if _workflow_manager is None:
                _workflow_manager = TelemetryAwareChatManager()
    return _workflow_manager
```

**Seed test telemetry and verify:**

```bash
redis-cli -h <database-ip> SET metrics:cpu:current 45
redis-cli -h <database-ip> SET metrics:memory:current 62
redis-cli -h <database-ip> HSET service:backend:health status healthy
curl -sk https://localhost:8443/api/chat/message \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the current system status?", "session_id": "test"}'
```

For alternative patterns (HTTP middleware, LLM interface middleware) and testing,
see [Section 3](#3-implementing-a-custom-middleware) and [Section 10](#10-complete-integration-example).

---


> **Benchmark question:** "How do you implement a custom middleware in AutoBot
> to intercept and modify LLM prompts based on real-time infrastructure
> telemetry?"

This guide documents AutoBot's LLM processing pipeline, all available
middleware interception points, and provides step-by-step implementation
patterns for building custom middleware that injects real-time infrastructure
telemetry into LLM prompts.

---

## Table of Contents

1. [LLM Processing Pipeline Architecture](#1-llm-processing-pipeline-architecture)
2. [The LLMHandlerMixin Architecture](#2-the-llmhandlermixin-architecture)
3. [Implementing a Custom Middleware](#3-implementing-a-custom-middleware)
4. [LLM Self-Awareness System](#4-llm-self-awareness-system)
5. [Analytics Middleware Integration](#5-analytics-middleware-integration)
6. [Prompt Template System](#6-prompt-template-system)
7. [Configuration](#7-configuration)
8. [Registering Custom Middleware](#8-registering-custom-middleware)
9. [Testing Your Middleware](#9-testing-your-middleware)
10. [Complete Integration Example](#10-complete-integration-example)

---

## 1. LLM Processing Pipeline Architecture

Every user message flows through a multi-stage pipeline before reaching the
LLM. Understanding each stage is essential for choosing the correct
interception point.

### Full Pipeline Diagram

```
User Message
  |
  v
FastAPI HTTP Layer
  |-- LLMAwarenessMiddleware  (injects system context into POST body)
  |-- AnalyticsMiddleware     (tracks API call timing and patterns)
  |-- TracingMiddleware       (OpenTelemetry distributed tracing spans)
  |-- ServiceAuthEnforcement  (validates Bearer tokens)
  |
  v
Chat API Router  (autobot-backend/api/chat.py)
  |-- Session ownership validation
  |-- Request model parsing (ChatMessage pydantic model)
  |
  v
ChatWorkflowManager  (chat_workflow/manager.py)
  |-- Composes: ConversationHandlerMixin
  |             ToolHandlerMixin
  |             LLMHandlerMixin        <-- PRIMARY INTERCEPTION POINT
  |             SessionHandlerMixin
  |
  v
LangGraph StateGraph  (chat_workflow/graph.py)
  |-- ChatState TypedDict (single source of truth)
  |-- Nodes: initialize -> detect_intent -> prepare_llm
  |           -> generate_response -> reflect_on_response (RLM)
  |           -> persist
  |-- Redis checkpointer for thread-based persistence
  |
  v
LLMHandlerMixin._prepare_llm_request_params()   <-- KEY METHOD
  |-- _get_selected_model()            -> model from config/env
  |-- _discover_ollama_from_slm()      -> SLM service discovery
  |-- _get_ollama_endpoint_for_model() -> GPU/CPU endpoint routing
  |-- _get_system_prompt()             -> system prompt + personality
  |-- _build_conversation_context()    -> last 2 exchanges
  |-- _retrieve_knowledge_context()    -> RAG retrieval
  |-- _build_full_prompt()             -> assembles final prompt
  |
  v
Ollama API Request  (HTTP POST to /api/generate)
  |-- Streaming response via aiohttp
  |-- Chunk-by-chunk type detection (thought/planning/response)
  |-- Tool call extraction and execution
  |
  v
Response Stream -> WebSocket -> User
```

### Key Source Files

All paths relative to `autobot-backend/`.

| File | Role |
|------|------|
| `api/chat.py` | FastAPI router, streaming endpoint |
| `chat_workflow/manager.py` | Orchestration class (all mixins) |
| `chat_workflow/llm_handler.py` | LLM request prep, prompt building |
| `chat_workflow/conversation.py` | Redis conversation persistence |
| `chat_workflow/models.py` | `WorkflowSession`, `StreamingMessage` |
| `chat_workflow/graph.py` | LangGraph `StateGraph`, `ChatState` |
| `prompt_manager.py` | Prompt loading from `resources/prompts/` |
| `middleware/llm_awareness_middleware.py` | HTTP system context injection |
| `middleware/analytics_middleware.py` | API call tracking |
| `llm_self_awareness.py` | System state awareness module |
| `llm_interface_pkg/optimization/integration.py` | `OptimizedLLMMiddleware` |

### Interception Points Summary

| Level | Location | Best For |
|-------|----------|----------|
| HTTP Middleware | `BaseHTTPMiddleware` | Request enrichment before handlers |
| Workflow Manager | `ChatWorkflowManager` subclass | Business-logic prompt modification |
| LLM Handler | `_prepare_llm_request_params()` | Direct prompt assembly control |
| LLM Interface | `OptimizedLLMMiddleware` subclass | Provider-level optimization |
| LangGraph Node | Custom `StateGraph` node | Graph pipeline stage injection |

---

## 2. The LLMHandlerMixin Architecture

`LLMHandlerMixin` (in `chat_workflow/llm_handler.py`) is the mixin that
`ChatWorkflowManager` inherits for LLM interaction. Its central method
`_prepare_llm_request_params()` is the **primary interception point**.

### Method Signature (from source)

```python
class LLMHandlerMixin:
    """Mixin for LLM interaction handling."""

    async def _prepare_llm_request_params(
        self,
        session: WorkflowSession,
        message: str,
        use_knowledge: bool = True,
        language: str = None,
    ) -> Dict[str, Any]:
        """Prepare LLM request parameters.

        Args:
            session: Active workflow session with conversation history.
            message: Current user message text.
            use_knowledge: Whether to perform RAG retrieval.
            language: ISO language code for response language.

        Returns:
            Dict with keys: endpoint, model, prompt, system_prompt,
            citations, used_knowledge.
        """
```

### Return Value Schema

| Key | Type | Description |
|-----|------|-------------|
| `endpoint` | `str` | Ollama URL with `/api/generate` suffix |
| `model` | `str` | Model name (e.g., `llama3.2:latest`) |
| `prompt` | `str` | Fully assembled prompt string |
| `system_prompt` | `str` | System prompt alone |
| `citations` | `list[dict]` | RAG knowledge base citations |
| `used_knowledge` | `bool` | Whether RAG context was retrieved |

### Prompt Assembly Order

`_build_full_prompt()` concatenates in this exact order:

```
[Personality Preamble]   <- personality_service (if active)
[System Prompt]          <- resources/prompts/chat/system_prompt_simple.md
[Language Instruction]   <- appended when language != "en"

[Knowledge Context]      <- RAG results (when retrieved)

**Recent Context:**
User: <previous message>
You: <previous response>

**Current user message:** <current message>

Assistant:
```

The best place to inject telemetry is between the knowledge context and the
conversation context, or as a separate section appended after the system
prompt.

### Helper Methods on LLMHandlerMixin

| Method | Purpose |
|--------|---------|
| `_get_selected_model()` | Resolves model from config with env var fallback |
| `_discover_ollama_from_slm()` | SLM fleet service discovery (cached 60s) |
| `_get_ollama_endpoint_for_model(model)` | Routes GPU models to `gpu_endpoint` |
| `_get_system_prompt(language)` | Personality preamble + prompt file + lang |
| `_get_personality_preamble()` | Active personality profile injection |
| `_build_conversation_context(session)` | Last 2 complete exchanges |
| `_retrieve_knowledge_context(msg, session)` | RAG via `conversation_aware_retrieve` |
| `_build_full_prompt(sys, know, conv, msg)` | Final prompt concatenation |
| `_interpret_command_results(...)` | Send command output to LLM for explanation |

---

## 3. Implementing a Custom Middleware

Three implementation patterns are available, each operating at a different
level of the pipeline. Choose based on your requirements:

| Pattern | Level | Access To | Recommended When |
|---------|-------|-----------|------------------|
| **Option A** | Workflow Manager | Session, RAG, conversation | You need full context awareness |
| **Option B** | LLM Interface | `LLMRequest`/`LLMResponse` | You need provider-level control |
| **Option C** | FastAPI HTTP | Raw HTTP request/response | You need API-level interception |

### Option A: Subclass ChatWorkflowManager (Recommended)

This is the recommended approach because it gives you access to the full
workflow context (session state, conversation history, RAG results) and lets
you modify the prompt at the exact point where it is assembled.

**File:** `autobot-backend/chat_workflow/telemetry_manager.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Custom middleware that injects infrastructure telemetry into LLM prompts."""

import logging
import time
from typing import Any, Dict

from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.models import WorkflowSession

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class TelemetryAwareChatManager(ChatWorkflowManager):
    """Extended chat workflow manager with infrastructure telemetry.

    Overrides _prepare_llm_request_params() to inject real-time
    infrastructure metrics into the prompt sent to the LLM. This
    gives the LLM awareness of current system state when answering
    infrastructure-related questions.
    """

    def __init__(self):
        """Initialize with async Redis client for telemetry."""
        super().__init__()
        self._telemetry_redis = None
        self._telemetry_enabled = True
        self._telemetry_cache = None
        self._cache_timestamp = 0
        self._cache_ttl = 30  # seconds

    async def _ensure_telemetry_redis(self):
        """Lazily initialize the async Redis client."""
        if self._telemetry_redis is None:
            self._telemetry_redis = await get_redis_client(
                async_client=True, database="main"
            )

    async def _gather_infrastructure_telemetry(self) -> str:
        """Collect real-time infrastructure telemetry from the fleet.

        Returns:
            Formatted markdown string with current infrastructure state.
        """
        now = time.time()
        if self._telemetry_cache and (now - self._cache_timestamp) < self._cache_ttl:
            return self._telemetry_cache

        await self._ensure_telemetry_redis()
        telemetry_data = {}

        # 1. Gather service health from Redis
        health_keys = await self._telemetry_redis.keys("service:*:health")
        for key in health_keys:
            service_name = key.decode().split(":")[1]
            health = await self._telemetry_redis.hgetall(key)
            telemetry_data[service_name] = {
                k.decode(): v.decode() for k, v in health.items()
            }

        # 2. Gather system metrics
        cpu = await self._telemetry_redis.get("metrics:cpu:current")
        mem = await self._telemetry_redis.get("metrics:memory:current")
        disk = await self._telemetry_redis.get("metrics:disk:current")

        # 3. Gather active alerts
        alerts = await self._telemetry_redis.lrange("alerts:active", 0, 10)

        # Format as context for LLM
        lines = ["\n## Current Infrastructure Status"]
        if cpu:
            lines.append(f"- CPU Usage: {cpu.decode()}%")
        if mem:
            lines.append(f"- Memory Usage: {mem.decode()}%")
        if disk:
            lines.append(f"- Disk Usage: {disk.decode()}%")

        if telemetry_data:
            lines.append("\n### Service Health:")
            for service, data in telemetry_data.items():
                status = data.get("status", "unknown")
                lines.append(f"- {service}: {status}")

        if alerts:
            lines.append("\n### Active Alerts:")
            for alert in alerts[:5]:
                lines.append(f"- {alert.decode()}")

        context = "\n".join(lines)
        self._telemetry_cache = context
        self._cache_timestamp = now
        return context

    async def _prepare_llm_request_params(
        self,
        session: WorkflowSession,
        message: str,
        use_knowledge: bool = True,
        language: str = None,
    ) -> Dict[str, Any]:
        """Override to inject telemetry into prompts.

        Calls the parent implementation to get the base parameters,
        then inserts a telemetry context section into the assembled
        prompt between the system prompt and the conversation context.

        Args:
            session: Active workflow session.
            message: Current user message.
            use_knowledge: Whether to perform RAG retrieval.
            language: ISO language code.

        Returns:
            Modified params dict with telemetry-enriched prompt.
        """
        # Get base params from parent
        params = await super()._prepare_llm_request_params(
            session, message, use_knowledge, language
        )

        if not self._telemetry_enabled:
            return params

        try:
            telemetry_context = await self._gather_infrastructure_telemetry()

            # Insert telemetry after the system prompt section
            system_prompt = params["system_prompt"]
            original_prompt = params["prompt"]

            # The prompt starts with the system prompt; inject telemetry
            # right after it, before knowledge/conversation context
            if original_prompt.startswith(system_prompt):
                remainder = original_prompt[len(system_prompt):]
                params["prompt"] = (
                    system_prompt
                    + telemetry_context
                    + remainder
                )
            else:
                # Fallback: append telemetry before the user message
                params["prompt"] = (
                    original_prompt + "\n" + telemetry_context
                )

            logger.info(
                "Injected infrastructure telemetry into LLM prompt"
            )
        except Exception as exc:
            logger.warning(
                "Telemetry injection failed (non-fatal): %s", exc
            )

        return params
```

**Wiring it up:** Replace the global `ChatWorkflowManager` singleton in
`chat_workflow/__init__.py`:

```python
# In chat_workflow/__init__.py, change the factory function:
from .telemetry_manager import TelemetryAwareChatManager

def get_chat_workflow_manager() -> ChatWorkflowManager:
    """Get the global chat workflow manager instance."""
    global _workflow_manager
    if _workflow_manager is None:
        with _workflow_manager_lock:
            if _workflow_manager is None:
                _workflow_manager = TelemetryAwareChatManager()
    return _workflow_manager
```

### Option B: OptimizedLLMMiddleware Pattern

Use this when you need to intercept at the LLM provider level, operating on
the standardized `LLMRequest` and `LLMResponse` dataclasses from
`llm_interface_pkg/models.py`.

**File:** `autobot-backend/llm_interface_pkg/optimization/telemetry_middleware.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Middleware that augments LLM requests with telemetry data."""

import logging
import time
from typing import Any, Callable, Coroutine, Dict

from autobot_shared.redis_client import get_redis_client

from ..models import LLMRequest, LLMResponse
from .integration import OptimizedLLMMiddleware

logger = logging.getLogger(__name__)


class TelemetryLLMMiddleware(OptimizedLLMMiddleware):
    """Middleware that augments LLM requests with telemetry data.

    Extends OptimizedLLMMiddleware to inject infrastructure metrics
    into the prompt messages before compression/batching/caching
    optimizations are applied.
    """

    def __init__(self, **kwargs):
        """Initialize with telemetry collection."""
        super().__init__(**kwargs)
        self._telemetry_cache: Dict[str, Any] = {}
        self._cache_ts = 0
        self._cache_ttl = 30

    async def _gather_telemetry(self) -> Dict[str, Any]:
        """Gather current infrastructure telemetry."""
        now = time.time()
        if self._telemetry_cache and (now - self._cache_ts) < self._cache_ttl:
            return self._telemetry_cache

        redis = get_redis_client(database="main")
        telemetry = {
            "cpu": redis.get("metrics:cpu:current"),
            "memory": redis.get("metrics:memory:current"),
            "disk": redis.get("metrics:disk:current"),
        }
        # Decode bytes
        telemetry = {
            k: v.decode() if v else "N/A"
            for k, v in telemetry.items()
        }

        self._telemetry_cache = telemetry
        self._cache_ts = now
        return telemetry

    def _augment_prompt(self, messages, telemetry):
        """Insert telemetry context into the message list."""
        telemetry_text = (
            f"\n## Infrastructure Status\n"
            f"- CPU: {telemetry['cpu']}%\n"
            f"- Memory: {telemetry['memory']}%\n"
            f"- Disk: {telemetry['disk']}%\n"
        )
        # Insert as a system message before the last user message
        augmented = list(messages)
        augmented.insert(-1, {
            "role": "system",
            "content": telemetry_text,
        })
        return augmented

    async def execute(
        self,
        request: LLMRequest,
        handler: Callable[
            [LLMRequest], Coroutine[Any, Any, LLMResponse]
        ],
    ) -> LLMResponse:
        """Execute with telemetry injection.

        Pre-process: inject telemetry into prompt messages.
        Execute: parent applies compression, batching, caching.
        Post-process: log response metrics with telemetry context.

        Args:
            request: The LLM request with messages list.
            handler: The actual LLM handler function.

        Returns:
            LLMResponse from the handler.
        """
        # Pre-process: inject telemetry
        telemetry = await self._gather_telemetry()
        request.messages = self._augment_prompt(
            request.messages, telemetry
        )
        request.metadata["telemetry_injected"] = True

        # Execute via parent (applies optimizations)
        response = await super().execute(request, handler)

        # Post-process: log metrics
        logger.info(
            "LLM request with telemetry: model=%s, tokens=%s",
            response.model,
            response.tokens_used,
        )

        return response
```

### Option C: FastAPI HTTP Middleware Pattern

For API-level interception that operates on the raw HTTP request before it
reaches any router. This follows the same pattern as the existing
`LLMAwarenessMiddleware` in `middleware/llm_awareness_middleware.py`.

**File:** `autobot-backend/middleware/llm_telemetry_middleware.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""HTTP middleware that enriches chat requests with telemetry."""

import json
import logging
import time
from typing import Any, Dict, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Fields in the request body that may contain the user message
MESSAGE_FIELDS = ["message", "prompt", "user_message", "query"]


class LLMTelemetryMiddleware(BaseHTTPMiddleware):
    """HTTP middleware that enriches chat requests with telemetry.

    Intercepts POST requests to chat endpoints, reads the JSON body,
    injects a telemetry_context field, and reconstructs the request.
    The chat handler can then read this field and incorporate it.
    """

    def __init__(self, app, enable_for_paths=None):
        """Initialize with configurable path filtering.

        Args:
            app: ASGI application.
            enable_for_paths: List of URL path prefixes to intercept.
        """
        super().__init__(app)
        self.enable_for_paths = enable_for_paths or [
            "/api/chat",
            "/api/llm",
        ]
        self._cache: Optional[str] = None
        self._cache_ts = 0
        self._cache_ttl = 30

    def _should_intercept(self, request: Request) -> bool:
        """Check if this request should be intercepted."""
        if request.method != "POST":
            return False
        return any(
            request.url.path.startswith(p)
            for p in self.enable_for_paths
        )

    async def _get_telemetry(self) -> str:
        """Get cached telemetry summary string."""
        now = time.time()
        if self._cache and (now - self._cache_ts) < self._cache_ttl:
            return self._cache

        redis = get_redis_client(database="main")
        cpu = redis.get("metrics:cpu:current")
        mem = redis.get("metrics:memory:current")

        summary = (
            f"CPU: {cpu.decode() if cpu else 'N/A'}%, "
            f"Memory: {mem.decode() if mem else 'N/A'}%"
        )
        self._cache = summary
        self._cache_ts = now
        return summary

    async def dispatch(self, request: Request, call_next):
        """Process request and inject telemetry if applicable."""
        if not self._should_intercept(request):
            return await call_next(request)

        try:
            body = await request.body()
            if body:
                data = json.loads(body)
                if isinstance(data, dict):
                    telemetry = await self._get_telemetry()
                    data["telemetry_context"] = telemetry
                    modified_body = json.dumps(data).encode()
                    request._body = modified_body
                    # Update content-length header
                    request.headers.__dict__["_list"] = [
                        (
                            (k.encode(), v.encode())
                            if k.lower() != "content-length"
                            else (
                                k.encode(),
                                str(len(modified_body)).encode(),
                            )
                        )
                        for k, v in request.headers.items()
                    ]
        except Exception as exc:
            logger.warning("Telemetry injection failed: %s", exc)

        response = await call_next(request)
        return response
```

---

## 4. LLM Self-Awareness System

AutoBot includes a built-in self-awareness system that gives the LLM
knowledge of its own capabilities, current development phase, and system
state. This is implemented across two modules:

- **`llm_self_awareness.py`** -- Core `LLMSelfAwareness` class
- **`middleware/llm_awareness_middleware.py`** -- HTTP middleware wrapper
- **`api/llm_awareness.py`** -- REST API endpoints

### API Endpoints

All endpoints are mounted at `/api/llm-awareness/`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | Awareness system health and maturity score |
| `GET` | `/context` | System context at specified detail level |
| `GET` | `/capabilities` | Detailed capabilities by category |
| `POST` | `/inject-context` | Inject awareness into a prompt string |
| `POST` | `/analyze-query` | Phase-aware query analysis |
| `GET` | `/summary/text` | Human-readable capability summary |
| `GET` | `/phase-info` | Current phase and progression status |
| `GET` | `/metrics` | Cache stats and operational metrics |
| `GET` | `/health` | Component-level health check |

### Context Levels

The `level` parameter accepts three values:

| Level | Includes | Use Case |
|-------|----------|----------|
| `basic` | Identity, capability count, phase | Low-overhead prompt enrichment |
| `detailed` | + capability categories, endpoints | Infrastructure-aware responses |
| `full` | + progression rules, history | Debugging and system analysis |

### Using the Awareness System Programmatically

```python
from llm_self_awareness import get_llm_self_awareness

async def get_enriched_prompt(original_prompt: str) -> str:
    """Enrich prompt with system self-awareness context.

    Args:
        original_prompt: The original prompt text.

    Returns:
        Prompt with system context appended.
    """
    awareness = get_llm_self_awareness()
    context = await awareness.get_system_context(
        include_detailed=True
    )
    import json
    context_str = json.dumps(context, indent=2)
    return f"{original_prompt}\n\n## System Context\n{context_str}"
```

### Using the LLMAwarenessInjector Utility

The `LLMAwarenessInjector` class in `llm_awareness_middleware.py` provides
higher-level helpers:

```python
from middleware.llm_awareness_middleware import (
    get_awareness_injector,
    inject_awareness,
    get_aware_system_prompt,
)

# Quick injection into any message
enriched = await inject_awareness(
    "What services are running?",
    level="detailed",
)

# Get a system prompt prefix with awareness context
prefix = await get_aware_system_prompt()
# Returns: "You are AutoBot, currently in Phase 5 with 78% maturity..."

# Full injector for custom control
injector = get_awareness_injector()
relevance = await injector.analyze_capability_relevance(
    "How do I check Redis health?"
)
# Returns: {"relevant_capabilities": [...], ...}
```

### How LLMAwarenessMiddleware Works (HTTP Layer)

The middleware (registered in `initialization/middleware.py`) intercepts
POST requests to configured paths and modifies the request body in-flight:

1. Checks if the request path matches (`/api/chat`, `/api/llm`, etc.)
2. Reads the JSON body and finds a message field
3. Calls `awareness.inject_awareness_context(message, context_level)`
4. Replaces the body and updates `Content-Length`
5. Adds response headers: `X-AutoBot-Phase`, `X-AutoBot-Maturity`,
   `X-AutoBot-Capabilities`

---

## 5. Analytics Middleware Integration

The `AnalyticsMiddleware` (in `middleware/analytics_middleware.py`) tracks
API call patterns and response times. It provides a pattern you can extend
for LLM-specific analytics.

### Existing AnalyticsMiddleware Pattern

```python
from middleware.analytics_middleware import AnalyticsMiddleware

class AnalyticsMiddleware(BaseHTTPMiddleware):
    """Tracks API calls for analytics."""

    def __init__(self, app, analytics_controller=None):
        super().__init__(app)
        self.analytics_controller = analytics_controller
        self.tracked_paths = {"/api/", "/docs", "/redoc"}
        self._background_tasks: set = set()

    async def dispatch(self, request, call_next):
        start_time = time.time()
        response = await call_next(request)
        response_time = time.time() - start_time

        # Track asynchronously (non-blocking)
        if self.analytics_controller:
            task = asyncio.create_task(
                self._track_call_async(
                    endpoint, response_time, status_code, method
                )
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        response.headers["X-Response-Time"] = f"{response_time:.3f}s"
        return response
```

### Extending for LLM-Specific Tracking

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLM-specific analytics tracking middleware."""

import asyncio
import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class LLMAnalyticsMiddleware(BaseHTTPMiddleware):
    """Track LLM request patterns and performance."""

    LLM_PATHS = {"/api/chat", "/api/llm"}

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Track LLM-specific metrics for chat endpoints."""
        is_llm = any(
            request.url.path.startswith(p) for p in self.LLM_PATHS
        )

        if not is_llm:
            return await call_next(request)

        start = time.time()
        response = await call_next(request)
        duration = time.time() - start

        # Fire-and-forget metric recording
        asyncio.create_task(
            self._record_llm_metrics(
                path=request.url.path,
                method=request.method,
                status=response.status_code,
                duration_s=duration,
            )
        )

        response.headers["X-LLM-Duration"] = f"{duration:.3f}s"
        return response

    async def _record_llm_metrics(
        self,
        path: str,
        method: str,
        status: int,
        duration_s: float,
    ) -> None:
        """Record LLM metrics to Redis for dashboard consumption."""
        try:
            redis = get_redis_client(database="analytics")
            key = f"llm:metrics:{path}"
            redis.lpush(key, f"{duration_s:.4f}:{status}")
            redis.ltrim(key, 0, 999)  # Keep last 1000 entries
        except Exception as exc:
            logger.debug("LLM metrics recording failed: %s", exc)
```

---

## 6. Prompt Template System

AutoBot uses a centralized `PromptManager` (in `prompt_manager.py`) that
loads prompt templates from the `resources/prompts/` directory.

### Architecture

- Templates are `.md`, `.txt`, or `.prompt` files under `resources/prompts/`
- File paths become dot-notation keys:
  `chat/system_prompt_simple.md` becomes `chat.system_prompt_simple`
- Jinja2 templating is supported for dynamic content
- Prompts are cached in Redis DB 2 (prompts database) with 24h TTL
- Change detection uses MD5 hashes of file content

### Usage

```python
from prompt_manager import (
    get_prompt,
    get_language_instruction,
    resolve_language,
    get_optimized_prompt,
    list_available_prompts,
    reload_prompts,
)

# Get a prompt by dot-notation key
system_prompt = get_prompt("chat.system_prompt_simple")

# Get with Jinja2 template variables
formatted = get_prompt(
    "orchestrator.system_prompt",
    user_name="admin",
    available_tools=["execute_command", "search_knowledge"],
)

# Language support
language = resolve_language("es")  # -> "es"
instruction = get_language_instruction("es")
# Returns: "\n\n**Language Requirement:** You MUST respond in Spanish..."

# vLLM prefix-cache-optimized prompt (static prefix + dynamic suffix)
optimized = get_optimized_prompt(
    base_prompt_key="default.agent.system.main",
    session_id="abc-123",
    user_name="admin",
    available_tools=["execute_command"],
)

# List all available prompts (with optional regex filter)
all_prompts = list_available_prompts()
chat_prompts = list_available_prompts(filter_pattern="chat\..*")

# Hot-reload during development
reload_prompts()
```

### Supported Languages

| Code | Language | Code | Language |
|------|----------|------|----------|
| `en` | English | `ja` | Japanese |
| `es` | Spanish | `ko` | Korean |
| `fr` | French | `ar` | Arabic |
| `de` | German | `ru` | Russian |
| `pt` | Portuguese | `it` | Italian |
| `zh` | Chinese | `nl` | Dutch |
| `hi` | Hindi | | |

---

## 7. Configuration

### Runtime Config File

**File:** `autobot-backend/config/config.yaml`

```yaml
# Primary path for _get_ollama_endpoint() in chat_workflow/llm_handler.py
backend:
  llm:
    ollama:
      endpoint: http://127.0.0.1:11434
      # GPU endpoint for model-to-endpoint routing (#1070)
      # gpu_endpoint: http://<backend-ip>:11434
      # gpu_models:
      #   - "qwen3.5:9b"
      #   - "mistral:7b-instruct"

# Fallback path for _get_ollama_endpoint_fallback() via get_host("ollama")
infrastructure:
  hosts:
    ollama: 127.0.0.1
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|--------|
| `AUTOBOT_OLLAMA_HOST` | `127.0.0.1` | Ollama host (highest priority) |
| `AUTOBOT_DEFAULT_LLM_MODEL` | `llama3.2:latest` | Default model name |
| `AUTOBOT_BACKEND_TLS_ENABLED` | `false` | Enable HTTPS on port 8443 |
| `AUTOBOT_DEV_MODE` | `false` | Enable hot-reload |
| `AUTOBOT_LOG_LEVEL` | `INFO` | Logging level |

### Endpoint Resolution Priority

1. **SLM service discovery** (`_discover_ollama_from_slm()`) -- fleet-managed
2. **`config.yaml`** `backend.llm.ollama.endpoint` -- explicit config
3. **`AUTOBOT_OLLAMA_HOST` env var** -- via `ConfigManager.get_host("ollama")`
4. **Hardcoded fallback** -- `ModelConstants.DEFAULT_OLLAMA_MODEL`

### SSOT Config (Never Hardcode IPs)

```python
from autobot_shared.ssot_config import config

# Access fleet node IPs
redis_host = config.redis.host      # -> "<database-ip>"
ai_stack_host = config.ai_stack.host # -> "<aiml-ip>"

# Access Redis properly
from autobot_shared.redis_client import get_redis_client
redis = get_redis_client(database="main")  # ALWAYS use this
```

---

## 8. Registering Custom Middleware

Middleware registration happens in `autobot-backend/initialization/middleware.py`
via the `configure_middleware()` function, which is called by `app_factory.py`
during application startup.

### Current Middleware Stack

```python
# initialization/middleware.py
def configure_middleware(app, allow_origins=None, ...):
    configure_cors(app, allow_origins)      # CORSMiddleware
    configure_gzip(app, gzip_minimum_size)  # GZipMiddleware
    configure_service_auth(app)             # ServiceAuthEnforcement
```

### Adding Your Middleware

```python
# In initialization/middleware.py, add to configure_middleware():

def configure_middleware(
    app: FastAPI,
    allow_origins=None,
    gzip_minimum_size: int = 1000,
    enable_service_auth: bool = True,
):
    """Configure all middleware for FastAPI application."""
    configure_cors(app, allow_origins)
    configure_gzip(app, gzip_minimum_size)

    if enable_service_auth:
        configure_service_auth(app)

    # --- Add custom middleware here ---

    # LLM Telemetry (Option C from Section 3)
    try:
        from middleware.llm_telemetry_middleware import (
            LLMTelemetryMiddleware,
        )
        app.add_middleware(LLMTelemetryMiddleware)
        logger.info("LLM Telemetry Middleware enabled")
    except ImportError as e:
        logger.warning("LLM Telemetry middleware not available: %s", e)

    # LLM Awareness (existing)
    try:
        from middleware.llm_awareness_middleware import (
            LLMAwarenessMiddleware,
        )
        app.add_middleware(LLMAwarenessMiddleware)
        logger.info("LLM Awareness Middleware enabled")
    except ImportError as e:
        logger.warning("LLM Awareness middleware not available: %s", e)

    # Analytics
    try:
        from middleware.analytics_middleware import AnalyticsMiddleware
        app.add_middleware(AnalyticsMiddleware)
        logger.info("Analytics Middleware enabled")
    except ImportError as e:
        logger.warning("Analytics middleware not available: %s", e)

    logger.info("All middleware configured successfully")
```

### Middleware Execution Order

FastAPI/Starlette middleware executes in **reverse registration order** for
requests (last registered runs first) and **registration order** for
responses. Keep this in mind when ordering middleware that depends on each
other.

```
Request flow:  Analytics -> LLMAwareness -> Telemetry -> Auth -> Handler
Response flow: Handler -> Auth -> Telemetry -> LLMAwareness -> Analytics
```

---

## 9. Testing Your Middleware

### Unit Test: Telemetry Injection

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for telemetry-aware chat manager."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from chat_workflow.models import WorkflowSession


@pytest.fixture
def mock_session():
    """Create a mock workflow session."""
    return WorkflowSession(
        session_id="test-session-001",
        workflow=MagicMock(),
        conversation_history=[
            {"user": "Hello", "assistant": "Hi there!"},
        ],
        metadata={},
    )


@pytest.mark.asyncio
async def test_telemetry_injection_into_prompt(mock_session):
    """Verify telemetry data is injected into LLM prompts."""
    from chat_workflow.telemetry_manager import (
        TelemetryAwareChatManager,
    )

    manager = TelemetryAwareChatManager()

    # Mock Redis telemetry data
    mock_redis = AsyncMock()
    mock_redis.keys.return_value = [
        b"service:backend:health",
    ]
    mock_redis.hgetall.return_value = {
        b"status": b"healthy",
        b"uptime": b"3600",
    }
    mock_redis.get.side_effect = [
        b"45",  # CPU
        b"62",  # Memory
        b"38",  # Disk
    ]
    mock_redis.lrange.return_value = []
    manager._telemetry_redis = mock_redis

    # Mock parent method
    with patch.object(
        type(manager).__mro__[1],
        "_prepare_llm_request_params",
        new_callable=AsyncMock,
        return_value={
            "endpoint": "http://127.0.0.1:11434/api/generate",
            "model": "llama3.2:latest",
            "prompt": "System prompt\n\nUser message",
            "system_prompt": "System prompt",
            "citations": [],
            "used_knowledge": False,
        },
    ):
        params = await manager._prepare_llm_request_params(
            session=mock_session,
            message="What is the system status?",
        )

    # Verify telemetry was injected
    assert "Infrastructure Status" in params["prompt"]
    assert "CPU Usage: 45%" in params["prompt"]
    assert "Memory Usage: 62%" in params["prompt"]
    assert "backend: healthy" in params["prompt"]


@pytest.mark.asyncio
async def test_telemetry_disabled_skips_injection(mock_session):
    """Verify telemetry is skipped when disabled."""
    from chat_workflow.telemetry_manager import (
        TelemetryAwareChatManager,
    )

    manager = TelemetryAwareChatManager()
    manager._telemetry_enabled = False

    original_prompt = "System prompt\n\nUser message"

    with patch.object(
        type(manager).__mro__[1],
        "_prepare_llm_request_params",
        new_callable=AsyncMock,
        return_value={
            "prompt": original_prompt,
            "system_prompt": "System prompt",
            "endpoint": "http://127.0.0.1:11434/api/generate",
            "model": "llama3.2:latest",
            "citations": [],
            "used_knowledge": False,
        },
    ):
        params = await manager._prepare_llm_request_params(
            session=mock_session,
            message="Hello",
        )

    assert params["prompt"] == original_prompt
    assert "Infrastructure" not in params["prompt"]


@pytest.mark.asyncio
async def test_telemetry_failure_is_non_fatal(mock_session):
    """Verify telemetry errors do not break the chat pipeline."""
    from chat_workflow.telemetry_manager import (
        TelemetryAwareChatManager,
    )

    manager = TelemetryAwareChatManager()

    # Make Redis raise an error
    mock_redis = AsyncMock()
    mock_redis.keys.side_effect = ConnectionError("Redis down")
    manager._telemetry_redis = mock_redis

    with patch.object(
        type(manager).__mro__[1],
        "_prepare_llm_request_params",
        new_callable=AsyncMock,
        return_value={
            "prompt": "Original prompt",
            "system_prompt": "System prompt",
            "endpoint": "http://127.0.0.1:11434/api/generate",
            "model": "llama3.2:latest",
            "citations": [],
            "used_knowledge": False,
        },
    ):
        # Should NOT raise -- telemetry failure is non-fatal
        params = await manager._prepare_llm_request_params(
            session=mock_session,
            message="Hello",
        )

    assert params["prompt"] == "Original prompt"
```

### Integration Test: HTTP Middleware

```python
import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from middleware.llm_telemetry_middleware import LLMTelemetryMiddleware


@pytest.fixture
def app_with_telemetry():
    """Create a test app with telemetry middleware."""
    app = FastAPI()
    app.add_middleware(LLMTelemetryMiddleware)

    @app.post("/api/chat/message")
    async def chat_message(request_data: dict):
        return {
            "received_telemetry": "telemetry_context" in request_data,
            "telemetry": request_data.get("telemetry_context"),
        }

    return app


@pytest.mark.asyncio
async def test_http_telemetry_injection(app_with_telemetry):
    """Verify HTTP middleware injects telemetry into request body."""
    transport = ASGITransport(app=app_with_telemetry)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/chat/message",
            json={"message": "What is the system status?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["received_telemetry"] is True
```

### Running Tests

```bash
# Run middleware tests
cd autobot-backend
python -m pytest chat_workflow/telemetry_manager_test.py -v

# Run with coverage
python -m pytest middleware/llm_telemetry_middleware_test.py -v --cov=middleware
```

---

## 10. Complete Integration Example

This section combines all concepts into a single working module that:

1. Intercepts LLM prompts before they are sent
2. Injects real-time infrastructure metrics from the fleet
3. Uses TTL-based caching to avoid Redis overhead per request
4. Handles errors gracefully without breaking the chat pipeline
5. Logs telemetry-enriched interactions for observability

```python
#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Complete Custom LLM Middleware with Infrastructure Telemetry.

This module shows how to:
1. Intercept LLM prompts before they are sent
2. Inject real-time infrastructure metrics
3. Modify prompts based on system state
4. Log telemetry-enriched interactions

Usage:
    # Replace the default manager in chat_workflow/__init__.py:
    from .telemetry_manager import TelemetryAwareChatManager

    def get_chat_workflow_manager():
        global _workflow_manager
        if _workflow_manager is None:
            with _workflow_manager_lock:
                if _workflow_manager is None:
                    _workflow_manager = TelemetryAwareChatManager()
        return _workflow_manager
"""

import logging
import time
from typing import Any, Dict

from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.models import WorkflowSession

from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config

logger = logging.getLogger(__name__)


class InfrastructureTelemetryMiddleware:
    """Collects and formats infrastructure telemetry for LLM context.

    This is the telemetry collection component. It gathers metrics
    from all fleet nodes via Redis and formats them into a markdown
    section suitable for injection into LLM prompts.

    Attributes:
        redis: Async Redis client for the main database.
        cache_ttl: Seconds before cached telemetry expires.
    """

    def __init__(self, cache_ttl: int = 30):
        """Initialize telemetry collector.

        Args:
            cache_ttl: Cache TTL in seconds (default 30).
        """
        self._redis = None
        self.cache_ttl = cache_ttl
        self._cached_telemetry = None
        self._cache_timestamp = 0

    async def _ensure_redis(self):
        """Lazily initialize async Redis."""
        if self._redis is None:
            self._redis = await get_redis_client(
                async_client=True, database="main"
            )

    async def collect(self) -> Dict[str, Any]:
        """Collect telemetry from all fleet nodes.

        Returns:
            Dict with node health, system metrics, and alerts.
        """
        now = time.time()
        if (
            self._cached_telemetry
            and (now - self._cache_timestamp) < self.cache_ttl
        ):
            return self._cached_telemetry

        await self._ensure_redis()

        # Fleet node health
        nodes = {}
        for name in ["main", "frontend", "npu", "redis", "ai_stack", "browser"]:
            ip = getattr(config.vms, name, None)
            if ip:
                health = await self._redis.hgetall(f"node:{ip}:health")
                nodes[name] = (
                    {k.decode(): v.decode() for k, v in health.items()}
                    if health
                    else {"status": "unknown"}
                )

        # System metrics
        cpu = await self._redis.get("metrics:cpu:current")
        mem = await self._redis.get("metrics:memory:current")
        disk = await self._redis.get("metrics:disk:current")

        # Active alerts
        raw_alerts = await self._redis.lrange("alerts:active", 0, 10)

        telemetry = {
            "nodes": nodes,
            "cpu": cpu.decode() if cpu else None,
            "memory": mem.decode() if mem else None,
            "disk": disk.decode() if disk else None,
            "alerts": [
                a.decode() for a in (raw_alerts or [])[:5]
            ],
            "timestamp": now,
        }

        self._cached_telemetry = telemetry
        self._cache_timestamp = now
        return telemetry

    def format_for_prompt(self, telemetry: Dict[str, Any]) -> str:
        """Format telemetry data as markdown for LLM context.

        Args:
            telemetry: Telemetry dict from collect().

        Returns:
            Markdown-formatted telemetry section.
        """
        lines = ["\n## Real-Time Infrastructure Telemetry"]

        if telemetry.get("cpu"):
            lines.append(f"- CPU Usage: {telemetry['cpu']}%")
        if telemetry.get("memory"):
            lines.append(f"- Memory Usage: {telemetry['memory']}%")
        if telemetry.get("disk"):
            lines.append(f"- Disk Usage: {telemetry['disk']}%")

        nodes = telemetry.get("nodes", {})
        if nodes:
            lines.append("\n### Fleet Node Status:")
            for node, data in nodes.items():
                status = data.get("status", "unknown")
                lines.append(f"- {node}: {status}")

        alerts = telemetry.get("alerts", [])
        if alerts:
            lines.append("\n### Active Alerts:")
            for alert in alerts:
                lines.append(f"- {alert}")

        return "\n".join(lines)


class TelemetryAwareChatManager(ChatWorkflowManager):
    """Chat workflow manager with infrastructure telemetry injection.

    Extends ChatWorkflowManager to inject real-time infrastructure
    telemetry into every LLM prompt. The telemetry section is
    inserted between the system prompt and the knowledge/conversation
    context so the LLM has infrastructure awareness when answering.

    Usage:
        # Replace in chat_workflow/__init__.py:
        _workflow_manager = TelemetryAwareChatManager()
    """

    def __init__(self):
        """Initialize with telemetry collector."""
        super().__init__()
        self.telemetry = InfrastructureTelemetryMiddleware(cache_ttl=30)
        self.telemetry_enabled = True

    async def _prepare_llm_request_params(
        self,
        session: WorkflowSession,
        message: str,
        use_knowledge: bool = True,
        language: str = None,
    ) -> Dict[str, Any]:
        """Override to inject telemetry into prompts.

        Calls the parent to get base parameters, then inserts a
        telemetry context section into the assembled prompt.

        Args:
            session: Active workflow session.
            message: Current user message.
            use_knowledge: Whether to perform RAG retrieval.
            language: ISO language code.

        Returns:
            Modified params dict with telemetry-enriched prompt.
        """
        params = await super()._prepare_llm_request_params(
            session, message, use_knowledge, language
        )

        if not self.telemetry_enabled:
            return params

        try:
            data = await self.telemetry.collect()
            telemetry_section = self.telemetry.format_for_prompt(data)

            system_prompt = params["system_prompt"]
            original = params["prompt"]

            if original.startswith(system_prompt):
                remainder = original[len(system_prompt):]
                params["prompt"] = (
                    system_prompt + telemetry_section + remainder
                )
            else:
                params["prompt"] = original + "\n" + telemetry_section

            # Record in session metadata for debugging
            session.metadata["telemetry_injected"] = True
            session.metadata["telemetry_cpu"] = data.get("cpu")
            session.metadata["telemetry_memory"] = data.get("memory")

            logger.info(
                "Injected infrastructure telemetry into LLM prompt "
                "(CPU=%s%%, MEM=%s%%)",
                data.get("cpu", "N/A"),
                data.get("memory", "N/A"),
            )
        except Exception as exc:
            logger.warning(
                "Telemetry injection failed (non-fatal): %s", exc
            )
            session.metadata["telemetry_injected"] = False

        return params
```

### Wiring the Complete Example

**Step 1.** Save the module as `autobot-backend/chat_workflow/telemetry_manager.py`.

**Step 2.** Update `autobot-backend/chat_workflow/__init__.py`:

```python
from .telemetry_manager import TelemetryAwareChatManager

def get_chat_workflow_manager() -> ChatWorkflowManager:
    """Get the global chat workflow manager instance."""
    global _workflow_manager
    if _workflow_manager is None:
        with _workflow_manager_lock:
            if _workflow_manager is None:
                _workflow_manager = TelemetryAwareChatManager()
    return _workflow_manager
```

**Step 3.** Populate Redis with telemetry data (from your monitoring stack):

```bash
# Example: set test telemetry values
redis-cli -h <database-ip> SET metrics:cpu:current 45
redis-cli -h <database-ip> SET metrics:memory:current 62
redis-cli -h <database-ip> SET metrics:disk:current 38
redis-cli -h <database-ip> HSET service:backend:health status healthy
redis-cli -h <database-ip> HSET service:frontend:health status healthy
```

**Step 4.** Restart the backend and verify:

```bash
# Check that the telemetry manager loaded
journalctl -u autobot-backend --since "30 seconds ago" | grep telemetry

# Send a test message
curl -sk https://localhost:8443/api/chat/message \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the current system status?", "session_id": "test"}'
```

The LLM response should now reference the actual CPU, memory, and service
health data from your infrastructure.

---

## Quick Reference: Decision Matrix

| Question | Answer |
|----------|--------|
| Need session/RAG context? | Use **Option A** (subclass `ChatWorkflowManager`) |
| Need provider-level control? | Use **Option B** (extend `OptimizedLLMMiddleware`) |
| Need API-level interception? | Use **Option C** (extend `BaseHTTPMiddleware`) |
| Need system self-awareness? | Use `LLMAwarenessMiddleware` (already built-in) |
| Need to track LLM metrics? | Extend `AnalyticsMiddleware` pattern |
| Need graph-based injection? | Add a custom node to the `StateGraph` |

---

## Related Documentation

- [LLM Interface Migration Guide](./LLM_Interface_Migration_Guide.md)
- [Configuration Guide](./CONFIGURATION_GUIDE.md)
- [Agent System Guide](./AGENT_SYSTEM_GUIDE.md)
- [Getting Started](./GETTING_STARTED_COMPLETE.md)
