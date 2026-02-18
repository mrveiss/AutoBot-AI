# autobot-slm-agent Infrastructure

> Role: `autobot-slm-agent` | Node: **ALL 9 nodes** | Ansible role: `slm_agent`

---

## Overview

Per-node SLM agent. Sends heartbeats to the SLM backend, executes code sync tasks triggered by SLM, reports health and system metrics, and runs Ansible playbooks on the SLM server (.19).

Deployed to every node. The only role with `deploy_to_all: true` besides `autobot-shared`.

---

## Ports

| Port | Protocol | Public | Purpose |
|------|----------|--------|---------|
| 9100 | HTTP | No (fleet-internal) | node_exporter (scraped by Prometheus on .19) |

---

## Services

| Unit | Type | Start Order |
|------|------|-------------|
| `autobot-slm-agent` | systemd | 1 |

---

## Health Check

```bash
# Check any node's agent
curl http://172.16.168.20:9100/metrics | head -5

# Check agent is registered with SLM
curl -sk https://172.16.168.19/api/nodes | jq '.[] | {id: .node_id, status: .status}'
```

---

## Secrets

| Secret | File | Description |
|--------|------|-------------|
| `agent_api_key` | `/etc/autobot/autobot-slm-agent.env` | Auth key for SLM backend API calls |
| `slm_backend_url` | `/etc/autobot/autobot-slm-agent.env` | SLM backend URL |
| `service_auth_token` | `/etc/autobot/autobot-slm-agent.env` | Inter-service auth |

---

## Deployment

```bash
# Deploy agent to all nodes (from autobot-slm-backend/ansible/)
ansible-playbook playbooks/deploy-full.yml --tags slm_agent

# Deploy to specific node
ansible-playbook playbooks/deploy-full.yml --tags slm_agent --limit 02-Frontend

# Restart on all nodes
ansible-playbook playbooks/slm-service-control.yml \
  -e "service=autobot-slm-agent action=restart"
```

---

## Node ID Requirements

**Critical**: Agent must be launched with `--node-id <node_id>` matching the inventory hostname.

```bash
# Correct (set in systemd unit by Ansible)
ExecStart=/opt/autobot/autobot-slm-agent/venv/bin/python main.py --node-id 01-Backend

# Also supported via env var
SLM_NODE_ID=01-Backend
```

If `node_id` is missing → `KeyError: 'node_id'` → crash loop (restart counter climbs to 300+).

---

## Known Gotchas

- **Legacy service cleanup**: The old service was named `autobot-agent`. The `slm_agent` Ansible role includes cleanup tasks to stop/disable/remove the legacy unit.
- **`--node-id` is required**: Must match `node_id` in SLM DB (inventory hostname). The Ansible role injects this into the systemd unit template.
- **Config file takes priority**: If `/opt/autobot/config.yaml` exists with no `node_id` key, the env var fallback is NEVER reached. The role now creates `config.yaml` with correct `node_id`.
- **Kali pip**: Use `--break-system-packages` flag when installing on Kali (Kali uses system Python 3.12 without venv by default). Fleet VMs use Ubuntu 22.04 + venv (no flag needed).
- **Heartbeat vs code_version**: Heartbeat should compare DB `node.code_version` (set by mark-synced) against `slm_agent_latest_commit` (from SLM). Never use `heartbeat.code_version` (stale runtime value).

---

## Ansible Role

Role: `slm_agent` in `autobot-slm-backend/ansible/roles/slm_agent/`

Key tasks:
- Stop + disable legacy `autobot-agent.service` (cleanup)
- Install Python venv + requirements
- Render systemd unit with `--node-id {{ inventory_hostname }}`
- Install + enable `autobot-slm-agent.service`
- Install node_exporter for Prometheus scraping
