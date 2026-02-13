# Consolidated Terminal API Documentation

## Overview

The Consolidated Terminal API unifies four separate terminal implementations into a single, cohesive system providing REST endpoints and WebSocket connections for secure terminal operations.

## Architecture

### Consolidated Components

The new API consolidates features from:
- **terminal.py**: Main REST API endpoints
- **simple_terminal_websocket.py**: Simple WebSocket + workflow control
- **secure_terminal_websocket.py**: Security auditing + command logging
- **base_terminal.py**: PTY infrastructure and process management

### Base URL
```
/api/terminal/consolidated
```

## Security Levels

### Available Security Levels
- **STANDARD**: Default level, allows most commands
- **ELEVATED**: Blocks dangerous commands, requires confirmation for risky operations
- **RESTRICTED**: Blocks both dangerous and high-risk commands

### Command Risk Assessment
Commands are automatically assessed for security risks:
- **SAFE**: Basic commands like `echo`, `pwd`, `ls`
- **MODERATE**: Commands requiring elevated privileges like `sudo`, `chmod`
- **HIGH**: Commands with redirection or complex operations
- **DANGEROUS**: Destructive commands like `rm -rf`, `dd`, system shutdowns

## REST API Endpoints

### Session Management

#### Create Terminal Session
```http
POST /api/terminal/consolidated/sessions
Content-Type: application/json

{
  "user_id": "string",
  "security_level": "standard|elevated|restricted",
  "enable_logging": boolean,
  "enable_workflow_control": boolean,
  "initial_directory": "string"
}
```

**Response:**
```json
{
  "session_id": "uuid",
  "status": "created",
  "security_level": "standard",
  "websocket_url": "/api/terminal/ws/{session_id}",
  "created_at": "2025-08-20T08:45:00Z"
}
```

#### List Active Sessions
```http
GET /api/terminal/consolidated/sessions
```

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "uuid",
      "user_id": "string",
      "security_level": "standard",
      "created_at": "timestamp",
      "is_active": boolean
    }
  ],
  "total": 1,
  "active": 1
}
```

#### Get Session Information
```http
GET /api/terminal/consolidated/sessions/{session_id}
```

**Response:**
```json
{
  "session_id": "uuid",
  "config": {
    "user_id": "string",
    "security_level": "standard",
    "enable_logging": boolean,
    "enable_workflow_control": boolean,
    "created_at": "timestamp"
  },
  "is_active": boolean,
  "statistics": {
    "connected_at": "timestamp",
    "messages_sent": 0,
    "messages_received": 0,
    "commands_executed": 0
  }
}
```

#### Delete Session
```http
DELETE /api/terminal/consolidated/sessions/{session_id}
```

**Response:**
```json
{
  "session_id": "uuid",
  "status": "deleted"
}
```

### Command Execution

#### Execute Single Command
```http
POST /api/terminal/consolidated/command
Content-Type: application/json

{
  "command": "string",
  "description": "string",
  "require_confirmation": boolean,
  "timeout": 30.0,
  "working_directory": "string",
  "environment": {}
}
```

**Response:**
```json
{
  "command": "echo test",
  "risk_level": "safe",
  "status": "assessed",
  "message": "Command assessed as safe risk",
  "requires_confirmation": false
}
```

#### Send Input to Session
```http
POST /api/terminal/consolidated/sessions/{session_id}/input
Content-Type: application/json

{
  "text": "string",
  "is_password": boolean
}
```

#### Send Signal to Session
```http
POST /api/terminal/consolidated/sessions/{session_id}/signal/{signal_name}
```

Supported signals: `SIGINT`, `SIGTERM`, `SIGKILL`, `SIGSTOP`, `SIGCONT`

### Audit and Security

#### Get Session Audit Log
```http
GET /api/terminal/consolidated/audit/{session_id}
```

**Response:**
```json
{
  "session_id": "uuid",
  "audit_available": boolean,
  "security_level": "standard",
  "message": "Audit log access requires elevated permissions"
}
```

## WebSocket API

### Primary WebSocket Endpoint
```
ws://localhost:8443/api/terminal/consolidated/ws/{session_id}
```

### Message Types

#### Client to Server Messages

##### Terminal Input
```json
{
  "type": "input",
  "text": "command to execute"
}
```

##### Ping
```json
{
  "type": "ping"
}
```

##### Terminal Resize
```json
{
  "type": "resize",
  "rows": 24,
  "cols": 80
}
```

##### Workflow Control
```json
{
  "type": "workflow_control",
  "action": "pause|resume|approve_step|cancel",
  "workflow_id": "string",
  "step_id": "string",
  "data": {}
}
```

#### Server to Client Messages

##### Terminal Output
```json
{
  "type": "output",
  "content": "command output",
  "metadata": {
    "session_id": "uuid",
    "timestamp": 1692518400.0,
    "terminal_type": "consolidated",
    "security_level": "standard"
  }
}
```

##### Security Warning
```json
{
  "type": "security_warning",
  "content": "Command blocked due to dangerous risk level: rm -rf /",
  "risk_level": "dangerous",
  "timestamp": 1692518400.0
}
```

##### Pong Response
```json
{
  "type": "pong",
  "timestamp": 1692518400.0
}
```

##### Error
```json
{
  "type": "error",
  "content": "Error message",
  "timestamp": 1692518400.0
}
```

## Backward Compatibility

### Legacy WebSocket Endpoints

The consolidated API maintains backward compatibility with existing implementations:

#### Simple Terminal (Legacy)
```
ws://localhost:8443/api/terminal/consolidated/ws/simple/{session_id}
```
- Maps to STANDARD security level
- Logging disabled
- Workflow control enabled

#### Secure Terminal (Legacy)
```
ws://localhost:8443/api/terminal/consolidated/ws/secure/{session_id}
```
- Maps to ELEVATED security level
- Logging enabled
- Full audit trail

## Security Features

### Command Risk Patterns

#### Dangerous Commands (Blocked at ELEVATED/RESTRICTED)
- File system destruction: `rm -r`, `rm -rf`, `sudo rm`
- Disk operations: `dd if=`, `mkfs`, `fdisk`
- Permission changes: `chmod 777`, `chown -R`
- System operations: `shutdown`, `reboot`, `halt`
- Network security: `iptables -F`, `ufw disable`

#### Moderate Risk Commands (Blocked at RESTRICTED)
- Privilege escalation: `sudo`, `su -`
- Package management: `apt-get install`, `pip install`
- System services: `systemctl`, `service`
- Mount operations: `mount`, `umount`

### Audit Logging

When logging is enabled, the system tracks:
- All commands executed with timestamps
- Risk level assessments
- User roles and security levels
- Message types and workflow actions
- Terminal resize events
- Command output lengths

## Error Handling

### Common Error Responses

#### Session Not Found
```json
{
  "detail": "Session not found",
  "status_code": 404
}
```

#### Session Not Active
```json
{
  "detail": "Session not active",
  "status_code": 404
}
```

#### Invalid Signal
```json
{
  "detail": "Invalid signal: INVALID",
  "status_code": 400
}
```

## Usage Examples

### JavaScript/Node.js Example

```javascript
import TerminalService from './services/TerminalService.js';

