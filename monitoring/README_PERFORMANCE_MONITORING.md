# AutoBot Performance Monitoring System

> **⚠️ DEPRECATED (Issue #469)**
>
> This legacy monitoring directory is deprecated as of Issue #469 - Prometheus/Grafana consolidation.
>
> **Use instead:**
> - **Prometheus Metrics**: `src/monitoring/prometheus_metrics.py` with domain-specific recorders
> - **Grafana Dashboards**: `config/grafana/dashboards/` (9 dashboards including autobot-performance.json)
> - **Frontend Integration**: `autobot-vue/src/composables/usePrometheusMetrics.ts`
> - **Backend API**: `/api/monitoring/metrics` endpoint
>
> **Scheduled for removal**: v3.0
>
> **Migration complete**: All metrics now flow through Prometheus with:
> - `PerformanceMetricsRecorder` for GPU/NPU/Performance metrics
> - Real-time alerts via `autobot_performance_alerts_total`
> - Multi-modal processing via `autobot_multimodal_processing_seconds`
> - Full Grafana visualization at `config/grafana/dashboards/autobot-performance.json`

---

## Overview (Legacy Documentation)

The AutoBot Performance Monitoring System is a comprehensive, enterprise-grade monitoring solution designed specifically for AutoBot's distributed architecture across 6 VMs. It provides real-time performance monitoring, automated optimization, benchmarking capabilities, and intelligent alerting.

## Architecture

### Distributed System Monitoring
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Main (WSL)    │    │  Frontend VM    │    │ NPU Worker VM   │
│ 172.16.168.20   │    │ 172.16.168.21   │    │ 172.16.168.22   │
│ Backend + Ollama│    │   Vue.js App    │    │ AI Acceleration │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Redis VM      │    │  AI Stack VM    │    │  Browser VM     │
│ 172.16.168.23   │    │ 172.16.168.24   │    │ 172.16.168.25   │
│   Data Layer    │    │ AI Processing   │    │ Web Automation  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Hardware Optimization
- **CPU**: Intel Ultra 9 185H (22 cores) - Optimized for multi-threaded workloads
- **Memory**: 46GB RAM - Efficient memory usage monitoring and cleanup
- **GPU**: NVIDIA RTX 4070 - AI workload acceleration monitoring
- **NPU**: Intel AI Boost - Hardware AI inference optimization
- **Storage**: 1TB+ SSD - High-performance disk I/O monitoring

## Components

### 1. Performance Monitor (`performance_monitor.py`)
**Real-time system monitoring across distributed infrastructure**

- **System Metrics**: CPU, memory, disk, network utilization
- **Service Health**: API response times, service availability
- **Database Performance**: Redis operations, connection pooling
- **Inter-VM Communication**: Latency, throughput, packet loss
- **Hardware Utilization**: GPU, NPU, thermal monitoring

**Key Features**:
- 30-second monitoring intervals (configurable)
- Automatic alert generation
- Historical data storage in Redis
- WebSocket real-time updates

### 2. Performance Dashboard (`performance_dashboard.py`)
**Real-time web interface for monitoring visualization**

- **Interactive Charts**: System performance over time
- **Service Status Grid**: Real-time health indicators
- **VM Communication Map**: Inter-VM performance metrics
- **Alert Management**: Real-time alert notifications
- **Resource Utilization**: CPU, memory, disk, GPU usage

**Dashboard Features**:
- Responsive dark-themed interface
- WebSocket live updates
- Historical performance graphs
- Mobile-friendly design
- Export capabilities

**Access**: `http://localhost:9090`

### 3. Performance Optimizer (`performance_optimizer.py`)
**Automated performance optimization engine**

- **System Optimization**: CPU, memory, disk cleanup
- **Service Optimization**: Restart unhealthy services, configuration tuning
- **Database Optimization**: Redis memory management, connection pooling
- **Network Optimization**: Route optimization, bandwidth tuning
- **Hardware Optimization**: GPU/NPU utilization improvements

**Optimization Categories**:
- **Critical**: Immediate action required (service down, high resource usage)
- **High**: Performance impact optimizations
- **Medium**: Efficiency improvements
- **Low**: Minor optimizations

### 4. Performance Benchmark (`performance_benchmark.py`)
**Comprehensive benchmarking suite**

- **API Benchmarking**: Endpoint response times, throughput testing
- **Database Benchmarking**: Redis operations performance
- **Network Benchmarking**: Inter-VM communication performance
- **System Benchmarking**: CPU, memory, disk I/O performance
- **Comprehensive Testing**: Full system performance evaluation

**Benchmark Types**:
- **Comprehensive**: Full system benchmark (300+ tests)
- **API**: RESTful endpoint performance
- **Database**: Redis performance across all databases
- **Network**: Inter-VM communication testing
- **System**: Hardware performance benchmarking

### 5. Monitor Control (`monitor_control.py`)
**Centralized control system for all monitoring components**

- **Service Management**: Start/stop monitoring components
- **Configuration Management**: Dynamic configuration updates
- **Status Reporting**: System health and performance summaries
- **Benchmark Orchestration**: Scheduled and on-demand benchmarking
- **Alert Management**: Centralized alerting system

## Installation

### Automatic Installation
```bash
# Run the comprehensive installation script
bash scripts/install-performance-monitoring.sh
```

The installer will:
1. Check system requirements
2. Install system dependencies
3. Set up Python virtual environment
4. Configure monitoring directories
5. Install systemd service
6. Configure log rotation
7. Set up dashboard reverse proxy
8. Create utility scripts
9. Validate installation

### Manual Installation

#### 1. Install Dependencies
```bash
# System packages
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv python3-dev build-essential \
    redis-tools htop iotop netstat-nat sysstat nodejs npm nginx

# Python packages
cd /home/kali/Desktop/AutoBot
python3 -m venv venv
source venv/bin/activate
pip install -r monitoring/requirements.txt
```

#### 2. Configure Service
```bash
# Copy service file
sudo cp monitoring/autobot-monitoring.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable autobot-monitoring.service
```

#### 3. Create Directories
```bash
mkdir -p logs/{performance,benchmarks,metrics,alerts}
chmod -R 755 monitoring/ logs/
```

## Configuration

### Main Configuration (`monitoring/monitoring_config.yaml`)

```yaml
# Core Settings
monitoring_interval: 30  # seconds
optimization_interval: 1800  # 30 minutes
dashboard_enabled: true
dashboard_port: 9090

# Alert Thresholds
alert_thresholds:
  cpu_percent: 80.0
  memory_percent: 85.0
  disk_percent: 90.0
  api_response_time: 5.0

# Auto-optimization
auto_optimization_enabled: true
max_optimizations_per_hour: 3
optimization_severity_threshold: "medium"
```

### VM Configuration
Each VM is configured with specific monitoring priorities:

- **Main (Critical)**: Backend API, Ollama LLM
- **Redis (Critical)**: Data layer, all databases
- **Frontend (High)**: Web interface, user experience
- **NPU Worker (High)**: AI acceleration, hardware monitoring
- **AI Stack (High)**: AI processing, model performance
- **Browser (Medium)**: Web automation, Playwright

## Usage

### Service Management

```bash
# Start monitoring system
sudo systemctl start autobot-monitoring.service

# Stop monitoring system
sudo systemctl stop autobot-monitoring.service

# Check service status
sudo systemctl status autobot-monitoring.service

# View service logs
journalctl -u autobot-monitoring.service -f
```

### Command Line Control

```bash
# Start all monitoring components
python monitoring/monitor_control.py --start

# Show current system status
python monitoring/monitor_control.py --status

# Run performance benchmark
python monitoring/monitor_control.py --benchmark comprehensive

# Run single optimization cycle
python monitoring/monitor_control.py --optimize-once

# Start dashboard only
python monitoring/monitor_control.py --dashboard-only
```

### Utility Scripts

```bash
# Quick status check
bash scripts/monitor-status.sh

# Run comprehensive benchmark
bash scripts/run-benchmark.sh comprehensive 300

# Run optimization
bash scripts/run-optimization.sh
```

### Dashboard Access

1. **Direct Access**: http://localhost:9090
2. **Nginx Proxy**: http://localhost (if configured)
3. **Remote Access**: http://172.16.168.20:9090

## Performance Baselines

### Expected Performance Metrics

#### System Performance
- **CPU Usage**: < 20% idle, < 80% under load
- **Memory Usage**: < 70% for optimal performance
- **Disk I/O**: > 500 MB/s sequential read/write
- **Network Latency**: < 5ms inter-VM communication

#### Service Performance  
- **API Response Time**: < 500ms for most endpoints
- **Database Operations**: < 10ms for Redis operations
- **WebSocket Latency**: < 100ms for real-time updates
- **Service Availability**: > 99.9% uptime

#### Hardware Utilization
- **GPU Utilization**: Efficient utilization for AI workloads
- **NPU Utilization**: Optimal inference performance
- **Thermal Management**: CPU < 80°C, GPU < 75°C
- **Memory Bandwidth**: > 40 GB/s effective throughput

### Benchmark Scores

#### Overall System Score Calculation
```
Overall Score = (API Performance × 0.3) + 
                (Database Performance × 0.25) + 
                (Network Performance × 0.2) + 
                (System Performance × 0.25)
```

#### Performance Grades
- **A+ (90-100)**: Exceptional performance
- **A (80-89)**: Excellent performance
- **B+ (70-79)**: Good performance
- **B (60-69)**: Adequate performance
- **C+ (50-59)**: Below expectations
- **C (40-49)**: Poor performance
- **D (<40)**: Critical performance issues

## Monitoring Strategies

### Production Monitoring

#### 24/7 Monitoring
- **Continuous System Monitoring**: Every 30 seconds
- **Automatic Optimization**: Every 30 minutes
- **Daily Benchmarking**: Comprehensive system benchmarks
- **Weekly Deep Analysis**: Full performance reports

#### Alert Management
- **Critical Alerts**: Service failures, system overload
- **High Priority**: Performance degradation, resource exhaustion
- **Medium Priority**: Optimization opportunities
- **Low Priority**: Information and trending data

#### Performance Optimization
- **Proactive Optimization**: Before performance degrades
- **Reactive Optimization**: In response to alerts
- **Scheduled Optimization**: Regular maintenance windows
- **Emergency Optimization**: Critical performance issues

### Development Monitoring

#### Development Workflow
- **Code Impact Monitoring**: Performance impact of changes
- **Resource Usage Tracking**: Development environment optimization
- **Benchmark Comparisons**: Before/after performance testing
- **Optimization Testing**: Validate optimization effectiveness

## Troubleshooting

### Common Issues

#### High CPU Usage
```bash
# Check top CPU consumers
htop

# Run CPU optimization
python monitoring/performance_optimizer.py --analyze

# Check service health
bash scripts/monitor-status.sh
```

#### Memory Issues
```bash
# Check memory usage
free -h

# Check Redis memory usage
redis-cli info memory

# Run memory optimization
python monitoring/monitor_control.py --optimize-once
```

#### Service Failures
```bash
# Check service status
python monitoring/monitor_control.py --status

# Check service logs
journalctl -u autobot-monitoring.service -f

# Restart unhealthy services
systemctl restart autobot-monitoring.service
```

#### Network Issues
```bash
# Test inter-VM connectivity
ping 172.16.168.21  # Frontend VM
ping 172.16.168.23  # Redis VM

# Run network benchmark
python monitoring/monitor_control.py --benchmark network

# Check network optimization opportunities
python monitoring/performance_optimizer.py --analyze
```

### Log Analysis

#### Log Locations
```
/home/kali/Desktop/AutoBot/logs/
├── monitoring_control.log          # Main monitoring logs
├── performance_monitor.log         # Performance data logs
├── optimization.log                # Optimization activities
├── alerts.log                     # Alert notifications
├── performance/                   # Detailed performance data
├── benchmarks/                    # Benchmark results
└── metrics/                       # Historical metrics
```

#### Log Analysis Commands
```bash
# View recent monitoring activity
tail -100 logs/monitoring_control.log

# Search for errors
grep -i error logs/*.log

# View performance trends
tail -50 logs/performance/*.jsonl

# Check optimization results
grep "improvement" logs/optimization.log
```

## API Reference

### REST API Endpoints

#### Dashboard API
```
GET  /api/metrics/current        # Current system metrics
GET  /api/metrics/history        # Historical performance data
GET  /api/system/status          # Overall system status
GET  /api/alerts                # Active alerts
GET  /ws                        # WebSocket endpoint
```

#### Control API
```python
# Monitor Control API
await monitor_control.get_current_status()
await monitor_control.run_single_benchmark('comprehensive')
await monitor_control.optimizer.run_optimization_cycle()
```

### WebSocket Events

#### Real-time Updates
```javascript
// Connect to monitoring WebSocket
const ws = new WebSocket('ws://localhost:9090/ws');

// Handle metrics updates
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'metrics_update') {
        updateDashboard(data.data);
    }
};
```

## Performance Optimization Guide

### System Optimization

#### CPU Optimization
- **Process Priority Tuning**: Adjust process priorities for optimal performance
- **CPU Affinity**: Bind critical processes to specific CPU cores
- **Load Balancing**: Distribute workloads across available cores
- **Thermal Management**: Monitor and manage CPU temperatures

#### Memory Optimization
- **Memory Cleanup**: Regular cleanup of unused memory
- **Cache Optimization**: Optimize system and application caches
- **Swap Management**: Configure optimal swap usage
- **Memory Leak Detection**: Identify and fix memory leaks

#### Disk Optimization
- **I/O Scheduling**: Optimize disk I/O schedulers
- **Disk Cleanup**: Regular cleanup of temporary files and logs
- **File System Optimization**: Optimize file system parameters
- **SSD Optimization**: Configure optimal SSD settings

### Service Optimization

#### Database Optimization
- **Redis Memory Management**: Optimize Redis memory usage
- **Connection Pooling**: Efficient database connection management
- **Query Optimization**: Optimize database queries
- **Index Optimization**: Maintain optimal database indexes

#### API Optimization
- **Response Caching**: Implement intelligent response caching
- **Connection Keep-Alive**: Optimize HTTP connections
- **Payload Compression**: Reduce data transfer overhead
- **Rate Limiting**: Implement intelligent rate limiting

### Network Optimization

#### Inter-VM Communication
- **Route Optimization**: Optimize network routing
- **Bandwidth Management**: Manage bandwidth allocation
- **Connection Pooling**: Efficient connection management
- **Protocol Optimization**: Choose optimal protocols

## Security Considerations

### Monitoring Security
- **Access Control**: Restrict dashboard and API access
- **Data Encryption**: Encrypt sensitive monitoring data
- **Log Security**: Secure log files and prevent tampering
- **Network Security**: Secure inter-VM communication

### Privacy Protection
- **Data Anonymization**: Anonymize personal data in logs
- **Retention Policies**: Implement data retention policies
- **Access Logging**: Log all monitoring access
- **Compliance**: Ensure compliance with data protection regulations

## Future Enhancements

### Planned Features
- **Machine Learning Optimization**: AI-powered performance optimization
- **Predictive Alerting**: Predict performance issues before they occur
- **Auto-Scaling**: Automatic resource scaling based on performance
- **Advanced Analytics**: Deep performance analytics and insights

### Integration Opportunities
- **Prometheus Integration**: Export metrics to Prometheus
- **Grafana Dashboards**: Advanced visualization with Grafana
- **ElasticSearch Integration**: Enhanced log analysis
- **Slack/Email Notifications**: Advanced alerting channels

## Support and Maintenance

### Regular Maintenance
- **Weekly Performance Reviews**: Review performance trends
- **Monthly Optimization**: Comprehensive optimization cycles
- **Quarterly Benchmarking**: Full system benchmarking
- **Annual Hardware Assessment**: Evaluate hardware upgrades

### Performance Tuning
- **Baseline Establishment**: Establish performance baselines
- **Trend Analysis**: Analyze performance trends
- **Bottleneck Identification**: Identify and resolve bottlenecks
- **Capacity Planning**: Plan for future capacity requirements

## Conclusion

The AutoBot Performance Monitoring System provides comprehensive, enterprise-grade monitoring capabilities specifically designed for AutoBot's distributed infrastructure. With real-time monitoring, automated optimization, and intelligent alerting, it ensures optimal performance across all 6 VMs while leveraging advanced hardware acceleration capabilities.

The system is designed for both production deployment and development use, providing the insights and automation needed to maintain peak performance in AutoBot's complex multi-modal AI platform.

For additional support or feature requests, refer to the AutoBot documentation or contact the development team.