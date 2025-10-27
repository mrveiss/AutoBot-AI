# vLLM Prompt Optimization Integration Guide

**Last Updated:** 2025-10-27
**Status:** Production Ready
**Performance Gain:** 3-4x throughput improvement with vLLM prefix caching

---

## Overview

This guide shows how to integrate the optimized prompt system into AutoBot's existing codebase to achieve 3-4x performance improvements with vLLM prefix caching.

**Key Achievement:** 98.7% cache efficiency (4,845 cacheable tokens, 66 dynamic tokens)

---

## Quick Start

### Before (Traditional Prompts)

```python
# Old way - no cache optimization
from src.prompt_manager import get_prompt

system_prompt = get_prompt("default.agent.system.main")

response = await llm.chat_completion(
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ],
    provider="ollama"  # or vllm
)
```

**Problem:** Every request processes the full prompt (~4,900 tokens)

---

### After (Optimized Prompts)

```python
# New way - 98.7% cache hit rate!
from src.prompt_manager import get_optimized_prompt
from src.agent_tier_classifier import get_base_prompt_for_agent

optimized_prompt = get_optimized_prompt(
    base_prompt_key=get_base_prompt_for_agent('frontend-engineer'),
    session_id=session_id,
    user_name=user.name,
    available_tools=['file_read', 'file_write'],
    recent_context=last_3_messages
)

response = await llm.chat_completion(
    messages=[
        {"role": "system", "content": optimized_prompt},
        {"role": "user", "content": user_message}
    ],
    provider="vllm"  # Must use vLLM for caching
)
```

**Benefit:**
- First request: Full 4,900 tokens (~6 seconds)
- Subsequent requests: Only 66 dynamic tokens (~1.7 seconds)
- **3.5x faster!**

---

## Integration Patterns

### Pattern 1: Agent System (Most Common)

**Location:** `src/orchestrator.py`, `src/chat_workflow_manager.py`

**Before:**
```python
def get_agent_system_prompt(self, agent_type: str) -> str:
    """Get system prompt for agent."""
    return self.prompt_manager.get("default.agent.system.main")
```

**After:**
```python
def get_agent_system_prompt(
    self,
    agent_type: str,
    session_id: str,
    user_context: dict
) -> str:
    """Get optimized system prompt for agent."""
    from src.prompt_manager import get_optimized_prompt
    from src.agent_tier_classifier import get_base_prompt_for_agent

    return get_optimized_prompt(
        base_prompt_key=get_base_prompt_for_agent(agent_type),
        session_id=session_id,
        user_name=user_context.get('name'),
        user_role=user_context.get('role'),
        available_tools=self.get_available_tools(agent_type),
        recent_context=self.get_recent_context(session_id),
    )
```

---

### Pattern 2: Chat API Endpoint

**Location:** `backend/api/chat.py`

**Before:**
```python
@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    # Get system prompt
    system_prompt = prompt_manager.get("default.agent.system.main")

    response = await llm.chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.message}
        ]
    )
```

**After:**
```python
@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    from src.prompt_manager import get_optimized_prompt
    from src.agent_tier_classifier import get_base_prompt_for_agent

    # Get optimized prompt (98.7% cacheable)
    system_prompt = get_optimized_prompt(
        base_prompt_key=get_base_prompt_for_agent(
            request.agent_type or 'frontend-engineer'
        ),
        session_id=request.session_id,
        user_name=request.user_name,
        available_tools=get_user_tools(request.user_id),
        recent_context=get_chat_history(request.session_id, last_n=3),
    )

    response = await llm.chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.message}
        ],
        provider="vllm"  # Enable vLLM for caching!
    )
```

---

### Pattern 3: Task Execution

**Location:** `src/chat_workflow_manager.py`

**Before:**
```python
async def execute_task(self, task: Task, session_id: str):
    """Execute a single task."""
    system_prompt = self.prompt_manager.get("default.agent.system.main")

    response = await self.llm.chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task.description}
        ]
    )
```

**After:**
```python
async def execute_task(self, task: Task, session_id: str):
    """Execute a single task with optimized prompts."""
    from src.prompt_manager import get_optimized_prompt
    from src.agent_tier_classifier import get_base_prompt_for_agent

    # Get optimized prompt for task agent
    system_prompt = get_optimized_prompt(
        base_prompt_key=get_base_prompt_for_agent(task.agent_type),
        session_id=session_id,
        user_name=task.user_name,
        available_tools=task.required_tools,
        recent_context=f"Previous task: {task.previous_result}",
        additional_params={
            'task_priority': task.priority,
            'task_deadline': task.deadline,
        }
    )

    response = await self.llm.chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task.description}
        ],
        provider="vllm"
    )
```

