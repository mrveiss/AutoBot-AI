# AutoBot Centralized Logging System

## Overview

The AutoBot Centralized Logging System provides comprehensive log collection, monitoring, and analysis across the entire distributed AutoBot infrastructure. It collects logs from all 5 VMs and the main WSL machine into a unified, organized structure for efficient troubleshooting and monitoring.

## Architecture

### Infrastructure Layout
- **Main Machine (WSL)**: `172.16.168.20` - Backend API + Log aggregation
- **VM1 Frontend**: `172.16.168.21` - Vue.js web interface logs
- **VM2 NPU Worker**: `172.16.168.22` - Hardware AI acceleration logs
- **VM3 Redis**: `172.16.168.23` - Database logs and metrics
- **VM4 AI Stack**: `172.16.168.24` - AI processing service logs
- **VM5 Browser**: `172.16.168.25` - Web automation logs

### Log Directory Structure
```
logs/autobot-centralized/
├── vm1-frontend/           # Frontend VM logs
│   ├── system/            # System-level logs
│   ├── application/       # Application-specific logs
│   ├── service/           # Service status logs
│   └── archived/          # Rotated/old logs
├── vm2-npu-worker/        # NPU Worker VM logs
├── vm3-redis/             # Redis VM logs
├── vm4-ai-stack/          # AI Stack VM logs
├── vm5-browser/           # Browser VM logs
├── main-wsl/              # Main machine logs
└── aggregated/            # Cross-VM aggregated logs
    ├── errors/            # Error aggregation
    ├── warnings/          # Warning aggregation
    └── info/              # Information aggregation
```

## Features

### 1. Automated Log Collection
- **Service logs**: Collected every 15 minutes
- **Application logs**: Collected hourly
- **Real-time collection**: On-demand collection available
- **Cross-VM coordination**: Synchronized collection from all VMs

### 2. Log Types Collected

#### VM1 Frontend (172.16.168.21)
- Nginx access and error logs
- Vue.js development server logs
- Node.js process information
- Build and deployment logs

#### VM2 NPU Worker (172.16.168.22)
- Intel OpenVINO logs
- AI inference process logs
- Hardware acceleration metrics
- NPU utilization data

#### VM3 Redis (172.16.168.23)
- Redis server logs
- Database keyspace information
- Memory usage statistics
- Client connection data

#### VM4 AI Stack (172.16.168.24)
- Python API server logs
- AI model processing logs
- GPU utilization metrics
- FastAPI/Uvicorn logs

#### VM5 Browser (172.16.168.25)
- Playwright automation logs
- VNC session logs
- Desktop environment logs
- Docker container logs

#### Main WSL Machine (172.16.168.20)
- Backend API logs
- System journal logs
- Process monitoring
- Resource utilization

### 3. Monitoring and Analysis Tools

#### Interactive Log Viewer
- VM-specific log browsing
- Log type filtering (system/application/service)
- Real-time search across all logs
- Live tail functionality

#### Monitoring Dashboard
- Real-time VM health status
- Service availability monitoring
- Log collection summary
- Recent activity tracking
- Error detection and alerting

#### Automated Analysis
- Error pattern detection
- Performance metric extraction
- Disk usage monitoring
- Collection status tracking

## Usage

### Quick Start

1. **Initial Setup** (one-time):
   ```bash
   # Setup centralized logging infrastructure
   ./scripts/logging/setup-centralized-logging.sh

   # Configure automation (cron jobs)
   ./scripts/logging/setup-log-automation.sh
   ```

2. **Daily Operations**:
   ```bash
   # View monitoring dashboard
   ./scripts/logging/monitoring-dashboard.sh

   # View logs interactively
   ./scripts/logging/view-centralized-logs.sh

   # Check collection status
   ./scripts/logging/log-collection-status.sh
   ```

### Manual Log Collection

```bash
# Collect service logs from all VMs
./scripts/logging/collect-service-logs.sh

# Collect application logs from all VMs
./scripts/logging/collect-application-logs.sh
```

### Log Viewing and Analysis

#### Using the Interactive Viewer
```bash
./scripts/logging/view-centralized-logs.sh
```

Features:
- Browse logs by VM
- Filter by log type (system/application/service)
- Search across all collected logs
- Live tail functionality
- Disk usage analysis

#### Using the Monitoring Dashboard
```bash
./scripts/logging/monitoring-dashboard.sh
```

Features:
- Real-time VM health monitoring
- Service status checking
- Log collection summary
- Recent activity tracking
- Quick actions for common tasks

### Command Line Analysis

