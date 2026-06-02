# Odysseus Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port five high-value patterns from the Odysseus open-source AI workspace into AutoBot: circuit-breaker consecutive-failure reset, adaptive context budget scaling, structured conversation compaction prompt + tool-message sanitization, memory fingerprinting to skip redundant LLM audits, and an agent entity-anchor UI convention.

**Architecture:** Each task is a surgical edit to one existing file (or one small addition). No new modules, no cross-cutting refactors. All changes are independently testable and committable.

**Tech Stack:** Python 3.11+, FastAPI, pytest, Redis, autobot_shared, llm_shared, chat_history

---

## File Map

| Task | File(s) touched | What changes |
|------|----------------|--------------|
| 1 | `autobot-backend/circuit_breaker.py` | Success in CLOSED state resets failure counter to 0 instead of decrementing by 1 |
| 1 | `autobot_shared/ssot_constants.py` | Add `CONSECUTIVE_RESET_ON_SUCCESS = True` to `CircuitBreakerDefaults` |
| 2 | `autobot-backend/context_window_manager.py` | Add `get_adaptive_context_length()` + `_CONTEXT_HEADROOM`/`_CONTEXT_HARD_MAX` constants |
| 3 | `autobot-backend/chat_history/context_overflow.py` | Replace summarizer prompt with Cursor-style structured template; add `_sanitize_tool_messages()` |
| 4 | `autobot-backend/memory/essential_story.py` | Add `_compute_facts_fingerprint()` and bake fingerprint into cache key |
| 5 | `autobot-backend/resources/prompts/chat/system_prompt.md` | Add `## UI Reference Conventions` section defining `[Name](#kind-id)` anchors |

---

## Task 1: Circuit Breaker — Consecutive-Failure Reset

**Problem:** `_record_success()` in CLOSED state does `failure_count = max(0, failure_count - 1)`. A pattern of fail-fail-success-fail accumulates net failures toward the threshold. One transient error immediately after a success still moves toward lockout. Odysseus resets to zero on any success so intermittent blips never accumulate.

**Files:**
- Modify: `autobot-backend/circuit_breaker.py:253`
- Modify: `autobot_shared/ssot_constants.py` (add constant)
- Test: `autobot-backend/circuit_breaker_test.py` (existing file, add two test cases)

- [ ] **Step 1: Verify the existing test file and read the failure_count decrement line**

```bash
grep -n "failure_count" autobot-backend/circuit_breaker.py | grep -v "threshold\|config\|stats\|history\|last_failure"
```
Expected output includes line ~253: `self.failure_count = max(0, self.failure_count - 1)`

- [ ] **Step 2: Add `CONSECUTIVE_RESET_ON_SUCCESS` to `CircuitBreakerDefaults`**

In `autobot_shared/ssot_constants.py`, inside `class CircuitBreakerDefaults:`, add after line `MAX_HISTORY_SIZE = 100`:

```python
    # Reset failure counter fully on any success in CLOSED state (Odysseus pattern).
    # When True, a single success clears accumulated transient failures immediately
    # instead of decrementing one-by-one toward zero.
    CONSECUTIVE_RESET_ON_SUCCESS: bool = True
```

- [ ] **Step 3: Add `reset_on_success` field to `CircuitBreakerConfig`**

In `autobot-backend/circuit_breaker.py`, inside `class CircuitBreakerConfig:`, add after the `min_calls_for_evaluation` field:

```python
    reset_on_success: bool = CircuitBreakerDefaults.CONSECUTIVE_RESET_ON_SUCCESS
```

- [ ] **Step 4: Change the CLOSED-state success handler**

In `autobot-backend/circuit_breaker.py`, in `_record_success()`, replace the CLOSED-state block (currently `elif self.state == CircuitState.CLOSED:`):

**Before:**
```python
            # Reset failure count on successful call in CLOSED state
            elif self.state == CircuitState.CLOSED:
                self.failure_count = max(0, self.failure_count - 1)
```

