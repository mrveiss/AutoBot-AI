# Monitoring Quick Reference Guide

**Author**: mrveiss
**Last Updated**: 2025-12-05

---

## 🚀 Quick Access

### Primary Dashboard Access
```
http://172.16.168.21:5173/monitoring/dashboards
```
Navigate: **AutoBot UI → Monitoring → Dashboards**

### Direct Service Access
| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://172.16.168.19:3000 | admin / autobot |
| Prometheus | http://172.16.168.19:9090 | (no auth) |
| AlertManager | http://172.16.168.19:9093 | (no auth) |

**Note:** Monitoring stack is deployed on SLM Server via Ansible playbooks (`slm_manager` role).

---

## 📊 Available Dashboards

### Core Dashboards

- **AutoBot Overview** - System-wide health snapshot
- **System Metrics** - CPU, memory, disk, load
- **Workflow Execution** - Task tracking and performance
- **Error Tracking** - Error rates and patterns
- **API Health** - API endpoint health and latency

### Integration Dashboards

- **Claude API** - Claude API usage and limits
- **GitHub Integration** - GitHub API metrics
- **LLM Providers** - All LLM providers (OpenAI, Anthropic, Ollama)

### Infrastructure Dashboards

- **Multi-Machine Health** - 6-VM infrastructure status
- **Redis Performance** - Redis operations, pool, memory
- **WebSocket Metrics** - Real-time connection stats
- **GPU/NPU Performance** - Hardware acceleration metrics

### Data Dashboards

- **Knowledge Base** - Vector store, search, embeddings

---

## 🔧 Common Commands

### Check Service Status
```bash
# All monitoring services
ssh autobot@172.16.168.19 'systemctl status prometheus grafana-server alertmanager'

# Backend metrics endpoint
curl http://172.16.168.20:8001/api/monitoring/metrics | head
```

### Restart Services
```bash
# Restart all monitoring services
ssh autobot@172.16.168.19 'sudo systemctl restart prometheus alertmanager grafana-server'

# Restart individual service
ssh autobot@172.16.168.19 'sudo systemctl restart grafana-server'
```

### View Logs
```bash
# Prometheus logs
ssh autobot@172.16.168.19 'sudo journalctl -u prometheus -f'

# Grafana logs
ssh autobot@172.16.168.19 'sudo journalctl -u grafana-server -f'

# AlertManager logs
ssh autobot@172.16.168.19 'sudo journalctl -u alertmanager -f'
```

### Check Metrics
```bash
# Test backend metrics endpoint
curl http://172.16.168.20:8001/api/monitoring/metrics

# Check Prometheus targets
curl http://172.16.168.19:9090/api/v1/targets | python3 -m json.tool

# Query specific metric
curl "http://172.16.168.19:9090/api/v1/query?query=autobot_cpu_usage_percent"
```

---

## 🏥 Health Checks

### Quick Health Check
```bash
# One-liner to check all services
echo "Backend:"; curl -s http://172.16.168.20:8001/api/health > /dev/null && echo "✅ UP" || echo "❌ DOWN"; \
echo "Prometheus:"; curl -s http://172.16.168.19:9090/-/healthy > /dev/null && echo "✅ UP" || echo "❌ DOWN"; \
echo "Grafana:"; curl -s http://172.16.168.19:3000/api/health > /dev/null && echo "✅ UP" || echo "❌ DOWN"; \
echo "AlertManager:"; curl -s http://172.16.168.19:9093/-/healthy > /dev/null && echo "✅ UP" || echo "❌ DOWN"
```

### Detailed Status
```bash
# Check scraping status
curl -s http://172.16.168.19:9090/api/v1/targets | \
  python3 -c "import sys, json; data = json.load(sys.stdin); \
  [print(f\"{r['labels']['job']}: {'✅ UP' if r['health'] == 'up' else '❌ DOWN'}\") \
  for r in data['data']['activeTargets']]"
```

---

## 🚨 Troubleshooting

### No Data in Dashboards

**Check 1**: Backend metrics endpoint
```bash
curl http://172.16.168.20:8001/api/monitoring/metrics
# Should return Prometheus-format metrics
```

