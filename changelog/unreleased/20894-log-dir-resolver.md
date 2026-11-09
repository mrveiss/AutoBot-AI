---
type: fix
scope: backend
issue: 20894
pr: 20980
---
Logs are never written inside the source tree: one resolver (`AUTOBOT_LOGS_DIR`, default the XDG state dir or a per-run temp dir under pytest) replaces the cwd-relative `logs` default.

Deployment check: the backend unit loads `EnvironmentFile={{ backend_code_dir }}/.env` (`autobot-slm-backend/ansible/roles/backend/templates/autobot-backend.service.j2:62`), written from `backend.env.j2`; `distributed.env.j2:35` is loaded only by the coordinator unit (`autobot-coordinator.service.j2:14`), so the backend did NOT get `AUTOBOT_LOGS_DIR`. Now set at `backend.env.j2:68` from `backend_logs_dir` (`roles/backend/defaults/main.yml:185`, same `<base>/logs` as before). The plugin logger now reads the same resolver.

Every Python service unit now sets `AUTOBOT_LOGS_DIR` (guarded by `repo_tests/service_units_set_logs_dir_20894_test.py`), from the role's own log variable: backend, celery, celery-beat and mcp-bridge via `roles/backend/templates/backend.env.j2:68`; slm-backend via `roles/slm_manager/templates/autobot-slm-backend.service.j2` (`slm_log_dir`); npu-worker via `roles/npu-worker/templates/npu-worker.env.j2` (`npu_log_dir`); tts-worker via `roles/tts-worker/templates/tts-worker.env.j2` (`tts_log_dir`); ai-stack via `roles/ai-stack/templates/ai-stack.env.j2` (`ai_log_dir`); already set: coordinator (`distributed.env.j2:35`), agent (`agent.env.j2:7`), slm-agent (`slm-agent.service.j2:73`). The four static units under `autobot-infrastructure/*/templates/` set it to `<WorkingDirectory>/logs`, what the cwd-relative default resolved to. Where a role variable differs from the old working-directory `logs/`, those logs move to the role's log directory on the next deploy.