```bash
# Search for errors across all VMs
grep -r -i "error" /home/kali/Desktop/AutoBot/logs/autobot-centralized/

# Find recent Redis issues
find /home/kali/Desktop/AutoBot/logs/autobot-centralized/vm3-redis/ -name "*.log" -mtime -1 -exec grep -l "error\|warning" {} \;

# Monitor disk usage
du -sh /home/kali/Desktop/AutoBot/logs/autobot-centralized/*/

# Check latest logs from specific VM
find /home/kali/Desktop/AutoBot/logs/autobot-centralized/vm1-frontend/ -name "*.log" -type f -printf "%TY-%Tm-%Td %TH:%TM %p\n" | sort -r | head -5
```

## Automation

### Cron Jobs
Automated log collection is configured via cron jobs:

```bash
# View current automation
crontab -l | grep -i autobot

# Service logs: Every 15 minutes
*/15 * * * * /home/kali/Desktop/AutoBot/scripts/logging/collect-service-logs.sh

# Application logs: Every hour
0 * * * * /home/kali/Desktop/AutoBot/scripts/logging/collect-application-logs.sh

# Log cleanup: Daily at 2 AM (keeps 7 days)
0 2 * * * find /home/kali/Desktop/AutoBot/logs/autobot-centralized -name "*.log" -mtime +7 -delete
```

### Log Rotation
- **Daily rotation**: Logs rotated daily
- **Retention**: 7 days for centralized logs, 14 days for main logs
- **Compression**: Old logs automatically compressed
- **Size management**: Automatic cleanup of large log files

## Troubleshooting

### Common Issues

#### 1. SSH Connection Problems
```bash
# Test SSH connectivity
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "hostname"

# Check SSH key permissions
chmod 600 ~/.ssh/autobot_key
```

#### 2. Missing Logs from Specific VM
```bash
# Check VM accessibility
./scripts/logging/log-collection-status.sh

# Manual collection from specific VM
ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "ps aux | grep redis"
```

#### 3. Disk Space Issues
```bash
# Check centralized logs disk usage
du -sh /home/kali/Desktop/AutoBot/logs/autobot-centralized/

# Clean old logs manually
find /home/kali/Desktop/AutoBot/logs/autobot-centralized/ -name "*.log" -mtime +3 -delete
```

#### 4. Cron Job Not Running
```bash
# Check cron status
systemctl status cron

# View cron logs
journalctl -u cron | tail -20

# Test cron job manually
/home/kali/Desktop/AutoBot/scripts/logging/collect-service-logs.sh
```

### Log Collection Status

Check collection health with:
```bash
./scripts/logging/log-collection-status.sh
```

This shows:
- Active cron jobs
- Log file counts per VM
- Recent collection activity
- Disk usage statistics

## Security Considerations

### SSH Key Authentication
- Uses certificate-based authentication (`~/.ssh/autobot_key`)
- No password authentication required
- Keys must be properly configured on all VMs

### Log Content Security
- System logs may contain sensitive information
- Application logs filtered for PII when possible
- Access restricted to authorized users only

### Network Security
- Log collection uses encrypted SSH connections
- No unencrypted log transmission
- Firewall-friendly (uses standard SSH port 22)

## Performance

### Collection Performance
- **Service logs**: ~6 seconds for all 5 VMs
- **Application logs**: ~20 seconds for all 5 VMs
- **Network overhead**: Minimal (compressed log transfer)
- **Disk usage**: ~4-5MB for typical hourly collection

### Optimization
- Logs compressed during transfer
- Selective collection based on VM type
- Automatic cleanup prevents disk bloat
- Parallel collection from multiple VMs

## Monitoring Metrics

The system tracks:
- **VM Health**: SSH connectivity, service status
- **Collection Status**: Success rates, timing, errors
- **Storage**: Disk usage, file counts, growth rates
- **Service Health**: Redis status, frontend processes, AI stack

## Integration

### With AutoBot Monitoring
- Integrates with existing monitoring infrastructure
- Provides logs for performance analysis
- Supports troubleshooting workflows
- Compatible with existing alert systems

### With Development Workflow
- Supports development debugging
- Provides deployment verification logs
- Enables performance optimization
- Facilitates issue root cause analysis

## Future Enhancements

### Planned Features
1. **Real-time Log Streaming**: WebSocket-based live log viewing
2. **Advanced Analytics**: Machine learning-based anomaly detection
3. **Alert Integration**: Automatic notification on critical events
4. **Dashboard Web UI**: Browser-based monitoring interface
5. **Log Parsing**: Structured log analysis and metrics extraction

### Scalability
- Designed for easy addition of new VMs
- Supports horizontal scaling of log collection
- Configurable retention and rotation policies
- Ready for cloud deployment if needed

## Conclusion

The AutoBot Centralized Logging System provides comprehensive visibility into the distributed AutoBot infrastructure. With automated collection, interactive viewing tools, and real-time monitoring, it enables efficient troubleshooting and proactive system maintenance across all 5 VMs and the main machine.

For support or questions, refer to the troubleshooting section or examine the individual script files in `scripts/logging/` for detailed implementation information.