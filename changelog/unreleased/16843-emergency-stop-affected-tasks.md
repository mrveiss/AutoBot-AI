---
type: fix
scope: backend
issue: 16843
pr: 0000
---
`POST /api/advanced-control/system/emergency-stop` now enumerates actually-running tasks (`TaskExecutionTracker.get_active_tasks()`) and passes them to the takeover manager instead of an always-empty list, and its response reports what was actually found (`tasks_paused`) instead of a fixed success string. This marks tasks paused for audit/visibility; it does not yet interrupt in-flight execution, since no code path currently checks paused-task state before continuing work -- that remains open on #16843.
