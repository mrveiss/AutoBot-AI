# SLM User Management System Design

**Issue:** #576 - User Management happens on SLM system
**Date:** 2026-02-05
**Status:** Approved

## Overview

Migrate all user management functionality from main AutoBot backend to SLM server, establishing SLM as the central authentication authority for the entire AutoBot platform.

## Architecture

### Two User Databases

```
┌──────────────────────────────────────────────────────┐
│ PostgreSQL Server 1: SLM Server (172.16.168.19:5432)│
│                                                      │
│ ┌──────────────────────────────────────────────┐   │
│ │ Database: slm_users (local)                  │   │
│ │ Purpose: SLM fleet management access         │   │
│ │ Users: Fleet admins, DevOps, system admins   │   │
│ │ Auth: SLM authenticates locally              │   │
│ └──────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ PostgreSQL Server 2: Redis VM (172.16.168.23:5432)  │
│                                                      │
│ ┌──────────────────────────────────────────────┐   │
│ │ Database: autobot_users (shared)             │   │
│ │ Purpose: AutoBot application functionality   │   │
│ │ Users: Chat users, tool users, end-users     │   │
│ │ Auth: Frontend/Main VM authenticate here    │   │
│ └──────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

### Connection Matrix

| Component | Connects To | Purpose |
|-----------|-------------|---------|
| **SLM Server** | `172.16.168.19:5432/slm_users` | Own auth |
| **SLM Server** | `172.16.168.23:5432/autobot_users` | Manage AutoBot users |
| **Frontend VM** | `172.16.168.23:5432/autobot_users` | User auth |
| **Main Backend** | `172.16.168.23:5432/autobot_users` | User auth |

### Benefits

- ✅ SLM fully independent (own local DB)
- ✅ AutoBot user DB on reliable Redis VM
- ✅ Clear separation of admin vs user populations
- ✅ SLM can manage AutoBot users remotely
- ✅ Instant consistency via shared database
- ✅ No complex sync infrastructure needed

## Code Migration

### Files to Migrate

```
FROM: /home/kali/Desktop/AutoBot/src/user_management/
TO:   /home/kali/Desktop/AutoBot/slm-server/user_management/

├── models/
│   ├── base.py
│   ├── user.py
│   ├── team.py
│   ├── organization.py
│   ├── role.py
│   ├── api_key.py
│   ├── sso.py
│   ├── mfa.py
│   └── audit.py
│
├── services/
│   ├── base_service.py
│   ├── user_service.py
│   ├── team_service.py
│   └── organization_service.py
│
├── schemas/
│   └── user.py
│
├── database.py (MODIFIED - dual DB support)
├── config.py (MODIFIED)
└── middleware/
    └── rbac_middleware.py
```

### Key Modifications

**1. `database.py` - Dual Database Support:**

```python
def get_slm_engine():
    """SLM local database (172.16.168.19:5432/slm_users)"""
    return create_async_engine(
        f"postgresql+asyncpg://{user}:{pwd}@172.16.168.19:5432/slm_users"
    )

def get_autobot_engine():
    """AutoBot user database (172.16.168.23:5432/autobot_users)"""
    return create_async_engine(
        f"postgresql+asyncpg://{user}:{pwd}@172.16.168.23:5432/autobot_users"
    )
```

**2. Services - Database Context:**

```python
class UserService:
    async def create_slm_user(self, db: AsyncSession, user_data):
        """Create user in SLM database"""
        # db connected to 172.16.168.19

    async def create_autobot_user(self, db: AsyncSession, user_data):
        """Create user in AutoBot database"""
        # db connected to 172.16.168.23
```

### Files to Delete from AutoBot

- Remove `src/user_management/` entirely
- Remove `backend/api/user_management/` entirely
- Update `backend/api/auth.py` to connect to Redis VM PostgreSQL

## API Structure

### SLM API Endpoints

```
SLM Server: http://172.16.168.19:8000/api/

