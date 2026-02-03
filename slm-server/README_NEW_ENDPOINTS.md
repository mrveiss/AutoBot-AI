# SLM Server - New API Endpoints Implementation

**Implementation Date:** 2026-01-15
**Author:** mrveiss
**Version:** 1.0.0

## Overview

This implementation adds seven new API endpoints to the Service Lifecycle Manager (SLM) server, providing complete host management functionality including SSH connection testing, lifecycle event tracking, PKI certificate management, and system update management.

## New Features

### 1. SSH Connection Testing
- Test SSH connectivity before node registration
- Validates credentials and retrieves OS information
- Returns connection timing metrics
- Handles authentication failures gracefully

### 2. Node Lifecycle Events
- Track all significant node lifecycle events
- Filter by event type and severity
- Paginated event history
- Structured event details in JSON format

### 3. PKI Certificate Management
- View certificate status and expiration
- Renew certificates with automatic rotation
- Deploy certificates via Ansible
- SHA256 fingerprint tracking

### 4. System Update Management
- Check for available updates per node
- Severity-based update prioritization
- Batch update application
- Update tracking and audit trail

## Quick Start

### 1. Install Dependencies

```bash
cd /home/kali/Desktop/AutoBot/slm-server
pip install -r requirements.txt
```

### 2. Run Database Migration

```bash
python migrations/add_events_certificates_updates_tables.py
```

Or specify custom database path:

```bash
python migrations/add_events_certificates_updates_tables.py /path/to/slm.db
```

### 3. Verify Installation

```bash
python scripts/verify_endpoints.py
```

### 4. Start Server

```bash
python main.py
```

### 5. Access API Documentation

Open in browser:
```
http://localhost:8080/api/docs
```

## API Endpoints

### SSH Connection Testing

```bash
# Test SSH connection
curl -X POST http://localhost:8080/api/nodes/test-connection \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "ip_address": "172.16.168.21",
    "ssh_user": "autobot",
    "ssh_port": 22,
    "ssh_password": "password"
  }'
```

### Node Events

```bash
# Get all events for a node
curl http://localhost:8080/api/nodes/{node_id}/events \
  -H "Authorization: Bearer $TOKEN"

# Filter by event type
curl "http://localhost:8080/api/nodes/{node_id}/events?type=deployment_completed" \
  -H "Authorization: Bearer $TOKEN"

# Filter by severity
curl "http://localhost:8080/api/nodes/{node_id}/events?severity=error" \
  -H "Authorization: Bearer $TOKEN"
```

### Certificate Management

```bash
# Get certificate status
curl http://localhost:8080/api/nodes/{node_id}/certificate \
  -H "Authorization: Bearer $TOKEN"

# Renew certificate
curl -X POST http://localhost:8080/api/nodes/{node_id}/certificate/renew \
  -H "Authorization: Bearer $TOKEN"

# Deploy certificate
curl -X POST http://localhost:8080/api/nodes/{node_id}/certificate/deploy \
  -H "Authorization: Bearer $TOKEN"
```

### Update Management

```bash
# Check for updates (all nodes)
curl http://localhost:8080/api/updates/check \
  -H "Authorization: Bearer $TOKEN"

# Check for updates (specific node)
curl "http://localhost:8080/api/updates/check?node_id=abc123" \
  -H "Authorization: Bearer $TOKEN"

# Apply updates
curl -X POST http://localhost:8080/api/updates/apply \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "abc123",
    "update_ids": ["upd-001", "upd-002"]
  }'
```

## Database Schema

### NodeEvent Table

```sql
CREATE TABLE node_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id VARCHAR(64) UNIQUE NOT NULL,
    node_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) DEFAULT 'info',
    message TEXT NOT NULL,
    details JSON DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Certificate Table

```sql
CREATE TABLE certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    certificate_id VARCHAR(64) UNIQUE NOT NULL,
    node_id VARCHAR(64) NOT NULL,
    fingerprint VARCHAR(128) NOT NULL,
    issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    public_key TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### UpdateInfo Table

