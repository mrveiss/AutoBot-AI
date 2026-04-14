# User Management Admin Guide

> Related: [Authentication & RBAC](../../developer/AUTHENTICATION_RBAC.md) | [Roles Reference](../../developer/ROLES.md)

This guide covers all user lifecycle operations in AutoBot: creating accounts, assigning roles, controlling access, and understanding how the system behaves in each deployment mode.

---

## 1. Overview

### Who Manages Users

User management is an admin-only function. Only accounts holding the `admin` system role (or `is_platform_admin=true`) may create, modify, deactivate, or delete other accounts. All write operations to `/user-management/users/*` are gated by the `require_platform_admin` dependency on the backend.

Regular users can only read their own profile (`GET /user-management/users/me`) and change their own password (`POST /user-management/users/{id}/change-password`).

### Deployment Mode Impact

AutoBot runs in one of two modes, controlled by `AUTOBOT_DEPLOYMENT_MODE`:

| Mode | User Management | Self-Registration | Database Required |
|---|---|---|---|
| `single_user` | Disabled — all requests are treated as admin | Disabled (HTTP 400) | No |
| `multi_user` | Enabled — full CRUD via PostgreSQL | Enabled (if not disabled) | Yes (PostgreSQL) |

In `single_user` mode every call to the user management endpoints that requires the database returns HTTP 503. `GET /user-management/users/me` and `GET /user-management/users/search` still respond (with synthetic data and an empty list respectively) so that the rest of the UI continues to function.

### Roles

AutoBot defines three system roles assignable through the admin panel. Additional roles (`operator`, `analyst`, `editor`) exist in the RBAC permission layer but are not yet exposed in the admin UI dropdown.

| Role | Typical Use | Key Capabilities |
|---|---|---|
| `admin` | Platform administrators | All permissions, user management, system config |
| `user` | Day-to-day operators | Goal submission, knowledge read/write, file operations |
| `readonly` | Auditors, stakeholders | View-only across all features |

See [AUTHENTICATION_RBAC.md](../../developer/AUTHENTICATION_RBAC.md) for the full permission matrix per role.

---

## 2. Accessing the Admin Panel

Navigate to `/admin/users` in your browser. The route is only rendered if your session token carries the `admin` role; any other role will receive a permission-denied redirect.

The panel shows a table with columns: **Username**, **Email**, **Display Name**, **Role**, **Status**, and **Actions**. A search bar at the top filters the list by username, email, or display name. By default, inactive accounts are hidden; use the `include_inactive` query parameter on the underlying API call if you need to display them.

---

## 3. Creating a User

1. Click **Add User** (top-right of the admin panel).
2. Fill in the modal form:

| Field | Required | Rules |
|---|---|---|
| `username` | Yes | 3–50 characters, alphanumeric plus `-` and `_`, stored lowercase |
| `email` | Yes | Valid email format, max 255 characters, stored lowercase |
| `password` | Yes | Min 8 chars, max 128 chars; must contain at least one uppercase letter, one lowercase letter, and one digit |
| `display_name` | No | Free text; defaults to username if omitted |
| `org_id` | No | UUID of the organisation; scopes the user to a tenant (see Section 9) |
| `role_ids` | No | Array of role UUIDs; the system `user` role is assigned by default |

3. Click **Create**. On success the new row appears in the table immediately.

**API equivalent:**

```http
POST /user-management/users
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "username": "jsmith",
  "email": "jsmith@example.com",
  "password": "Secret1234",
  "display_name": "Jane Smith",
  "org_id": null,
  "role_ids": []
}
```

Response `201 Created`:

```json
{
  "success": true,
  "message": "User 'jsmith' created successfully",
  "user": {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "username": "jsmith",
    "email": "jsmith@example.com",
    "display_name": "Jane Smith",
    "is_active": true,
    "is_verified": false,
    "mfa_enabled": false,
    "is_platform_admin": false,
    "roles": [{"id": "...", "name": "user"}],
    "created_at": "2026-04-14T10:00:00Z"
  }
}
```