**After:**
```python
            # Reset failure count on successful call in CLOSED state.
            # When reset_on_success is True (default), any success fully clears
            # accumulated transient failures — prevents gradual false lockout.
            elif self.state == CircuitState.CLOSED:
                if self.config.reset_on_success:
                    self.failure_count = 0
                else:
                    self.failure_count = max(0, self.failure_count - 1)
```

- [ ] **Step 5: Write failing tests**

Add to the bottom of `autobot-backend/circuit_breaker_test.py` (or create it if it only contains the quick e2e):

```python
def test_success_resets_failure_count_to_zero():
    """Consecutive-reset: any success fully clears accumulated failures."""
    config = CircuitBreakerConfig(failure_threshold=5, reset_on_success=True)
    cb = CircuitBreaker("test_reset", config)

    # Accumulate 3 failures — circuit stays CLOSED (threshold is 5)
    err = ConnectionError("oops")
    for _ in range(3):
        cb._record_failure(0.1, err)
    assert cb.failure_count == 3
    assert cb.state == CircuitState.CLOSED

    # One success should reset to 0, not 2
    cb._record_success(0.1)
    assert cb.failure_count == 0


def test_success_decrements_when_reset_disabled():
    """Legacy mode: success decrements failure_count by 1 when reset_on_success=False."""
    config = CircuitBreakerConfig(failure_threshold=5, reset_on_success=False)
    cb = CircuitBreaker("test_decrement", config)

    err = ConnectionError("oops")
    for _ in range(3):
        cb._record_failure(0.1, err)
    assert cb.failure_count == 3

    cb._record_success(0.1)
    assert cb.failure_count == 2  # decremented, not zeroed
```

- [ ] **Step 6: Run failing tests**

