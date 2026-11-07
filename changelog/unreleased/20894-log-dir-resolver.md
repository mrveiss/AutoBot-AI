---
type: fix
scope: backend
issue: 20894
pr: 0000
---
Logs are never written inside the source tree: one resolver (`AUTOBOT_LOGS_DIR`, default the XDG state dir or a per-run temp dir under pytest) replaces the cwd-relative `logs` default.

Deployment check: the backend unit loads `EnvironmentFile={{ backend_code_dir }}/.env` (`autobot-slm-backend/ansible/roles/backend/templates/autobot-backend.service.j2:62`), written from `backend.env.j2`; `distributed.env.j2:35` is loaded only by the coordinator unit (`autobot-coordinator.service.j2:14`), so the backend did NOT get `AUTOBOT_LOGS_DIR`. Now set at `backend.env.j2:68` from `backend_logs_dir` (`roles/backend/defaults/main.yml:185`, same `<base>/logs` as before). The plugin logger now reads the same resolver.
