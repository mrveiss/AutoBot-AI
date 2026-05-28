# Agent Belief State — Architecture Design

**Status**: Proposed  
**Date**: 2026-05-27  
**Author**: CTO (MVA-1405)  
**Parent**: MVA-1401 / GH#6629  

---

## 1. Problem Statement

`TaskContext` in `autobot-backend/agent_loop/types.py` is a **pure execution log**. It records what happened (tools called, errors, think results) but not what the agent *learned*. Every iteration the agent must re-derive facts from raw tool history, leading to three failure modes:

| Failure mode | Example | Cost |
|---|---|---|
| **Hallucinated re-query** | Agent reads port from file, then asks about it again two iterations later | +1–3 redundant LLM calls |
| **Contradiction blindness** | `read_file` returns port 8080; later `run_command` returns port 3000; agent doesn't notice | Wrong downstream decisions |
| **Token waste** | Full tool-output history passed to think/LLM context on every iteration | Linear token growth per task |

The fix is to add a **belief state layer** alongside the execution log: a typed, keyed dictionary of `Assertion` objects that summarises what the agent currently believes is true, where each belief is grounded in specific tool executions.

---

## 2. Proposed Data Model

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ToolExecutionRef:
    """Pointer to the tool execution that produced or refuted a fact."""
    tool_name: str
    iteration: int
    call_hash: str          # Same hash used by repetition-detection


@dataclass
class Assertion:
    """A fact the agent believes to be currently true."""
    key: str                          # e.g. "run_command:port/backend"
    value: Any                        # Extracted value, typed by extractor
    confidence: float                 # 0.0–1.0
    sources: list[ToolExecutionRef]   # All evidence for this belief
    confirmed_at: datetime
    refuted_at: datetime | None = None
    refutation_source: ToolExecutionRef | None = None

    @property
    def is_active(self) -> bool:
        """False when the assertion has been contradicted."""
        return self.refuted_at is None


@dataclass
class ContradictionRecord:
    """Logged when a new extraction contradicts an existing active assertion."""
    key: str
    prior_value: Any
    prior_confidence: float
    new_value: Any
    new_confidence: float
    iteration: int
    resolution: str          # "updated" | "suppressed" | "surfaced_to_think"
    timestamp: datetime = field(default_factory=lambda: __import__('autobot_shared.time_utils', fromlist=['now_utc']).now_utc())
```

### TaskContext additions (additive, no breaking changes)

```python
@dataclass
class TaskContext:
    # ... all existing fields unchanged ...

    # Belief state (Phase 1 addition)
    assertions: dict[str, Assertion] = field(default_factory=dict)
    contradictions: list[ContradictionRecord] = field(default_factory=list)
```

The `tools_executed` list is **kept unchanged** — all existing consumers continue to work.

---

## 3. Open Question Decisions

### Q1 — Assertion key namespace

**Decision: dotted reverse-DNS prefix with path suffix.**

Format: `{tool_prefix}/{discriminator}`

| Tool | Example key | What it identifies |
|---|---|---|
| `read_file` | `read_file:/etc/hosts` | Content status of a specific file |
| `web_search` | `web_search:port-forwarding-docker` | Search topic (slugified query) |
| `run_command` | `run_command:exit_code/git-status` | Exit code of a specific command class |
| `run_command` | `run_command:port/backend` | Detected running port |

**Rationale**: forward slash separates the "tool space" from the "entity identity." No URI overhead. Flat enough to query with `assertions.get("run_command:port/backend")`. Structured enough to iterate by namespace with `startswith("run_command:")`.

**Rejected alternatives**:
- Flat strings (`"backend_port"`) — collide across tools without convention enforcement
- URIs (`tool://read_file//etc/hosts`) — unnecessary parsing complexity for v1
- Nested dicts — harder to index, serialize, and patch

### Q2 — Extractor mechanism

**Decision: per-tool rule-based extractors for v1; LLM extractor deferred to v2.**

Each tool that produces structured facts registers a synchronous extractor function:

```python
ExtractorFn = Callable[[str, dict[str, Any]], list[tuple[str, Any, float]]]
# Returns: list of (key, value, confidence) tuples
```

