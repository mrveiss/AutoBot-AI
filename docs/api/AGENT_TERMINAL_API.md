## Agent Terminal API Documentation

**API Version:** 1.0.0
**Base URL:** `/api/agent-terminal`
**Security:** Integrated with SecureCommandExecutor, RBAC enforcement, comprehensive audit logging

---

## Overview

The Agent Terminal API provides secure programmatic terminal access for AI agents during chat conversations. It implements a comprehensive security model with risk assessment, approval workflows, and user control mechanisms.

### Security Features

- **CVE-002 Compliance**: Prompt injection detection and prevention
- **CVE-003 Compliance**: No god mode - all agents subject to RBAC
- **Command Risk Assessment**: Commands classified as SAFE/MODERATE/HIGH/DANGEROUS
- **Approval Workflow**: HIGH/DANGEROUS commands require user approval
- **User Control**: Users can interrupt and take control at any time
- **Audit Logging**: All commands logged with security metadata

### Agent Roles

| Role | Max Risk Level | Auto-Approve Safe | Auto-Approve Moderate | Allow High | Allow Dangerous |
|------|----------------|-------------------|------------------------|------------|-----------------|
| **chat_agent** | MODERATE | Yes | No | No | No |
| **automation_agent** | HIGH | Yes | Yes | Yes (with approval) | No |
| **system_agent** | HIGH | Yes | Yes | Yes (with approval) | No |
| **admin_agent** | DANGEROUS | Yes | Yes | Yes (with approval) | Yes (with approval) |

### Session States

- **AGENT_CONTROL**: Agent is executing commands
- **USER_INTERRUPT**: User requested control
- **USER_CONTROL**: User has control, agent commands blocked
- **AGENT_RESUME**: Agent resuming after user control

---

## API Endpoints

### 1. Create Agent Terminal Session

**POST** `/api/agent-terminal/sessions`

Create a new terminal session for an AI agent.

#### Request Body

```json
{
  "agent_id": "string (required)",
  "agent_role": "string (required)",
  "conversation_id": "string (optional)",
  "host": "string (optional, default: main)",
  "metadata": "object (optional)"
}
```

**Agent Roles:**
- `chat_agent` - Chat agents (lowest privilege)
- `automation_agent` - Workflow automation agents
- `system_agent` - System monitoring agents
- `admin_agent` - Administrative agents (highest privilege)

**Available Hosts:**
- `main` - Main machine (172.16.168.20)
- `frontend` - Frontend VM (172.16.168.21)
- `npu-worker` - NPU Worker VM (172.16.168.22)
- `redis` - Redis VM (172.16.168.23)
- `ai-stack` - AI Stack VM (172.16.168.24)
- `browser` - Browser VM (172.16.168.25)

#### Response (201 Created)

```json
{
  "status": "created",
  "session_id": "uuid",
  "agent_id": "string",
  "agent_role": "string",
  "conversation_id": "string",
  "host": "string",
  "state": "agent_control",
  "created_at": 1234567890.123
}
```

#### Example

```bash
curl -X POST http://172.16.168.20:8001/api/agent-terminal/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "chat_agent_1",
    "agent_role": "chat_agent",
    "conversation_id": "conv_abc123",
    "host": "main"
  }'
```

---

### 2. List Agent Terminal Sessions

**GET** `/api/agent-terminal/sessions`

List agent terminal sessions with optional filtering.

#### Query Parameters

- `agent_id` (optional): Filter by agent ID
- `conversation_id` (optional): Filter by conversation ID

#### Response (200 OK)

```json
{
  "status": "success",
  "total": 5,
  "sessions": [
    {
      "session_id": "uuid",
      "agent_id": "string",
      "agent_role": "string",
      "conversation_id": "string",
      "host": "string",
      "state": "string",
      "created_at": 1234567890.123,
      "last_activity": 1234567890.123,
      "command_count": 10
    }
  ]
}
```

#### Example

```bash
# List all sessions
curl http://172.16.168.20:8001/api/agent-terminal/sessions

# List sessions for specific agent
curl http://172.16.168.20:8001/api/agent-terminal/sessions?agent_id=chat_agent_1

# List sessions for specific conversation
curl http://172.16.168.20:8001/api/agent-terminal/sessions?conversation_id=conv_abc123
```

---

### 3. Get Agent Terminal Session

**GET** `/api/agent-terminal/sessions/{session_id}`

Get detailed information about a specific agent terminal session.

#### Response (200 OK)

```json
{
  "status": "success",
  "session_id": "uuid",
  "agent_id": "string",
  "agent_role": "string",
  "conversation_id": "string",
  "host": "string",
  "state": "string",
  "created_at": 1234567890.123,
  "last_activity": 1234567890.123,
  "uptime": 3600.5,
  "command_count": 10,
  "pending_approval": {
    "command": "string",
    "risk": "moderate",
    "reasons": ["array of strings"],
    "timestamp": 1234567890.123
  },
  "metadata": {}
}
```

