# AutoBot Authentication & RBAC Architecture

> **Status:** Active — all 6 acceptance criteria from GH #6511 implemented.
> **Single source of truth:** [`autobot_shared/auth/permissions.py`](../../autobot_shared/auth/permissions.py)
> **Cross-service parity test:** [`autobot-backend/tests/integration/test_cross_service_auth_parity.py`](../../autobot-backend/tests/integration/test_cross_service_auth_parity.py)

---

## Overview

AutoBot enforces authentication and authorization across two backend services:

| Service | Purpose |
|---|---|
| `autobot-backend` | Main API server — agents, knowledge base, analytics, workflows |
| `autobot-slm-backend` | Service lifecycle manager — user management, settings, system control |

Before GH #6511 these services used independent `Permission` enums and
`ROLE_PERMISSIONS` dicts with no shared code — a security drift risk where a
permission added to one service was invisible to the other.  The fix moved all
permission definitions to `autobot_shared/auth/permissions.py`, which both
backends now import directly.

---

## Layered Architecture

```
HTTP Request
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 1: JWT Extraction & Validation                   │
│  autobot_shared/auth/jwt_core.py                        │
│  • decode_jwt_or_none() / decode_jwt()                  │
│  • Algorithm: HS256, secret per-service env var         │
│  • JWTExpiredError / JWTDecodeError typed exceptions    │
└────────────────────┬────────────────────────────────────┘
                     │ payload dict {sub, role, admin, ...}
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Role Derivation                               │
│                                                         │
│  Preferred path (new tokens):                           │
│    role = Role(payload["role"])                         │
│                                                         │
│  Fallback path (legacy tokens without "role" field):    │
│    role = Role.ADMIN if payload["admin"] else Role.USER │
│                                                         │
│  Unknown role string → Role.USER (safe default)         │
└────────────────────┬────────────────────────────────────┘
                     │ Role enum member
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Permission Lookup                             │
│  autobot_shared/auth/permissions.py :: ROLE_PERMISSIONS │
│                                                         │
│  ROLE_PERMISSIONS: Dict[Role, List[Permission]]         │
│  Single canonical table — both backends import it.      │
│  Adding a permission here propagates to both services   │
│  automatically on next deploy.                          │
└────────────────────┬────────────────────────────────────┘
                     │ permission ∈ role_perms?
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 4: Enforcement                                   │
│                                                         │
│  autobot-backend:                                       │
│    auth_rbac.py :: require_permission(Permission.X)     │
│    → FastAPI Depends() factory                          │
│    → raises raise_auth_error("AUTH_0003", ...)          │
│    → audit log via SecurityLayer                        │
│                                                         │
│  autobot-slm-backend:                                   │
│    services/auth.py :: require_permission(Permission.X) │
│    → async FastAPI Depends() factory                    │
│    → raises HTTPException(403, ...)                     │
│    → audit log via SLM audit service                   │
└─────────────────────────────────────────────────────────┘
```

---

## Canonical Import Paths

### Shared module (add new permissions here)

```python
from autobot_shared.auth.permissions import Permission, Role, ROLE_PERMISSIONS
```

### autobot-backend endpoint guard

```python
from auth_rbac import require_permission, require_role, Permission
# Permission and Role are re-exported from autobot_shared.auth.permissions

@router.get("/admin/users")
async def list_users(
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_permission(Permission.ADMIN_USERS_READ)),
):
    ...
```

### autobot-slm-backend endpoint guard

```python
from services.auth import require_permission
from autobot_shared.auth.permissions import Permission

@router.post("/settings/config")
async def update_config(
    _: dict = Depends(require_permission(Permission.ADMIN_CONFIG_WRITE)),
):
    ...
```

---

## Permission String Convention

All `Permission` enum values use **dot-notation**: `category.resource` or `category.resource.action`.

```
category  .  resource  .  action
   api    .   read
   api    .   write
 admin    .   users    .  read
 admin    .   users    .  write
security  .   manage
```

### Categories

| Category | Description | Example |
|---|---|---|
| `api` | Core API access | `api.read`, `api.write`, `api.admin` |
| `knowledge` | Knowledge base | `knowledge.read`, `knowledge.write` |
| `analytics` | Analytics data | `analytics.view`, `analytics.export` |
| `agent` | Agent execution | `agent.view`, `agent.execute`, `agent.terminal` |
| `workflow` | Workflow engine | `workflow.view`, `workflow.create`, `workflow.execute` |
| `files` | File operations | `files.view`, `files.upload`, `files.delete` |
| `security` | Security controls | `security.view`, `security.audit`, `security.manage` |
| `admin` | System administration | `admin.users.read`, `admin.config.write`, `admin.system` |
| `mcp` | Model Context Protocol | `mcp.read`, `mcp.execute`, `mcp.manage` |
| `batch` | Batch jobs | `batch.view`, `batch.create`, `batch.execute` |
| `sandbox` | Sandbox execution | `sandbox.view`, `sandbox.execute` |

> **Legacy:** `allow_shell_execute` uses a non-dot format for historical reasons.
> It has no single-user mode bypass (the only permission without one).

