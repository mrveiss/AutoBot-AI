# Log Forwarding

**Author**: mrveiss
**Copyright**: © 2025 mrveiss

## Overview

AutoBot's Log Forwarding feature enables centralized log aggregation by forwarding logs from all distributed services to external logging platforms. Configure and manage log destinations through the GUI Settings panel.

## Supported Destinations

| Destination | Protocol | Use Case |
|-------------|----------|----------|
| **Seq** | HTTP/CLEF | Structured logging with web UI, .NET ecosystem |
| **Elasticsearch** | HTTP/Bulk API | Full-text search, Kibana dashboards |
| **Grafana Loki** | HTTP/Push API | Lightweight, native Grafana integration |
| **Syslog** | UDP/TCP/TCP+TLS | Traditional Unix logging, network devices |
| **Webhook** | HTTP POST | Custom integrations (Slack, Discord, PagerDuty) |
| **File** | Local filesystem | Backup/archive, compliance requirements |

## Quick Start

### 1. Access Log Forwarding Settings

Navigate to **Settings** → **Log Forwarding** tab in the AutoBot web interface.

### 2. Add a Destination

1. Click **Add Destination**
2. Select destination type (Seq, Elasticsearch, Loki, Syslog, Webhook, or File)
3. Configure connection settings
4. Click **Test Connection** to verify
5. Save the destination

### 3. Start Forwarding

Toggle the **Service Status** switch to start forwarding logs to all enabled destinations.

## Configuration Guide

### Seq

Seq is a structured logging server ideal for .NET applications and CLEF format logs.

```
Name: production-seq
Type: Seq
URL: http://seq-server:5341
API Key: (optional, for authentication)
Min Level: Information
```

**Features:**
- Real-time log streaming
- Powerful query language
- Dashboards and alerts
- Signal-based filtering

### Elasticsearch

Send logs to Elasticsearch for full-text search and Kibana visualization.

```
Name: elk-cluster
Type: Elasticsearch
URL: http://elasticsearch:9200
Index: autobot-logs
Username: elastic (optional)
Password: ******* (optional)
Min Level: Information
```

**Index Pattern:** Logs are indexed as `{index}-YYYY.MM.DD` for daily rotation.

### Grafana Loki

Lightweight log aggregation designed for Grafana.

```
Name: loki-prod
Type: Loki
URL: http://loki:3100
Min Level: Debug
```

**Labels Applied:**
- `job`: autobot
- `source`: (container name or log file)
- `level`: (log level)

### Syslog

Traditional syslog forwarding with UDP, TCP, or TCP+TLS support.

```
Name: syslog-server
Type: Syslog
Host: 192.168.168.49
Port: 514
Protocol: UDP | TCP | TCP+TLS
Min Level: Warning
```

**Protocol Options:**

| Protocol | Port | Use Case |
|----------|------|----------|
| UDP | 514 | Fast, fire-and-forget, LAN only |
| TCP | 514 | Reliable delivery, no encryption |
| TCP+TLS | 6514 | Secure, encrypted transmission |

**TLS Configuration (TCP+TLS only):**
- **CA Certificate**: Path to CA cert for server verification
- **Client Certificate**: Path to client cert for mutual TLS
- **Client Key**: Path to client private key
- **Verify SSL**: Enable/disable certificate verification

### Webhook

Send logs as JSON payloads to any HTTP endpoint.

```
Name: slack-alerts
Type: Webhook
URL: https://hooks.slack.com/services/XXX/YYY/ZZZ
Min Level: Error
```

**Payload Format:**
```json
{
  "timestamp": "2025-01-06T12:00:00.000Z",
  "level": "Error",
  "message": "Connection timeout to database",
  "source": "Backend-Main",
  "properties": {
    "host": "autobot-main",
    "service": "api"
  }
}
```

### File

Write logs to local files for archival or compliance.

```
Name: archive-logs
Type: File
Path: /var/log/autobot/forwarded.log
Min Level: Information
```

**Features:**
- Automatic rotation (configurable size/time)
- Compression support
- Retention policies

## Scope Configuration

### Global Scope

Forward logs from **all AutoBot hosts** to the destination.

```
Scope: Global
```

Hosts included:
- autobot-main (172.16.168.20) - Backend API
- autobot-frontend (172.16.168.21) - Web interface
- autobot-npu-worker (172.16.168.22) - NPU acceleration
- autobot-redis (172.16.168.23) - Redis data layer
- autobot-ai-stack (172.16.168.24) - AI processing
- autobot-browser (172.16.168.25) - Browser automation

### Per-Host Scope

Forward logs from **selected hosts only**.

```
Scope: Per-Host
Target Hosts: [autobot-main, autobot-ai-stack]
```

Use cases:
- Separate production/development logs
- Route critical services to premium logging
- Reduce log volume for cost optimization

