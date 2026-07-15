# Content Reach — Task 1 (Core Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `ContentSourceRegistry` foundation — backend ABC, fallback chain, probe-cached + circuit-breaker-guarded chain execution, a `doctor`-style health probe, and the new `SourceType` values — so later source tasks (web-search, youtube, reddit, web-page, social) plug in as backends.

**Architecture:** A registry mirroring `llm_shared/fallback_chain.py` one layer down: each *content source* owns a `ContentSourceChain` of `ContentBackend`s executed primary→fallback. Execution probes each backend for real liveness (30s TTL cache), guards the call with the existing `CircuitBreaker`, attributes every success via `track_source`, and never raises to the caller (returns a structured failure result).

**Tech Stack:** Python 3.10+, `dataclasses`, `abc`, existing `circuit_breaker.py`, `source_attribution.py`, `api/system_health.py`, `autobot_shared.singleton_factory.lazy_singleton`.

## Global Constraints

- Copyright header on every new file: `# Copyright 2025-2026 mrveiss` / `# SPDX-License-Identifier: Apache-2.0` / `# AutoBot - AI-Powered Automation Platform` / `# Author: mrveiss` (verbatim, matching existing files).
- Async-first — no sync/blocking calls on async paths.
- Reuse canonical modules — never duplicate circuit-breaker, attribution, or logging.
- Logging via `from autobot_shared.logging_manager import get_logger` — no `print()`.
- No commit trailers (mrveiss sole author) — plain `git commit -m` only.
- Commit type/scope format: `feat(content-reach): <desc> (#10932)`.
- All work in worktree `.worktrees/issue-10932` (branch `issue-10932`).
- Tests run from the backend dir: `cd autobot-backend && python -m pytest <path> -v`.
- No `-n auto` in test commands.

---

### Task 1.1: `ContentBackend` ABC + request/result dataclasses

**Files:**
- Create: `autobot-backend/content_reach/__init__.py`
- Create: `autobot-backend/content_reach/base.py`
- Test: `autobot-backend/tests/content_reach/test_base.py`

**Interfaces:**
- Consumes: `source_attribution.SourceType`, `source_attribution.SourceReliability`
- Produces:
  - `ContentRequest(query: str = "", url: str = "", source: str = "", limit: int = 5, conversation_id: str = "content-reach", options: dict = {})`
  - `ContentResult(success: bool, source_type: SourceType, backend_used: str, text: str = "", structured: dict = {}, url: str = "", reliability: SourceReliability = MEDIUM, metadata: dict = {})` with classmethod `ContentResult.failure(source_type: SourceType, detail: str) -> ContentResult`
  - `BackendError(Exception)`
  - `class ContentBackend(ABC)` with attrs `name: str`, `source_type: SourceType`, and abstract `async def probe() -> bool`, `async def fetch(request: ContentRequest) -> ContentResult`

- [ ] **Step 1: Write the failing test**

Create `autobot-backend/tests/content_reach/test_base.py`:
```python
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
import pytest

from content_reach.base import BackendError, ContentBackend, ContentRequest, ContentResult
from source_attribution import SourceReliability, SourceType


def test_content_result_failure_factory():
    r = ContentResult.failure(SourceType.WEB_SEARCH, "boom")
    assert r.success is False
    assert r.source_type is SourceType.WEB_SEARCH
    assert r.backend_used == "none"
    assert r.metadata["error"] == "boom"


def test_content_request_defaults():
    req = ContentRequest(query="hello")
    assert req.query == "hello"
    assert req.limit == 5
    assert req.options == {}


def test_content_backend_is_abstract():
    with pytest.raises(TypeError):
        ContentBackend()  # abstract methods unimplemented


@pytest.mark.asyncio
async def test_concrete_backend_roundtrip():
    class Dummy(ContentBackend):
        name = "dummy"
        source_type = SourceType.WEB_SEARCH

        async def probe(self) -> bool:
            return True

        async def fetch(self, request: ContentRequest) -> ContentResult:
            return ContentResult(
                success=True,
                source_type=self.source_type,
                backend_used=self.name,
                text=f"result for {request.query}",
                reliability=SourceReliability.MEDIUM,
            )

    d = Dummy()
    assert await d.probe() is True
    res = await d.fetch(ContentRequest(query="q"))
    assert res.success and res.text == "result for q"
    assert isinstance(BackendError(), Exception)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest tests/content_reach/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_reach'`

