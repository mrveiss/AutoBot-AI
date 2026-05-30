# Agent Belief State Architecture

**Status:** Phase 1 prototype  
**Issue:** [GH#6629](https://github.com/mrveiss/AutoBot-AI/issues/6629) (MVA-1644)  
**Related:** #6627 (stagnation detection), #6626 (confidence reasoning), #6628 (error-severity retry)

---

## Problem

`TaskContext` records what the agent *did* (execution log). But the agent's reasoning depends on what it *believes is true* about the world, which must be re-derived from raw `(tool, args, result)` history every iteration.

This is wasteful and fragile:

- Agent reads `config.json`, sees `port: 8001` in iteration 2, but asks "what port is the backend on?" in iteration 5.
- Agent confirms file exists (`file.txt`), but a later iteration assumes it doesn't.
- Multiple tool calls implicitly contradict each other; the agent never notices or resolves.

The agent has no unified view of *established facts*—only fragments scattered across tool history.

## Solution: Separate Execution Log from Belief State

**Execution log** (unchanged): what happened in the task
- `tools_executed`: list of tool names
- `errors`: list of errors encountered
- `user_messages`: user feedback
- `think_history`: reasoning steps
- `tool_call_hashes`: call counts for repetition detection

**Belief state** (new): what the agent knows to be true
- `assertions`: dict[str, Assertion] — keyed beliefs with confidence and sources
- `contradictions`: list[ContradictionRecord] — detected inconsistencies

---

## Design Decisions (GH#6629)

### 1. Co-locate on TaskContext, Clearly Grouped

**Execution log fields** + **Belief state fields** live on TaskContext without requiring separate objects. This makes the separation obvious while keeping the single source of truth.

### 2. Assertion Key Namespace

Canonical fact keys, not tool names. E.g., `read_file:config.json:exists` instead of coupling beliefs to which tool extracted them.

### 3. Per-Tool Rule-Based Extractors (Phase 1)

Registered tools have Extractor subclasses that emit `(key, value, confidence)` triples from tool output.

Phase 1 covers: read_file, web_search, run_command. LLM-based extraction for unregistered tools deferred to Phase 2 (cost analysis: rule-based is ~0ms/$0; LLM adds ~150ms/~$0.001 per call).

### 4. Contradiction Handling

Refute-in-place, log, surface (do not halt):
- Log all contradictions
- Surface high-confidence deltas to think prompt
- Let agent reason naturally

### 5. BeliefState Query API

Wrap assertions/contradictions on TaskContext. Provide query and summary methods for thinking.

```python
class BeliefState:
    def get(self, key: str) -> Assertion | None
    def get_value(self, key: str, default: Any = None) -> Any
    def active_assertions(self) -> list[Assertion]
    def summary(self, max_contradictions: int = 3) -> str  # for think prompts
```

### 6. Inject Belief Summary into Think Prompts

Before thinking, give agent established facts:

```
## Established Beliefs
- `read_file:config.json:exists` = True  (confidence: 100%)
- `read_file:config.json:port` = 8001  (confidence: 95%)

## Recent Contradictions (agent should verify)
- `run_command:exit_code:backend-start`: previously 0, now 1 — treat as uncertain
```

---

## Implementation

### TaskContext Fields

```python
# Execution log
task_id: str
tools_executed: list[str]
errors: list[str]
user_messages: list[str]
think_history: list[ThinkResult]
# ...

# Belief state (GH#6629)
assertions: dict[str, Assertion]
contradictions: list[ContradictionRecord]
```

### BeliefStateUpdater

Extracts assertions from tool results and merges into TaskContext:

```python
updater = BeliefStateUpdater()
contradictions = updater.update(ctx, tool_name, tool_output, call_hash, iteration)
```

### BeliefState Wrapper

Query interface for think prompts:

```python
belief_state = BeliefState.from_task_context(ctx)
summary = belief_state.summary()  # human-readable for think injection
```

---

## Summary

**GH#6629 separates execution log from belief state:**
- Execution log: what agent did (tools, errors, messages, history)
- Belief state: what agent knows (assertions with confidence, contradictions)

**Enables:**
- Stagnation detection (novelty scoring against established facts)
- Confidence reasoning (agent sees which facts are certain vs. uncertain)
- Loop control (grounded reasoning without re-parsing history)

**Phase 2 (future):**
- LLM-based extraction for unregistered tools
- Belief persistence across tasks
- Cross-task belief inheritance
