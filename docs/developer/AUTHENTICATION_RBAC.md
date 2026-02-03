# Authentication and RBAC System

> Issue #744: Complete Authentication and RBAC System

This document describes AutoBot's authentication and Role-Based Access Control (RBAC) system.

## Overview

AutoBot implements a comprehensive security system with:
- JWT-based authentication
- Session management with Redis persistence
- Role-Based Access Control (RBAC)
- Fine-grained permission decorators
- Audit logging

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   API Request   │────▶│ auth_middleware  │────▶│  SecurityLayer  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │                         │
                               ▼                         ▼
                        ┌──────────────┐         ┌─────────────┐
                        │  auth_rbac   │         │ Audit Log   │
                        └──────────────┘         └─────────────┘
```

## Key Components

### 1. Authentication Middleware (`src/auth_middleware.py`)

Provides core authentication functionality:

```python
from src.auth_middleware import (
    get_current_user,        # FastAPI dependency for user authentication
    check_admin_permission,  # Dependency for admin-only endpoints
    auth_middleware,         # Global middleware instance
)
```

### 2. RBAC Permission System (`src/auth_rbac.py`)

Provides fine-grained permission control:

```python
from src.auth_rbac import (
    Permission,              # Permission enum
    Role,                    # Role enum
    require_permission,      # Permission decorator
    require_role,            # Role decorator
    require_any_permission,  # OR-based permission check
)
```

## Roles

| Role | Description | Access Level |
|------|-------------|--------------|
| `admin` | Full system access | All permissions |
| `operator` | Execute operations | Execute but not manage |
| `analyst` | Analytics focus | View and export analytics |
| `editor` | Content creation | Create and modify content |
| `user` | Standard access | Basic read operations |
| `readonly` | View only | Read-only access |

## Permissions

Permissions follow the naming convention: `category.action` or `category.resource.action`

### Permission Categories

| Category | Examples | Description |
|----------|----------|-------------|
| `api` | `api.read`, `api.write`, `api.admin` | Core API access |
| `knowledge` | `knowledge.read`, `knowledge.write`, `knowledge.delete` | Knowledge base operations |
| `analytics` | `analytics.view`, `analytics.export`, `analytics.manage` | Analytics access |
| `agent` | `agent.view`, `agent.execute`, `agent.terminal` | Agent operations |
| `workflow` | `workflow.view`, `workflow.create`, `workflow.execute` | Workflow management |
| `files` | `files.view`, `files.upload`, `files.delete` | File operations |
| `security` | `security.view`, `security.audit`, `security.manage` | Security features |
| `admin` | `admin.users.*`, `admin.config.*`, `admin.system` | Administration |
| `mcp` | `mcp.read`, `mcp.execute`, `mcp.manage` | MCP operations |
| `batch` | `batch.view`, `batch.create`, `batch.execute` | Batch jobs |
| `sandbox` | `sandbox.view`, `sandbox.execute`, `sandbox.manage` | Sandbox operations |

## Usage Examples

### Basic Authentication

All endpoints require basic authentication:

```python
from fastapi import APIRouter, Depends
from src.auth_middleware import get_current_user

router = APIRouter()

@router.get("/endpoint")
async def my_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """Requires authenticated user."""
    return {"user": current_user["username"]}
```

### Admin-Only Endpoints

For endpoints requiring admin role:

```python
from src.auth_middleware import check_admin_permission

@router.get("/admin/users")
async def list_users(
    admin_check: bool = Depends(check_admin_permission),
):
    """Requires admin role."""
    return {"users": [...]}
```

### Fine-Grained Permission Control

For specific permission requirements:

```python
from src.auth_rbac import Permission, require_permission

@router.get("/analytics/export")
async def export_analytics(
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_permission(Permission.ANALYTICS_EXPORT)),
):
    """Requires analytics.export permission."""
    return {"data": [...]}
```

### Role-Based Access

For endpoints requiring specific roles:

```python
from src.auth_rbac import Role, require_role

@router.post("/workflows/execute")
async def execute_workflow(
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_role(Role.ADMIN, Role.OPERATOR)),
):
    """Requires admin or operator role."""
    return {"status": "executing"}
