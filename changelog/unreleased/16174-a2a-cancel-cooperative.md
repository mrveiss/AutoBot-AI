---
type: fix
scope: a2a
issue: 16174
pr: 0
---
Cancelling an A2A task now stops its executor at defined checkpoints instead of only bounding an orphaned work-claim at its TTL: `execute_a2a_task` checks for cancellation before scrubbing, before calling the orchestrator, and after it returns, so a cancelled task performs no further work and releases its claim as soon as the next checkpoint sees the cancellation — without ever unlocking a scope while the work holding it is still writing.