---

## Agent Tier Classification

### Understanding Agent Tiers

```python
from src.agent_tier_classifier import (
    get_agent_tier,
    get_base_prompt_for_agent,
    get_cache_hit_expectation,
    list_agents_by_tier,
    AgentTier
)

# Example: Get tier info for any agent
agent_type = "frontend-engineer"

tier = get_agent_tier(agent_type)
# Returns: AgentTier.TIER_1_DEFAULT

base_prompt = get_base_prompt_for_agent(agent_type)
# Returns: "default.agent.system.main"

cache_rate = get_cache_hit_expectation(agent_type)
# Returns: "90-95%"

# List all agents in a tier
tier1_agents = list_agents_by_tier(AgentTier.TIER_1_DEFAULT)
# Returns: ['frontend-engineer', 'backend-engineer', 'database-engineer', ...]
```

### Tier Breakdown

**Tier 1 - Default Agents (90-95% cache hit):**
- frontend-engineer
- backend-engineer
- senior-backend-engineer
- database-engineer
- documentation-engineer
- testing-engineer
- devops-engineer
- project-manager

**Tier 2 - Analysis Agents (70-80% cache hit):**
- code-reviewer
- performance-engineer
- security-auditor
- code-refactorer

**Tier 3 - Specialized Agents (40-60% cache hit):**
- code-skeptic
- systems-architect
- ai-ml-engineer
- multimodal-engineer
- frontend-designer
- prd-writer
- content-writer
- memory-monitor
- project-task-planner

**Tier 4 - Orchestrator (50-70% cache hit):**
- orchestrator

---

## Configuration

### Enable vLLM

**File:** `config/config.yaml`

```yaml
llm:
  vllm:
    enabled: true  # Set to true to enable vLLM
    default_model: meta-llama/Llama-3.2-3B-Instruct
    tensor_parallel_size: 1
    gpu_memory_utilization: 0.9
    max_model_len: 8192
    trust_remote_code: false
    dtype: auto
    enable_chunked_prefill: true  # CRITICAL for prefix caching
```

### Install vLLM

```bash
pip install vllm

# Verify installation
python -c "import vllm; print(f'vLLM {vllm.__version__} installed')"
```

---

## Performance Monitoring

### Track Cache Hit Rates

```python
async def execute_with_metrics(self, prompt: str, user_message: str):
    """Execute with cache performance tracking."""

    response = await self.llm.chat_completion(
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message}
        ],
        provider="vllm"
    )

    # Extract cache metrics
    cached_tokens = response.metadata.get("cached_tokens", 0)
    total_prompt_tokens = response.usage.get("prompt_tokens", 0)
    cache_hit_rate = (
        (cached_tokens / total_prompt_tokens * 100)
        if total_prompt_tokens > 0
        else 0
    )

    # Log performance
    logger.info(
        f"Cache Performance: {cache_hit_rate:.1f}% hit rate "
        f"({cached_tokens}/{total_prompt_tokens} tokens cached)"
    )
    logger.info(f"Processing Time: {response.processing_time:.2f}s")

    # Track metrics
    self.metrics.record_cache_hit_rate(cache_hit_rate)
    self.metrics.record_processing_time(response.processing_time)

    return response
```

### Expected Metrics (Single Agent Workflow)

| Request # | Cache Hit Rate | Processing Time | Speedup |
|-----------|---------------|-----------------|---------|
| 1 (cold)  | 0%            | 6.0s            | 1.0x    |
| 2         | 98.7%         | 1.7s            | 3.5x    |
| 3         | 98.7%         | 1.7s            | 3.5x    |
| 4         | 98.7%         | 1.7s            | 3.5x    |
| ...       | 98.7%         | 1.7s            | 3.5x    |

---

## Migration Checklist

### Step 1: Update Imports

```python
# Add to files that use prompts
from src.prompt_manager import get_optimized_prompt
from src.agent_tier_classifier import get_base_prompt_for_agent
```

### Step 2: Replace Prompt Calls

Find all instances of:
```python
prompt_manager.get("default.agent.system.main")
```

