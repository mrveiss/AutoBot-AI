---
type: security
scope: infra
issue: 15317
pr: 0000
---
ChromaDB's systemd unit no longer binds `--host 0.0.0.0` by default on either the ai-stack or redis role's template (nor in the infra decorative reference copy) — a new `chromadb_bind_host` variable (`autobot-slm-backend/ansible/inventory/group_vars/all.yml`), defaulting to `127.0.0.1`, now controls the bind address separately from the pre-existing client-dial `chromadb_host`. A multi-node install that needs ChromaDB reachable from another host must set `chromadb_bind_host` explicitly and add a subnet-scoped firewall rule for port 8100.
