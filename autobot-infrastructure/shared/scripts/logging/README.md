# AutoBot Enhanced Centralized Logging System

## 🚀 Quick Start

### One-Command Deployment
```bash
# Deploy the complete enhanced centralized logging system
bash scripts/logging/deploy-enhanced-logging.sh
```

### Pre-Deployment Check
```bash
# Verify system readiness before deployment
bash scripts/logging/quick-deploy-verification.sh
```

## 📊 Perfect for Current GPU Performance Issues

Your system is currently experiencing GPU performance regressions:
```
🚨 REGRESSION ALERT: GPU utilization dropped from 17.0% to 4-21%
```

The enhanced logging system provides:
- **Real-time GPU regression detection**
- **Cross-VM correlation** during performance drops
- **Historical trend analysis**
- **Intelligent alerting** for performance issues
- **Web dashboards** for visualization

## 🎯 System Overview

### Enhanced Features Added to Existing Infrastructure

| Component | Enhancement | Purpose |
|-----------|-------------|---------|
| **Loki + Grafana** | Modern log aggregation | Web-based log visualization and analysis |
| **Promtail Agents** | Real-time log shipping | Live log streaming from all 5 VMs |
| **AI Log Parser** | Intelligent categorization | Automatic performance issue detection |
| **Real-Time Monitor** | Live alerting | Instant notifications for GPU regressions |
| **Performance Aggregator** | Trend analysis | Historical GPU performance tracking |

### Infrastructure Layout
```
Main Machine (172.16.168.20)    │ VM1 Frontend (172.16.168.21)
├── Loki (port 3100)            │ ├── Promtail agent
├── Grafana (port 3001)         │ ├── nginx logs
├── Real-time monitor           │ └── autobot-frontend logs
├── Performance aggregator      │
└── Enhanced log parser         │ VM2 NPU Worker (172.16.168.22)
                                │ ├── Promtail agent
                                │ ├── autobot-npu-worker logs
                                │ └── docker logs
                                │
                                │ VM3 Redis (172.16.168.23)
                                │ ├── Promtail agent
                                │ └── redis-stack-server logs
                                │
                                │ VM4 AI Stack (172.16.168.24)
                                │ ├── Promtail agent
                                │ ├── autobot-ai-stack logs
                                │ └── autobot-backend logs
                                │
                                │ VM5 Browser (172.16.168.25)
                                │ ├── Promtail agent
                                │ ├── autobot-playwright logs
                                │ └── docker logs
```

## 🛠️ Available Scripts

### Core Deployment
- **`deploy-enhanced-logging.sh`** - Complete enhanced system deployment
- **`quick-deploy-verification.sh`** - Pre-deployment system check
- **`logging-system-status.sh`** - System health monitoring

### Existing Scripts (Enhanced)
- **`setup-centralized-logging.sh`** - Basic rsyslog-based collection
- **`view-centralized-logs.sh`** - Interactive log browser
- **`collect-service-logs.sh`** - Service log collection
- **`collect-application-logs.sh`** - Application log collection
- **`real-time-monitor.sh`** - Live monitoring with alerts

### Advanced Analytics
- **`enhanced-log-parser.py`** - AI-powered log categorization
- **`performance-aggregator.py`** - Performance trend analysis
- **`monitoring-dashboard.sh`** - Comprehensive monitoring interface

## 🔧 Management Commands

### Daily Operations
```bash
# Check system status
bash scripts/logging/logging-system-status.sh

# View logs interactively
bash scripts/logging/view-centralized-logs.sh

# Monitor in real-time (perfect for GPU issues!)
bash scripts/logging/real-time-monitor.sh
```

### Performance Analysis
```bash
# Analyze GPU performance trends
python3 scripts/logging/performance-aggregator.py \
  --centralized-dir logs/autobot-centralized \
  --print-summary

# Parse logs with AI categorization
python3 scripts/logging/enhanced-log-parser.py \
  --centralized-dir logs/autobot-centralized \
  --summary
```

### Manual Log Collection
```bash
# Collect from all VMs
bash scripts/logging/collect-service-logs.sh
bash scripts/logging/collect-application-logs.sh

# Collect from specific VM
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "journalctl -u autobot* --since '1 hour ago'"
```

## 🌐 Web Interfaces

### Loki API (Direct Access)
- **URL**: http://172.16.168.20:3100
- **Purpose**: Direct log querying and API access

**Example LogQL queries:**
```logql
# Monitor GPU performance issues
{job="autobot-performance"} |= "GPU" |= "regression"

# Find all errors across VMs
{job="autobot-system"} |= "error" | line_format "{{.timestamp}} {{.vm}} {{.message}}"

# Track API response times
rate({job="autobot-performance"} |= "API" [5m])
```

### Grafana Dashboard
- **URL**: http://172.16.168.20:3001
- **Credentials**: admin / autobot123
- **Features**: Pre-configured AutoBot dashboards, GPU regression visualization

## 📁 Log Organization

