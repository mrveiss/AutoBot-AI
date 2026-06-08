# Device Token JWT Authentication (MVA-3237)

Security audit [MVA-3084](/MVA/issues/MVA-3084) identified that device token JWT authentication and scoping specified in Phase 1 ([MVA-3081](/MVA/issues/MVA-3081)) was not implemented. This document describes the implementation.

## Overview

Mobile devices paired via QR code receive a JWT token that allows them to authenticate API requests independently from the desktop session. This provides:

- **Independent authentication**: Devices don't need the desktop to stay connected
- **Scoped access**: Tokens are scoped to prevent privilege escalation
- **Audit trail**: Device actions are logged separately from user sessions

## JWT Structure

Device JWTs contain the following claims:

```json
{
  "sub": "<device_id>",
  "user_id": "<user_id>",
  "scope": "read-only" | "admin",
  "type": "device_token",
  "exp": <timestamp>
}
```

- **sub**: Device UUID from `desktop_mobile_devices.id`
- **user_id**: Owner user ID
- **scope**: Token scope (`read-only` or `admin`)
- **type**: Always `"device_token"` to distinguish from user JWTs
- **exp**: Expiry timestamp (default 90 days)

## Scopes

### read-only

**Default scope** for all newly paired devices. Allows:
- Reading conversations
- Reading knowledge base entries
- Receiving push notifications
- Syncing conversation history

**Rejects**:
- Creating/updating/deleting conversations
- Modifying knowledge base
- Admin operations
- User management

### admin

**Elevated scope** (requires manual promotion). Allows:
- All read-only operations
- Creating/updating conversations
- Modifying knowledge base (if user has permission)

**Still rejects**:
- User management (requires full user session)
- System admin operations (requires full user session)

## Authentication Flow

### 1. Device Pairing

```
Desktop                                Mobile App
   |                                       |
   | GET /api/devices/pair-qr             |
   |<--------------------------------------|
   | {challenge_token, expires_in}        |
   |                                       |
   | Display QR code                       |
   |                                       |
   |                                  Scan QR
   |                                       |
   | POST /api/devices/pair                |
   |   {challenge_token, device_token...} |
   |<--------------------------------------|
   | {device_id, device_jwt}               |
   |-------------------------------------->|
   |                                       |
   |                              Store device_jwt
```

### 2. API Requests

Mobile app includes the device JWT in the `Authorization` header:

```http
GET /api/conversations
Authorization: Bearer <device_jwt>
```

The middleware:
1. Extracts the Bearer token
2. Validates it as a device JWT (checks `type: "device_token"`)
3. Returns a synthetic user dict with `auth_method: "device_jwt"`

### 3. Scope Enforcement (Fail-Closed Security Model)

**Important**: Device JWTs are **REJECTED by default** by `get_current_user()`. This fail-closed model prevents accidental privilege escalation.

Endpoints that should be accessible to mobile devices must explicitly use the `require_device_jwt` dependency:

```python
# Read-only endpoint (accessible to all device tokens)
@router.get("/conversations")
async def list_conversations(
    current_user: Dict = Depends(require_device_jwt),  # Accepts read-only and admin
    ...
):
    ...

# Admin-only endpoint (requires admin scope)
@router.post("/conversations")
async def create_conversation(
    current_user: Dict = Depends(lambda r: require_device_jwt(r, min_scope="admin")),
    ...
):
    # Only device tokens with admin scope can access this
    ...

# User-only endpoint (device tokens blocked)
@router.get("/admin/users")
async def list_users(
    current_user: Dict = Depends(get_current_user),  # Rejects device JWTs
    ...
):
    # Only full user sessions can access this
    ...
```

The `require_device_jwt` dependency:
- Validates the device JWT
- Checks the device still exists in the database (revocation check)
- Enforces minimum scope requirement
- Returns user data with device-specific fields

## API Endpoint Authorization

### Accepts Device Tokens (Read-Only)

