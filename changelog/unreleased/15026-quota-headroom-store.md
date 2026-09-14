---
type: feat
scope: backend
issue: 15026
pr: 0000
---
Add llm_shared/quota_headroom.py, a Redis-backed cross-worker store recording provider rate-limit headroom (the missing "quota monitor" llc/api/costs.py already referred to); rate_limit_backoff.py now persists a zero-remaining/reset-at reading on every 429 instead of discarding what it parses.