```
logs/autobot-centralized/
├── alerts/                      # 🚨 Generated alerts
│   ├── critical/                # System failures
│   ├── warning/                 # Performance regressions
│   └── performance/             # GPU/CPU/memory issues
├── metrics/                     # 📊 Performance analysis
│   ├── performance/             # GPU regression reports
│   ├── system/                  # VM health metrics
│   └── application/             # Service performance
├── aggregated/                  # 🧠 AI-processed logs
│   ├── by-service/              # nginx, redis, docker, autobot-*
│   ├── by-severity/             # critical, error, warning, info
│   └── by-time/                 # temporal aggregations
├── vm1-frontend/                # 🌐 Frontend VM logs
├── vm2-npu-worker/              # ⚡ NPU Worker VM logs
├── vm3-redis/                   # 💾 Redis VM logs
├── vm4-ai-stack/                # 🤖 AI Stack VM logs
├── vm5-browser/                 # 🌍 Browser VM logs
└── main-wsl/                    # 🖥️ Main machine logs
    ├── backend/                 # Backend API logs
    ├── loki/                    # Loki server logs
    └── performance/             # Performance monitor integration
```

## 🚨 GPU Performance Monitoring

### Current Issue Detection
Your performance monitor shows recurring GPU regressions:
```
REGRESSION DETECTED: GPU utilization dropped from 17.0% to 4.0%
REGRESSION DETECTED: GPU utilization dropped from 17.0% to 11.0%
```

### Enhanced GPU Monitoring Features

1. **Real-Time Alerts**
   ```bash
   # Get instant notifications for GPU regressions
   bash scripts/logging/real-time-monitor.sh
   ```

2. **Historical Analysis**
   ```bash
   # Analyze GPU performance patterns over time
   python3 scripts/logging/performance-aggregator.py \
     --centralized-dir logs/autobot-centralized
   ```

3. **Cross-VM Correlation**
   - Correlates GPU drops with system events across all VMs
   - Identifies potential causes (service restarts, resource contention)
   - Tracks timing relationships between VMs

4. **Intelligent Categorization**
   - Automatically categorizes GPU issues as performance alerts
   - Severity assessment (1-5 scale)
   - Pattern recognition for recurring problems

## 🔔 Alert System

### Alert Categories
- 🚨 **CRITICAL**: System failures, crashes, security breaches
- ❌ **ERROR**: Application errors, failed operations, timeouts
- ⚠️ **WARNING**: Performance degradation, resource warnings
- 📊 **PERFORMANCE**: GPU regressions, high CPU/memory usage
- 🔒 **SECURITY**: Unauthorized access, suspicious activity

### Integration Options
```bash
# Configure webhook alerts (Slack, Discord, etc.)
export ALERT_WEBHOOK="https://hooks.slack.com/your-webhook"
bash scripts/logging/real-time-monitor.sh
```

## 🔧 Troubleshooting

### Common Issues

1. **VM Connectivity**
   ```bash
   # Check VM status
   bash scripts/vm-management/status-all-vms.sh

   # Test SSH connectivity
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "echo test"
   ```

2. **Missing Logs**
   ```bash
   # Force log collection
   bash scripts/logging/collect-service-logs.sh
   bash scripts/logging/collect-application-logs.sh
   ```

3. **Loki/Grafana Issues**
   ```bash
   # Check Docker containers
   docker ps | grep autobot-loki
   docker ps | grep autobot-grafana

   # Restart if needed
   cd config/logging/loki
   docker-compose -f docker-compose-loki.yml restart
   ```

4. **Promtail Agent Issues**
   ```bash
   # Check agent status on VM
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "sudo systemctl status promtail"

   # Restart agent
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "sudo systemctl restart promtail"
   ```

### Performance Analysis Commands
```bash
# Find GPU regressions in logs
grep -r "REGRESSION.*GPU" logs/autobot-centralized/

# Check recent errors
grep -r -i "error\|failed" logs/autobot-centralized/ | head -20

# Monitor disk usage
du -sh logs/autobot-centralized/*

# Find most active log sources
find logs/autobot-centralized/ -name "*.log" -printf "%s %p\n" | sort -rn | head -10
```

## 📈 Benefits Over Existing System

### Before Enhancement
- ❌ Manual log collection across 5 VMs
- ❌ No real-time GPU regression detection
- ❌ Scattered logs with no correlation
- ❌ Limited performance analysis capabilities
- ❌ No web-based visualization

### After Enhancement
- ✅ **Automatic real-time monitoring** across all VMs
- ✅ **Intelligent GPU regression detection** with instant alerts
- ✅ **AI-powered log categorization** and analysis
- ✅ **Web-based dashboards** with Grafana
- ✅ **Cross-VM correlation** for root cause analysis
- ✅ **Automated performance reports** and trend analysis
- ✅ **Webhook integration** for external notifications
- ✅ **Historical data** for long-term performance tracking

## 🎯 Perfect for Your Environment

This enhanced centralized logging system is specifically designed to address:

1. **Current GPU Performance Issues** (17% → 4-21% fluctuations)
2. **Distributed VM Log Management** (5 VMs + main machine)
3. **Real-Time Performance Monitoring**
4. **Cross-System Correlation Analysis**
5. **Automated Alert Generation**
6. **Historical Trend Analysis**

**Deploy with one command and immediately start tracking your GPU performance regressions with intelligent analysis and alerting!**

---

## 📚 Documentation

- **Complete Guide**: `docs/CENTRALIZED_LOGGING_SYSTEM.md`
- **Architecture Docs**: `docs/architecture/DISTRIBUTED_ARCHITECTURE.md`
- **Troubleshooting**: Built into interactive scripts

## 🚀 Get Started Now

```bash
# 1. Verify system readiness
bash scripts/logging/quick-deploy-verification.sh

# 2. Deploy enhanced logging system
bash scripts/logging/deploy-enhanced-logging.sh

# 3. Start monitoring your GPU performance issues!
bash scripts/logging/real-time-monitor.sh
```