**Error codes:**

| HTTP | Meaning |
|---|---|
| `409 Conflict` | Username or email already in use |
| `422 Unprocessable Entity` | Validation failure (see `detail` field) |
| `503 Service Unavailable` | User management not enabled (single_user mode) |

---

## 4. Managing Roles

### Via the Admin Panel

Each row in the users table contains an inline `<select>` dropdown with the three system roles: `admin`, `user`, `readonly`. Changing the value fires a `PUT /user-management/users/{id}/role` request immediately — no save button is needed.

Changing a user's role replaces all existing system role assignments atomically. Custom (non-system) roles are preserved.

### Via the API

```http
PUT /user-management/users/{user_id}/role
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "role": "admin"
}
```

Accepted values for `role`: `admin`, `user`, `readonly`. Any other string returns `400 Bad Request`.

Response `200 OK`:

```json
{
  "success": true,
  "message": "Role updated to 'admin' for user jsmith",
  "username": "jsmith",
  "role": "admin"
}
```

### Fine-Grained Role Assignment

For advanced use cases (assigning roles by UUID, or assigning multiple roles), use the role-assignment endpoints directly:

```http
POST /user-management/users/{user_id}/roles/{role_id}   # assign
DELETE /user-management/users/{user_id}/roles/{role_id} # revoke
```

### What Each Role Can Do

| Capability | readonly | user | admin |
|---|---|---|---|
| View knowledge base | Yes | Yes | Yes |
| Write to knowledge base | No | Yes | Yes |
| Submit goals / run agents | No | Yes | Yes |
| Upload files | No | Yes | Yes |
| Delete files | No | No | Yes |
| View analytics | Yes | Yes | Yes |
| Export analytics | No | No | Yes |
| Manage users | No | No | Yes |
| Modify system config | No | No | Yes |
| Execute MCP tools | No | Yes | Yes |
| Run sandbox operations | No | Yes | Yes |

---

## 5. Activate / Deactivate / Delete

### Deactivate

Use deactivation when you want to suspend access temporarily without losing the account history. The user cannot log in while inactive; their data and role assignments are preserved.

Click the ban icon in the Actions column, or call:

```http
POST /user-management/users/{user_id}/deactivate
Authorization: Bearer <admin-token>
```

Response: the updated `UserResponse` with `is_active: false`.

### Activate

Reactivates a previously deactivated account. The user can log in again immediately.

Click the check-circle icon (visible only for inactive rows), or call:

```http
POST /user-management/users/{user_id}/activate
Authorization: Bearer <admin-token>
```

### Delete

Deletion is irreversible for hard deletes. AutoBot performs a **soft delete** by default (the row is flagged and hidden from list queries) unless `?hard_delete=true` is passed.

Click the trash icon in the Actions column, or call:

```http
DELETE /user-management/users/{user_id}?hard_delete=false
Authorization: Bearer <admin-token>
```

Response `200 OK`:

```json
{
  "success": true,
  "message": "User 3fa85f64-... deleted successfully"
}
```

**Guidance:**

- Prefer **deactivate** when the user may return or when audit trails are needed.
- Use **soft delete** (default) when removing an account permanently but preserving references in logs.
- Use **hard delete** only when you must expunge PII and have confirmed no dependent records remain.

---

## 6. User Self-Registration

When `AUTOBOT_DEPLOYMENT_MODE` is not `single_user`, new users can create their own accounts via the signup endpoint.

**Endpoint:** `POST /auth/signup`

**No authentication required.**

```http
POST /auth/signup
Content-Type: application/json

{
  "username": "newuser",
  "email": "newuser@example.com",
  "password": "Secure99!",
  "display_name": "New User"
}
```

Field rules (enforced server-side):