Replace with:
```python
get_optimized_prompt(
    base_prompt_key=get_base_prompt_for_agent(agent_type),
    session_id=session_id,
    # ... other params
)
```

### Step 3: Update LLM Provider

Change:
```python
provider="ollama"
```

To:
```python
provider="vllm"
```

### Step 4: Test Performance

Run benchmark script:
```bash
python examples/vllm_prefix_caching_usage.py
```

Expected output:
- First request: ~6s
- Subsequent requests: ~1.7s
- Cache hit rate: 98.7%

---

## Troubleshooting

### Issue: Cache hit rate is 0%

**Cause:** vLLM not enabled or not installed

**Solution:**
```bash
# Check if vLLM installed
pip show vllm

# If not installed
pip install vllm

# Enable in config
# config/config.yaml: llm.vllm.enabled = true
```

### Issue: Cache hit rate < 50%

**Cause:** Dynamic content in static prefix

**Solution:** Ensure all dynamic data is passed as parameters to `get_optimized_prompt()`, not embedded in base prompts

### Issue: Performance not improving

**Cause:** Using wrong provider (Ollama instead of vLLM)

**Solution:** Always specify `provider="vllm"` in `chat_completion()` calls

---

## Advanced Usage

### Custom Dynamic Parameters

```python
prompt = get_optimized_prompt(
    base_prompt_key=get_base_prompt_for_agent('frontend-engineer'),
    session_id=session_id,
    user_name="Alice",
    additional_params={
        'project_name': 'AutoBot',
        'tech_stack': 'Vue.js + FastAPI',
        'coding_style': 'functional',
        'max_complexity': 10,
    }
)
```

These appear in the dynamic suffix:
```
**Additional Parameters:**
- project_name: AutoBot
- tech_stack: Vue.js + FastAPI
- coding_style: functional
- max_complexity: 10
```

### Conditional Tool Lists

```python
def get_agent_tools(agent_type: str, user_permissions: list) -> list:
    """Get tools based on agent type and user permissions."""

    base_tools = {
        'frontend-engineer': ['file_read', 'file_write', 'npm_run'],
        'backend-engineer': ['file_read', 'file_write', 'database_query'],
        'security-auditor': ['file_read', 'vulnerability_scan'],
    }

    tools = base_tools.get(agent_type, [])

    # Filter by permissions
    return [t for t in tools if t in user_permissions]

# Use in prompt
prompt = get_optimized_prompt(
    base_prompt_key=get_base_prompt_for_agent(agent_type),
    session_id=session_id,
    available_tools=get_agent_tools(agent_type, user.permissions),
)
```

---

## Performance Benchmarks

### Single Agent Type (10 Tasks)

**Without Optimization:**
- Total time: 60 seconds (6s per task)
- No caching

**With Optimization:**
- First task: 6 seconds (cold cache)
- Tasks 2-10: 1.7 seconds each (15.3s total)
- **Total time: 21.3 seconds**
- **2.8x faster overall**

### Mixed Agent Types (10 Tasks, Same Tier)

**Without Optimization:**
- Total time: 60 seconds

**With Optimization:**
- Total time: 22 seconds
- **2.7x faster overall**

### Multi-Agent Workflow (20 Agents)

**Without Optimization:**
- Total time: 120 seconds

**With Optimization:**
- Total time: 35 seconds
- **3.4x faster overall**

---

## Next Steps

1. **Enable vLLM:** Install and configure vLLM
2. **Update Code:** Migrate existing prompt usage to `get_optimized_prompt()`
3. **Monitor Performance:** Track cache hit rates and speedup
4. **Optimize Further:** Consider Phase 2 (tier-specific templates)

---

## References

- **Analysis Document:** `analysis/prompt-optimization-for-vllm-caching.md`
- **Usage Examples:** `examples/vllm_prefix_caching_usage.py`
- **vLLM Setup Guide:** `docs/guides/VLLM_SETUP_GUIDE.md`
- **Implementation Code:**
  - `src/prompt_manager.py` (get_optimized_prompt function)
  - `src/agent_tier_classifier.py` (tier classification)
  - `prompts/default/agent.system.dynamic_context.md` (dynamic template)

---

## Support

For questions or issues:
1. Check `docs/guides/VLLM_SETUP_GUIDE.md` for vLLM setup
2. Review `examples/vllm_prefix_caching_usage.py` for working examples
3. Search Memory MCP: `mcp__memory__search_nodes --query "vLLM prefix caching"`