- [ ] **Step 3: Create the package `__init__.py`**

Create `autobot-backend/content_reach/__init__.py`:
```python
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Content Reach — external web/social content capability for agents (#10932)."""
```

- [ ] **Step 4: Implement `base.py`**

Create `autobot-backend/content_reach/base.py`:
```python
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Core abstractions for Content Reach backends (#10932)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from source_attribution import SourceReliability, SourceType


class BackendError(Exception):
    """Raised by a ContentBackend when a fetch attempt fails."""


@dataclass
class ContentRequest:
    """A request for external content."""

    query: str = ""
    url: str = ""
    source: str = ""
    limit: int = 5
    conversation_id: str = "content-reach"
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentResult:
    """Normalized result returned by a backend."""

    success: bool
    source_type: SourceType
    backend_used: str
    text: str = ""
    structured: dict[str, Any] = field(default_factory=dict)
    url: str = ""
    reliability: SourceReliability = SourceReliability.MEDIUM
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def failure(cls, source_type: SourceType, detail: str) -> "ContentResult":
        """Build a non-successful result carrying an error detail."""
        return cls(
            success=False,
            source_type=source_type,
            backend_used="none",
            metadata={"error": detail},
        )


class ContentBackend(ABC):
    """A single way to fetch content for a source (e.g. ddgs, jina, browser)."""

    name: str
    source_type: SourceType

    @abstractmethod
    async def probe(self) -> bool:
        """Return True if this backend is actually working right now."""

    @abstractmethod
    async def fetch(self, request: ContentRequest) -> ContentResult:
        """Fetch content; raise BackendError (or return success=False) on failure."""
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest tests/content_reach/test_base.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-10932
git add autobot-backend/content_reach/__init__.py autobot-backend/content_reach/base.py autobot-backend/tests/content_reach/test_base.py
git commit -m "feat(content-reach): ContentBackend ABC + request/result dataclasses (#10932)"
```

---

### Task 1.2: `ContentSourceChain` + env-driven reorder

**Files:**
- Create: `autobot-backend/content_reach/chain.py`
- Test: `autobot-backend/tests/content_reach/test_chain.py`

**Interfaces:**
- Consumes: `content_reach.base.ContentBackend`, `source_attribution.SourceType`
- Produces:
  - `ContentSourceChain(source: str, source_type: SourceType, backends: list[ContentBackend])`
  - method `backend_names() -> list[str]`
  - method `reordered() -> ContentSourceChain` — applies env override `AUTOBOT_CONTENT_CHAIN_<SOURCE>=name1,name2`; named backends move first (original order for the rest); unknown names ignored.

- [ ] **Step 1: Write the failing test**

Create `autobot-backend/tests/content_reach/test_chain.py`:
```python
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from content_reach.base import ContentBackend
from content_reach.chain import ContentSourceChain
from source_attribution import SourceType


def _stub(backend_name: str) -> ContentBackend:
    class _B(ContentBackend):
        name = backend_name
        source_type = SourceType.WEB_SEARCH

        async def probe(self):
            return True

        async def fetch(self, request):
            raise NotImplementedError

    return _B()


def _chain():
    return ContentSourceChain(
        source="web_search",
        source_type=SourceType.WEB_SEARCH,
        backends=[_stub("ddgs"), _stub("jina"), _stub("browser")],
    )


def test_backend_names_preserve_order():
    assert _chain().backend_names() == ["ddgs", "jina", "browser"]


def test_reorder_noop_without_env(monkeypatch):
    monkeypatch.delenv("AUTOBOT_CONTENT_CHAIN_WEB_SEARCH", raising=False)
    assert _chain().reordered().backend_names() == ["ddgs", "jina", "browser"]


def test_reorder_promotes_named_backends(monkeypatch):
    monkeypatch.setenv("AUTOBOT_CONTENT_CHAIN_WEB_SEARCH", "browser,ddgs")
    assert _chain().reordered().backend_names() == ["browser", "ddgs", "jina"]


def test_reorder_ignores_unknown_names(monkeypatch):
    monkeypatch.setenv("AUTOBOT_CONTENT_CHAIN_WEB_SEARCH", "nope,jina")
    assert _chain().reordered().backend_names() == ["jina", "ddgs", "browser"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest tests/content_reach/test_chain.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_reach.chain'`

