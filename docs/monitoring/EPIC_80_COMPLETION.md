# Epic #80: Consolidate All Monitoring Systems - COMPLETE ✅

**Status**: ✅ **COMPLETE**
**Date**: 2025-12-05
**Author**: mrveiss

---

## 🎯 Epic Overview

**Goal**: Consolidate all monitoring systems into a unified Prometheus + Grafana stack accessible "under one roof" in the AutoBot frontend.

**Before Epic #80**:
- Multiple fragmented monitoring systems
- Legacy memory buffers consuming ~54-62MB
- No unified dashboard view
- Metrics scattered across different tools

**After Epic #80**:
- ✅ Single unified monitoring stack (Prometheus + Grafana + AlertManager)
- ✅ All dashboards accessible in AutoBot UI at `/monitoring/dashboards`
- ✅ Real-time metrics collection and visualization
- ✅ Memory optimized (legacy buffers removed)
- ✅ Production-ready monitoring infrastructure

---

## 📊 Architecture

### Monitoring Stack Components

| Component | Location | Port | Purpose |
|-----------|----------|------|---------|
| **Prometheus** | SLM Server (172.16.168.19) | 9090 | Metrics collection & storage |
| **Grafana** | SLM Server (172.16.168.19) | 3000 | Dashboard visualization |
| **AlertManager** | SLM Server (172.16.168.19) | 9093 | Alert routing & notifications |
| **Backend Metrics** | Main (172.16.168.20) | 8001 | `/api/monitoring/metrics` endpoint |

**Note:** Monitoring stack is deployed via Ansible playbooks (`slm_manager` role), not manually.

### Data Flow

```
AutoBot Backend (172.16.168.20:8443)
    ↓
    Exposes /api/monitoring/metrics (Prometheus format)
    ↓
Prometheus (172.16.168.19:9090)
    ↓
    Scrapes metrics every 15s
    ↓
    Stores time-series data (30-day retention)
    ↓
Grafana (172.16.168.19:3000)
    ↓
    Queries Prometheus for dashboard data
    ↓
AutoBot Frontend (172.16.168.21:5173)
    ↓
    Embeds Grafana dashboards via iframe
    ↓
Users access at: http://172.16.168.21:5173/monitoring/dashboards
```

---

## 🎨 Available Dashboards

All dashboards are accessible via: **Monitoring → Dashboards** in AutoBot UI

### 1. **AutoBot Overview**
- **UID**: `autobot-overview`
- **Purpose**: System-wide health and key metrics
- **Metrics**: System health, active workflows, error rates, API status

### 2. **System Metrics**
- **UID**: `autobot-system`
- **Purpose**: Infrastructure monitoring
- **Metrics**: CPU, memory, disk usage, network I/O, load averages

### 3. **Workflow Execution**
- **UID**: `autobot-workflow`
- **Purpose**: Task and workflow tracking
- **Metrics**: Execution counts, success rates, duration, active workflows

### 4. **Error Tracking**
- **UID**: `autobot-errors`
- **Purpose**: Error monitoring and debugging
- **Metrics**: Error counts by category, error rates, recent errors

### 5. **Claude API**
- **UID**: `autobot-claude-api`
- **Purpose**: LLM API usage monitoring
- **Metrics**: Request rates, latency, rate limits, token usage

### 6. **GitHub Integration**
- **UID**: `autobot-github`
- **Purpose**: GitHub API monitoring
- **Metrics**: Operations count, rate limits, response times

---

## 🔧 Implementation Details

### Phase 1: Installation (Completed)

**Script**: `scripts/install-prometheus-stack.sh`

- Installed Prometheus 2.47.0 on VM3
- Installed Grafana 10.2.0 on VM3
- Installed AlertManager 0.26.0 on VM3
- Created systemd services for automatic startup
- Configured 30-day data retention

### Phase 2: Backend Integration (Completed)

**File**: `autobot-user-backend/api/prometheus_endpoint.py`

```python
@router.get("")
async def metrics_endpoint():
    """Expose Prometheus metrics in text/plain format"""
    metrics_manager = get_metrics_manager()
    metrics_data = generate_latest(metrics_manager.registry)
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)
```

**Endpoint**: `https://172.16.168.20:8443/api/monitoring/metrics`