┌─────────────────────────────────────────────────────┐
│ SLM Admin User Management (Local DB)                │
├─────────────────────────────────────────────────────┤
│ POST   /api/slm-users                               │
│ GET    /api/slm-users                               │
│ GET    /api/slm-users/{user_id}                     │
│ PATCH  /api/slm-users/{user_id}                     │
│ DELETE /api/slm-users/{user_id}                     │
│ POST   /api/slm-users/{user_id}/roles               │
│ POST   /api/slm-auth/login                          │
│ POST   /api/slm-auth/logout                         │
│ GET    /api/slm-auth/me                             │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ AutoBot User Management (Remote DB on Redis VM)     │
├─────────────────────────────────────────────────────┤
│ POST   /api/autobot-users                           │
│ GET    /api/autobot-users                           │
│ GET    /api/autobot-users/{user_id}                 │
│ PATCH  /api/autobot-users/{user_id}                 │
│ DELETE /api/autobot-users/{user_id}                 │
│ POST   /api/autobot-users/{user_id}/roles           │
│                                                      │
│ POST   /api/autobot-teams                           │
│ GET    /api/autobot-teams                           │
│ PATCH  /api/autobot-teams/{team_id}/members         │
└─────────────────────────────────────────────────────┘
```

### Authentication Flows

**SLM Admin Login:**
```
User → SLM Admin UI → POST /api/slm-auth/login
                      ↓
                SLM checks 172.16.168.19:5432/slm_users
                      ↓
                Returns JWT token
```

**AutoBot User Login:**
```
User → Frontend UI → POST /api/auth/login
                     ↓
           Main Backend checks 172.16.168.23:5432/autobot_users
                     ↓
                Returns JWT token
```

### AutoBot Backend Changes

```python
# backend/api/auth.py
async def login(username, password):
    # Connect to 172.16.168.23:5432/autobot_users
    async with get_autobot_db_session() as db:
        user = await authenticate_user(db, username, password)
        return create_jwt_token(user)
```

### SLM Manages AutoBot Users

```python
# slm-server/api/autobot_users.py
@router.post("/api/autobot-users")
async def create_autobot_user(
    user_data: UserCreate,
    current_admin: User = Depends(require_slm_admin)
):
    # Connect to REMOTE database (172.16.168.23)
    async with get_autobot_db_session() as db:
        user = await user_service.create_user(db, user_data)

        # Optional: Notify Frontend VM of user change via webhook
        await notify_autobot_user_change(user)

        return user
```

## Sync & Notification Mechanism

### Direct Database Access (Recommended)

```
SLM creates user
    ↓
Writes to 172.16.168.23:5432/autobot_users
    ↓
Frontend/Main Backend reads from same database
    ↓
No sync needed - instant consistency
```

### Benefits

- ✅ Instant consistency (no sync delay)
- ✅ Simple architecture (no webhooks/queues)
- ✅ PostgreSQL handles concurrency
- ✅ No sync failures to handle

### Optional: Cache Invalidation

If Frontend/Main Backend caches user data (permissions, roles):

```python
# slm-server/api/autobot_users.py
@router.patch("/api/autobot-users/{user_id}")
async def update_autobot_user(user_id: str, updates: UserUpdate):
    # Update in database
    async with get_autobot_db_session() as db:
        user = await user_service.update_user(db, user_id, updates)

    # Optional: Notify AutoBot to invalidate cache
    await redis_client.publish(
        "user:cache:invalidate",
        json.dumps({"user_id": user_id})
    )

    return user
```

```python
# backend/api/auth.py (AutoBot Main Backend)
async def listen_for_user_changes():
    """Subscribe to Redis pub/sub for user cache invalidation"""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("user:cache:invalidate")

    async for message in pubsub.listen():
        user_id = json.loads(message["data"])["user_id"]
        # Invalidate local cache
        permission_cache.delete(user_id)
```

## Frontend Changes

### SLM Admin Dashboard

Update `slm-admin/src/views/settings/admin/UserManagementSettings.vue`:

```typescript
// OLD: Calls AutoBot backend
const API_BASE = '/autobot-api'

// NEW: Calls SLM backend with dual user management
const SLM_API_BASE = 'http://172.16.168.19:8000/api'

// Two user management sections:
// 1. SLM Admins
async function loadSLMAdmins() {
  const response = await fetch(`${SLM_API_BASE}/slm-users`)
  slmAdmins.value = await response.json()
}