v1 extractors (rule-based, no LLM cost):

| Tool | Extracted facts | Method |
|---|---|---|
| `read_file` | File exists/missing, file content hash, detected port number | Regex on output |
| `run_command` | Exit code, stdout snippet, port number from `lsof`/`ss` output | Regex on stdout |
| `web_search` | Topic answered (bool), key entities | Keyword scan on snippet |

**Rationale** (Boring Technology lens): Rule-based extraction for the 3 most common tools costs zero extra tokens. An LLM extractor could extract richer facts but doubles per-iteration cost and adds latency. This can be layered on in v2 once we have the container and benchmarks.

**Rejected alternatives**:
- Universal LLM extractor — high token cost, cannot ship as default for all tasks
- Hybrid v1 — adds conditional-extractor complexity before we have benchmark evidence

### Q3 — Contradiction handling

**Decision: update-by-default with threshold-gated think surfacing.**

Algorithm (runs inside the belief-state updater after each extractor produces new facts):

```
for each new (key, value, confidence) from extractor:
    if key not in assertions:
        INSERT new Assertion
    elif assertions[key].value == value:
        UPDATE confirmed_at, merge sources  # same fact reconfirmed
    else:
        RECORD ContradictionRecord
        if abs(new_confidence - old_confidence) > CONTRADICTION_SURFACE_THRESHOLD (0.3):
            queue_think(ASSUMPTION_CHECK, context=contradiction_summary)
        if new_confidence >= assertions[key].confidence:
            REPLACE assertion with new value
        else:
            SUPPRESS new value, mark refuted_at on incoming
```

**Rationale**: Halting on any contradiction is too fragile — tools routinely produce slightly different outputs (timestamps, log lines). Update-by-default gives agents the latest known-good value. Surfacing high-delta contradictions to the existing `ASSUMPTION_CHECK` think category keeps humans in the loop on meaningful conflicts without a new code path.

**Rejected alternatives**:
- Always halt on contradiction — too fragile, blocks long tasks
- Always pick latest without surfacing — misses genuine environment contradictions
- New `CONTRADICTION` think category — unnecessary; `ASSUMPTION_CHECK` covers it

### Q4 — Persistence

**Decision: session-scoped only for v1.**

`assertions` and `contradictions` live on `TaskContext`, which persists for the lifetime of one task run. They are not serialized to Redis or the database in v1.

Cross-session persistence is deferred until:
1. Benchmark shows belief state provides value within sessions
2. Key-namespace design is stable enough that old keys don't become stale

**Migration path to cross-session**: serialize `assertions` dict as a JSON column on the task record; add TTL-based expiry per assertion.

### Q5 — Extraction cost

**Decision: rule-based extraction is sufficient for v1.**

No additional LLM calls are required. Rule-based extractors run synchronously in O(len(output)) time. Token overhead is zero — extracted facts are *summarised into* the think prompt, replacing verbose tool-output history.

The net token effect is expected to be **negative** (fewer tokens per think call) because the compressed `assertions` dict replaces `tools_executed` list expansion in the completion think prompt.

### Q6 — Backward compatibility

**Decision: fully additive — no migration, no breakage.**

Changes are:
1. New `assertions` and `contradictions` fields on `TaskContext` with `field(default_factory=...)` defaults
2. New `belief_state.py` module — standalone, no imports from `loop.py`
3. New `extractors/` package — called from one integration point in `loop.py` after tool execution
4. New think-tool variant — the existing `_think_before_completion` receives a new optional parameter; defaults to old behavior if `assertions` is empty

All existing callers of `TaskContext`, `ThinkTool`, and `loop.py` continue to work unchanged.

---

## 4. Architecture

```
agent_loop/
├── types.py                    ← add Assertion, ContradictionRecord, ToolExecutionRef
│                                  add assertions/contradictions fields to TaskContext
├── belief_state.py             ← NEW: BeliefStateUpdater class
│                                  - update(task_ctx, tool_name, tool_output, call_hash, iteration)
│                                  - _handle_contradiction(...)
│                                  - _maybe_queue_think(...)
├── extractors/
│   ├── __init__.py             ← registry: {tool_name: ExtractorFn}
│   ├── read_file.py            ← extracts: file exists, content hash, port refs
│   ├── run_command.py          ← extracts: exit code, port number, command class
│   └── web_search.py           ← extracts: topic answered, key entity mentions
└── loop.py                     ← two integration points:
                                   1. after tool execution → call BeliefStateUpdater.update()
                                   2. in _think_before_completion → include assertions summary
```