```

### OR-Based Permissions

When any of several permissions is acceptable:

```python
from src.auth_rbac import require_any_permission

@router.get("/dashboard")
async def view_dashboard(
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_any_permission(
        Permission.ANALYTICS_VIEW,
        Permission.ADMIN_SYSTEM,
    )),
):
    """Requires either analytics.view OR admin.system permission."""
    return {"dashboard": {...}}
```

## Authentication Flow

### 1. JWT Token Authentication

```
Client                     Server
  │                          │
  │  POST /auth/login        │
  │  {username, password}    │
  │─────────────────────────▶│
  │                          │ Validate credentials
  │                          │ Create JWT token
  │  {token: "eyJ..."}       │
  │◀─────────────────────────│
  │                          │
  │  GET /api/endpoint       │
  │  Authorization: Bearer   │
  │─────────────────────────▶│
  │                          │ Verify JWT
  │                          │ Extract user data
  │  {response}              │
  │◀─────────────────────────│
```

### 2. Session-Based Authentication

Sessions are stored in Redis with configurable TTL:

```python
# Session creation
session_id = auth_middleware.create_session(user_data, request)

# Session retrieval
session = auth_middleware.get_session(session_id)

# Session invalidation (logout)
auth_middleware.invalidate_session(session_id)
```

## Security Features

### Account Lockout

After 3 failed login attempts, the account is locked for 15 minutes:

```python
# Check if account is locked
if auth_middleware.is_account_locked(username):
    raise_auth_error("AUTH_0001", "Account temporarily locked")
```

### Audit Logging

All authentication events are logged to `data/audit.log`:

```json
{
  "timestamp": "2026-02-03T14:00:00",
  "user": "admin",
  "action": "login_successful",
  "outcome": "success",
  "details": {"ip": "192.168.1.100", "role": "admin"}
}
```

### Single-User Mode

For development/personal use, authentication can be bypassed:

```bash
export AUTOBOT_SINGLE_USER_MODE=true
```

In single-user mode:
- All requests are treated as admin
- No authentication required
- Permission checks are bypassed

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AUTOBOT_JWT_SECRET` | JWT signing secret (min 32 chars) | Auto-generated |
| `AUTOBOT_SINGLE_USER_MODE` | Enable single-user mode | `true` |
| `AUTOBOT_AUDIT_LOG_FILE` | Audit log file path | `data/audit.log` |

### Config File (`config/config.yaml`)

```yaml
security_config:
  enable_auth: true
  session_timeout_minutes: 30
  max_failed_attempts: 3
  lockout_duration_minutes: 15

  roles:
    admin:
      permissions:
        - "files.*"
        - "allow_goal_submission"
        - "allow_kb_read"
        - "allow_kb_write"
        - "allow_shell_execute"

    user:
      permissions:
        - "files.view"
        - "files.download"
        - "allow_goal_submission"
        - "allow_kb_read"
```

## Testing

Run the RBAC tests:

```bash
python -m pytest tests/security/test_auth_rbac.py -v
```

Run the authentication security tests:

```bash
python scripts/utilities/test-authentication-security.py
```

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `AUTH_0001` | Account temporarily locked | Too many failed login attempts |
| `AUTH_0002` | Authentication required | No valid token/session |
| `AUTH_0003` | Insufficient permissions | User lacks required permission |

## Related Files

- `src/auth_middleware.py` - Core authentication middleware
- `src/auth_rbac.py` - RBAC permission system
- `src/security_layer.py` - Security layer with permission checking
- `tests/security/test_auth_rbac.py` - RBAC tests
- `scripts/utilities/test-authentication-security.py` - Security tests

## Migration Notes

### From Guest Fallback

The guest role fallback has been removed (Issue #744). All endpoints now require explicit authentication. To migrate:

1. Add `Depends(get_current_user)` to all endpoint parameters
2. Add `Issue #744: Requires authenticated user.` to docstrings
3. For admin endpoints, add `Depends(check_admin_permission)`

### Adding New Permissions

1. Add permission to `Permission` enum in `src/auth_rbac.py`
2. Add to appropriate role in `ROLE_PERMISSIONS`
3. Add tests in `tests/security/test_auth_rbac.py`
4. Document in this file
