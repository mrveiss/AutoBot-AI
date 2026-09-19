---
type: fix
scope: backend
issue: 17070
pr: 0000
---
The SLM reconciler's service-heartbeat sync now runs each service's DB work in its own savepoint instead of a bare `except Exception` that swallowed a DB-level failure without rolling back, which poisoned the session and cascaded `PendingRollbackError` across every remaining service (1,545 warnings in one 2h window); a genuine connection-level failure now aborts the sync once, with a single clear log line, instead of repeating.