**Check 2**: Prometheus scraping
```bash
curl http://172.16.168.19:9090/api/v1/targets | grep autobot-backend -A 10
# Look for "health": "up"
```

**Check 3**: Grafana datasource
```bash
curl http://172.16.168.19:3000/api/datasources
# Should show Prometheus datasource
```

**Fix**: Restart backend
```bash
bash run_autobot.sh --restart
```

### Grafana Not Loading

**Check**: Service status
```bash
ssh autobot@172.16.168.19 'sudo systemctl status grafana-server'
```

**Fix**: Restart Grafana
```bash
ssh autobot@172.16.168.19 'sudo systemctl restart grafana-server'
```

### High Prometheus Memory

**Check**: Data size
```bash
ssh autobot@172.16.168.19 'du -sh /var/lib/prometheus/'
```

**Fix**: Reduce retention (if > 5GB)
```bash
# Edit prometheus service
ssh autobot@172.16.168.19 'sudo nano /etc/systemd/system/prometheus.service'
# Change: --storage.tsdb.retention.time=30d
# To:     --storage.tsdb.retention.time=15d

# Reload and restart
ssh autobot@172.16.168.19 'sudo systemctl daemon-reload && sudo systemctl restart prometheus'
```

---

## 📈 Metrics Reference

### Key Metrics to Monitor

**System Health**:

- `autobot_cpu_usage_percent` - CPU utilization
- `autobot_memory_usage_percent` - Memory usage
- `autobot_load_average_1m` - System load

**Workflow Performance**:

- `autobot_workflow_executions_total` - Total workflows
- `autobot_active_workflows` - Currently running
- `autobot_workflow_duration_seconds` - Execution time

**Error Rates**:

- `autobot_errors_total` - Total errors by category
- `autobot_timeout_total` - Timeout events
- `rate(autobot_errors_total[5m])` - Error rate per second

**API Usage**:

- `autobot_claude_api_requests_total` - Claude API calls
- `autobot_claude_api_rate_limit_remaining` - Rate limit
- `autobot_github_api_operations_total` - GitHub operations

**LLM Providers** (Issue #470):

- `autobot_llm_requests_total` - LLM requests by provider
- `autobot_llm_tokens_total` - Token usage
- `autobot_llm_request_latency_seconds` - Response time

**Knowledge Base** (Issue #470):

- `autobot_knowledge_search_latency_seconds` - Search performance
- `autobot_knowledge_cache_hits_total` - Cache effectiveness
- `autobot_knowledge_vectors_total` - Vector count

**WebSocket** (Issue #470):

- `autobot_websocket_connections_active` - Active connections
- `autobot_websocket_messages_sent_total` - Message throughput

**Redis** (Issue #470):

- `autobot_redis_operations_total` - Operation counts
- `autobot_redis_operation_latency_seconds` - Latency
- `autobot_redis_memory_used_bytes` - Memory usage

### PromQL Quick Examples

```promql
# CPU usage above 80%
autobot_cpu_usage_percent > 80

# Error rate (errors per second over 5 minutes)
rate(autobot_errors_total[5m])

# Average workflow duration
avg(autobot_workflow_duration_seconds)

# Total workflows by status
sum(autobot_workflow_executions_total) by (status)

# 95th percentile API latency
histogram_quantile(0.95, rate(autobot_claude_api_response_time_seconds_bucket[5m]))
```

---

## 🎯 Best Practices

1. **Check dashboards daily** - Review AutoBot Overview dashboard
2. **Monitor error rates** - Keep error rate < 1% of total operations
3. **Watch API limits** - Claude API rate limit should stay > 100
4. **Review alerts weekly** - Check AlertManager for firing alerts
5. **Archive old data** - Prometheus auto-deletes after 30 days

---

## 📚 Additional Resources

- **Full Documentation**: `docs/monitoring/EPIC_80_COMPLETION.md`
- **Configuration Files**: `config/prometheus/`, `config/grafana/`
- **Dashboard JSONs**: `config/grafana/dashboards/`
- **Metrics Code**: `src/monitoring/prometheus_metrics.py`

---

**For support**: Check full documentation or restart services if issues persist.

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