- [ ] **Step 3: Implement `chain.py`**

Create `autobot-backend/content_reach/chain.py`:
```python
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Content source fallback chain — mirrors llm_shared.fallback_chain (#10932)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from content_reach.base import ContentBackend
from source_attribution import SourceType


@dataclass
class ContentSourceChain:
    """Ordered primary+fallback backends for one content source."""

    source: str
    source_type: SourceType
    backends: list[ContentBackend]

    def backend_names(self) -> list[str]:
        """Return backend names in execution order."""
        return [b.name for b in self.backends]

    def reordered(self) -> "ContentSourceChain":
        """Apply AUTOBOT_CONTENT_CHAIN_<SOURCE> env override, if present."""
        env_key = f"AUTOBOT_CONTENT_CHAIN_{self.source.upper()}"
        spec = os.environ.get(env_key, "").strip()
        if not spec:
            return self

        wanted = [n.strip() for n in spec.split(",") if n.strip()]
        by_name = {b.name: b for b in self.backends}
        promoted = [by_name[n] for n in wanted if n in by_name]
        promoted_names = {b.name for b in promoted}
        remainder = [b for b in self.backends if b.name not in promoted_names]
        return ContentSourceChain(
            source=self.source,
            source_type=self.source_type,
            backends=promoted + remainder,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest tests/content_reach/test_chain.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-10932
git add autobot-backend/content_reach/chain.py autobot-backend/tests/content_reach/test_chain.py
git commit -m "feat(content-reach): ContentSourceChain with env-driven reorder (#10932)"
```

---

### Task 1.3: `ContentSourceRegistry` — probe-cached, CB-guarded execution

**Files:**
- Create: `autobot-backend/content_reach/registry.py`
- Test: `autobot-backend/tests/content_reach/test_registry.py`

**Interfaces:**
- Consumes: `content_reach.base.*`, `content_reach.chain.ContentSourceChain`, `circuit_breaker.get_circuit_breaker_manager`, `circuit_breaker.CircuitBreakerOpenError`, `source_attribution.track_source`, `lazy_singleton`
- Produces:
  - `ContentSourceRegistry` with:
    - `register_chain(chain: ContentSourceChain) -> None`
    - `get_chain(source: str) -> ContentSourceChain | None`
    - `list_sources() -> dict[str, list[str]]`
    - `async fetch(source: str, request: ContentRequest) -> ContentResult`
    - `async probe_all() -> dict[str, list[str]]` (live backend names per source)
    - `clear() -> None` (test helper)
  - `get_content_source_registry` = `lazy_singleton(ContentSourceRegistry)`
- Behavior: `fetch` tries each backend in `chain.reordered()`; skips backends failing a 30s-cached `probe()`; guards `fetch` with `CircuitBreaker.call_async`; on `CircuitBreakerOpenError` or any exception or `success=False`, advances to next; first success is `track_source`-attributed and returned; all-fail returns `ContentResult.failure(chain.source_type, ...)`. Unknown source returns `ContentResult.failure(SourceType.WEB_SEARCH, ...)`.

- [ ] **Step 1: Write the failing test**