const terminal = new TerminalService();

// Create session
const sessionId = await terminal.createSession();

// Connect WebSocket
await terminal.connect(sessionId, {
  onOutput: (data) => {
    console.log('Terminal output:', data.content);
  },
  onStatusChange: (status) => {
    console.log('Connection status:', status);
  },
  onError: (error) => {
    console.error('Terminal error:', error);
  }
});

// Send command
terminal.sendInput(sessionId, 'ls -la');

// Close session
await terminal.closeSession(sessionId);
```

### Python Example

```python
import asyncio
import aiohttp
import websockets
import json

async def terminal_example():
    # Create session
    async with aiohttp.ClientSession() as session:
        async with session.post(
            'https://localhost:8443/api/terminal/consolidated/sessions',
            json={'user_id': 'python_user', 'security_level': 'standard'}
        ) as response:
            session_data = await response.json()
            session_id = session_data['session_id']

    # Connect WebSocket
    ws_url = f'ws://localhost:8443/api/terminal/consolidated/ws/{session_id}'
    async with websockets.connect(ws_url) as websocket:
        # Send command
        await websocket.send(json.dumps({
            'type': 'input',
            'text': 'echo Hello World'
        }))

        # Receive output
        response = await websocket.recv()
        data = json.loads(response)
        print(f"Output: {data['content']}")

# Run example
asyncio.run(terminal_example())
```

## API Information Endpoint

### Get API Information
```http
GET /api/terminal/consolidated/
```

**Response:**
```json
{
  "name": "Consolidated Terminal API",
  "version": "1.0.0",
  "description": "Unified terminal API combining all previous implementations",
  "features": [
    "REST API for session management",
    "WebSocket-based real-time terminal access",
    "Security assessment and command auditing",
    "Workflow automation control integration",
    "Multi-level security controls",
    "Backward compatibility with existing endpoints"
  ],
  "endpoints": {
    "sessions": "/api/terminal/sessions",
    "websocket_primary": "/api/terminal/ws/{session_id}",
    "websocket_simple": "/api/terminal/ws/simple/{session_id}",
    "websocket_secure": "/api/terminal/ws/secure/{session_id}"
  },
  "security_levels": ["standard", "elevated", "restricted"],
  "consolidated_from": [
    "terminal.py",
    "simple_terminal_websocket.py",
    "secure_terminal_websocket.py",
    "base_terminal.py"
  ]
}
```

## Migration Guide

### Migrating from Legacy APIs

#### From simple_terminal_websocket.py
Replace WebSocket URL:
```javascript
// Old
ws://localhost:8443/api/terminal/ws/simple/{session_id}

// New (backward compatible)
ws://localhost:8443/api/terminal/consolidated/ws/simple/{session_id}

// Recommended
ws://localhost:8443/api/terminal/consolidated/ws/{session_id}
```

#### From secure_terminal_websocket.py
Update to use elevated security:
```javascript
// Create session with elevated security
await fetch('/api/terminal/consolidated/sessions', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    security_level: 'elevated',
    enable_logging: true
  })
});
```

#### From terminal.py REST endpoints
Update base URL:
```javascript
// Old
/api/terminal/sessions

// New
/api/terminal/consolidated/sessions
```

## Performance Considerations

- All operations are async and non-blocking
- Session creation: < 100ms
- Command execution: < 50ms for simple commands
- WebSocket latency: < 10ms for local connections
- Maximum concurrent sessions: 100 (configurable)
- Command history: Limited to 1000 entries per session
- Audit log: Configurable retention period

## Troubleshooting

### Connection Issues
1. Verify backend is running: `./run_agent.sh --test-mode`
2. Check WebSocket URL format
3. Ensure session exists before connecting
4. Verify CORS settings for cross-origin requests

### Command Execution Issues
1. Check command risk level assessment
2. Verify security level permissions
3. Review audit logs for blocked commands
4. Ensure proper message format

### Performance Issues
1. Monitor concurrent session count
2. Check command history size
3. Review audit log retention settings
4. Verify async operation implementation
