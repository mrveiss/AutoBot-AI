---
type: security
scope: redis
issue: 16626
pr: 0
---
Every product Redis client can now authenticate with an ACL username as well as the password (`AUTOBOT_REDIS_USERNAME`). Covered clients: the shared client, Celery, the backend env, the Windows NPU worker, the exporter, the Redis and replication roles, the deploy playbooks and the ops scripts. With no username configured, every client authenticates exactly as before. This is the first step of the zero-outage Redis authentication rollout.
