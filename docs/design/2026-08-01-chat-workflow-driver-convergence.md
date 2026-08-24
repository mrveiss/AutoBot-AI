# Chat-workflow driver convergence — scope and evidence (#12652)

**Status:** decision document, no code changes
**Date:** 2026-08-01
**Issue:** #12652 (umbrella #12645)

## Why this document exists

#12652 describes "parallel chat-workflow drivers (`async_chat_workflow` +
hand-rolled loop + LangGraph)" with "governance gates enforced twice", and asks
for scope before any convergence. This sits on the live chat path — the largest
blast radius of anything remaining in #12645 — so the issue's own instruction
was scope-first.

Measured on `Dev_new_gui` at `a6d7aa1ce`.

**The headline finding: these are not three parallel drivers.** One of them
calls another. A fourth orchestration layer exists that neither issue mentions.
And the duplicated governance gate is real, but it is not where the issue
points.

## What actually runs

`api/chat.py` reaches exactly one entry point:

```python
# autobot-backend/api/chat.py:124
from chat_workflow import ChatWorkflowManager
manager = ChatWorkflowManager()
```

Everything else is reached from there.

| module | lines | role |
|---|---|---|
| `chat_workflow/manager.py` | 3608 | **the live driver.** Owns a hand-rolled continuation loop *and* invokes the LangGraph |
| `chat_workflow/tool_handler.py` | 3584 | mixin on the manager — tool dispatch, approvals, web search |
| `chat_workflow/graph.py` | 1617 | LangGraph `StateGraph`, **driven by the manager**, not independently |
| `async_chat_workflow.py` | 429 | `AsyncChatWorkflow` + `WorkflowMessage` |
| `orchestration/graph_runner.py` | 742 | `AutoBotGraph` — an in-house `StateGraph` clone intended to replace LangGraph |
| `chat_workflow/session_handler.py` | 332 | consumes `AsyncChatWorkflow` |

### The manager both loops and delegates

`manager.py` runs its own iteration loop:

```python
# manager.py:2820
for iteration in range(1, self.MAX_CONTINUATION_ITERATIONS + 1):
```

*and* compiles and invokes the LangGraph, from two separate call sites:

```python
# manager.py:3430 and manager.py:3554
from .graph import get_compiled_graph
graph = await get_compiled_graph(self)
...
result = await graph.ainvoke(initial_state, config=config)   # :3476
```

So `graph.py` is **not a competing driver**. It is a component the manager
calls, on some paths and not others. `get_compiled_graph` has no production
caller outside `manager.py`.

This matters for scoping: "retire graph.py in favour of the manager" is not a
migration between two rival implementations. It is a decision about **which of
the manager's two internal execution strategies survives**, and the graph's
nodes would have to be folded back into a 3608-line file that already has a
loop.

### `async_chat_workflow.py` is two things wearing one name

- **`WorkflowMessage`** — the message type imported by `manager.py:23`,
  `tool_handler.py:22` and `graph.py:278`. Load-bearing for all three.
- **`AsyncChatWorkflow`** — an actual driver, imported by
  `session_handler.py:14` and lazily at `manager.py:313`.

Retiring "async_chat_workflow" as a *driver* is therefore not the same as
deleting the module. `WorkflowMessage` is a shared contract and would need a
home first — most naturally `chat_workflow/models.py`, which already holds
`WorkflowSession`.

### A fourth layer nobody has mentioned

`orchestration/graph_runner.py` builds `AutoBotGraph`, an in-house
`StateGraph`-compatible builder, and documents a migration path *away* from
LangGraph:

> `chat_workflow/graph.py` currently builds a LangGraph `StateGraph`. That graph
> can be migrated in three steps once this module stabilises: … Replace
> `builder = StateGraph(ChatState)` with `builder = AutoBotGraph(ChatState)` …
> Remove the `AsyncRedisSaver` checkpointer wiring — `GraphRunner` handles
> checkpointing internally.

It also notes the `interrupt()`-based approval mechanism would be replaced by
`GraphRunner.pause()`/`resume()`, tracked in **#6826**, and that **#3228 was
closed prematurely**.

**Any decision to make `graph.py` canonical collides with this**, because the
stated plan is to replace its `StateGraph` with `AutoBotGraph`. Choosing
LangGraph as the target without reconciling `graph_runner.py` would mean
converging onto a layer that another workstream intends to swap out.

