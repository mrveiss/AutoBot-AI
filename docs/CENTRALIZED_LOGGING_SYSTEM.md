# AutoBot Centralized Logging System

## Overview

The AutoBot Centralized Logging System provides comprehensive, real-time log collection, aggregation, and monitoring across the entire distributed VM infrastructure. The system combines traditional rsyslog functionality with modern tools like Loki and Promtail for enhanced log management.

## Architecture

### Components

1. **Loki + Grafana Stack** - Modern log aggregation and visualization
2. **Promtail Agents** - Lightweight log shippers on each VM
3. **rsyslog** - Traditional syslog forwarding (fallback)
4. **Enhanced Log Parser** - Intelligent log categorization and alerting
5. **Real-Time Monitor** - Live log monitoring with instant alerts
6. **Performance Aggregator** - Performance metrics analysis

### Infrastructure Layout

```
Main Machine (172.16.168.20)
├── Loki (port 3100) - Log aggregation
├── Grafana (port 3001) - Log visualization
├── rsyslog server (port 514) - Syslog collection
└── Enhanced parsers and monitors

VM1 Frontend (172.16.168.21)
├── Promtail agent
├── rsyslog client
└── nginx, autobot-frontend logs

VM2 NPU Worker (172.16.168.22)
├── Promtail agent
├── rsyslog client
└── autobot-npu-worker, docker logs

VM3 Redis (172.16.168.23)
├── Promtail agent
├── rsyslog client
└── redis-stack-server logs

VM4 AI Stack (172.16.168.24)
├── Promtail agent
├── rsyslog client
└── autobot-ai-stack, autobot-backend logs

VM5 Browser (172.16.168.25)
├── Promtail agent
├── rsyslog client
└── autobot-playwright, docker logs
```

## Installation & Setup

### Quick Start - One Command Deployment

```bash
# Deploy the complete enhanced logging system
bash scripts/logging/deploy-enhanced-logging.sh
```

This single command will:
- ✅ Deploy Loki + Grafana stack on main machine
- ✅ Install Promtail agents on all 5 VMs
- ✅ Configure rsyslog forwarding (fallback)
- ✅ Create intelligent log parsing system
- ✅ Setup real-time monitoring and alerting
- ✅ Configure performance regression detection
- ✅ Create automated log collection

### Individual Component Setup

```bash
# Setup basic centralized logging (existing system)
bash scripts/logging/setup-centralized-logging.sh

# Deploy only the enhanced features
bash scripts/logging/deploy-enhanced-logging.sh --enhanced-only

# Check system status
bash scripts/logging/logging-system-status.sh
```

## Usage

### 🖥️ Interactive Log Viewer

```bash
# Launch the enhanced interactive log browser
bash scripts/logging/view-centralized-logs.sh
```

**Features:**
- Browse logs by VM (Frontend, NPU Worker, Redis, AI Stack, Browser)
- Filter by log type (system/application/service)
- Search across all logs with highlighting
- Real-time tail functionality
- Live error tracking
- Disk usage monitoring
- Performance summary view

### 🔴 Real-Time Monitoring & Alerting

```bash
# Start intelligent real-time log monitoring
bash scripts/logging/real-time-monitor.sh
```

**Alert Categories:**
- 🚨 **CRITICAL**: System failures, crashes, security breaches
- ❌ **ERROR**: Application errors, failed operations, timeouts
- ⚠️ **WARNING**: Performance degradation, resource warnings
- 📊 **PERFORMANCE**: GPU regressions, high CPU/memory usage
- 🔒 **SECURITY**: Unauthorized access, suspicious activity

**Perfect for monitoring the GPU performance regressions that are currently being detected!**

### 📊 Performance Analysis

```bash
# Analyze performance metrics including GPU regressions
python3 scripts/logging/performance-aggregator.py \
  --centralized-dir logs/autobot-centralized \
  --print-summary

# Generate comprehensive performance report
python3 scripts/logging/performance-aggregator.py \
  --centralized-dir logs/autobot-centralized
```

**Tracks:**
- GPU utilization and regressions (like the current 17% → 6-11% drops)
- CPU usage across all VMs
- Memory consumption patterns
- API response times
- Service health status
- Network latency

### 🧠 Intelligent Log Parsing

