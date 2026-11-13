---
type: fix
scope: backend
issue: 21456
---

The notification router's single-instance lock now holds a per-instance token instead of the constant `1`. `stop()` releases it only while it still holds that token, so a worker that never held the lock, or whose lock lapsed and was taken by another worker, no longer deletes the current holder's lock. The running router renews the lock every third of its lifetime (owner-checked), which the old comment claimed but nothing did; if a renewal finds the lock lost, or none succeeds for a whole lifetime, the router stops routing without touching the key. A failed release is logged and left to the lock's expiry. The lifetime is `AUTOBOT_LLC_NOTIFICATION_ROUTER_LOCK_TTL_SECONDS` (default 30). During a rolling restart an old worker's constant `1` lock is never deleted by a new worker and lapses on its own expiry, since old code never renews it.