Create `autobot-backend/tests/content_reach/test_registry.py`:
```python
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
import pytest

from content_reach.base import BackendError, ContentBackend, ContentRequest, ContentResult
from content_reach.chain import ContentSourceChain
from content_reach.registry import ContentSourceRegistry
from source_attribution import SourceType


class StubBackend(ContentBackend):
    def __init__(self, name, *, live=True, mode="ok"):
        self.name = name
        self.source_type = SourceType.WEB_SEARCH
        self._live = live
        self._mode = mode  # ok | fail_exc | fail_result
        self.fetch_calls = 0

    async def probe(self):
        return self._live

    async def fetch(self, request):
        self.fetch_calls += 1
        if self._mode == "fail_exc":
            raise BackendError("nope")
        if self._mode == "fail_result":
            return ContentResult.failure(self.source_type, "empty")
        return ContentResult(
            success=True,
            source_type=self.source_type,
            backend_used=self.name,
            text="ok-" + self.name,
        )


def _registry(*backends):
    reg = ContentSourceRegistry()
    reg.register_chain(
        ContentSourceChain(source="web_search", source_type=SourceType.WEB_SEARCH, backends=list(backends))
    )
    return reg


@pytest.mark.asyncio
async def test_first_success_wins():
    primary, fallback = StubBackend("a"), StubBackend("b")
    reg = _registry(primary, fallback)
    res = await reg.fetch("web_search", ContentRequest(query="q"))
    assert res.success and res.backend_used == "a"
    assert fallback.fetch_calls == 0


@pytest.mark.asyncio
async def test_falls_through_dead_probe():
    dead, alive = StubBackend("a", live=False), StubBackend("b")
    res = await _registry(dead, alive).fetch("web_search", ContentRequest(query="q"))
    assert res.success and res.backend_used == "b"
    assert dead.fetch_calls == 0


@pytest.mark.asyncio
async def test_falls_through_exception_then_result_failure():
    boom, empty, good = StubBackend("a", mode="fail_exc"), StubBackend("b", mode="fail_result"), StubBackend("c")
    res = await _registry(boom, empty, good).fetch("web_search", ContentRequest(query="q"))
    assert res.success and res.backend_used == "c"


@pytest.mark.asyncio
async def test_all_fail_returns_failure_result():
    res = await _registry(StubBackend("a", mode="fail_exc")).fetch("web_search", ContentRequest(query="q"))
    assert res.success is False
    assert res.source_type is SourceType.WEB_SEARCH
    assert "all backends failed" in res.metadata["error"]


@pytest.mark.asyncio
async def test_unknown_source_returns_failure():
    res = await ContentSourceRegistry().fetch("nope", ContentRequest(query="q"))
    assert res.success is False
    assert "unknown source" in res.metadata["error"]


@pytest.mark.asyncio
async def test_probe_result_is_cached(monkeypatch):
    b = StubBackend("a")
    calls = {"n": 0}
    orig = b.probe

    async def counting_probe():
        calls["n"] += 1
        return await orig()

    b.probe = counting_probe
    reg = _registry(b)
    await reg.fetch("web_search", ContentRequest(query="q"))
    await reg.fetch("web_search", ContentRequest(query="q"))
    assert calls["n"] == 1  # second fetch used the cache


@pytest.mark.asyncio
async def test_probe_all_lists_live_backends():
    reg = _registry(StubBackend("a"), StubBackend("b", live=False))
    live = await reg.probe_all()
    assert live == {"web_search": ["a"]}


def test_list_sources():
    reg = _registry(StubBackend("a"), StubBackend("b"))
    assert reg.list_sources() == {"web_search": ["a", "b"]}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest tests/content_reach/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_reach.registry'`

- [ ] **Step 3: Implement `registry.py`**