## The duplicated governance gate — the real one

The issue says governance gates are "enforced twice". They are, but the two
implementations are **structurally different**, not copies:

**Path A — the graph's node-based gate** (`graph.py`)

```
generate_response
  -> _tool_call_needs_approval(tc, ctx)        # :488, sets tc["needs_approval"]
  -> route_after_generation                     # :1411 any(tc["needs_approval"])
  -> request_approval                           # :895 node, interrupt()-based
  -> execute_tools                              # :942
```

**Path B — the manager/tool_handler message-based gate**

```
tool_handler._approval_category_for(tool_name, declared)   # :629
tool_handler._emit_approval_required / _emit_approval_received
manager._handle_tool_message_types                          # :2213
  -> tool_msg.type == "command_approval_request"            # :2227
  -> has_pending_approval                                   # :2225
```

Path B additionally carries an **auto-approval allowlist of read-only tools**
(`tool_handler.py:52`, GH#11568/#11662) and maps approval *categories* declared
on a work item (GH#11160). Path A has neither concept.

**This is the finding that should drive the decision.** A policy change — adding
a tool to the approval set, changing what auto-approves — applied to one path
does not reach the other. That is the same failure mode as #12925's denial-audit
gap and #12924's inert session revocation: two mechanisms, one updated.

**Not yet measured:** which user-visible flows take Path A versus Path B, and
whether any flow can reach tool execution through a path where neither gate
fires. That is the single highest-value follow-up measurement and it needs a
running system — it cannot be settled by reading the call graph.

## Options

### A. Manager is canonical; fold the graph's nodes into it

- **For:** it is what already serves production traffic; no rewrite of the live
  path; `graph.py`'s 1617 lines collapse.
- **Against:** grows a 3608-line file that already has a hand-rolled loop, and
  discards LangGraph's checkpointing/interrupt machinery — which is what
  `request_approval` is built on. Path A's approval semantics would have to be
  re-expressed in Path B.
- **Cost:** high, and concentrated in the riskiest file.

### B. Graph is canonical; migrate the manager's loop into nodes

- **For:** the better long-term shape if graph orchestration is the intent;
  approval becomes a first-class node rather than a message type.
- **Against:** rewrites the live chat path. **And it collides with
  `graph_runner.py`**, whose documented plan is to replace LangGraph's
  `StateGraph` with `AutoBotGraph`. Converging onto `StateGraph` now means
  migrating twice.
- **Cost:** highest. Should not start before #6826 / `graph_runner.py`'s status
  is settled.

### C. Converge the governance gate only; leave the drivers alone

- **For:** targets the actual defect — one approval policy, enforced once — at a
  fraction of the risk. Independent of whichever driver eventually wins, and
  strictly required by both A and B anyway.
- **Against:** does not reduce the driver count, so #12652 as literally worded
  would remain partly open.
- **Cost:** moderate and bounded, concentrated in policy code rather than
  control flow.

### D. Do nothing under #12645; re-file as its own epic

- **For:** honest about scale. This is ~10,300 lines across six modules with a
  fourth orchestration layer mid-flight; it is not an internal-fork cleanup.
- **Against:** leaves a known duplicated security-relevant gate unaddressed
  unless C is filed separately.

## Recommendation

**C first, then decide A vs B separately — and not before `graph_runner.py`'s
status is resolved.**

The duplicated approval gate is a real, security-relevant defect that exists
today and is independent of the driver question. Both A and B require fixing it
anyway. Doing it first removes the risk from whichever driver decision follows,
and it is the only part of this issue that is bounded.

The driver convergence itself is not an internal-fork cleanup and does not
belong under #12645's contract. It should be re-filed as its own epic with
#6826 and `graph_runner.py` in scope, because choosing LangGraph as canonical
while another workstream plans to replace `StateGraph` would be converging onto
a moving target.

## What must be measured before A or B

1. Which flows take Path A vs Path B, on a running system.
2. Whether any flow reaches tool execution with neither gate firing.
3. Whether `graph_runner.py` / #6826 is live or dormant — it decides whether B
   converges onto LangGraph or onto `AutoBotGraph`.
4. Whether `AsyncChatWorkflow` (as opposed to `WorkflowMessage`) has live
   traffic via `session_handler.py`.

---

**Author:** mrveiss
**Copyright:** © 2025 mrveiss