// 2. AutoBot Users (managed remotely)
async function loadAutoBotUsers() {
  const response = await fetch(`${SLM_API_BASE}/autobot-users`)
  autobotUsers.value = await response.json()
}
```

### Updated UI Layout

```vue
<template>
  <div class="user-management">
    <!-- Tab 1: SLM Administrators -->
    <div v-if="activeTab === 'slm-admins'">
      <h2>SLM Fleet Administrators</h2>
      <p>These users can access the SLM admin dashboard</p>
      <UserTable :users="slmAdmins" @create="createSLMAdmin" />
    </div>

    <!-- Tab 2: AutoBot Users -->
    <div v-if="activeTab === 'autobot-users'">
      <h2>AutoBot Application Users</h2>
      <p>These users can access AutoBot chat and tools</p>
      <UserTable :users="autobotUsers" @create="createAutoBotUser" />
    </div>

    <!-- Tab 3: Teams (AutoBot only) -->
    <div v-if="activeTab === 'teams'">
      <h2>AutoBot Teams</h2>
      <TeamTable :teams="autobotTeams" />
    </div>
  </div>
</template>
```

### AutoBot Frontend (autobot-vue)

Minimal changes - just update API connection:

```typescript
// autobot-vue/src/stores/auth.ts
// No changes - still connects to Main Backend
const API_BASE = 'http://172.16.168.20:8001/api'

// Main Backend now connects to 172.16.168.23:5432/autobot_users
// Frontend doesn't need to know about SLM
```

## Implementation Phases

### Phase 1: Database Setup
- [ ] Create `slm_users` database on SLM Server (172.16.168.19:5432)
- [ ] Create `autobot_users` database on Redis VM (172.16.168.23:5432)
- [ ] Run Alembic migrations on both databases
- [ ] Create initial SLM admin user

### Phase 2: Code Migration to SLM
- [ ] Copy `src/user_management/` → `slm-server/user_management/`
- [ ] Modify `database.py` for dual database support
- [ ] Update `config.py` for SLM environment
- [ ] Create SLM API endpoints (`/api/slm-users`, `/api/autobot-users`)

### Phase 3: AutoBot Backend Updates
- [ ] Update `backend/api/auth.py` to connect to `172.16.168.23:5432/autobot_users`
- [ ] Remove `src/user_management/` from AutoBot
- [ ] Remove `backend/api/user_management/` from AutoBot
- [ ] Update SSOT config for PostgreSQL connections

### Phase 4: Frontend Updates
- [ ] Update `slm-admin/src/views/settings/admin/UserManagementSettings.vue`
- [ ] Add tabs for SLM vs AutoBot users
- [ ] Update API calls to point to SLM server
- [ ] Test user creation/modification flows

### Phase 5: Testing & Migration
- [ ] Migrate existing users from AutoBot to `autobot_users` database
- [ ] Create initial SLM admin accounts
- [ ] Test SLM admin login
- [ ] Test AutoBot user login
- [ ] Test user management operations from SLM admin UI
- [ ] Verify cache invalidation (if implemented)

### Phase 6: Documentation & Cleanup
- [ ] Update deployment documentation
- [ ] Update API documentation
- [ ] Update architecture diagrams
- [ ] Clean up old user management code from AutoBot

## Technical Considerations

### Security
- Both databases require secure credentials
- JWT tokens remain separate (SLM vs AutoBot)
- SLM admin users cannot automatically access AutoBot
- RBAC permissions enforced in both systems

### Performance
- Direct database access = no sync latency
- Optional Redis pub/sub for cache invalidation
- PostgreSQL connection pooling for both databases

### Backward Compatibility
- Existing AutoBot users migrated to new database
- JWT tokens regenerated after migration
- No downtime required (blue-green deployment possible)

### Failure Modes
- If SLM is down, AutoBot auth still works (separate DB)
- If Redis VM PostgreSQL is down, AutoBot auth fails (single point)
- SLM can manage users even if AutoBot is offline

## Success Criteria

- ✅ SLM admin can create/manage SLM admin users
- ✅ SLM admin can create/manage AutoBot users
- ✅ AutoBot users can login via Frontend UI
- ✅ SLM admins can login via SLM admin UI
- ✅ User changes in SLM immediately reflected in AutoBot
- ✅ All existing AutoBot users migrated successfully
- ✅ No user management code remains in main AutoBot backend

## Related Issues

- #576 - User Management System with SSO, 2FA, and API Keys
- #601 - SSOT Phase 1: Foundation
- #694 - Config consolidation

## References

- Existing user management: `src/user_management/`
- SLM auth: `slm-server/api/auth.py`
- AutoBot auth: `backend/api/auth.py`
