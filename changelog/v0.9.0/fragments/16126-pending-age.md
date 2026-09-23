---
type: feat
scope: tooling
issue: 16126
pr: 0
---
`scripts/lib/check_run_status.py` gains `pending_ages()`, distinguishing a check that has been pending for minutes (fresh, wait) from one pending for much longer with nothing else moving (stuck, act) — a third state `check_run_status()`'s plain reported/not-green contract couldn't express.