```bash
cd autobot-backend && python -m pytest circuit_breaker_test.py::test_success_resets_failure_count_to_zero circuit_breaker_test.py::test_success_decrements_when_reset_disabled -v
```
Expected: 2 failures (AttributeError or AssertionError — the field doesn't exist yet / old behavior)

- [ ] **Step 7: Run tests after implementation**

```bash
cd autobot-backend && python -m pytest circuit_breaker_test.py::test_success_resets_failure_count_to_zero circuit_breaker_test.py::test_success_decrements_when_reset_disabled -v
```
Expected: PASS PASS

- [ ] **Step 8: Run full circuit-breaker test suite to check no regressions**

```bash
cd autobot-backend && python -m pytest circuit_breaker_test.py circuit_breaker_quick_e2e_test.py -v
```
Expected: all green

- [ ] **Step 9: Commit**

```bash
git add autobot_shared/ssot_constants.py autobot-backend/circuit_breaker.py autobot-backend/circuit_breaker_test.py
git commit -m "feat(circuit-breaker): reset failure count to zero on success in CLOSED state

Ports the consecutive-failure-reset pattern from Odysseus. Previously a
success decremented failure_count by 1, so alternating fail/success still
accumulated toward the threshold. Now any success in CLOSED state clears
the counter entirely, preventing transient blips from causing false lockout.

Controlled by CircuitBreakerDefaults.CONSECUTIVE_RESET_ON_SUCCESS (default True)
and the per-instance reset_on_success config field."
```

---

## Task 2: Context Window Manager — Adaptive Budget for Unknown Models

**Problem:** `_get_default_config()` returns `context_window_tokens: 4096` for any model not in `config/context_windows.yaml`. A newly added Ollama model is silently capped at 4096 tokens even if it has 128k context. Odysseus scales to `context_length * 0.85` capped at 200k for models it doesn't recognize.

**Files:**
- Modify: `autobot-backend/context_window_manager.py`
- Test: `autobot-backend/tests/test_context_window_manager.py` (create)

- [ ] **Step 1: Write failing tests**

Create `autobot-backend/tests/test_context_window_manager.py`:

```python
"""Tests for adaptive context budget scaling (Odysseus pattern)."""
import pytest
from unittest.mock import patch
from context_window_manager import ContextWindowManager, _CONTEXT_HEADROOM, _CONTEXT_HARD_MAX


def test_constants_exist():
    assert 0 < _CONTEXT_HEADROOM < 1
    assert _CONTEXT_HARD_MAX >= 128_000


def test_adaptive_context_unknown_model_uses_registry():
    """Unknown model with registry hit → scales to headroom% of registry value."""
    mgr = ContextWindowManager.__new__(ContextWindowManager)
    mgr.config = mgr._get_default_config()
    mgr.current_model = "default"

    with patch.object(mgr, "_query_known_context_length", return_value=128_000):
        result = mgr.get_adaptive_context_length("some-new-model")

    assert result == int(128_000 * _CONTEXT_HEADROOM)


def test_adaptive_context_unknown_model_registry_miss():
    """Unknown model with no registry entry → falls back to 4096."""
    mgr = ContextWindowManager.__new__(ContextWindowManager)
    mgr.config = mgr._get_default_config()
    mgr.current_model = "default"

    with patch.object(mgr, "_query_known_context_length", return_value=0):
        result = mgr.get_adaptive_context_length("totally-unknown-model")

    assert result == 4096


def test_adaptive_context_yaml_model_uses_yaml():
    """Model in YAML config → uses YAML context_window_tokens, not registry."""
    mgr = ContextWindowManager.__new__(ContextWindowManager)
    mgr.config = {
        "models": {
            "default": {"name": "default", "context_window_tokens": 4096, "max_output_tokens": 2048,
                         "message_budget": {"system_prompt": 500, "recent_messages": 20, "max_history_tokens": 3000}},
            "known-model": {"context_window_tokens": 32_768, "max_output_tokens": 4096,
                             "message_budget": {"system_prompt": 500, "recent_messages": 20, "max_history_tokens": 16000}},
        },
        "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},
    }
    mgr.current_model = "default"
    result = mgr.get_adaptive_context_length("known-model")
    assert result == 32_768


def test_adaptive_context_hard_cap():
    """Very large context window is capped at _CONTEXT_HARD_MAX."""
    mgr = ContextWindowManager.__new__(ContextWindowManager)
    mgr.config = mgr._get_default_config()
    mgr.current_model = "default"

    with patch.object(mgr, "_query_known_context_length", return_value=2_000_000):
        result = mgr.get_adaptive_context_length("giant-model")

    assert result == _CONTEXT_HARD_MAX
```

- [ ] **Step 2: Run failing tests**

```bash
cd autobot-backend && python -m pytest tests/test_context_window_manager.py -v
```
Expected: ImportError on `_CONTEXT_HEADROOM`, `_CONTEXT_HARD_MAX`, `get_adaptive_context_length`

- [ ] **Step 3: Implement constants and new methods**

In `autobot-backend/context_window_manager.py`, after the imports block add:

```python
_CONTEXT_HEADROOM: float = 0.85
_CONTEXT_HARD_MAX: int = 200_000
```

Then add two methods to the `ContextWindowManager` class, after `get_architecture_family()`:

```python
    def _query_known_context_length(self, model_name: str) -> int:
        """Try to get context window from llm_shared model registry.

        Returns 0 when the model is unknown to the registry.
        """
        try:
            from llm_shared.model_param_registry import get_model_kwargs
            kwargs = get_model_kwargs(model_name)
            return int(kwargs.get("context_window_tokens", 0))
        except Exception:
            return 0

    def get_adaptive_context_length(self, model_name: str | None = None) -> int:
        """Return the effective context length for token budget calculations.

        Resolution order:
        1. Model in YAML config → return declared context_window_tokens exactly.
        2. Model unknown to YAML → query llm_shared registry; if found, scale by
           _CONTEXT_HEADROOM and cap at _CONTEXT_HARD_MAX.
        3. Registry also misses → return YAML default (4096).

        This prevents newly-added Ollama models from being silently capped at the
        YAML fallback of 4096 tokens when their actual context window is 128k+.
        """
        model = model_name or self.current_model
        if model in self.config["models"]:
            return int(self.config["models"][model].get("context_window_tokens", 4096))

        discovered = self._query_known_context_length(model)
        if discovered > 0:
            scaled = int(discovered * _CONTEXT_HEADROOM)
            return min(scaled, _CONTEXT_HARD_MAX)

        # Fall through to YAML default
        default_entry = self.config["models"].get(self.config["models"]["default"]["name"], {})
        return int(default_entry.get("context_window_tokens", 4096))
```

- [ ] **Step 4: Run tests**

```bash
cd autobot-backend && python -m pytest tests/test_context_window_manager.py -v
```
Expected: all 4 PASS

- [ ] **Step 5: Smoke-test existing context_window_manager tests still pass**

```bash
cd autobot-backend && python -m pytest -k "context_window" -v
```
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/context_window_manager.py autobot-backend/tests/test_context_window_manager.py
git commit -m "feat(context): adaptive context budget for unknown models

Adds get_adaptive_context_length() to ContextWindowManager. Models not in
context_windows.yaml now scale to 85% of their registry-discovered context
window (capped at 200k) instead of silently falling back to 4096 tokens.

Ports the adaptive budget pattern from Odysseus src/context_budget.py."
```

---

## Task 3: Conversation Compaction — Structured Summary Prompt + Tool-Message Sanitization

**Problem:** `ConversationSummarizer._SUMMARIZATION_PROMPT` produces a generic 2–3 paragraph summary that loses structured context (what was done, what's pending, key facts). Orphaned `tool_call`/`tool` message pairs are not stripped before trimming, which can cause provider validation errors. Odysseus uses a Cursor-style structured template and sanitizes orphans.

**Files:**
- Modify: `autobot-backend/chat_history/context_overflow.py`
- Test: `autobot-backend/chat_history/context_overflow_test.py` (existing — add cases)

- [ ] **Step 1: Read the existing test file to understand test patterns**

```bash
head -60 autobot-backend/chat_history/context_overflow_test.py
```

- [ ] **Step 2: Write failing tests for sanitization**

Add to `autobot-backend/chat_history/context_overflow_test.py`:

```python
from chat_history.context_overflow import ConversationSummarizer, _sanitize_tool_messages


def test_sanitize_removes_orphaned_tool_message():
    """Tool messages with no preceding tool_calls assistant message are dropped."""
    msgs = [
        {"role": "user", "content": "do something"},
        {"role": "tool", "content": "result", "tool_call_id": "abc"},  # orphan
        {"role": "assistant", "content": "done"},
    ]
    result = _sanitize_tool_messages(msgs)
    roles = [m["role"] for m in result]
    assert roles == ["user", "assistant"]


def test_sanitize_keeps_valid_tool_batch():
    """tool messages that follow an assistant tool_calls message are kept."""
    msgs = [
        {"role": "user", "content": "search"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "t1", "function": {"name": "search"}}]},
        {"role": "tool", "content": "results", "tool_call_id": "t1"},
        {"role": "assistant", "content": "Here are the results."},
    ]
    result = _sanitize_tool_messages(msgs)
    assert len(result) == 4


def test_sanitize_no_tool_messages_passthrough():
    """Messages with no tool messages pass through unchanged."""
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    assert _sanitize_tool_messages(msgs) == msgs


def test_structured_summary_prompt_has_required_sections():
    """New summarizer prompt contains all Cursor-style structured sections."""
    prompt = ConversationSummarizer._SUMMARIZATION_PROMPT
    for section in ["User Goal", "What Was Done", "Current State", "Pending", "Key Context"]:
        assert section in prompt, f"Missing section: {section}"
```

- [ ] **Step 3: Run failing tests**

```bash
cd autobot-backend && python -m pytest chat_history/context_overflow_test.py::test_sanitize_removes_orphaned_tool_message chat_history/context_overflow_test.py::test_sanitize_keeps_valid_tool_batch chat_history/context_overflow_test.py::test_sanitize_no_tool_messages_passthrough chat_history/context_overflow_test.py::test_structured_summary_prompt_has_required_sections -v
```
Expected: ImportError on `_sanitize_tool_messages`, plus section assertion failure

- [ ] **Step 4: Replace the summarizer prompt and add sanitizer**

In `autobot-backend/chat_history/context_overflow.py`, replace `ConversationSummarizer._SUMMARIZATION_PROMPT` and add `_sanitize_tool_messages` as a module-level function.

Replace the prompt string:

```python
    _SUMMARIZATION_PROMPT = (
        "You are summarizing a conversation to preserve context after compaction. "
        "Produce a structured summary that lets the conversation continue seamlessly.\n\n"
        "Use this format:\n\n"
        "## Conversation Summary\n"
        "**Turns summarized:** {{count}}\n\n"
        "### User Goal\n"
        "One sentence describing what the user is trying to accomplish.\n\n"
        "### What Was Done\n"
        "- Bullet points of completed actions, decisions made, and key outputs\n"
        "- Include specific file paths, function names, variable names, URLs, and config values\n"
        "- Note any errors encountered and how they were resolved\n\n"
        "### Current State\n"
        "What is the system/task state right now? What was the last thing discussed?\n\n"
        "### Pending / Next Steps\n"
        "- What remains to be done\n"
        "- Any open questions or blockers\n\n"
        "### Key Context\n"
        "- Important constraints, preferences, or decisions that must not be forgotten\n"
        "- Specific values: model names, ports, paths, credentials references, versions\n\n"
        "Keep the summary under 1000 tokens. Be dense — every token should carry information.\n\n"
        "Conversation to summarize:\n"
        "{{conversation}}\n\n"
        "Provide ONLY the structured summary above — no preamble or meta-commentary."
    )