```bash
# Parse all VM logs with AI-powered categorization
python3 scripts/logging/enhanced-log-parser.py \
  --centralized-dir logs/autobot-centralized \
  --summary

# Parse specific VM with detailed analysis
python3 scripts/logging/enhanced-log-parser.py \
  --centralized-dir logs/autobot-centralized \
  --vm vm1-frontend
```

**Capabilities:**
- Automatic log categorization (performance/security/system/application/network)
- Severity assessment (1-5 scale)
- Intelligent alert generation
- Context-aware parsing for different log formats
- Performance regression detection

## 🌐 Web Interfaces

### Loki API
- **URL**: http://172.16.168.20:3100
- **Purpose**: Direct log querying and API access
- **Query Language**: LogQL

**Example queries:**
```logql
# Find all errors in the last hour
{job="autobot-system"} |= "error" | line_format "{{.timestamp}} {{.message}}"

# Monitor GPU performance issues
{job="autobot-performance"} |= "GPU" |= "regression"

# Track specific VM activity
{host="vm1-frontend"} | json | line_format "{{.level}} {{.message}}"

# Monitor API response times
rate({job="autobot-performance"} |= "API" [5m])
```

### Grafana Logs Dashboard
- **URL**: http://172.16.168.20:3001
- **Credentials**: admin / autobot123
- **Features**:
  - Pre-configured AutoBot dashboards
  - GPU regression visualization
  - Cross-VM log correlation
  - Performance metrics integration
  - Custom alert rules
  - Real-time log streaming

## 📁 Directory Structure

```
logs/autobot-centralized/
├── aggregated/              # AI-processed and categorized logs
│   ├── by-service/          # nginx, redis, docker, autobot-*
│   ├── by-severity/         # critical, error, warning, info
│   └── by-time/             # hourly, daily aggregations
├── alerts/                  # Generated alerts (perfect for GPU regressions!)
│   ├── critical/            # System failures, crashes
│   ├── warning/             # Performance issues, regressions
│   └── performance/         # GPU drops, CPU spikes, memory issues
├── metrics/                 # Performance analysis
│   ├── performance/         # GPU/CPU/memory trends
│   ├── system/              # VM health metrics
│   └── application/         # Service-specific metrics
├── vm1-frontend/            # Frontend VM (172.16.168.21)
│   ├── system/              # syslog, kernel logs
│   ├── application/         # nginx, autobot-frontend
│   ├── service/             # systemd services
│   ├── real-time/           # Live processed logs
│   ├── parsed/              # AI-categorized logs
│   └── alerts/              # VM-specific alerts
├── vm2-npu-worker/          # NPU Worker VM (172.16.168.22)
├── vm3-redis/               # Redis VM (172.16.168.23)
├── vm4-ai-stack/            # AI Stack VM (172.16.168.24)
├── vm5-browser/             # Browser VM (172.16.168.25)
└── main-wsl/                # Main machine (172.16.168.20)
    ├── backend/             # Backend API logs
    ├── loki/                # Loki server logs
    ├── grafana/             # Grafana logs
    └── performance/         # Main performance monitor
```

## 🚨 GPU Performance Regression Monitoring

**The system is specifically designed to catch and analyze the GPU performance issues you're experiencing!**

### Current GPU Issues Detected
Your performance monitor is showing:
```
🚨 REGRESSION ALERT: GPU utilization dropped from 17.0% to 6-11%
```

### Enhanced GPU Monitoring Features

1. **Real-Time Detection**
   ```bash
   # Monitor GPU regressions in real-time
   bash scripts/logging/real-time-monitor.sh
   ```

2. **Historical Analysis**
   ```bash
   # Analyze GPU performance patterns
   python3 scripts/logging/performance-aggregator.py \
     --centralized-dir logs/autobot-centralized \
     --print-summary
   ```

3. **Alert Configuration**
   - Automatic alerts when GPU drops below thresholds
   - Pattern recognition for recurring issues
   - Correlation with system events
   - Integration with existing performance monitor

4. **Root Cause Analysis**
   - Cross-VM log correlation during GPU drops
   - Service activity correlation
   - Resource contention detection
   - Timeline analysis of events

## 🔧 System Status & Health Monitoring

```bash
# Check overall logging system health
bash scripts/logging/logging-system-status.sh
```

