# SLM Server API - Quick Reference

## Installation

```bash
cd /home/kali/Desktop/AutoBot/slm-server
pip install paramiko>=3.0.0
python migrations/add_events_certificates_updates_tables.py
python main.py
```

## API Base URL

```
http://localhost:8080/api
```

## Authentication

```bash
# Get token
TOKEN=$(curl -X POST http://localhost:8080/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r .access_token)

# Use token
curl http://localhost:8080/api/nodes \
  -H "Authorization: Bearer $TOKEN"
```

## New Endpoints

### 1. Test SSH Connection

```bash
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

**Response:**
```json
{
  "success": true,
  "message": "SSH connection successful",
  "os_info": "Linux 5.15.0-91-generic x86_64",
  "connection_time_ms": 234.5
}
```

### 2. Get Node Events

```bash
# All events
curl http://localhost:8080/api/nodes/abc123/events \
  -H "Authorization: Bearer $TOKEN"

# Filter by type
curl "http://localhost:8080/api/nodes/abc123/events?type=deployment_completed" \
  -H "Authorization: Bearer $TOKEN"

# Filter by severity
curl "http://localhost:8080/api/nodes/abc123/events?severity=error&page=1&per_page=20" \
  -H "Authorization: Bearer $TOKEN"
```

**Event Types:**
- node_registered, node_enrolled
- heartbeat_received, heartbeat_missed
- status_changed
- deployment_started, deployment_completed, deployment_failed
- certificate_issued, certificate_renewed, certificate_expired
- ssh_connection_failed, ssh_connection_success

**Severity Levels:**
- info, warning, error, critical

### 3. Certificate Management

```bash
# Get certificate
curl http://localhost:8080/api/nodes/abc123/certificate \
  -H "Authorization: Bearer $TOKEN"

# Renew certificate
curl -X POST http://localhost:8080/api/nodes/abc123/certificate/renew \
  -H "Authorization: Bearer $TOKEN"

# Deploy certificate
curl -X POST http://localhost:8080/api/nodes/abc123/certificate/deploy \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Update Management

```bash
# Check for updates (all)
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

## Python Examples

### Test SSH Connection

```python
import httpx

async def test_ssh():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8080/api/nodes/test-connection",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "ip_address": "172.16.168.21",
                "ssh_user": "autobot",
                "ssh_port": 22,
                "ssh_password": "password"
            }
        )
        return response.json()
```

### Get Node Events

```python
async def get_events(node_id: str, event_type: str = None):
    params = {}
    if event_type:
        params["type"] = event_type

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://localhost:8080/api/nodes/{node_id}/events",
            headers={"Authorization": f"Bearer {token}"},
            params=params
        )
        return response.json()
```

### Renew Certificate

```python
async def renew_cert(node_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://localhost:8080/api/nodes/{node_id}/certificate/renew",
            headers={"Authorization": f"Bearer {token}"}
        )
        return response.json()
```

### Apply Updates

```python
async def apply_updates(node_id: str, update_ids: list):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8080/api/updates/apply",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "node_id": node_id,
                "update_ids": update_ids
            }
        )
        return response.json()
```

## Database Queries

### Get Recent Events

```sql
SELECT * FROM node_events
WHERE node_id = 'abc123'
ORDER BY created_at DESC
LIMIT 10;
```

### Get Active Certificates

```sql
SELECT * FROM certificates
WHERE status = 'active'
AND expires_at > datetime('now');
```

### Get Pending Updates

```sql
SELECT * FROM updates
WHERE is_applied = 0
ORDER BY severity DESC, created_at DESC;
```

## Error Codes

- `200 OK` - Success
- `201 Created` - Resource created
- `204 No Content` - Success, no response body
- `400 Bad Request` - Invalid input
- `401 Unauthorized` - Missing/invalid token
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

## Common Issues

### SSH Connection Fails
- Check network connectivity
- Verify SSH service running
- Confirm credentials
- Check firewall rules

### Events Not Found
- Verify node exists
- Check node_id is correct
- Ensure migration was run

### Certificate 404
- Create certificate first (POST renew)
- Check node_id exists

### Updates Empty
- Create test update records
- Verify node_id filter

## Documentation

- Full API docs: `/api/docs` (when server running in debug mode)
- Complete reference: `docs/API_ENDPOINTS.md`
- Implementation details: `docs/IMPLEMENTATION_SUMMARY.md`
- README: `README_NEW_ENDPOINTS.md`
- Changes: `CHANGES.txt`

## Support

Run verification:
```bash
python scripts/verify_endpoints.py
```

Check server health:
```bash
curl http://localhost:8080/api/health
```

View server logs:
```bash
# Check console output where server is running
```