```

Add `_sanitize_tool_messages` as a module-level function before `class ConversationSummarizer`:

```python
def _sanitize_tool_messages(msgs: list) -> list:
    """Drop orphaned tool messages and dangling assistant tool_calls.

    OpenAI/Anthropic APIs require every role='tool' message to immediately
    follow an assistant message that carries tool_calls. Front-trimming
    conversation history can cut the assistant tool_calls parent while keeping
    its tool responses, causing provider validation errors.
    """
    cleaned = []
    in_batch = False
    for m in msgs:
        role = m.get("role")
        if role == "tool":
            if in_batch:
                cleaned.append(m)
            # else: orphan — drop silently
            continue
        if role == "assistant" and m.get("tool_calls"):
            in_batch = True
        else:
            in_batch = False
        cleaned.append(m)
    return cleaned
```

- [ ] **Step 5: Update `summarize_messages` to use sanitizer and new format**

In `summarize_messages()`, update `_format_messages` call to handle `role`/`content` schema (the LLM API format) in addition to the legacy `sender`/`text` schema, and sanitize before summarizing:

Replace `_format_messages`:

```python
    def _format_messages(self, messages: list) -> str:
        """Format messages into readable conversation text.

        Handles both API schema (role/content) and display schema (sender/text).
        """
        lines = []
        for msg in messages:
            role = msg.get("role") or msg.get("sender", "unknown")
            content = msg.get("content") or msg.get("text", "")
            if isinstance(content, list):
                # OpenAI multi-part content — extract text parts only
                content = " ".join(
                    p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
                )
            if role and content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)
```

In `summarize_messages()`, add sanitization before formatting — replace:
```python
            conversation_text = self._format_messages(messages)
```
with:
```python
            conversation_text = self._format_messages(_sanitize_tool_messages(messages))
