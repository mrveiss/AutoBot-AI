---
type: fix
scope: backend
issue: 22003
pr: 0000
---
Triggering a Company OS routine now answers 202 only when the routine was put on the schedule. If the schedule store is unavailable or the write fails, the trigger answers 503 and the failure is logged, instead of answering 202 for a run that never happens.