> **Legacy DB seeds:** `SYSTEM_PERMISSIONS` (in the same file) uses colon-notation
> (`users:read`, `teams:create`) for database row seeding only.  Do not add new
> members to `SYSTEM_PERMISSIONS` with colon format; use dot-notation in `Permission`.

---

## Roles & Default Permission Sets

| Role | Level | Description |
|---|---|---|
| `admin` | 5 | Full access including shell execution |
| `operator` | 4 | Operations without admin/security controls |
| `analyst` | 3 | Read + analytics export, no writes |
| `editor` | 3 | API read/write + knowledge/workflow creation |
| `user` | 2 | Standard read access |
| `readonly` | 1 | Minimal read-only access |

> **Guest role removed** — GH #744: unauthenticated requests are rejected at JWT
> validation.  There is no guest/anonymous permission set.

---

## Adding a New Permission

1. **Add the member** to `Permission` in `autobot_shared/auth/permissions.py`:
   ```python
   # === New Category ===
   MYCAT_READ  = "mycat.read"
   MYCAT_WRITE = "mycat.write"
   ```

2. **Grant to roles** in `ROLE_PERMISSIONS` in the same file:
   ```python
   Role.ADMIN: [
       ...,
       Permission.MYCAT_READ,
       Permission.MYCAT_WRITE,
   ],
   Role.OPERATOR: [
       ...,
       Permission.MYCAT_READ,
   ],
   ```

3. **Both backends see the change** on next deploy — no second edit required.

4. **Verify the parity test passes**:
   ```bash
   cd autobot-backend
   pytest tests/integration/test_cross_service_auth_parity.py -v
   ```
   The `test_all_permissions_covered_by_role_permissions` test will fail if you
   add a permission to the enum but forget to add it to `ROLE_PERMISSIONS`.

---

## Permission Cache (SLM backend)

The SLM backend's `user_management/middleware/rbac_middleware.py` maintains an
in-process L1 cache (5-minute TTL) for database-backed user permission lookups:

```
Redis key:  rbac:perm:<user_id>
Invalidation channel: autobot:rbac:invalidate
TTL: 300 seconds (CACHE_TTL_SECONDS)
```

Cache invalidation is propagated across all SLM worker processes via the
`autobot:rbac:invalidate` Redis pub/sub channel.  When a user's roles change:
- The publishing worker clears the L1 entry immediately.
- All other workers receive the pub/sub message and clear their L1 entries.

Maximum stale-permission window: `CACHE_TTL_SECONDS` (default 300 s) in the
edge case where Redis pub/sub delivery fails.

---

## JWT Token Shape

Both backends produce and consume the same JWT payload format:

```json
{
  "sub":   "username",
  "role":  "admin",
  "admin": true,
  "exp":   1234567890
}
```

- `role` — preferred field; maps directly to `Role` enum.
- `admin` — legacy boolean; used as fallback if `role` is absent.
- Both fields are set by `AuthService.create_token_response` in SLM's `services/auth.py`.

> **Note (memory):** SLM login → `access_token`; main backend → `token`.
> Response field names differ but the JWT payload format is identical.

---

## Acceptance Criteria (GH #6511)

| # | Criterion | Status |
|---|---|---|
| 1 | Single `Permission` enum in `autobot_shared/auth/permissions.py`; both backends import it | ✅ |
| 2 | No duplicate `ROLE_PERMISSIONS`; one canonical dict in shared module | ✅ |
| 3 | All JWT validation routes through `autobot_shared/auth/jwt_core.py` | ✅ |
| 4 | SLM permission cache backed by Redis with pub/sub invalidation | ✅ |
| 5 | All 65 `Depends(get_current_user)` callers continue working unchanged | ✅ |
| 6 | Cross-service permission parity test added (`test_cross_service_auth_parity.py`) | ✅ |

---

## Related Files

| File | Role |
|---|---|
| `autobot_shared/auth/permissions.py` | **Single source of truth** — Permission enum, Role enum, ROLE_PERMISSIONS |
| `autobot_shared/auth/jwt_core.py` | JWT encode/decode, bcrypt helpers |
| `autobot-backend/auth_rbac.py` | FastAPI `require_permission` / `require_role` dependencies |
| `autobot-backend/auth_middleware.py` | `get_current_user` dependency, session management |
| `autobot-backend/security_layer.py` | Audit logging for permission denials |
| `autobot-slm-backend/services/auth.py` | SLM `require_permission` / `get_current_user` |
| `autobot-slm-backend/user_management/middleware/rbac_middleware.py` | DB-backed permission middleware with Redis cache |
| `autobot-backend/tests/integration/test_cross_service_auth_parity.py` | Cross-service parity test (MVA-127) |

---

## Related Issues

- GH #6511 — Unify 4 auth/RBAC layers (parent)
- GH #744 — Phase 6 RBAC decorators (closed — created `auth_rbac.py`)
- GH #6475 — Unified audit log (permission deny events)
- GH #6473 — Run-scoped short-lived JWTs
