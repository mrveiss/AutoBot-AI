# PostgreSQL User Management Database Deployment

**Issue:** #786
**Date:** 2026-02-06
**Status:** Implementation Complete

## Overview

This document describes the deployment of PostgreSQL databases for user management in the AutoBot platform. The architecture uses a dual-database approach:

1. **SLM Server Database** (172.16.168.19) - Local SLM admin users
2. **AutoBot Users Database** (172.16.168.23/Redis VM) - Remote application users

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      SLM Server (172.16.168.19)                 │
│  ┌─────────────────┐    ┌─────────────────────────────────────┐ │
│  │  PostgreSQL     │    │          SLM Backend                │ │
│  │  ├─ slm         │◄───│  (asyncpg + SQLAlchemy)             │ │
│  │  └─ slm_users   │    │                                     │ │
│  └─────────────────┘    └─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Remote connection
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Redis VM (172.16.168.23)                    │
│  ┌─────────────────┐                                            │
│  │  PostgreSQL     │                                            │
│  │  └─ autobot_users│                                           │
│  └─────────────────┘                                            │
└─────────────────────────────────────────────────────────────────┘
```

## Database Configuration

### Environment Variables

The SLM backend uses these environment variables (with defaults):

```bash
# Main SLM operational database
SLM_DATABASE_URL="postgresql+asyncpg://slm_app@127.0.0.1:5432/slm"

# SLM admin users database
SLM_USERS_DATABASE_URL="postgresql+asyncpg://slm_app@127.0.0.1:5432/slm_users"

# AutoBot application users database (on Redis VM)
AUTOBOT_USERS_DATABASE_URL="postgresql+asyncpg://autobot_app@172.16.168.23:5432/autobot_users"

# Connection pool settings
SLM_DB_POOL_SIZE=20
SLM_DB_POOL_MAX_OVERFLOW=10
SLM_DB_POOL_RECYCLE=3600
```

## Deployment Methods

### Method 1: Infrastructure Wizard (GUI)

1. Navigate to **Infrastructure** in the SLM Admin sidebar
2. Click **Run Setup Wizard**
3. Select the "User Management Database" playbook
4. Review variables and target hosts
5. Confirm and execute

### Method 2: Direct Playbook Execution

```bash
# On SLM server
cd /home/autobot/slm-server/ansible

# Deploy PostgreSQL and create databases
ansible-playbook -i inventory/hosts.yml playbooks/user-management-db.yml
```

### Method 3: Using ansible-runner (Programmatic)

```python
import ansible_runner

result = ansible_runner.run(
    playbook='playbooks/user-management-db.yml',
    inventory='inventory/hosts.yml',
    private_data_dir='/home/autobot/slm-server/ansible'
)
```

## Ansible Playbook Details

### Playbook: `user-management-db.yml`

**Location:** `slm-server/ansible/playbooks/user-management-db.yml`

**Tasks performed:**
1. Install PostgreSQL 15 on target hosts
2. Configure `postgresql.conf` for remote connections
3. Set up `pg_hba.conf` with secure authentication
4. Create databases (`slm`, `slm_users`, `autobot_users`)
5. Create database users with appropriate privileges
6. Enable and start PostgreSQL service

**Variables:**
- `postgresql_version`: "15" (default)
- `slm_db_user`: "slm_app"
- `autobot_db_user`: "autobot_app"
- `slm_db_password`: Auto-generated or from vault
- `autobot_db_password`: Auto-generated or from vault

## Migration System

### Running Migrations

Migrations run automatically on SLM backend startup. For manual execution:

```bash
cd /home/autobot/slm-server
python -m migrations.runner
```

### Migration Files

All migrations have been updated for PostgreSQL compatibility:
- Uses `psycopg2` for synchronous operations
- Uses `SERIAL PRIMARY KEY` instead of `INTEGER PRIMARY KEY AUTOINCREMENT`
- Uses `JSONB` instead of `JSON` for native PostgreSQL JSON support
- Uses `information_schema` instead of SQLite's `PRAGMA`

## Health Checks

### Database Health Endpoint

```bash
curl http://172.16.168.19:8000/api/health/database
```

**Response:**
```json
{
  "status": "healthy",
  "database": "postgresql"
}
```

### General Health Endpoint

```bash
curl http://172.16.168.19:8000/api/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "database": "healthy",
  "nodes_online": 5,
  "nodes_total": 5
}
```

## Troubleshooting

### Connection Issues

1. **Check PostgreSQL is running:**
   ```bash
   sudo systemctl status postgresql
   ```

2. **Verify pg_hba.conf allows connections:**
   ```bash
   sudo cat /etc/postgresql/15/main/pg_hba.conf | grep -v "^#"
   ```

3. **Test connection:**
   ```bash
   psql -h 127.0.0.1 -U slm_app -d slm -c "SELECT 1"
   ```

### Migration Failures

1. **Check database exists:**
   ```bash
   psql -h 127.0.0.1 -U postgres -c "\\l"
   ```

2. **Run migrations manually:**
   ```bash
   python -m migrations.runner
   ```

3. **Check migration status:**
   ```sql
   SELECT * FROM migrations_applied ORDER BY applied_at;
   ```

## Security Considerations

1. **Password Management:** Database passwords are generated by Ansible and stored in environment variables
2. **Network Security:** PostgreSQL only accepts connections from specific IPs via `pg_hba.conf`
3. **User Privileges:** Database users have minimal required privileges (no superuser access)
4. **Connection Encryption:** Consider enabling SSL/TLS for production environments

## Related Files

- `slm-server/config.py` - Database URL configuration
- `slm-server/services/database.py` - Database service with connection pooling
- `slm-server/migrations/` - PostgreSQL-compatible migrations
- `slm-server/ansible/playbooks/user-management-db.yml` - Deployment playbook
- `slm-admin/src/views/InfrastructureView.vue` - Infrastructure wizard UI
