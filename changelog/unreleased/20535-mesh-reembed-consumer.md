---
type: fix
scope: backend
issue: 20535
pr: 21074
---
Documents flagged stale by mesh staleness propagation are now re-indexed: a leader-leased consumer drains mesh:reembed_queue into the document re-index queue, with bounded retries and a dead-letter list.
