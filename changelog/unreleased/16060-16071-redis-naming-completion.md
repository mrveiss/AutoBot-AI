---
type: fix
scope: infra
issue: 16060
pr: 0
---
Recorded why `node-roles.ts` and `api/deployments.py` list `redis-server`/`redis-cli` for the redis role — binary names Redis Stack genuinely ships, not the systemd unit (`redis-stack-server`) the fleet manages via `services/role_units.py` — completing #16060's remaining "correct or record as display-only" criterion.

`fix-architecture-issues.sh`'s Redis-stop step no longer discards its result with a blanket `|| true`: it now checks whether each unit (`redis-server`, `redis-stack-server`) is actually installed before attempting to stop it, and reports a real stop failure instead of swallowing it identically to an absent unit — completing #16071's AC4.