```sql
CREATE TABLE updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    update_id VARCHAR(64) UNIQUE NOT NULL,
    node_id VARCHAR(64),
    package_name VARCHAR(255) NOT NULL,
    current_version VARCHAR(64),
    available_version VARCHAR(64) NOT NULL,
    update_type VARCHAR(20) DEFAULT 'package',
    severity VARCHAR(20) DEFAULT 'normal',
    description TEXT,
    is_applied BOOLEAN DEFAULT 0,
    applied_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Event Types

The system tracks 13 different event types:

- `node_registered` - Node first registered
- `node_enrolled` - Node enrollment completed
- `heartbeat_received` - Regular heartbeat received
- `heartbeat_missed` - Expected heartbeat not received
- `status_changed` - Node status changed
- `deployment_started` - Deployment initiated
- `deployment_completed` - Deployment successful
- `deployment_failed` - Deployment failed
- `certificate_issued` - New certificate issued
- `certificate_renewed` - Certificate renewed
- `certificate_expired` - Certificate expired
- `ssh_connection_failed` - SSH test failed
- `ssh_connection_success` - SSH test succeeded

## Event Severity Levels

- `info` - Informational events
- `warning` - Potential issues
- `error` - Error conditions
- `critical` - Critical failures

## Code Structure

```
slm-server/
├── api/
│   ├── nodes.py          # SSH, Events, Certificates (5 new endpoints)
│   └── updates.py        # Update management (2 new endpoints)
├── models/
│   ├── database.py       # NodeEvent, Certificate, UpdateInfo models
│   └── schemas.py        # Request/response schemas
├── migrations/
│   └── add_events_certificates_updates_tables.py
├── scripts/
│   └── verify_endpoints.py
└── docs/
    ├── API_ENDPOINTS.md
    └── IMPLEMENTATION_SUMMARY.md
```

## Testing

### Manual Testing

1. **Test SSH Connection:**
   ```bash
   # Should succeed
   curl -X POST http://localhost:8080/api/nodes/test-connection \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"ip_address": "172.16.168.21", "ssh_user": "autobot", "ssh_password": "correct_password"}'

   # Should fail
   curl -X POST http://localhost:8080/api/nodes/test-connection \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"ip_address": "172.16.168.21", "ssh_user": "autobot", "ssh_password": "wrong_password"}'
   ```

2. **Test Event Creation:**
   - Register a node
   - Check events endpoint
   - Verify event was created

3. **Test Certificate Lifecycle:**
   - Get certificate status (should 404 if none exists)
   - Renew certificate
   - Get certificate status again (should return new cert)
   - Renew again (old cert should be expired)

4. **Test Update Management:**
   - Create some update records in database
   - Check updates
   - Apply updates
   - Verify job creation

### Automated Testing

Create unit tests for:
- SSH connection with mock paramiko
- Event creation and retrieval
- Certificate renewal logic
- Update filtering

## Security Considerations

1. **SSH Passwords:** Never stored in responses or logs
2. **JWT Authentication:** All endpoints require valid token
3. **Input Validation:** Pydantic schemas validate all inputs
4. **SQL Injection:** SQLAlchemy ORM prevents injection
5. **Rate Limiting:** Consider adding for SSH testing endpoint

## Performance Considerations

1. **SSH Testing:** Uses thread pool to avoid blocking
2. **Event Pagination:** Limits query results
3. **Database Indexes:** All foreign keys and query fields indexed
4. **Async Operations:** All endpoints use async/await

## Known Limitations

1. **Certificate Generation:** Currently creates dummy certificates
   - Replace with real PKI in production
   - Integrate with proper CA

2. **Update Application:** Only creates job, doesn't execute
   - Implement Ansible playbook execution
   - Add update rollback capability

3. **SSH Key Support:** Only password authentication tested
   - Add SSH key validation
   - Support key-based auth

## Future Enhancements

1. **Event Subscriptions:** WebSocket notifications for events
2. **Scheduled Updates:** Cron-based update scheduling
3. **Certificate Monitoring:** Automatic expiration alerts
4. **SSH Key Management:** Full PKI integration
5. **Update Dependencies:** Dependency resolution
6. **Rollback Support:** Update and deployment rollbacks

## Troubleshooting

### SSH Connection Test Fails

1. Check network connectivity
2. Verify SSH service is running on target
3. Confirm credentials are correct
4. Check firewall rules

### Events Not Showing

1. Verify migration was run
2. Check database file permissions
3. Confirm node_id exists

### Certificate Operations Fail

1. Ensure node exists
2. Check database write permissions
3. Verify migration created tables

### Updates Not Found

1. Create test update records
2. Verify node_id matches
3. Check is_applied flag

## Support

For issues or questions:
- Check `docs/API_ENDPOINTS.md` for complete API reference
- Review `docs/IMPLEMENTATION_SUMMARY.md` for design details
- Run `python scripts/verify_endpoints.py` to verify installation

## License

AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss
