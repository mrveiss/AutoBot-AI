# SSH Connection Manager - Multi-Host Terminal Access

## Overview

The SSH Connection Manager provides secure, efficient remote terminal access to all AutoBot hosts through a connection pool architecture. This enables agents and users to execute commands on any of the 6 distributed hosts while maintaining security, performance, and audit compliance.

## Features

- **Connection Pooling**: Efficient SSH connection reuse (max 5 connections per host)
- **Health Monitoring**: Automatic health checks every 60 seconds
- **Timeout Management**: 300s idle timeout, 30s connect timeout
- **Security Validation**: Integration with SecureCommandExecutor for command risk assessment
- **Audit Logging**: Comprehensive logging of all SSH operations
- **Multi-Host Support**: Manages all 6 AutoBot hosts from single interface
- **Error Handling**: Exponential backoff retry logic for failed connections
- **Interactive PTY**: Support for interactive terminal sessions
- **Batch Execution**: Execute commands on multiple hosts in parallel or sequentially

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Remote Terminal API                       │
│  FastAPI endpoints + WebSocket for real-time interaction    │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                      SSH Manager                             │
│  Host configuration, command execution, security validation  │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                  SSH Connection Pool                         │
│  Connection lifecycle, health checks, timeout management     │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    Paramiko SSH Client                       │
│  Low-level SSH protocol implementation                       │
└─────────────────────────────────────────────────────────────┘
```

### Host Configuration

AutoBot manages 6 distributed hosts:

| Host | IP | Port | Description |
|------|-------|------|-------------|
| main | 172.16.168.20 | 22 | Main machine - Backend API + VNC Desktop |
| frontend | 172.16.168.21 | 22 | Frontend VM - Web interface |
| npu-worker | 172.16.168.22 | 22 | NPU Worker VM - Hardware AI acceleration |
| redis | 172.16.168.23 | 22 | Redis VM - Data layer |
| ai-stack | 172.16.168.24 | 22 | AI Stack VM - AI processing |
| browser | 172.16.168.25 | 22 | Browser VM - Web automation (Playwright) |

## Installation & Setup

### Prerequisites

1. **SSH Key Authentication**:
   ```bash
   # Ensure SSH key exists
   ls ~/.ssh/autobot_key

   # If missing, generate new key
   ssh-keygen -t rsa -b 4096 -f ~/.ssh/autobot_key -N ""
   ```

2. **SSH Access Configuration**:
   ```bash
   # Copy public key to all hosts
   for host in 172.16.168.{20..25}; do
       ssh-copy-id -i ~/.ssh/autobot_key.pub autobot@$host
   done
   ```

3. **Install Dependencies**:
   ```bash
   pip install paramiko pyyaml
   ```

### Configuration

Edit `config/config.yaml`:

```yaml
ssh:
  enabled: true
  key_path: ~/.ssh/autobot_key
  connection_pool:
    max_connections_per_host: 5
    connect_timeout: 30
    idle_timeout: 300
    health_check_interval: 60
  hosts:
    main:
      ip: 172.16.168.20
      port: 22
      user: autobot
      description: Main machine - Backend API + VNC Desktop
      enabled: true
    # ... (other hosts)
```

## Usage

### Python API

#### 1. Initialize SSH Manager

```python
from backend.services.ssh_manager import SSHManager

# Create and start SSH manager
ssh_manager = SSHManager(
    ssh_key_path='~/.ssh/autobot_key',
    config_path='config/config.yaml',
    enable_audit_logging=True
)

await ssh_manager.start()
```

#### 2. Execute Single Command

```python
# Execute command on specific host
result = await ssh_manager.execute_command(
    host='frontend',
    command='systemctl status nginx',
    timeout=30,
    validate=True,  # Enable security validation
    use_pty=False   # Simple command execution
)

print(f"Exit Code: {result.exit_code}")
print(f"Output: {result.stdout}")
print(f"Execution Time: {result.execution_time}s")
```

#### 3. Execute Batch Commands

```python
# Execute on multiple hosts in parallel
results = await ssh_manager.execute_command_all_hosts(
    command='uptime',
    timeout=30,
    validate=True,
    parallel=True
)

for host, result in results.items():
    if isinstance(result, RemoteCommandResult):
        print(f"{host}: {result.stdout}")
```

#### 4. Interactive PTY Session

```python
# Execute interactive command with PTY
result = await ssh_manager.execute_command(
    host='ai-stack',
    command='python3',
    timeout=60,
    use_pty=True  # Enable PTY for interactive commands
)
```

#### 5. Health Checks

```python
# Check health of all hosts
health_status = await ssh_manager.health_check_all_hosts()

for host, is_healthy in health_status.items():
    status = "✓" if is_healthy else "✗"
    print(f"{status} {host}")
```

#### 6. Connection Pool Statistics

```python
# Get pool statistics
stats = await ssh_manager.get_pool_stats()

for pool_key, pool_stats in stats.items():
    print(f"{pool_key}:")
    print(f"  Total: {pool_stats['total']}")
    print(f"  Active: {pool_stats['active']}")
    print(f"  Idle: {pool_stats['idle']}")
```

### REST API Endpoints

#### List Hosts

```bash
GET /api/remote-terminal/hosts

Response:
{
  "hosts": [
    {
      "name": "main",
      "ip": "172.16.168.20",
      "port": 22,
      "username": "autobot",
      "description": "Main machine - Backend API + VNC Desktop",
      "enabled": true
    },
    ...
  ],
  "total": 6,
  "enabled": 6
}
```

#### Execute Command

```bash
POST /api/remote-terminal/execute
Content-Type: application/json

{
  "host": "frontend",
  "command": "systemctl status nginx",
  "timeout": 30,
  "validate": true,
  "use_pty": false
}

Response:
{
  "host": "frontend",
  "command": "systemctl status nginx",
  "stdout": "● nginx.service - A high performance web server\n...",
  "stderr": "",
  "exit_code": 0,
  "success": true,
  "execution_time": 0.234,
  "timestamp": "2025-10-04T10:30:15.123456",
  "security_info": {
    "validated": true,
    "risk_level": "safe"
  }
}
```

#### Batch Execution

```bash
POST /api/remote-terminal/batch
Content-Type: application/json

{
  "hosts": ["main", "frontend", "redis"],
  "command": "uptime",
  "timeout": 30,
  "validate": true,
  "parallel": true
}

Response:
{
  "command": "uptime",
  "hosts": ["main", "frontend", "redis"],
  "parallel": true,
  "results": {
    "main": {
      "stdout": "10:30:15 up 5 days, 12:34, 2 users...",
      "exit_code": 0,
      "success": true
    },
    ...
  },
  "total_hosts": 3,
  "successful": 3
}
```

#### Health Check

```bash
GET /api/remote-terminal/health

Response:
{
  "timestamp": "2025-10-04T10:30:15.123456",
  "hosts": {
    "main": true,
    "frontend": true,
    "npu-worker": false,
    "redis": true,
    "ai-stack": true,
    "browser": true
  },
  "total": 6,
  "healthy": 5,
  "unhealthy": 1,
  "disabled": 0
}
```

#### Connection Pool Stats

```bash
GET /api/remote-terminal/stats

Response:
{
  "timestamp": "2025-10-04T10:30:15.123456",
  "pools": {
    "autobot@172.16.168.20:22": {
      "total": 2,
      "idle": 1,
      "active": 1,
      "unhealthy": 0,
      "closed": 0
    },
    ...
  },
  "total_connections": 5,
  "active_connections": 2,
  "idle_connections": 3
}
```

### WebSocket Terminal

#### Create Interactive Session

```javascript
// Create session
const response = await fetch('/api/remote-terminal/sessions', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    host: 'frontend',
    session_type: 'interactive'
  })
});

const { session_id, websocket_url } = await response.json();

// Connect WebSocket
const ws = new WebSocket(`ws://localhost:8001${websocket_url}`);

// Initialize connection
ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'init',
    host: 'frontend'
  }));
};

// Handle messages
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);

  switch (message.type) {
    case 'connected':
      console.log('Connected to', message.host);
      break;
    case 'output':
      console.log(message.content);
      break;
    case 'error':
      console.error(message.content);
      break;
  }
};

