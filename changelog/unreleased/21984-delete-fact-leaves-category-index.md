---
type: fix
scope: backend
issue: 21984
---
Deleting a fact, or a session's facts, now removes its id from its category set and its quarantine index, and decrements the category's fact count. The cleanup is best-effort: if Redis fails during it, the delete still succeeds, the failure is logged and a stale id can remain. Stale ids that already exist are not cleaned here (#22223).
