---
type: security
scope: redis
issue: 16627
pr: 0
---
The SLM now generates the product Redis password once, and every client sends it as the `default` user. Covered clients: the backend (including its self-update env render), the AI stack, the Redis role's own readiness check and exporter, and the SLM's replication and backup, which now read the canonical credential instead of a node's config file and pass it to `redis-cli` on stdin. The server still requires no password, so nothing can be locked out; enforcement is the next step (#16628). The unauthenticated NPU bootstrap endpoint no longer returns the Redis password (#16657).