| Field | Required | Validation |
|---|---|---|
| `username` | Yes | 3–50 chars, alphanumeric plus `-`/`_`, lowercased |
| `email` | Yes | Must contain `@`, max 255 chars, lowercased |
| `password` | Yes | 8–128 chars; requires uppercase, lowercase, and digit |
| `display_name` | No | Defaults to username if omitted |

Response `200 OK` on success:

```json
{
  "success": true,
  "message": "Account created successfully. You can now log in.",
  "username": "newuser"
}
```

The new account is assigned the `user` role automatically. An admin must elevate the role if higher privileges are needed.

**Error codes:**

| HTTP | Meaning |
|---|---|
| `400 Bad Request` | `single_user` mode — self-registration is disabled |
| `409 Conflict` | Username or email already in use |
| `422 Unprocessable Entity` | Password/username validation failure |

### single_user Mode Note

In `single_user` deployment mode the signup endpoint always returns:

```json
HTTP 400
{
  "detail": "Self-registration is not available in single-user mode"
}
```

To add users in single_user mode you must switch to `multi_user` mode and provision a PostgreSQL database, or use the admin panel from an account that already holds admin credentials.

---

## 7. Password Management

### User-Initiated Change

Users may change their own password via:

```http
POST /user-management/users/{user_id}/change-password
Authorization: Bearer <user-token>
Content-Type: application/json

{
  "current_password": "OldSecret1",
  "new_password": "NewSecret2"
}
```

The `current_password` field is required when called by the owning user. Admins changing another user's password may omit it (`require_current` is set to `false` server-side when `current_password` is absent).

New password must satisfy the same strength rules as signup (8–128 chars, uppercase, lowercase, digit).

On success all existing sessions for that user (except the one making the request) are invalidated.

### Rate Limiting

The change-password endpoint is protected by `PasswordChangeRateLimiter`. If the rate limit is exceeded the endpoint returns:

```http
HTTP 429 Too Many Requests
```

The counter resets automatically on a successful change. There is no admin UI to manually reset a rate-limit counter; wait for the window to expire or restart the backend service.

### Admin Password Reset

Admins do not have a dedicated "reset password" UI button. To reset another user's password, call the change-password endpoint with `current_password` omitted:

```http
POST /user-management/users/{user_id}/change-password
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "current_password": null,
  "new_password": "TemporaryPass1"
}
```

Then instruct the user to change the temporary password immediately on next login.

---

## 8. API Reference

All endpoints are prefixed `/user-management/users` and require a valid JWT bearer token unless noted otherwise. Write endpoints additionally require the `admin` role.

| Method | Path | Auth Required | Admin Only | Description |
|---|---|---|---|---|
| `GET` | `/` | Yes | No | List users (paginated, searchable) |
| `GET` | `/me` | Yes | No | Get current user profile |
| `GET` | `/search` | No | No | Search users for sharing dialogs |
| `GET` | `/{user_id}` | Yes | No | Get user by ID |
| `POST` | `/` | Yes | Yes | Create user |
| `PATCH` | `/{user_id}` | Yes | Yes | Update user profile |
| `DELETE` | `/{user_id}` | Yes | Yes | Delete user (soft by default) |
| `POST` | `/{user_id}/activate` | Yes | Yes | Activate user |
| `POST` | `/{user_id}/deactivate` | Yes | Yes | Deactivate user |
| `POST` | `/{user_id}/change-password` | Yes | No* | Change password |
| `PUT` | `/{user_id}/role` | Yes | Yes | Set system role by name |
| `POST` | `/{user_id}/roles/{role_id}` | Yes | Yes | Assign role by UUID |
| `DELETE` | `/{user_id}/roles/{role_id}` | Yes | Yes | Revoke role by UUID |

*Users may change their own password; admins may change any user's password.

### Pagination