| Endpoint | Method | Scope Required |
|----------|--------|----------------|
| `/api/conversations` | GET | read-only |
| `/api/conversations/{id}` | GET | read-only |
| `/api/conversations/{id}/messages` | GET | read-only |
| `/api/knowledge` | GET | read-only |
| `/api/devices` | GET | read-only |

### Requires Admin Scope or User Session

| Endpoint | Method | Scope Required |
|----------|--------|----------------|
| `/api/conversations` | POST | admin or user session |
| `/api/conversations/{id}` | PATCH | admin or user session |
| `/api/conversations/{id}` | DELETE | admin or user session |
| `/api/conversations/{id}/messages` | POST | admin or user session |
| `/api/knowledge` | POST/PATCH/DELETE | admin or user session |

### Requires User Session Only (No Device Tokens)

| Endpoint | Method | Reason |
|----------|--------|--------|
| `/api/users` | ALL | User management requires full session |
| `/api/admin/*` | ALL | System admin operations |
| `/api/devices/pair-qr` | GET | QR generation tied to active desktop session |
| `/api/devices/{id}` | DELETE | Device unpairing requires desktop confirmation |

## Configuration

### Environment Variables

```bash
# Device JWT signing secret (separate from user JWT secret)
DEVICE_JWT_SECRET=<64-char-secret>

# Token lifetime in days (default: 90)
DEVICE_JWT_TTL_DAYS=90
```

If `DEVICE_JWT_SECRET` is not set, falls back to `AUTOBOT_JWT_SECRET`.

### Database

The `desktop_mobile_devices` table includes a `token_scope` column:

```sql
ALTER TABLE desktop_mobile_devices 
ADD COLUMN token_scope VARCHAR(32) NOT NULL DEFAULT 'read-only';
```

Migration: `20260604_052_device_token_scope.py`

## Security Considerations

### Fail-Closed Authorization Model

Device JWTs use a **fail-closed** security model:

1. **Default Deny**: `get_current_user()` rejects device JWTs - they cannot access standard user endpoints
2. **Explicit Allowlist**: Only endpoints using `require_device_jwt` accept device tokens
3. **Revocation Check**: Every request validates the device still exists in the database
4. **Scope Enforcement**: Minimum scope is validated on every request

This prevents:
- Privilege escalation via device tokens
- Revoked devices from accessing APIs (JWT still valid but device deleted)
- Accidental exposure of admin endpoints to mobile devices

### Scope Promotion

Promoting a device from `read-only` to `admin` scope:

1. Requires desktop user session (not another device token)
2. Requires explicit user confirmation
3. Logged to audit trail
4. New JWT minted with updated scope

**TODO**: Implement scope promotion endpoint (future work)

### Token Revocation

Device tokens are **actively validated** on every request:

1. `require_device_jwt` checks the database for device existence
2. If the device was deleted, the request is rejected with 403
3. Revocation is **immediate** - no delay waiting for JWT expiry

Deleting a device via `DELETE /api/devices/{id}`:
- Removes the device from `desktop_mobile_devices` table
- All subsequent API requests with that device's JWT fail instantly
- No need for Redis denylist (device existence check is sufficient)

### Expiry

Device tokens expire after 90 days (configurable via `DEVICE_JWT_TTL_DAYS`). Expired tokens are rejected by the JWT validation layer.

Mobile apps should:
- Store the expiry timestamp
- Prompt re-pairing when near expiry
- Handle 401 responses gracefully

## Testing

Integration tests: `autobot-backend/tests/integration/test_device_jwt_auth.py`

Run tests:
```bash
pytest autobot-backend/tests/integration/test_device_jwt_auth.py -v
```

## Related Issues

- [MVA-3237](/MVA/issues/MVA-3237) - Phase 1.5 implementation
- [MVA-3084](/MVA/issues/MVA-3084) - Security audit findings
- [MVA-3081](/MVA/issues/MVA-3081) - Phase 1 (incomplete)
- [MVA-3036](/MVA/issues/MVA-3036#document-adr) - Parent ADR
