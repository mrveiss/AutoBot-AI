---
name: dead-code-review
description: Use when removing, flagging, or evaluating any code that appears unused, unreferenced, or commented out — before deletion
---

# Dead Code Review

**Core principle:** Unused code is not the same as unwanted code. Code exists for a reason — find the reason before removing it.

## The Three Categories

Before touching any dead-looking code, classify it:

| Category | Definition | Action |
|----------|-----------|--------|
| **Truly dead** | Proven never called, no open issue, no git context suggesting intent | Remove — with documented justification |
| **Unwired** | Implemented but not yet connected (no caller, no route, no event hook) | Create **implementation gap** issue. Do NOT delete. |
| **Future phase** | Exists for a planned feature or phase not yet started | Note the issue/comment, leave it. Do NOT delete. |

**When in doubt → Unwired. Create an issue.**

## Step 1 — Check git history first

```bash
# Who wrote it and when — read the commit message for intent
git log --all --follow -p <file> | head -60

# Search commits mentioning this function/class
git log --all --oneline --grep="<function_name>"

# When was it last touched?
git blame <file> | grep -n "<function_name>"
```

If the commit message says "add X endpoint" or "implement Y for phase 3" — this is **unwired or future-phase**, not dead.

## Step 2 — Search for references

```bash
# Is anything calling or importing it?
grep -r "<function_name>" --include="*.py" --include="*.ts" --include="*.vue" .

# Is it referenced in tests, even if test is skipped?
grep -r "<function_name>" --include="test_*.py" --include="*.spec.ts" .

# Is it referenced in any issue or TODO?
grep -r "<function_name>" --include="*.md" docs/
gh issue list --search "<function_name>" --state all
```

Zero references ≠ safe to delete. A function waiting to be wired up will have zero callers.

## Step 3 — Check for wiring signals

Look for these patterns that indicate the code is **unwired, not dead**:

```python
# Signal: Function exists but no route registered
async def get_analytics_summary(...):  # no @router.get("/analytics/summary")

# Signal: Service method exists but never called from handlers
class ConfigRevisionService:
    async def record_revision(self, ...):  # no caller in api/ layer

# Signal: Event handler registered nowhere
async def on_agent_complete(event):  # never passed to event_bus.subscribe()

# Signal: Feature flag gates it
if feature_flags.get("new_search_ui"):
    # This whole block appears dead until flag is enabled
```

**Any of these → Unwired. Create an issue.**

## Step 4 — Classify and act

### If Truly Dead
Must satisfy ALL of these before deleting:
- [ ] No callers found anywhere in codebase
- [ ] Git history shows no feature intent (e.g., "cleanup", "remove old code")
- [ ] No open GitHub issue referencing the functionality
- [ ] No TODO/FIXME comment nearby suggesting wiring intent
- [ ] Removing it does not break any tests

Then document the removal:
```bash
git commit -m "chore: remove dead <name> — no callers, confirmed via grep + git log (#NNNN)"
```

### If Unwired → Implementation Gap Issue

Unwired code is a feature that was built but never connected. This is an **implementation gap** — not a cleanup task, not an enhancement, not tech debt. It needs to be wired up to deliver the intended functionality.

```bash
gh issue create \
  --title "impl gap: wire up <name> — <what it does>" \
  --body "## Implementation Gap
<function/class/module> in <file:line> is fully implemented but has no callers/routes/subscribers.

## What it does
<brief description from reading the code and git history>

## What is missing to complete it
- [ ] <route registration / event subscription / frontend call / lifecycle hook / etc.>
- [ ] <any other wiring needed>

## Location
\`<file>\` line <N> — \`<function_or_class_name>\`

## Discovered During
Working on #<original-issue>

## Evidence it was intentional
<git commit message / comment / related issue that shows this was planned>" \
  --label "enhancement,backend,priority: medium"
```

Then report:
```
Created #<number>: implementation gap for <name>.
This code is complete but unwired — leaving it in place.
Should I: a) Wire it now  b) Finish current issue first  c) Leave for later
```

### If Future Phase
Leave the code. Add a comment if context is unclear:
```python
# TODO(#NNNN): Wire this up in phase X — see issue for details
```

## Red Flags — STOP before deleting

- "This function has no callers" → Check git history first
- "This import is unused" → Check if it's a re-export
- "This class is never instantiated" → Check for dynamic instantiation or factory patterns
- "This file is never imported" → Check for dynamic loading or string-based references
- "autoflake/linter flagged it" → Linters don't understand intent. Investigate manually.

## Common Patterns in AutoBot

```python
# Pattern: Service implemented, not yet registered in app lifecycle
class ProcessAdapterService:  # exists but start()/stop() not called in lifespan

# Pattern: API endpoint implemented, not registered on router
async def get_config_revision(...):  # missing @router.get(...)

# Pattern: Agent tool defined, not added to tools list
async def search_knowledge(...):  # defined but not in agent.tools = [...]

# Pattern: WebSocket event emitted but no subscriber
await publish_live_event("agent.complete", ...)  # no subscriber registered
```

All of these look dead. None of them should be deleted — they need issues to wire them up.