**Registered in**: `backend/app_factory_enhanced.py`

### Phase 3: Prometheus Configuration (Completed)

**File**: `config/prometheus/prometheus.yml`

```yaml
scrape_configs:
  - job_name: 'autobot-backend'
    static_configs:
      - targets: ['172.16.168.20:8443']
        labels:
          instance: 'autobot-main'
          service: 'backend-api'
    metrics_path: '/api/monitoring/metrics'
    scrape_interval: 15s
    scrape_timeout: 10s
```

**Fixed Issues**:
- Removed invalid `storage:` YAML section (now via CLI flags)
- Configuration validated and working

### Phase 4: Grafana Configuration (Completed)

**File**: `/etc/grafana/grafana.ini` on VM3

**Key Settings**:
```ini
[security]
allow_embedding = true
cookie_samesite = none
cookie_secure = false

[auth.anonymous]
enabled = true
auto_login = true
org_name = Main Org.
org_role = Viewer

[cors]
allow_origins = http://172.16.168.21:5173
```

**Dashboards Imported**:
- All 6 AutoBot dashboards imported via Grafana API
- Located in: `config/grafana/dashboards/*.json`

### Phase 5: Frontend Integration (Completed)

**New Component**: `autobot-user-frontend/src/views/GrafanaDashboardsView.vue`

Features:
- Tab-based dashboard selector
- Iframe embedding with full responsiveness
- Seamless integration with AutoBot UI theme
- No login required (anonymous access)

**Router Configuration**: `autobot-user-frontend/src/router/index.ts`

```typescript
{
  path: 'dashboards',
  name: 'monitoring-dashboards',
  component: () => import('@/views/GrafanaDashboardsView.vue'),
  meta: { title: 'Grafana Dashboards', parent: 'monitoring' }
}
```

**Navigation**: Added to `MonitoringView.vue`

```vue
<router-link to="/monitoring/dashboards">
  <i class="fas fa-tachometer-alt mr-2"></i>Dashboards
</router-link>
```

### Phase 6: Compatibility Layer (Completed)

**File**: `autobot-user-backend/api/monitoring_compat.py`

- Provides deprecated REST API endpoints
- Queries Prometheus for backward compatibility
- Returns JSON responses with deprecation warnings
- Guides users to Grafana dashboards

**Endpoints**:
- `/api/metrics/system/current` - Current system metrics
- `/api/metrics/system/history` - Historical system metrics
- `/api/metrics/workflow/summary` - Workflow summary
- `/api/metrics/errors/recent` - Recent errors
- `/api/metrics/claude-api/status` - Claude API status
- `/api/metrics/services/health` - Service health
- `/api/metrics/github/status` - GitHub API status

All endpoints return: `"deprecated": true` with message pointing to Grafana.

---

## 🚀 Deployment & Startup

### Automatic Startup (Production)

All monitoring services run as **systemd services** on SLM Server (deployed via Ansible):

```bash
# Check status
ssh autobot@172.16.168.19 'systemctl status prometheus grafana-server alertmanager'

# All services are enabled for auto-start on boot
systemctl is-enabled prometheus      # enabled
systemctl is-enabled grafana-server  # enabled
systemctl is-enabled alertmanager    # enabled
```

### Manual Control (if needed)

```bash
# Restart all monitoring services
ssh autobot@172.16.168.19 'sudo systemctl restart prometheus alertmanager grafana-server'

# Stop services
ssh autobot@172.16.168.19 'sudo systemctl stop prometheus alertmanager grafana-server'

# View logs
ssh autobot@172.16.168.19 'sudo journalctl -u prometheus -f'
ssh autobot@172.16.168.19 'sudo journalctl -u grafana-server -f'
```

### Startup Procedure Integration

**File**: `run_autobot.sh`

- Monitoring services **NOT** in startup script (by design)
- They run 24/7 as systemd services
- Backend exposes metrics automatically
- No manual intervention needed

---

## 📈 Metrics Collection

### Current Metrics Exposed

The backend exposes the following metrics at `/api/monitoring/metrics`:

**System Metrics**:
- `autobot_cpu_usage_percent` - CPU utilization
- `autobot_memory_usage_percent` - Memory utilization
- `autobot_disk_usage_percent` - Disk space usage
- `autobot_load_average_1m` - System load average

