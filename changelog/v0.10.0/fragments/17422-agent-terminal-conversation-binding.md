---
type: fix
scope: backend
issue: 17422
pr: 0000
---
Agent-terminal session creation now refuses (404) a `conversation_id` the caller does not own, so a user can no longer bind another user's conversation and inherit its pending command approval.