// Send commands
ws.send(JSON.stringify({
  type: 'input',
  text: 'ls -la\n'
}));
```

## Security Features

### Command Validation

All commands are validated through SecureCommandExecutor:

```python
# Dangerous commands are blocked
await ssh_manager.execute_command(
    host='redis',
    command='rm -rf /',  # BLOCKED
    validate=True
)
# Raises PermissionError: Command blocked
```

### Risk Levels

Commands are classified by risk:

- **SAFE**: Standard commands (echo, ls, pwd, etc.)
- **MODERATE**: Commands requiring sudo, chmod, package installation
- **HIGH**: Commands with redirection, pipes, multiple commands
- **DANGEROUS**: Destructive commands (rm -rf, dd, mkfs, etc.)

### Audit Logging

All SSH operations are logged to `logs/audit.log`:

```json
{
  "timestamp": "2025-10-04T10:30:15.123456",
  "event_type": "command_execution",
  "data": {
    "host": "frontend",
    "command": "systemctl restart nginx",
    "timeout": 30,
    "use_pty": false,
    "validated": true
  }
}
```

## Performance Optimization

### Connection Pooling

- **Reuse**: Connections are reused across multiple commands
- **Limit**: Maximum 5 connections per host prevents resource exhaustion
- **Cleanup**: Idle connections closed after 300s

### Health Monitoring

- **Interval**: Health checks every 60s
- **Method**: Execute simple `echo` command
- **Action**: Unhealthy connections removed from pool

### Retry Logic

Failed connections retry with exponential backoff:

1. **Attempt 1**: Immediate
2. **Attempt 2**: 1s delay
3. **Attempt 3**: 2s delay

## Troubleshooting

### Connection Failures

```python
# Debug connection issues
import logging
logging.getLogger('backend.services.ssh_connection_pool').setLevel(logging.DEBUG)

# Test individual host
result = await ssh_manager.execute_command(
    host='problematic_host',
    command='echo "test"',
    timeout=10
)
```

### Permission Issues

```bash
# Verify SSH key permissions
chmod 600 ~/.ssh/autobot_key
chmod 644 ~/.ssh/autobot_key.pub

# Test SSH access manually
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21
```

### Pool Exhaustion

```python
# Monitor pool usage
stats = await ssh_manager.get_pool_stats()
print(f"Active connections: {sum(s['active'] for s in stats.values())}")

# Increase pool size in config.yaml
ssh:
  connection_pool:
    max_connections_per_host: 10  # Increased from 5
```

## Testing

### Unit Tests

```bash
# Run unit tests
pytest tests/test_ssh_connection_pool.py -v
```

### Integration Tests

```bash
# Run integration tests (requires SSH access)
pytest tests/test_ssh_manager_integration.py -v -m integration

# Run specific test
pytest tests/test_ssh_manager_integration.py::test_execute_command_simple -v
```

### Manual Testing

```python
# Quick manual test
from backend.services.ssh_manager import SSHManager

async def test():
    manager = SSHManager()
    await manager.start()

    result = await manager.execute_command(
        host='main',
        command='echo "Hello from SSH Manager"'
    )

    print(result.stdout)
    await manager.stop()

import asyncio
asyncio.run(test())
```

## Best Practices

1. **Use Connection Pooling**: Let the pool manage connections, don't create direct SSH clients
2. **Enable Validation**: Always validate commands in production (`validate=True`)
3. **Set Timeouts**: Specify reasonable timeouts to prevent hanging
4. **Monitor Health**: Regularly check host health status
5. **Review Audit Logs**: Monitor SSH activity for security compliance
6. **Use PTY Wisely**: Only enable PTY for interactive commands
7. **Batch Operations**: Use parallel execution for independent commands

## Migration from Direct SSH

### Before (Direct SSH)

```python
import paramiko

client = paramiko.SSHClient()
client.connect(hostname='172.16.168.21', username='autobot', key_filename='~/.ssh/autobot_key')
stdin, stdout, stderr = client.exec_command('ls')
output = stdout.read().decode()
client.close()
```

### After (SSH Manager)

```python
from backend.services.ssh_manager import SSHManager

ssh_manager = SSHManager()
await ssh_manager.start()

result = await ssh_manager.execute_command(
    host='frontend',
    command='ls'
)
print(result.stdout)

# Connection automatically pooled and reused
```

## API Reference

See source code documentation:
- `backend/services/ssh_connection_pool.py` - Connection pool implementation
- `backend/services/ssh_manager.py` - SSH manager service
- `backend/api/remote_terminal.py` - REST API endpoints

## Support

For issues or questions:
1. Check logs in `logs/audit.log`
2. Review configuration in `config/config.yaml`
3. Run health checks via API
4. Examine connection pool statistics

## Version History

- **1.0.0** (2025-10-04): Initial implementation
  - Connection pooling with health monitoring
  - Multi-host command execution
  - Security validation integration
  - Comprehensive audit logging
  - REST API and WebSocket support
