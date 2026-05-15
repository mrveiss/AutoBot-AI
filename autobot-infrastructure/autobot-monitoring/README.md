# autobot-monitoring Infrastructure

> Role: `autobot-monitoring` | Node: SLM (.19 / 172.16.168.19) | Ansible role: `monitoring`

---

## Overview

Prometheus + Grafana monitoring stack colocated with the SLM server on .19. Prometheus scrapes node_exporter from all 9 nodes (port 9100) and SLM backend metrics. Grafana dashboards are proxied through the SLM nginx at `/grafana/`.

Both Prometheus and Grafana bind loopback — external access is via nginx proxy only.

---

## Ports

| Port | Protocol | Public | Purpose |
|------|----------|--------|---------|
| 9090 | HTTP | No (loopback) | Prometheus (proxied via nginx at /prometheus/) |
| 3000 | HTTP | No (loopback) | Grafana (proxied via nginx at /grafana/) |

**Warning**: Port 3000 conflicts with `autobot-browser-worker` if colocated. Do not assign both to the same node.

---

## Services

| Unit | Type | Start Order |
|------|------|-------------|
| `autobot-monitoring-prometheus` | systemd | 1 |
| `autobot-monitoring-grafana` | systemd | 2 |

---

## Health Check

```bash
# Via nginx proxy
curl -sk https://172.16.168.19/prometheus/-/healthy
curl -sk https://172.16.168.19/grafana/api/health | jq
```

---

## Secrets

| Secret | File | Description |
|--------|------|-------------|
| `grafana_password` | `/etc/autobot/monitoring-secrets.env` | Grafana admin password |

---

## Deployment

```bash
# Deploy monitoring stack
ansible-playbook playbooks/deploy-slm-manager.yml --tags monitoring

# Restart Grafana only
ansible-playbook playbooks/slm-service-control.yml \
  -e "service=autobot-monitoring-grafana action=restart"
```

---

## Prometheus Scrape Targets

Configured in `autobot-infrastructure/autobot-monitoring/prometheus.yml`:
- All 9 nodes: `172.16.168.{19-27}:9100` (node_exporter via autobot-slm-agent)
- SLM backend: `localhost:8000/metrics`
- NPU worker: `172.16.168.22:8081/metrics`

---

## Known Gotchas

- **Port 3000 conflict with browser-worker**: monitoring (grafana) and browser-worker both default to port 3000. Monitoring binds loopback; browser-worker binds all interfaces. Keep on separate nodes.
- **nginx proxy paths**: Grafana must be configured with `GF_SERVER_ROOT_URL=https://172.16.168.19/grafana/` for correct redirect handling.
- **External Grafana support**: See `docs/developer/GRAFANA_EXTERNAL_HOST_SETUP.md` for migrating Grafana to a dedicated VM.

---

## Ansible Role

Role: `monitoring` in `autobot-slm-backend/ansible/roles/monitoring/`

Key tasks:
- Install prometheus + grafana packages
- Render `prometheus.yml` scrape config
- Configure Grafana with nginx subpath
- systemd unit install + start
