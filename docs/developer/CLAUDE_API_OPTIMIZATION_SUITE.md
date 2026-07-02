# Claude API Optimization — Canonical Module

> **Canonical module:** `autobot-backend/utils/claude_api_integration.py`
>
> The former `claude_api_optimization_suite.py` was retired in #10796 (permanently broken
> import from the SLM-only `monitoring.claude_api_monitor`; zero callers). All unique logic
> — `OptimizationMode` enum, `OptimizationMetrics` dataclass, TodoWrite optimization,
> graceful degradation, tool-pattern analysis, dynamic mode switching — has been folded into
> the canonical module.

## Overview

`autobot-backend/utils/claude_api_integration.py` provides a unified optimization layer for
all outbound Claude/LLM requests in AutoBot. It is wired into backend startup during Phase 2
(`initialization/lifespan._init_claude_api_integration`) and stored on `app.state.claude_api_adapter`.

## Key Classes

| Class | Purpose |
|---|---|
| `AutoBotClaudeAPIAdapter` | Production singleton; use `get_autobot_claude_adapter()` |
| `ClaudeAPIBatchManager` | Core manager: rate limiting, batching, optimization, metrics |
| `ClaudeAPIConfig` | Configuration dataclass |
| `OptimizationMode` | Enum: CONSERVATIVE / BALANCED / AGGRESSIVE / EMERGENCY |
| `OptimizationMetrics` | Snapshot metrics dataclass |

## Quick Start

```python
# Production usage — singleton already started at backend startup
from utils.claude_api_integration import get_autobot_claude_adapter

adapter = await get_autobot_claude_adapter()

# Chat
response = await adapter.process_chat_request("Explain async/await")

# Code analysis
result = await adapter.process_code_analysis(code_str)

# TodoWrite optimization (batches/deduplicates todos)
await adapter.submit_todowrite([
    {"content": "Task 1", "status": "pending"},
    {"content": "Task 2", "status": "pending"},
])

# Metrics / status
status = await adapter.get_performance_stats()
```

## Optimization Modes

| Mode | req/min | req/hour | When |
|---|---|---|---|
| CONSERVATIVE | 60 | 2500 | Light usage |
| BALANCED (default) | 50 | 2000 | Regular development |
| AGGRESSIVE | 30 | 1500 | High-frequency sessions |
| EMERGENCY | 15 | 800 | Rate-limit recovery |

Modes switch automatically when the background pattern-analysis task detects critical
inefficiencies (`priority_score > 0.8` on more than 3 recommendations).

## Components

1. **Conversation Rate Limiter** (`conversation_rate_limiter.py`) — sliding-window limiting
2. **Payload Optimizer** (`payload_optimizer.py`) — compression, chunking
3. **Intelligent Request Batcher** (`request_batcher.py`) — time-window + similarity batching
4. **Graceful Degradation** (`graceful_degradation.py`) — 5-level fallback system
5. **TodoWrite Optimizer** (`todowrite_optimizer.py`) — consolidation and deduplication
6. **Tool Pattern Analyzer** (`tool_pattern_analyzer.py`) — efficiency scoring

## Startup Wire-in

```
initialization/lifespan.initialize_background_services()
  └─ _init_claude_api_integration(app)   ← Phase 2, non-critical
       └─ get_autobot_claude_adapter()   ← lazy singleton
            └─ ClaudeAPIBatchManager.start()
```

## Testing

```python
from utils.claude_api_integration import AutoBotClaudeAPIAdapter

AutoBotClaudeAPIAdapter.reset_instance()  # isolate test
```