#### Example

```bash
curl http://172.16.168.20:8001/api/agent-terminal/sessions/550e8400-e29b-41d4-a716-446655440000
```

---

### 4. Delete Agent Terminal Session

**DELETE** `/api/agent-terminal/sessions/{session_id}`

Close and delete an agent terminal session.

#### Response (200 OK)

```json
{
  "status": "deleted",
  "session_id": "uuid"
}
```

#### Example

```bash
curl -X DELETE http://172.16.168.20:8001/api/agent-terminal/sessions/550e8400-e29b-41d4-a716-446655440000
```

---

### 5. Execute Agent Command

**POST** `/api/agent-terminal/execute?session_id={session_id}`

Execute a command in an agent terminal session with security controls.

#### Query Parameters

- `session_id` (required): Session ID

#### Request Body

```json
{
  "command": "string (required)",
  "description": "string (optional)",
  "force_approval": "boolean (optional, default: false)"
}
```

#### Response - Success (Auto-Approved)

```json
{
  "status": "success",
  "command": "string",
  "stdout": "string",
  "stderr": "string",
  "return_code": 0,
  "security": {
    "risk": "safe",
    "reasons": ["Safe command"],
    "sandboxed": false,
    "approved": false
  }
}
```

#### Response - Pending Approval (MODERATE/HIGH/DANGEROUS)

```json
{
  "status": "pending_approval",
  "command": "string",
  "risk": "moderate",
  "reasons": ["Moderate-risk command: mkdir"],
  "description": "string",
  "agent_role": "chat_agent",
  "approval_required": true
}
```

#### Response - Blocked (Insufficient Permissions)

```json
{
  "status": "error",
  "error": "Command risk high exceeds agent max risk moderate",
  "command": "string",
  "risk": "high",
  "agent_role": "chat_agent"
}
```

#### Example

```bash
# Execute safe command (auto-approved)
curl -X POST "http://172.16.168.20:8001/api/agent-terminal/execute?session_id=550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "echo \"Hello World\"",
    "description": "Test echo command"
  }'

# Execute moderate command (requires approval)
curl -X POST "http://172.16.168.20:8001/api/agent-terminal/execute?session_id=550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "mkdir /tmp/test_dir",
    "description": "Create test directory"
  }'
```

---

### 6. Approve/Deny Agent Command

**POST** `/api/agent-terminal/sessions/{session_id}/approve`

Approve or deny a pending agent command.

#### Request Body

```json
{
  "approved": "boolean (required)",
  "user_id": "string (optional)"
}
```

#### Response - Approved

```json
{
  "status": "approved",
  "command": "string",
  "result": {
    "stdout": "string",
    "stderr": "string",
    "return_code": 0
  }
}
```

#### Response - Denied

```json
{
  "status": "denied",
  "command": "string",
  "message": "Command execution denied by user"
}
```

#### Example

```bash
# Approve command
curl -X POST http://172.16.168.20:8001/api/agent-terminal/sessions/550e8400-e29b-41d4-a716-446655440000/approve \
  -H "Content-Type: application/json" \
  -d '{
    "approved": true,
    "user_id": "user_123"
  }'

# Deny command
curl -X POST http://172.16.168.20:8001/api/agent-terminal/sessions/550e8400-e29b-41d4-a716-446655440000/approve \
  -H "Content-Type: application/json" \
  -d '{
    "approved": false,
    "user_id": "user_123"
  }'
```

---

### 7. User Interrupt (Take Control)

**POST** `/api/agent-terminal/sessions/{session_id}/interrupt`

User interrupts agent and takes control of the terminal session.

#### Request Body

```json
{
  "user_id": "string (required)"
}
```

#### Response (200 OK)

```json
{
  "status": "success",
  "message": "Agent interrupted, user has control",
  "previous_state": "agent_control",
  "current_state": "user_control",
  "pending_approval": {
    "command": "string",
    "risk": "moderate"
  }
}
```

#### Example

```bash
curl -X POST http://172.16.168.20:8001/api/agent-terminal/sessions/550e8400-e29b-41d4-a716-446655440000/interrupt \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123"
  }'
```

---

### 8. Agent Resume (Return Control)

**POST** `/api/agent-terminal/sessions/{session_id}/resume`

Resume agent control after user interrupt.

#### Response (200 OK)

```json
{
  "status": "success",
  "message": "Agent control resumed",
  "current_state": "agent_control"
}
```

#### Example

```bash
curl -X POST http://172.16.168.20:8001/api/agent-terminal/sessions/550e8400-e29b-41d4-a716-446655440000/resume
```

---

## Security Workflow

### Command Execution Flow

