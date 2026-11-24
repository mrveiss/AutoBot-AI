---
type: fix
scope: backend
issue: 21984
---
Deleting a fact, or a session's facts, now removes its id from its category set and its quarantine index, so category counts and pages stay exact after a delete.
