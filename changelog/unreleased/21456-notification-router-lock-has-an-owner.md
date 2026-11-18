---
type: fix
scope: backend
issue: 21456
---

The notification router's single-instance lock now holds a per-instance token instead of the constant `1`, and every started worker keeps contesting it for its lifetime. The holder renews it every third of its lifetime (owner-checked); a worker that skipped it at boot, or lost it, tries to take it at the same interval and starts routing the moment it does, so after a Redis flush, failover or outage no restart is needed to get a router back. Routing runs only while the lock is held: if a renewal finds the lock gone or foreign, or none is confirmed for a whole lifetime, routing stops and the key is left alone. `stop()` ends the loop and the routing task and deletes the key only while it still holds this instance's token. A worker with no Redis no longer routes unlocked (it could not receive events anyway, and would route beside the holder once Redis returned). The lifetime is `AUTOBOT_LLC_NOTIFICATION_ROUTER_LOCK_TTL_SECONDS` (default 30). During a rolling restart an old worker's constant `1` lock is neither renewed nor deleted by a new worker and lapses on its own expiry, after which a new worker takes it; an old worker's `stop()` deletes whatever the key holds, which a new holder notices at its next renewal and takes the lock again.