```
1. Agent submits command
   ↓
2. Validate session exists and is in AGENT_CONTROL state
   ↓
3. Assess command risk (SecureCommandExecutor)
   ↓
4. Check agent role permissions
   ↓
5. Determine if approval is needed
   ├─ SAFE → Auto-approve if permitted by agent role
   ├─ MODERATE → Requires approval for chat_agent
   ├─ HIGH → ALWAYS requires approval
   └─ DANGEROUS → ALWAYS requires approval (all roles)
   ↓
6. If approved → Execute command
   ↓
7. Return result with security metadata
   ↓
8. Log to audit trail
```

### Risk Assessment Levels

| Risk Level | Description | Examples |
|------------|-------------|----------|
| **SAFE** | Read-only commands | `ls`, `cat`, `echo`, `pwd` |
| **MODERATE** | File operations | `mkdir`, `cp`, `mv`, `chmod` |
| **HIGH** | System modifications | `sudo` commands, service management |
| **DANGEROUS** | Destructive operations | `rm -rf`, `dd`, `mkfs`, system shutdown |
| **FORBIDDEN** | Never allowed | `kill`, `shutdown`, harmful patterns |

### Agent Permission Matrix

| Command Risk | chat_agent | automation_agent | system_agent | admin_agent |
|--------------|------------|------------------|--------------|-------------|
| SAFE | ✓ Auto-approve | ✓ Auto-approve | ✓ Auto-approve | ✓ Auto-approve |
| MODERATE | ⚠️ Requires approval | ✓ Auto-approve | ✓ Auto-approve | ✓ Auto-approve |
| HIGH | ❌ Blocked | ⚠️ Requires approval | ⚠️ Requires approval | ⚠️ Requires approval |
| DANGEROUS | ❌ Blocked | ❌ Blocked | ❌ Blocked | ⚠️ Requires approval |
| FORBIDDEN | ❌ Blocked | ❌ Blocked | ❌ Blocked | ❌ Blocked |

---

## Error Codes

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | `invalid_agent_role` | Invalid agent role specified |
| 404 | `session_not_found` | Agent terminal session not found |
| 403 | `user_has_control` | User has control, agent commands blocked |
| 403 | `insufficient_permissions` | Agent role lacks permission for command risk level |
| 500 | `execution_error` | Command execution failed |

---

## Configuration

Agent terminal configuration in `config/config.yaml`:

```yaml
backend:
  agent_terminal:
    default_host: main
    session_timeout: 3600  # 1 hour
    approval_required_for:
      - moderate
      - high
      - dangerous
    max_concurrent_sessions: 10
```

---

## Integration Example

### Python Client

```python
import httpx

# Create session
async def create_agent_session():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://172.16.168.20:8001/api/agent-terminal/sessions",
            json={
                "agent_id": "chat_agent_1",
                "agent_role": "chat_agent",
                "conversation_id": "conv_abc123"
            }
        )
        return response.json()

# Execute command
async def execute_command(session_id, command):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://172.16.168.20:8001/api/agent-terminal/execute?session_id={session_id}",
            json={
                "command": command,
                "description": "Agent command"
            }
        )
        return response.json()

# Workflow
session = await create_agent_session()
session_id = session["session_id"]

# Execute safe command (auto-approved)
result = await execute_command(session_id, "echo 'Hello World'")

# Execute moderate command (requires approval)
result = await execute_command(session_id, "mkdir /tmp/test")
if result["status"] == "pending_approval":
    print(f"Command requires approval: {result['command']}")
    # User approves via frontend UI
```

---

## Audit Logging

All agent terminal activity is logged to `logs/audit.log` with the following structure:

```json
{
  "timestamp": "2025-10-04T12:00:00Z",
  "event": "agent_terminal_command",
  "session_id": "uuid",
  "agent_id": "string",
  "agent_role": "chat_agent",
  "command": "string",
  "risk": "moderate",
  "status": "pending_approval",
  "approved_by": "user_123",
  "result": {
    "return_code": 0,
    "execution_time": 0.123
  }
}
```

---

## Security Best Practices

1. **Always use lowest privilege agent role** for the task
2. **Review pending approvals carefully** before approving
3. **Monitor audit logs** for suspicious activity
4. **Use user interrupt** if agent behavior seems unexpected
5. **Close sessions** when conversation ends
6. **Configure appropriate timeouts** for your use case
7. **Never bypass approval workflow** - it exists for security

---

## Related Documentation

- [SecureCommandExecutor Documentation](../security/SECURE_COMMAND_EXECUTOR.md)
- [CVE-002 Prompt Injection Fix](../../reports/security/CVE-AUTOBOT-2025-002-SECURITY-AUDIT.md)
- [CVE-003 God Mode Fix](../../reports/security/CVE-AUTOBOT-2025-003-GOD-MODE-FIX-REPORT.md)
- [Chat Workflow Manager](../../src/chat_workflow_manager.py)
- [Terminal Tool Integration](../../src/tools/terminal_tool.py)

---

**Last Updated:** 2025-10-04
**API Version:** 1.0.0
**Status:** Production Ready