**Monitors:**
- ✅ All 5 VM connectivity (172.16.168.21-25)
- ✅ Loki and Grafana services
- ✅ Promtail agents on each VM
- ✅ rsyslog forwarding
- ✅ Recent alert activity
- ✅ Performance metrics
- ✅ Disk usage trends

## 🤖 Automation & Collection

### Automated Collection (Already Running)
- **Service logs**: Every 15 minutes via cron
- **Application logs**: Every hour via cron
- **Performance analysis**: Every 5 minutes
- **Alert processing**: Real-time

### Manual Collection
```bash
# Collect service logs from all VMs
bash scripts/logging/collect-service-logs.sh

# Collect application logs
bash scripts/logging/collect-application-logs.sh

# Force immediate performance analysis
python3 scripts/logging/performance-aggregator.py \
  --centralized-dir logs/autobot-centralized
```

## 🔔 Alerting Integration

### Webhook Integration
```bash
# Configure external alerts (Slack, Discord, etc.)
export ALERT_WEBHOOK="https://hooks.slack.com/your-webhook"
bash scripts/logging/real-time-monitor.sh
```

### Alert Types for Your Environment
- **GPU Regression Alerts** (like current 17% → 6-11% drops)
- **API Response Time Spikes**
- **Service Failure Notifications**
- **VM Connectivity Issues**
- **Resource Exhaustion Warnings**

## 🚀 Quick Start Commands

```bash
# 1. Deploy the enhanced logging system
bash scripts/logging/deploy-enhanced-logging.sh

# 2. Check system status
bash scripts/logging/logging-system-status.sh

# 3. Start real-time monitoring (perfect for GPU issues!)
bash scripts/logging/real-time-monitor.sh

# 4. View logs interactively
bash scripts/logging/view-centralized-logs.sh

# 5. Analyze performance (including GPU regressions)
python3 scripts/logging/performance-aggregator.py \
  --centralized-dir logs/autobot-centralized \
  --print-summary
```

## 🔧 Troubleshooting

### VM Connectivity Issues
```bash
# Test SSH to all VMs
bash scripts/vm-management/status-all-vms.sh

# Redeploy SSH keys if needed
bash scripts/utilities/setup-ssh-keys.sh
```

### Missing Logs
```bash
# Force log collection
bash scripts/logging/collect-service-logs.sh
bash scripts/logging/collect-application-logs.sh
```

### Loki/Grafana Issues
```bash
# Restart logging stack
cd config/logging/loki
docker-compose -f docker-compose-loki.yml restart
```

### Promtail Agent Issues
```bash
# Check/restart Promtail on specific VM
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "sudo systemctl status promtail"
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "sudo systemctl restart promtail"
```

## 📈 Performance Benefits

### Before Enhanced Logging
- ❌ Manual log collection across 5 VMs
- ❌ No real-time GPU regression detection
- ❌ Scattered logs with no correlation
- ❌ Manual performance analysis

### After Enhanced Logging
- ✅ **Automatic real-time monitoring** across all VMs
- ✅ **Intelligent GPU regression detection** (perfect for current issues!)
- ✅ **AI-powered log categorization** and alerting
- ✅ **Web-based dashboards** with Grafana
- ✅ **Cross-VM correlation** for root cause analysis
- ✅ **Automated performance reports**
- ✅ **Webhook integration** for external notifications

## 🔗 Integration Points

### Existing AutoBot Systems
- **Performance Monitor**: Enhanced analysis of current GPU regressions
- **VM Management**: Integration with status checking scripts
- **Backend Monitoring**: API performance correlation
- **Ansible Playbooks**: Automated deployment across VMs

### External Integrations
- **Slack/Discord**: Webhook alerts for GPU regressions
- **Monitoring Dashboards**: Grafana visualization
- **CI/CD Pipelines**: Log-based deployment validation
- **Security Tools**: Alert correlation and analysis

---

## 🎯 Perfect for Your Current Needs

This enhanced centralized logging system is **specifically designed** to help with the GPU performance regressions you're experiencing. It will:

1. **Detect** GPU drops in real-time (17% → 6-11%)
2. **Correlate** with system events across all VMs
3. **Alert** immediately when regressions occur
4. **Analyze** patterns and trends
5. **Visualize** performance data in Grafana
6. **Archive** historical data for long-term analysis

**Deploy with one command and start monitoring your GPU performance issues immediately!**

```bash
bash scripts/logging/deploy-enhanced-logging.sh
```