## API Reference

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/log-forwarding/destinations` | List all destinations |
| POST | `/api/log-forwarding/destinations` | Create destination |
| PUT | `/api/log-forwarding/destinations/{name}` | Update destination |
| DELETE | `/api/log-forwarding/destinations/{name}` | Delete destination |
| POST | `/api/log-forwarding/destinations/{name}/test` | Test connectivity |
| POST | `/api/log-forwarding/test-all` | Test all destinations |
| GET | `/api/log-forwarding/status` | Get service status |
| POST | `/api/log-forwarding/start` | Start forwarding |
| POST | `/api/log-forwarding/stop` | Stop forwarding |
| GET | `/api/log-forwarding/destination-types` | List supported types |
| GET | `/api/log-forwarding/known-hosts` | List AutoBot hosts |

### Example: Create Syslog Destination

```bash
curl -X POST http://localhost:8001/api/log-forwarding/destinations \
  -H "Content-Type: application/json" \
  -d '{
    "name": "central-syslog",
    "type": "syslog",
    "host": "192.168.168.49",
    "port": 514,
    "syslog_protocol": "udp",
    "min_level": "Information",
    "scope": "global",
    "enabled": true
  }'
```

### Example: Test Connection

```bash
curl -X POST http://localhost:8001/api/log-forwarding/destinations/central-syslog/test
```

Response:
```json
{
  "success": true,
  "message": "Connection successful",
  "latency_ms": 12.5
}
```

## Troubleshooting

### Connection Failed

**Symptoms:** Test connection fails, destination shows unhealthy.

**Solutions:**
1. Verify URL/host is reachable: `nc -zv host port`
2. Check firewall rules allow outbound traffic
3. Verify credentials are correct
4. For TLS: Ensure certificates are valid and paths are correct

### Logs Not Appearing

**Symptoms:** Forwarding is running but no logs in destination.

**Solutions:**
1. Check min level filter (Debug logs won't appear if set to Warning)
2. Verify destination is enabled
3. Check batch settings (logs are batched before sending)
4. Review error count in destination status

### High Memory Usage

**Symptoms:** Log forwarder consuming excessive memory.

**Solutions:**
1. Reduce batch size
2. Increase batch timeout to send more frequently
3. Add destinations with faster response times
4. Filter by higher log level to reduce volume

### SSL/TLS Errors

**Symptoms:** TCP+TLS connections fail with certificate errors.

**Solutions:**
1. Verify CA certificate path is correct
2. Ensure certificate is not expired: `openssl x509 -in cert.pem -noout -dates`
3. For self-signed certs, disable SSL verification (not recommended for production)
4. Check certificate chain is complete

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AutoBot Log Sources                       │
├─────────────┬─────────────┬─────────────┬──────────────────┤
│   Docker    │  Log Files  │   Backend   │   Frontend       │
│ Containers  │  (*.log)    │   Process   │   (Console)      │
└──────┬──────┴──────┬──────┴──────┬──────┴────────┬─────────┘
       │             │             │               │
       └─────────────┴──────┬──────┴───────────────┘
                            │
                   ┌────────▼────────┐
                   │  Log Forwarder  │
                   │    Service      │
                   │  (Queue-based)  │
                   └────────┬────────┘
                            │
       ┌──────────┬─────────┼─────────┬──────────┐
       │          │         │         │          │
┌──────▼───┐ ┌────▼────┐ ┌──▼──┐ ┌────▼────┐ ┌───▼───┐
│   Seq    │ │Elastic- │ │Loki │ │ Syslog  │ │Webhook│
│  (CLEF)  │ │ search  │ │     │ │UDP/TCP  │ │ HTTP  │
└──────────┘ └─────────┘ └─────┘ └─────────┘ └───────┘
```

## Security Considerations

### Credentials

- API keys and passwords are stored encrypted in configuration
- Credentials are masked in API responses (show only last 4 characters)
- Use environment variables for sensitive values in production

### TLS/SSL

- Always use TCP+TLS for syslog over untrusted networks
- Verify server certificates to prevent MITM attacks
- Use mutual TLS (client certificates) for high-security environments

### Path Validation

- Certificate paths are validated to prevent directory traversal
- Only paths within allowed directories are accepted
- Symlinks are resolved and validated

## Files

| File | Purpose |
|------|---------|
| `scripts/logging/log_forwarder.py` | Core forwarding service |
| `backend/api/log_forwarding.py` | REST API endpoints |
| `autobot-vue/src/components/settings/LogForwardingSettings.vue` | GUI component |
| `config/log_forwarding.json` | Persistent configuration (auto-generated) |

## Related

- [Logging Standards](../developer/LOGGING_STANDARDS.md) - Application logging guidelines
- [Infrastructure Deployment](../developer/INFRASTRUCTURE_DEPLOYMENT.md) - VM architecture
- [SSOT Configuration](../developer/SSOT_CONFIG_GUIDE.md) - Centralized configuration