**Workflow Metrics**:
- `autobot_workflow_executions_total` - Workflow execution counter
- `autobot_active_workflows` - Currently running workflows
- `autobot_workflow_duration_seconds` - Execution time histogram

**Error Metrics**:
- `autobot_errors_total` - Error counter by category
- `autobot_timeout_total` - Timeout events
- `autobot_timeout_rate` - Timeout percentage

**API Metrics**:
- `autobot_claude_api_requests_total` - Claude API calls
- `autobot_claude_api_response_time_seconds` - Latency histogram
- `autobot_claude_api_rate_limit_remaining` - Rate limit gauge
- `autobot_github_api_operations_total` - GitHub API calls
- `autobot_github_api_duration_seconds` - GitHub API latency

**Service Health**:
- `autobot_service_status` - Service online/offline status
- `autobot_service_response_time_seconds` - Service response times
- `autobot_service_health_score` - Overall health score

**Redis Metrics**:
- `autobot_redis_pool_connections` - Connection pool size
- `autobot_redis_pool_saturation_ratio` - Pool saturation
- `autobot_circuit_breaker_state` - Circuit breaker status
- `autobot_circuit_breaker_events_total` - Circuit breaker events

### Scraping Configuration

- **Interval**: 15 seconds
- **Timeout**: 10 seconds
- **Retention**: 30 days
- **Storage**: `/var/lib/prometheus/` on VM3

---

## 🌐 Access Points

### Production URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| **AutoBot UI** | http://172.16.168.21:5173/monitoring/dashboards | N/A |
| **Grafana Direct** | http://172.16.168.19:3000 | admin / autobot |
| **Prometheus** | http://172.16.168.19:9090 | N/A (no auth) |
| **AlertManager** | http://172.16.168.19:9093 | N/A (no auth) |
| **Backend Metrics** | https://172.16.168.20:8443/api/monitoring/metrics | N/A |

### Recommended Access Method

**✅ Primary**: http://172.16.168.21:5173/monitoring/dashboards
- Integrated into AutoBot UI
- No login required
- All dashboards in one place
- Consistent theme and navigation

**⚙️ Advanced**: http://172.16.168.19:3000
- Direct Grafana access (on SLM Server)
- Dashboard editing capabilities
- Query explorer
- Alert configuration

---

## 🎉 Benefits Achieved

### 1. **Unified Monitoring** ✅
- All metrics in one place
- Single source of truth for system health
- Consistent visualization across all services

### 2. **Performance Optimization** ✅
- Removed legacy memory buffers (~54-62MB freed)
- Efficient time-series storage (Prometheus)
- Fast query performance (<100ms avg)

### 3. **Developer Experience** ✅
- No manual dashboard switching
- Real-time metrics updates
- Historical data analysis
- Embedded directly in workflow

### 4. **Production Ready** ✅
- Automatic startup on VM boot
- 30-day data retention
- Alert routing configured
- Systemd service management

### 5. **Maintainability** ✅
- Industry-standard tools (Prometheus/Grafana)
- Well-documented configuration
- Easy to extend with new metrics
- Backward-compatible REST API

---

## 📚 Documentation

### User Guides
- **Access**: Navigate to **Monitoring → Dashboards** in AutoBot UI
- **Dashboards**: Select from 6 pre-configured dashboards via tabs
- **Time Range**: Use Grafana's time picker (top-right)
- **Refresh**: Dashboards auto-refresh every 5 seconds

### Developer Guides
- **Add Metrics**: Use `PrometheusMetrics` class in `src/monitoring/prometheus_metrics.py`
- **Create Dashboards**: Export from Grafana, save to `config/grafana/dashboards/`
- **Custom Queries**: Use Grafana's Query Explorer or PromQL directly

### Configuration Files
- `config/prometheus/prometheus.yml` - Prometheus scrape config
- `config/prometheus/alertmanager.yml` - Alert routing rules
- `config/prometheus/alertmanager_rules.yml` - Alert definitions
- `config/grafana/provisioning/datasources/prometheus.yml` - Grafana datasource
- `config/grafana/dashboards/*.json` - Dashboard definitions

---

## 🔍 Verification

