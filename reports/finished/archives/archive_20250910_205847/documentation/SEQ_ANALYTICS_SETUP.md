# AutoBot Seq Analytics Setup Guide

## Overview

This guide covers the comprehensive log aggregation and analysis system for AutoBot using Seq centralized logging.

## Quick Start

1. **Start the log forwarder:**
   ```bash
   ./scripts/start_seq.sh
   ```

2. **Access Seq Dashboard:**
   - URL: http://localhost:5341
   - Default credentials: admin / autobot123 (if required)

## Architecture

### Log Sources
- **Backend Services**: Main AutoBot application logs
- **Docker Containers**: All AutoBot-related containers
  - `autobot-npu-worker`: NPU processing logs
  - `autobot-log-collector`: FluentD aggregation
  - `autobot-log-viewer`: Seq container logs
  - `autobot-playwright-vnc`: Browser automation logs
  - `autobot-ai-stack`: AI processing logs
  - `autobot-redis`: Database logs

### Log Flow
```
AutoBot Backend → Log Forwarder → Seq
Docker Containers → Log Forwarder → Seq
```

## Components

### 1. Simple Docker Log Forwarder
- **File**: `scripts/simple_docker_log_forwarder.py`
- **Purpose**: Streams logs from all AutoBot containers and backend to Seq
- **Features**:
  - Real-time log streaming
  - Automatic container discovery
  - Backend process monitoring
  - Queue-based log processing
  - Graceful shutdown handling

### 2. Seq Analytics Setup
- **File**: `scripts/setup_seq_analytics.py`
- **Purpose**: Comprehensive Seq configuration for AutoBot
- **Features**:
  - Query creation for error analysis
  - Dashboard setup
  - Alert configuration
  - Retention policies

### 3. Seq Startup Script
- **File**: `scripts/start_seq.sh`
- **Purpose**: One-command startup for complete analytics
- **Features**:
  - Container health checks
  - Log forwarder startup
  - Test log verification
  - PID management

## Pre-configured Queries

### Error Analysis
1. **Critical Errors**: All exceptions and failures
2. **WebSocket Issues**: Connection problems
3. **Backend Errors**: Service-specific issues

### Performance Monitoring
1. **Slow Responses**: Timeout and delay detection
2. **Memory Issues**: High usage warnings
3. **Container Resources**: Resource utilization problems

### System Health
1. **Service Startup**: Initialization tracking
2. **Health Checks**: Container status monitoring
3. **Database Connections**: Redis and DB connectivity

### Security Monitoring
1. **Authentication**: Login and token events
2. **Failed Requests**: Authorization failures

### Operational Insights
1. **Chat Messages**: Message flow tracking
2. **API Patterns**: Request frequency analysis
3. **NPU Activity**: Processing workload monitoring

## Manual Setup Instructions

### 1. Create Queries in Seq
From `config/seq-basic-queries.json`:

```sql
-- AutoBot Error Summary
select @l as Level, count(*) as Count
from stream
where Application = 'AutoBot' and @l = 'Error'
group by @l

-- AutoBot Container Activity
select ContainerName, count(*) as LogCount
from stream
where LogType = 'DockerContainer' and @t >= Now() - 1h
group by ContainerName

-- AutoBot Recent Errors
select top 20 @t, Source, @mt
from stream
where Application = 'AutoBot' and @l = 'Error'
order by @t desc
```

### 2. Create Dashboards
1. **System Overview**:
   - Log sources summary
   - Message counts by level
   - Container activity levels

2. **Error Analytics**:
   - Recent error timeline
   - Error frequency by source
   - Most common error messages

3. **Performance Metrics**:
   - Response time tracking
   - Resource usage patterns
   - Container performance

### 3. Setup Alerts
Create alerts for:
- Critical system errors
- WebSocket disconnections
- Backend service failures
- Container health issues

## Usage

