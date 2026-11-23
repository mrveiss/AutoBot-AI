---
type: fix
scope: backend
issue: 21957
pr: 0000
---
Knowledge category listings no longer count research-quarantined facts: `total_count` and `has_more` are exact and pages are full, using a quarantine-aware index over the category fact sets.
