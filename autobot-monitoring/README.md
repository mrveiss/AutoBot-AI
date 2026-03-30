# autobot-monitoring

Prometheus + Grafana configuration for AutoBot observability.

---

## Docker-Compose Deployment

Static config files used when running the monitoring profile locally:

```
autobot-monitoring/
  prometheus.yml                          # Prometheus scrape config (docker service names)
  grafana/
    provisioning/
      datasources/prometheus.yml          # Auto-provisioned Prometheus datasource
      dashboards/dashboards.yml           # Dashboard provider (scans grafana/dashboards/)
```

Start the monitoring stack:

```bash
docker compose --env-file docker/.env.docker --profile monitoring up -d
```

Grafana: http://localhost:3000 (admin / set via `GRAFANA_ADMIN_PASSWORD` env var, default: `autobot`)
Prometheus: http://localhost:9090

---

## Fleet (Ansible) Deployment

For fleet nodes, Prometheus config is rendered from a Jinja2 template that
injects the dynamic node inventory:

```
autobot-slm-backend/ansible/roles/monitoring/
  templates/prometheus.yml.j2    # Fleet scrape config with dynamic node targets
  templates/grafana.ini.j2       # Grafana config (subpath, auth)
  tasks/prometheus.yml           # Install + configure Prometheus
  tasks/grafana.yml              # Install + configure Grafana
```

Deploy with:

```bash
ansible-playbook playbooks/deploy-slm-manager.yml --tags monitoring
```

See `autobot-infrastructure/autobot-monitoring/` for the infrastructure manifest.

---

## Python Metrics Library

The Python `PrometheusMetricsManager` and domain-specific recorder classes live in:

```
autobot-shared/monitoring/
  prometheus_metrics.py          # Core metrics manager + singleton
  metrics/                       # Domain-specific recorder classes
    workflow.py, github.py, ...
```

Import in backend services via the re-export shim:

```python
from monitoring.prometheus_metrics import get_metrics_manager
metrics = get_metrics_manager()
```

See `autobot-backend/monitoring/prometheus_metrics.py` for the shim.
Issue #937 replaced the original no-op stub with the real shared implementation.