Create `autobot-backend/content_reach/registry.py`:
```python
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ContentSourceRegistry — probe-cached, circuit-breaker-guarded chain execution (#10932)."""

from __future__ import annotations

import time

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from circuit_breaker import CircuitBreakerOpenError, get_circuit_breaker_manager
from content_reach.base import ContentRequest, ContentResult
from content_reach.chain import ContentSourceChain
from source_attribution import SourceType, track_source

logger = get_logger(__name__)

# Liveness-probe cache TTL, matching provider_registry's 30s convention.
_PROBE_TTL_S = 30.0


class ContentSourceRegistry:
    """Maps content sources to fallback chains and executes them resiliently."""

    def __init__(self) -> None:
        self._chains: dict[str, ContentSourceChain] = {}
        self._probe_cache: dict[str, tuple[float, bool]] = {}

    def register_chain(self, chain: ContentSourceChain) -> None:
        """Register (or overwrite) the chain for a source."""
        self._chains[chain.source] = chain

    def get_chain(self, source: str) -> ContentSourceChain | None:
        """Return the chain for a source, or None."""
        return self._chains.get(source)

    def list_sources(self) -> dict[str, list[str]]:
        """Return {source: [backend names in order]} for all registered sources."""
        return {source: chain.backend_names() for source, chain in self._chains.items()}

    def clear(self) -> None:
        """Remove all chains and cached probes (test helper)."""
        self._chains.clear()
        self._probe_cache.clear()

    async def _is_live(self, backend) -> bool:
        cached = self._probe_cache.get(backend.name)
        now = time.monotonic()
        if cached is not None and now - cached[0] < _PROBE_TTL_S:
            return cached[1]
        try:
            live = await backend.probe()
        except Exception as exc:  # a probe must never crash the registry
            logger.warning("content_reach probe %s raised %s: %s", backend.name, type(exc).__name__, exc)
            live = False
        self._probe_cache[backend.name] = (now, live)
        return live

    async def probe_all(self) -> dict[str, list[str]]:
        """Return {source: [live backend names]} — powers the health probe."""
        result: dict[str, list[str]] = {}
        for source, chain in self._chains.items():
            result[source] = [b.name for b in chain.backends if await self._is_live(b)]
        return result

    async def fetch(self, source: str, request: ContentRequest) -> ContentResult:
        """Run the source's chain primary→fallback and return the first success."""
        chain = self.get_chain(source)
        if chain is None:
            return ContentResult.failure(SourceType.WEB_SEARCH, f"unknown source: {source}")

        chain = chain.reordered()
        request.source = source
        manager = get_circuit_breaker_manager()
        last_detail = "no backend attempted"

        for backend in chain.backends:
            if not await self._is_live(backend):
                last_detail = f"{backend.name}: probe failed"
                continue

            breaker = manager.get_breaker(f"content_reach:{backend.name}")
            try:
                result = await breaker.call_async(backend.fetch, request)
            except CircuitBreakerOpenError:
                last_detail = f"{backend.name}: circuit open"
                continue
            except Exception as exc:
                last_detail = f"{backend.name}: {type(exc).__name__}: {exc}"
                self._probe_cache.pop(backend.name, None)  # force re-probe after a live failure
                continue

            if result.success:
                track_source(
                    chain.source_type,
                    result.text[:500],
                    reliability=result.reliability,
                    metadata={
                        "backend": backend.name,
                        "url": result.url,
                        "source": source,
                        **result.metadata,
                    },
                )
                return result

            last_detail = f"{backend.name}: unsuccessful result"

        return ContentResult.failure(chain.source_type, f"all backends failed ({last_detail})")


get_content_source_registry = lazy_singleton(ContentSourceRegistry)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest tests/content_reach/test_registry.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-10932
git add autobot-backend/content_reach/registry.py autobot-backend/tests/content_reach/test_registry.py
git commit -m "feat(content-reach): ContentSourceRegistry probe-cached CB-guarded execution (#10932)"
```

---

### Task 1.4: New `SourceType` values for content attribution

**Files:**
- Modify: `autobot-backend/source_attribution.py:23-35` (add enum members) and `:70-81` (add icons)
- Test: `autobot-backend/tests/content_reach/test_source_types.py`

**Interfaces:**
- Produces: `SourceType.YOUTUBE`, `SourceType.REDDIT`, `SourceType.WEB_PAGE`, `SourceType.SOCIAL`

- [ ] **Step 1: Write the failing test**