```

Also update the prompt format call. The new template uses `{{conversation}}` instead of `{conversation}` to avoid Python `.format()` conflicts with the double-brace sections. Change the prompt application line:

```python
            prompt = self._SUMMARIZATION_PROMPT.replace("{{conversation}}", conversation_text).replace("{{count}}", str(len(messages)))
```

- [ ] **Step 6: Run tests**

```bash
cd autobot-backend && python -m pytest chat_history/context_overflow_test.py -v
```
Expected: all green (including the 4 new cases and all existing ones)

- [ ] **Step 7: Commit**

```bash
git add autobot-backend/chat_history/context_overflow.py autobot-backend/chat_history/context_overflow_test.py
git commit -m "feat(chat): structured compaction prompt and tool-message sanitization

Replaces the generic 2-paragraph summarization prompt with a Cursor-style
structured template (User Goal / What Was Done / Current State / Pending /
Key Context) that preserves actionable context across compaction boundaries.

Also adds _sanitize_tool_messages() to strip orphaned role=tool messages
before trimming — prevents provider validation errors when front-trimming
cuts an assistant tool_calls parent while keeping its tool responses.

Ports patterns from Odysseus src/context_compactor.py."
```

---

## Task 4: Memory Essential Story — Fingerprint Cache Key

**Problem:** `EssentialStoryGenerator` caches the story in Redis keyed only by `model_name`. When facts are added, edited, or deleted, the cache is still served until TTL expiry (5 minutes), so the agent uses a stale summary. Odysseus uses a SHA-256 fingerprint of fact content as part of the cache key so any change invalidates automatically.

**Files:**
- Modify: `autobot-backend/memory/essential_story.py`
- Test: `autobot-backend/memory/essential_story_test.py` (create)

- [ ] **Step 1: Write failing tests**

Create `autobot-backend/memory/essential_story_test.py`:

```python
"""Tests for EssentialStoryGenerator fingerprint cache key (Odysseus pattern)."""
import hashlib
import pytest
from memory.essential_story import _compute_facts_fingerprint


def test_fingerprint_is_deterministic():
    facts = [
        {"id": "1", "content": "User prefers Python", "metadata": {"category": "preference"}},
        {"id": "2", "content": "User works at Acme Corp", "metadata": {"category": "identity"}},
    ]
    assert _compute_facts_fingerprint(facts) == _compute_facts_fingerprint(facts)


def test_fingerprint_is_order_independent():
    facts_a = [
        {"id": "1", "content": "A"},
        {"id": "2", "content": "B"},
    ]
    facts_b = [
        {"id": "2", "content": "B"},
        {"id": "1", "content": "A"},
    ]
    assert _compute_facts_fingerprint(facts_a) == _compute_facts_fingerprint(facts_b)


def test_fingerprint_changes_on_content_edit():
    facts_before = [{"id": "1", "content": "old text", "metadata": {"category": "fact"}}]
    facts_after  = [{"id": "1", "content": "new text", "metadata": {"category": "fact"}}]
    assert _compute_facts_fingerprint(facts_before) != _compute_facts_fingerprint(facts_after)


def test_fingerprint_changes_on_add():
    base = [{"id": "1", "content": "fact one"}]
    extended = [{"id": "1", "content": "fact one"}, {"id": "2", "content": "fact two"}]
    assert _compute_facts_fingerprint(base) != _compute_facts_fingerprint(extended)


def test_fingerprint_empty_list():
    assert _compute_facts_fingerprint([]) == _compute_facts_fingerprint([])
    assert isinstance(_compute_facts_fingerprint([]), str)
    assert len(_compute_facts_fingerprint([])) == 64  # sha256 hex digest
