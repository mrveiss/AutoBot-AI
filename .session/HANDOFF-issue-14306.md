# Handoff: issue-14306

status: complete
pr: #14347
base_at_push: origin/Dev_new_gui @ 7f5d11605
gates: flake8=PASS black=PASS isort=PASS tests=PASS (10 new, 18 with adjacent)
needs_rebase_before_merge: no
remaining: (none — awaiting review + CI + merge)

## What landed here — NOT what the issue asked for

#14306 reported that `keep_system_prompt` preserves nothing, framed as a schema
mismatch: the filter compares the API-shape role key against records the store
keeps under `sender`, so it never matches.

**That fix was written, reviewed, and then reverted on purpose.** Nothing persists
a system prompt into a session — `_get_system_prompt()` composes one per turn and
sends it straight to the provider. The only writers using that speaker are command
approval/cancellation notices and overflow summaries. So resolving the mismatch
made the default reset preserve "Command approved" as though it were the prompt:
worse than preserving nothing, which is what the broken comparison did by accident.

The filter is deliberately left matching the API shape, with a test pinning that
and a docstring pointing at **#14359** (remove the flag — owner decision
2026-08-16). Do not "fix" that comparison without reading it.

## What was actually broken, and is fixed

The reset **never ran at all**. Two defects on the same path, both found by review,
neither a schema issue:

1. `get_session` is `async def`; the call was unawaited. The coroutine failed the
   membership test, the bare `except` swallowed it, and the function returned `[]`
   — so the reader looked fixed while being unreachable.
2. `chat_manager.clear_session(...)` does not exist on any mixin. Both request
   flags default to on, so the DEFAULT reset raised `AttributeError` into the
   endpoint's generic handler on every request. Replaced with
   `update_session(session_id, {"messages": []})`, which clears messages without
   destroying the session record.

## The part worth remembering

My tests mocked `get_session` with a **sync** `MagicMock` for an **async** method.
That is precisely what hid defect 1: the fix mutation-tested at 0 failures before
the mock was corrected, 6 after. A mock whose shape does not match the real
callee tests nothing.

## Deliberately NOT done here

The `llm_role` clamp from the sibling PR (#14338) is not used on this path, and
should not be. That clamp exists to make a **provider request** legal. This path
writes back to storage, where the faithful speaker is the correct one.