Create `autobot-backend/tests/content_reach/test_source_types.py`:
```python
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from datetime import datetime, timezone

import pytest

from source_attribution import Source, SourceReliability, SourceType


@pytest.mark.parametrize("member,value", [
    ("YOUTUBE", "youtube"),
    ("REDDIT", "reddit"),
    ("WEB_PAGE", "web_page"),
    ("SOCIAL", "social"),
])
def test_new_source_types_exist(member, value):
    assert SourceType[member].value == value


def test_new_source_types_have_citation_icons():
    for member in ("YOUTUBE", "REDDIT", "WEB_PAGE", "SOCIAL"):
        src = Source(
            type=SourceType[member],
            reliability=SourceReliability.MEDIUM,
            content="c",
            timestamp=datetime.now(tz=timezone.utc),
            metadata={"name": "x"},
        )
        # Non-default icon means the type was added to the icon map.
        assert not src.format_citation().startswith("📋")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest tests/content_reach/test_source_types.py -v`
Expected: FAIL — `KeyError: 'YOUTUBE'`

- [ ] **Step 3: Add the enum members**

In `autobot-backend/source_attribution.py`, extend the `SourceType` enum (after `FILE_CONTENT = "file_content"` at line 35):
```python
    FILE_CONTENT = "file_content"
    YOUTUBE = "youtube"  # #10932 content reach
    REDDIT = "reddit"  # #10932 content reach
    WEB_PAGE = "web_page"  # #10932 content reach
    SOCIAL = "social"  # #10932 content reach
```

- [ ] **Step 4: Add citation icons**

In `format_citation`'s `source_icon` dict (after the `SourceType.FILE_CONTENT: "📄",` line), add:
```python
            SourceType.FILE_CONTENT: "📄",
            SourceType.YOUTUBE: "📺",
            SourceType.REDDIT: "👽",
            SourceType.WEB_PAGE: "🌐",
            SourceType.SOCIAL: "💬",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest tests/content_reach/test_source_types.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-10932
git add autobot-backend/source_attribution.py autobot-backend/tests/content_reach/test_source_types.py
git commit -m "feat(content-reach): add YOUTUBE/REDDIT/WEB_PAGE/SOCIAL source types (#10932)"
```

---

### Task 1.5: `doctor`-style health probe

**Files:**
- Modify: `autobot-backend/api/system_health.py:47-53` (add `CONTENT_REACH` to `KnownProbes`)
- Create: `autobot-backend/content_reach/health.py`
- Test: `autobot-backend/tests/content_reach/test_health.py`

**Interfaces:**
- Consumes: `api/system_health.{ComponentHealth, KnownProbes, register_health_probe}`, `content_reach.registry.get_content_source_registry`
- Produces: async `probe_content_reach(request=None) -> ComponentHealth` registered under `KnownProbes.CONTENT_REACH`. Status: `ok` if every source has ≥1 live backend; `down` if none registered or all sources dead; `degraded` if some (not all) sources dead. `data={"sources": {...}, "live": {...}}`.

- [ ] **Step 1: Add `CONTENT_REACH` to `KnownProbes`**

In `autobot-backend/api/system_health.py`, add to the `KnownProbes` enum (after `PRICING = "pricing"  # GH#6480`):
```python
    PRICING = "pricing"  # GH#6480
    CONTENT_REACH = "content_reach"  # #10932
```

- [ ] **Step 2: Write the failing test**

Create `autobot-backend/tests/content_reach/test_health.py`:
```python
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
import pytest

from content_reach.base import ContentBackend
from content_reach.chain import ContentSourceChain
from content_reach.health import probe_content_reach
from content_reach.registry import get_content_source_registry
from source_attribution import SourceType


class _B(ContentBackend):
    def __init__(self, name, live):
        self.name = name
        self.source_type = SourceType.WEB_SEARCH
        self._live = live

    async def probe(self):
        return self._live

    async def fetch(self, request):
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _clean_registry():
    reg = get_content_source_registry()
    reg.clear()
    yield
    reg.clear()


@pytest.mark.asyncio
async def test_down_when_no_sources():
    ch = await probe_content_reach(None)
    assert ch.name == "content_reach"
    assert ch.status == "down"


@pytest.mark.asyncio
async def test_ok_when_all_sources_have_live_backend():
    reg = get_content_source_registry()
    reg.register_chain(ContentSourceChain("web_search", SourceType.WEB_SEARCH, [_B("a", True)]))
    ch = await probe_content_reach(None)
    assert ch.status == "ok"
    assert ch.data["live"] == {"web_search": ["a"]}


@pytest.mark.asyncio
async def test_degraded_when_some_source_dead():
    reg = get_content_source_registry()
    reg.register_chain(ContentSourceChain("web_search", SourceType.WEB_SEARCH, [_B("a", True)]))
    reg.register_chain(ContentSourceChain("youtube", SourceType.YOUTUBE, [_B("b", False)]))
    ch = await probe_content_reach(None)
    assert ch.status == "degraded"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest tests/content_reach/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_reach.health'`