### Integration point 1 — after tool execution

In `_execute_iteration_phases`, after each tool result is recorded:

```python
# existing: self._current_context.record_observation(result, iteration)
# new (additive):
self._belief_updater.update(
    ctx=self._current_context,
    tool_name=tool_name,
    tool_output=result,
    call_hash=call_hash,
    iteration=self._iteration_count,
)
```

### Integration point 2 — think_before_completion

```python
context = f"""
Task: {self._current_context.description}
Iterations: {self._iteration_count}
Tools executed: {len(self._current_context.tools_executed)}
Errors: {len(self._current_context.errors)}
Duration: {self._current_context.get_duration_ms():.0f}ms

Active beliefs ({len(active)}):
{belief_summary}
"""
```

Where `belief_summary` is a compact rendering of active `assertions` (key → value @ confidence), capped at 20 entries to bound token cost.

---

## 5. Benchmark Plan

**Goal**: measure whether belief state reduces iterations, token cost, and hallucinated re-queries.

**Setup**: 5 representative task templates run with and without belief state (A/B via `AgentLoopConfig.belief_state_enabled: bool = False`).

| # | Task | Why representative |
|---|---|---|
| 1 | Find backend port from process list + config file | Exercises port extraction, cross-tool confirmation |
| 2 | Read multiple files, summarize findings | File-exists assertions, content-hash dedup |
| 3 | Run git commands, report branch state | Exit-code assertions, command repetition |
| 4 | Web search 3 topics, answer composite question | Search-topic assertions, reuse suppression |
| 5 | Multi-step debug: find error, read logs, fix | Exercises contradictions when logs rotate |

**Metrics** (per task, per variant):
- Total iterations to completion
- Total input tokens to LLM (counted from event log)
- Hallucinated re-query count (tool called with identical args after result already in assertions)
- Contradiction events triggered
- Think calls triggered (total, belief-state-triggered)

**Threshold for "ship"**: ≥2 of 5 tasks show ≥10% token reduction AND no regression on hallucinated-re-query rate.

---

## 6. Files Affected

| File | Change type |
|---|---|
| `autobot-backend/agent_loop/types.py` | Additive: 3 new dataclasses + 2 new fields on `TaskContext` |
| `autobot-backend/agent_loop/belief_state.py` | New file |
| `autobot-backend/agent_loop/extractors/__init__.py` | New file |
| `autobot-backend/agent_loop/extractors/read_file.py` | New file |
| `autobot-backend/agent_loop/extractors/run_command.py` | New file |
| `autobot-backend/agent_loop/extractors/web_search.py` | New file |
| `autobot-backend/agent_loop/loop.py` | 2 integration points (~10 lines each) |
| `docs/architecture/agent-belief-state.md` | This document |

---

## 7. Decision Gate

After the benchmark:

| Outcome | Criterion | Action |
|---|---|---|
| **Ship** | ≥2/5 tasks: ≥10% token reduction, no hallucination regression | Promote to main, enable by default |
| **Scope-down** | Mixed results; clear wins on specific tool types only | Enable per-tool, disable globally |
| **Shelve** | No measurable improvement OR latency regression > 5ms/iter | Close GH#6629, document findings |

Decision will be recorded as an addendum to this document after benchmark results are in.

---

## 8. Related

- GH#6629 — source specification  
- GH#6469 — goal ancestry (adjacent structural state on `TaskContext`)  
- GH#6626 — confidence-based abstention (uses `ThinkResult.confidence`, adjacent)  
- GH#6627 — stagnation detector (uses `ObservationFingerprint`, adjacent)  
- MVA-1401 — parent architecture roadmap issue  

---

*This document is Phase 1 of the belief-state work. Implementation is gated on this design being accepted. The benchmark phase (Section 5) must run before a ship/scope-down/shelve decision is recorded.*