`GET /user-management/users` accepts standard pagination parameters:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | integer | 20 | Records per page (max 100) |
| `offset` | integer | 0 | Record offset |
| `search` | string | — | Filter by email, username, or display name |
| `include_inactive` | boolean | false | Include deactivated accounts |

Response:

```json
{
  "users": [...],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

### Update User Profile

```http
PATCH /user-management/users/{user_id}
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "email": "newemail@example.com",
  "display_name": "Updated Name",
  "bio": "Senior engineer",
  "avatar_url": "https://example.com/avatar.png",
  "preferences": {"theme": "dark"}
}
```

All fields are optional. Returns the updated `UserResponse`.

---

## 9. Multi-Tenancy

AutoBot supports multi-tenant deployments where data is scoped by `org_id`. Each user record carries an optional `org_id` UUID that determines which organisation's data they can access.

### How It Works

- When a user is created with an `org_id`, the `UserService` applies a tenant filter (`apply_tenant_filter`) to all list and search queries. Users in organisation A cannot see users or data belonging to organisation B.
- `TenantContext` is constructed from the authenticated user's JWT claims and passed to every service call.
- Platform admins (`is_platform_admin=true`) bypass tenant filters and can see all users across all organisations.

### Creating Users in an Organisation

Pass the `org_id` field during user creation:

```http
POST /user-management/users
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "username": "orguser",
  "email": "orguser@corp.com",
  "password": "Corp1234",
  "org_id": "a1b2c3d4-0000-0000-0000-000000000001"
}
```

### Workspace Isolation

Each organisation's data (knowledge base collections, agent sessions, file uploads) is namespaced by `org_id` at the Redis and PostgreSQL layer. Removing a user from an organisation does not delete their data; it must be cleaned up separately via the knowledge management or file APIs.

---

## 10. Troubleshooting

### User Cannot Log In

1. Check that the account is **active** (`is_active: true`) in the admin panel.
2. Check for account lockout: after 3 failed login attempts the account is locked for 15 minutes. The lockout state is stored in Redis. Confirm via the audit log (`data/audit.log`) for `AUTH_0001` events.
3. Verify the password was not changed by another admin. Ask the user to confirm which credential they are using.
4. In `multi_user` mode, confirm PostgreSQL is reachable. Backend startup errors are logged to `/var/log/autobot/backend-error.log`.

### Permission Denied (403)

The user's current role does not include the required permission. Steps:

1. Navigate to `/admin/users` and confirm the user's displayed role.
2. Cross-reference the role against the permission matrix in Section 4 of this guide.
3. If the user needs elevated access, change their role via the inline dropdown.
4. If the action requires a permission not covered by any of the three system roles, check [AUTHENTICATION_RBAC.md](../../developer/AUTHENTICATION_RBAC.md) for advanced role configuration.

### Forgot Password / No Reset Email

AutoBot does not currently send password-reset emails. The recovery flow is:

1. User contacts an admin.
2. Admin issues a temporary password via the change-password API (see Section 7).
3. Admin instructs the user to log in with the temporary password and change it immediately.

### Admin Panel Shows "User management is not available"

This message appears when `AUTOBOT_DEPLOYMENT_MODE=single_user`. To enable multi-user management:

1. Set `AUTOBOT_DEPLOYMENT_MODE=multi_user` in your environment.
2. Ensure `AUTOBOT_DATABASE_URL` points to a running PostgreSQL instance.
3. Run database migrations: `alembic upgrade head` (or re-deploy via Ansible playbook).
4. Restart the backend service.

### Duplicate Username / Email on Create (409)

The username and email must be globally unique (or unique within an org in strict-tenant mode). Either choose a different value or locate the existing account using the search bar and reactivate it if it was deactivated.

### Rate Limit on Password Change (429)

Wait for the rate-limit window to expire. If immediate access is needed, restart the backend service (the in-memory rate-limit counters are stored in Redis and will reset on service restart, or naturally expire according to the configured TTL).