- [ ] **Step 4: Implement `health.py`**

Create `autobot-backend/content_reach/health.py`:
```python
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Content Reach health probe — AutoBot's `doctor` analog for content sources (#10932)."""

from __future__ import annotations

from fastapi import Request

from api.system_health import ComponentHealth, KnownProbes, register_health_probe
from content_reach.registry import get_content_source_registry


@register_health_probe(KnownProbes.CONTENT_REACH)
async def probe_content_reach(request: Request | None = None) -> ComponentHealth:
    """Report per-source/per-backend liveness for content reach."""
    registry = get_content_source_registry()
    sources = registry.list_sources()
    name = KnownProbes.CONTENT_REACH.value

    if not sources:
        return ComponentHealth(name=name, status="down", detail="no content sources registered")

    live = await registry.probe_all()
    dead_sources = [s for s, live_backends in live.items() if not live_backends]

    if not dead_sources:
        status = "ok"
    elif len(dead_sources) < len(sources):
        status = "degraded"
    else:
        status = "down"

    return ComponentHealth(
        name=name,
        status=status,
        detail=f"{len(sources)} sources; dead: {dead_sources or 'none'}",
        data={"sources": sources, "live": live},
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest tests/content_reach/test_health.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Run the full foundation suite + import smoke**

Run: `cd autobot-backend && python -m pytest tests/content_reach/ -v`
Expected: PASS (all foundation tests green)

Run: `cd autobot-backend && python -c "import content_reach.base, content_reach.chain, content_reach.registry, content_reach.health; print('imports ok')"`
Expected: `imports ok`

- [ ] **Step 7: Commit**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-10932
git add autobot-backend/api/system_health.py autobot-backend/content_reach/health.py autobot-backend/tests/content_reach/test_health.py
git commit -m "feat(content-reach): doctor-style health probe for content sources (#10932)"
```

---

## Wiring note (deferred to Task 7)

The health probe in `health.py` only registers when the module is imported. Actual boot-time registration (importing `content_reach.health`) and agent-tool registration land in **Task 7** of the umbrella, alongside the first real backends (Tasks 2–6). Task 1 is import-clean and fully unit-tested standalone; it does not change runtime behavior until a source chain is registered.

## Self-Review

**Spec coverage:**
- Spec §3 file layout → Tasks 1.1–1.5 create `base`/`chain`/`registry`/`health` + `SourceType` edits. `sources/` and `backends/browser.py` are later umbrella tasks (2–6), correctly out of scope for Task 1. ✓
- Spec §4.1 ContentBackend ABC → Task 1.1 ✓
- Spec §4.2 ContentSourceChain + env reorder → Task 1.2 ✓
- Spec §4.3 registry probe-cache + CB-guard + all-fail structured result → Task 1.3 ✓
- Spec §4.5 health probe (`doctor` analog) → Task 1.5 ✓
- Spec §6 new SourceType values + fallback-on-any-failure → Tasks 1.4 + 1.3 ✓
- Spec §4.4 BrowserBackend, §4.6 agent tools, §7 deps → later umbrella tasks (noted, not gaps). ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows full code. ✓

**Type consistency:** `ContentResult.failure(source_type, detail)`, `ContentSourceChain(source, source_type, backends)`, `registry.fetch(source, request)`, `registry.probe_all()`, `get_content_source_registry()`, `KnownProbes.CONTENT_REACH`, `ComponentHealth(name,status,detail,data)` — signatures identical across Tasks 1.1→1.5. ✓
