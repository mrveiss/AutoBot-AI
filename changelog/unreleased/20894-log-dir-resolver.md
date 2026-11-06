---
type: fix
scope: backend
issue: 20894
pr: 0000
---
Logs are never written inside the source tree: one resolver (`AUTOBOT_LOGS_DIR`, default the XDG state dir or a per-run temp dir under pytest) replaces the cwd-relative `logs` default.