```

- [ ] **Step 2: Run failing tests**

```bash
cd autobot-backend && python -m pytest memory/essential_story_test.py -v
```
Expected: ImportError on `_compute_facts_fingerprint`

- [ ] **Step 3: Implement `_compute_facts_fingerprint` and update cache key**

In `autobot-backend/memory/essential_story.py`, add `import hashlib` to the imports (it's in stdlib — just add it).

Add after `_DEFAULT_BUDGET = 600`:

```python
def _compute_facts_fingerprint(facts: list) -> str:
    """Return a SHA-256 hex digest of fact (id, content, category) tuples.

    Order-independent: sorted before hashing so reordering facts does not
    invalidate the cache. Any add, edit, or delete changes the digest.
    """
    items = sorted(
        (
            str(f.get("id", "")),
            str(f.get("content", "")),
            str((f.get("metadata") or {}).get("category", "")),
        )
        for f in facts
    )
    h = hashlib.sha256()
    for triple in items:
        h.update(("\x1f".join(triple) + "\x1e").encode("utf-8"))
    return h.hexdigest()
```

Update the cache key template:

```python
_CACHE_KEY = "autobot:essential_story:{model_name}:{fingerprint}"
```

Update `generate()` to compute the fingerprint before the cache lookup:

```python
    async def generate(self, model_name: str | None = None) -> str:
        try:
            budget = await self._get_token_budget(model_name or "default")
            facts = await self._fetch_top_facts(budget)
            fingerprint = _compute_facts_fingerprint(facts)
            cached = await self._get_cached(model_name or "default", fingerprint)
            if cached is not None:
                return cached
            story = await self._format_output(facts)
            await self._set_cached(model_name or "default", fingerprint, story)
            return story
        except Exception:
            logger.warning(
                "EssentialStoryGenerator.generate failed — returning empty string",
                exc_info=True,
            )
            return ""
```

Update `_get_cached` and `_set_cached` signatures to accept fingerprint:

```python
    async def _get_cached(self, model_name: str, fingerprint: str) -> str | None:
        """Return cached story string from Redis, or None on miss/error."""
        try:
            from autobot_shared.redis_client import get_redis_client

            redis = await get_redis_client(database="knowledge")
            key = _CACHE_KEY.format(model_name=model_name, fingerprint=fingerprint)
            value = await redis.get(key)
            if value is None:
                return None
            return value.decode("utf-8") if isinstance(value, bytes) else value
        except Exception:
            logger.debug("Essential story cache get failed", exc_info=True)
            return None

    async def _set_cached(self, model_name: str, fingerprint: str, story: str) -> None:
        """Write story to Redis cache with TTL_5_MINUTES TTL."""
        try:
            from autobot_shared.redis_client import get_redis_client
            from constants.ttl_constants import TTL_5_MINUTES

            redis = await get_redis_client(database="knowledge")
            key = _CACHE_KEY.format(model_name=model_name, fingerprint=fingerprint)
            await redis.setex(key, TTL_5_MINUTES, story)
        except Exception:
            logger.debug("Essential story cache set failed", exc_info=True)
```

- [ ] **Step 4: Run fingerprint tests**

```bash
cd autobot-backend && python -m pytest memory/essential_story_test.py -v
```
Expected: all 5 PASS

- [ ] **Step 5: Import check**

```bash
cd autobot-backend && python -c "from memory.essential_story import EssentialStoryGenerator, _compute_facts_fingerprint; print('OK')"
```
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/memory/essential_story.py autobot-backend/memory/essential_story_test.py
git commit -m "feat(memory): fingerprint-keyed cache for EssentialStoryGenerator

Adds _compute_facts_fingerprint() that hashes (id, content, category)
tuples with SHA-256. The fingerprint is baked into the Redis cache key so
any add, edit, or delete to the fact set automatically invalidates the
cache — no more stale essential-story summaries after memory updates.

Ports the memory-consolidation fingerprinting pattern from Odysseus
services/memory/memory_extractor.py."
```

---

## Task 5: Agent System Prompt — Entity Anchor UI Convention