### Starting Log Analytics
```bash
# Start comprehensive analytics
./scripts/start_seq.sh

# Start only log forwarder
python scripts/simple_docker_log_forwarder.py

# Test connection and send logs
python scripts/seq_auth_setup.py
```

### Monitoring Operations
```bash
# Check forwarder status
ps aux | grep simple_docker_log_forwarder

# Stop forwarder
kill $(cat /tmp/autobot_log_forwarder.pid)

# View container logs being forwarded
docker logs autobot-npu-worker --follow
```

### Query Examples
```sql
-- Find all WebSocket disconnections in last hour
select @t, Source, @mt
from stream
where Source like '%WebSocket%'
and @t >= Now() - 1h
and (@l = 'Warning' or @l = 'Error')
order by @t desc

-- Container resource warnings
select ContainerName, @t, @mt
from stream
where LogType = 'DockerContainer'
and (@mt like '%memory%' or @mt like '%cpu%')
and @l in ['Warning', 'Error']
order by @t desc

-- API performance tracking
select @t, @mt
from stream
where @mt like '%ms'
and (@mt like '%slow%' or @mt like '%timeout%')
order by @t desc
```

## Troubleshooting

### Common Issues

1. **No logs appearing in Seq**
   - Check if log forwarder is running: `ps aux | grep log_forwarder`
   - Verify Seq container health: `docker ps | grep autobot-log-viewer`
   - Test log ingestion manually with curl

2. **Authentication errors**
   - Seq may not require authentication by default
   - Try accessing without login first
   - Check container logs: `docker logs autobot-log-viewer`

3. **Container discovery issues**
   - Verify AutoBot containers are running: `docker ps`
   - Check container naming conventions
   - Review log forwarder output for discovered containers

### Log Verification
```bash
# Check if Seq is receiving logs
curl -s "http://localhost:5341/api/events?count=5"

# Send test log manually
curl -X POST http://localhost:5341/api/events/raw \
  -H "Content-Type: application/vnd.serilog.clef" \
  -d '{"@t":"2025-08-21T14:30:00.000Z","@l":"Information","@mt":"Test log from AutoBot","Source":"Test"}'

# Check log forwarder status
tail -f /dev/null & LOG_TAIL_PID=$!; kill $LOG_TAIL_PID
```

## Performance Considerations

### Resource Usage
- **CPU**: Log forwarder uses minimal CPU (~1-2%)
- **Memory**: ~50MB for log forwarder process
- **Network**: Depends on log volume, typically <1MB/min
- **Disk**: Seq stores logs, configure retention policies

### Scaling
- For high-volume environments, consider:
  - Log sampling for non-critical events
  - Separate Seq instances for different log types
  - Log archiving for long-term storage
  - Load balancing for multiple forwarders

## Integration with AutoBot

### Startup Integration
Add to `run_agent.sh`:
```bash
# Start log analytics if requested
if [ "$ENABLE_SEQ_LOGGING" = "true" ]; then
    echo "🔄 Starting Seq log analytics..."
    ./scripts/start_seq.sh &
    SEQ_PID=$!
    echo "📊 Seq analytics started (PID: $SEQ_PID)"
fi
```

### Configuration
In `src/config.py`:
```python
# Seq logging configuration
SEQ_ENABLED = os.getenv('AUTOBOT_SEQ_ENABLED', 'false').lower() == 'true'
SEQ_URL = os.getenv('AUTOBOT_SEQ_URL', 'http://localhost:5341')
SEQ_API_KEY = os.getenv('AUTOBOT_SEQ_API_KEY', '')
```

## Security Notes

- Seq dashboard may contain sensitive log information
- Consider access controls for production environments
- Log retention policies should comply with data governance
- API keys should be rotated regularly
- Network access to Seq should be restricted as needed

---

**Status**: ✅ Complete log aggregation system implemented
**Last Updated**: 2025-08-21
**Version**: 1.0