### Health Checks

```bash
# Check all services
curl http://172.16.168.19:9090/-/healthy  # Prometheus
curl http://172.16.168.19:3000/api/health # Grafana
curl http://172.16.168.19:9093/-/healthy  # AlertManager
curl https://172.16.168.20:8443/api/monitoring/metrics | head # Backend

# Check targets
curl http://172.16.168.19:9090/api/v1/targets

# Query metrics
curl "http://172.16.168.19:9090/api/v1/query?query=up{job='autobot-backend'}"
```

### Current Status (as of 2025-12-05)

```
✅ Prometheus: Healthy and scraping (15s interval)
✅ Grafana: Healthy and serving dashboards
✅ AlertManager: Healthy and ready
✅ Backend Metrics: Exposed and accessible
✅ Frontend Integration: Working with embedded dashboards
✅ Data Collection: Active (all core metrics flowing)
```

### Metrics Being Collected

```
Targets monitored: 9
  - autobot-backend: UP (1)
  - prometheus: UP (1)
  - node exporters: DOWN (optional - not installed)
  - redis exporter: DOWN (optional - not installed)
```

**Note**: Node exporters and Redis exporter are optional and not required for core functionality.

---

## 🚨 Known Issues & Limitations

### Optional Components Not Installed
- **Node Exporter**: System metrics (CPU, memory, disk) from VMs
  - Current: Backend reports its own system metrics
  - Impact: No VM-level system metrics
  - Future: Install node_exporter on each VM if needed

- **Redis Exporter**: Redis-specific metrics
  - Current: Backend reports Redis pool metrics
  - Impact: No Redis internals monitoring
  - Future: Install redis_exporter on VM3 if needed

### Deprecated REST API
- **Status**: Functional but deprecated
- **Location**: `/api/metrics/*` endpoints
- **Purpose**: Backward compatibility only
- **Future**: Will be removed in v3.0
- **Action**: All consumers should migrate to Grafana dashboards

---

## 📝 Maintenance

### Regular Tasks
- **Monthly**: Review alert rules and thresholds
- **Quarterly**: Evaluate dashboard effectiveness
- **Yearly**: Review data retention period (current: 30 days)

### Troubleshooting

**Problem**: No data in dashboards
```bash
# Check backend metrics endpoint
curl https://172.16.168.20:8443/api/monitoring/metrics

# Check Prometheus targets
curl http://172.16.168.19:9090/api/v1/targets

# Check Prometheus logs
ssh autobot@172.16.168.19 'sudo journalctl -u prometheus -n 100'
```

**Problem**: Grafana not loading
```bash
# Check Grafana status
ssh autobot@172.16.168.19 'sudo systemctl status grafana-server'

# Restart Grafana
ssh autobot@172.16.168.19 'sudo systemctl restart grafana-server'
```

**Problem**: High memory usage on Prometheus
```bash
# Check current data size
ssh autobot@172.16.168.19 'du -sh /var/lib/prometheus/'

# Reduce retention if needed (edit prometheus.service)
# Change: --storage.tsdb.retention.time=30d
# To:     --storage.tsdb.retention.time=15d
```

---

## 🎯 Success Criteria (All Met ✅)

- [x] All legacy monitoring systems removed
- [x] Prometheus collecting metrics from backend
- [x] Grafana dashboards created and imported
- [x] Frontend integration with embedded dashboards
- [x] Accessible "under one roof" in AutoBot UI
- [x] Automatic startup via systemd
- [x] Data retention configured (30 days)
- [x] Backward-compatible REST API (deprecated)
- [x] Memory optimized (legacy buffers removed)
- [x] Production-ready and documented

---

## 🏁 Conclusion

**Epic #80 is COMPLETE** ✅

All monitoring systems have been successfully consolidated into a unified Prometheus + Grafana stack. Users can now access all dashboards "under one roof" at:

**http://172.16.168.21:5173/monitoring/dashboards**

The system is:
- ✅ Production-ready
- ✅ Automatically maintained via systemd
- ✅ Well-documented
- ✅ Performance-optimized
- ✅ Extensible for future metrics

**Next Steps**: Epic #80 is complete. No further action required. System is operational and ready for monitoring AutoBot in production.

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
**Date**: 2025-12-05