**Problem:** AutoBot's agent has no standardized way to reference entities (sessions, documents, tasks) as clickable links. Responses name entities in plain text; users cannot jump directly to them. Odysseus establishes `[Name](#kind-id)` anchors that the frontend converts to navigation buttons — a zero-backend-cost UX improvement that requires only a system-prompt addition.

**Files:**
- Modify: `autobot-backend/resources/prompts/chat/system_prompt.md`
- Test: manual validation (grep confirms section added; no runtime test needed)

- [ ] **Step 1: Verify current prompt has no anchor convention**

```bash
grep -n "anchor\|#session-\|#document-\|#task-\|kind-id" autobot-backend/resources/prompts/chat/system_prompt.md
```
Expected: no output

- [ ] **Step 2: Add UI Reference Conventions section**

In `autobot-backend/resources/prompts/chat/system_prompt.md`, insert the following block immediately before the `## Personality Guidelines` heading (currently around line 357):

```markdown
## UI Reference Conventions

When referencing AutoBot entities in your replies, use markdown link syntax with hash-prefixed anchors. The frontend converts these into clickable navigation buttons:

- **Sessions / chats:** `[Name](#session-<id>)`
- **Documents:** `[Title](#document-<id>)`
- **Tasks:** `[Task name](#task-<id>)`
- **Workflows:** `[Workflow name](#workflow-<id>)`
- **Knowledge items:** `[Item title](#knowledge-<id>)`

**Format:** `[link text](#kind-<id>)` — text in square brackets, anchor in parens.

**Examples:**
- After creating a session with id `89effa28`: "Created [New Chat](#session-89effa28) — click to open."
- Listing recent sessions:
  ```
  1. [Backend Debug](#session-abc123) — 2h ago
  2. [Code Review](#session-def456) — yesterday
  ```
- After running a task with id `42`: "Task [Nightly Sync](#task-42) is now scheduled."

Use these anchors wherever you mention a specific entity by ID. Plain-text mentions of IDs (e.g., "session abc123") are not clickable.

```

- [ ] **Step 3: Verify the section was added correctly**

```bash
grep -n "UI Reference Conventions\|#session-\|#document-\|#task-" autobot-backend/resources/prompts/chat/system_prompt.md
```
Expected: lines showing the new section heading and anchor examples.

- [ ] **Step 4: Confirm prompt still loads cleanly**

```bash
cd autobot-backend && python -c "
from prompt_manager import PromptManager
pm = PromptManager()
p = pm.get_prompt('chat.system_prompt')
assert '## UI Reference Conventions' in p
assert '#session-' in p
print('OK — prompt loads and contains anchor convention')
"
```
Expected: `OK — prompt loads and contains anchor convention`

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/resources/prompts/chat/system_prompt.md
git commit -m "feat(agent): add entity anchor UI convention to chat system prompt

Establishes [Name](#kind-id) as the standard for referencing AutoBot
entities (sessions, documents, tasks, workflows, knowledge) in agent
replies. The frontend converts these anchors into clickable navigation
buttons, making agent responses significantly more navigable.

Ports the UI conventions pattern from Odysseus src/agent_loop.py."
```

---

## Self-Review

**Spec coverage check:**
- ✅ Circuit breaker consecutive reset → Task 1
- ✅ Auto-scaling context budget for unknown models → Task 2
- ✅ Structured compaction prompt → Task 3
- ✅ Tool-message orphan sanitization → Task 3
- ✅ Memory fingerprint cache key → Task 4
- ✅ Agent entity anchor convention → Task 5

**Placeholder scan:** None found — all steps contain actual code.

**Type consistency check:**
- `_compute_facts_fingerprint(facts: list) -> str` used consistently in Task 4
- `get_adaptive_context_length(model_name: str | None) -> int` matches usage in Task 2
- `_sanitize_tool_messages(msgs: list) -> list` matches test imports in Task 3
- `_CACHE_KEY` format string updated before `_get_cached`/`_set_cached` signatures in Task 4 ✅
