---
type: docs
scope: infra
issue: 16060
pr: 0
---
Recorded why `node-roles.ts` and `api/deployments.py` list `redis-server`/`redis-cli` for the redis role — binary names Redis Stack genuinely ships, not the systemd unit (`redis-stack-server`) the fleet manages via `services/role_units.py` — completing #16060 and #16071's remaining "correct or record as display-only" criterion.
