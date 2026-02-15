# Session & Secret Data Migration Scripts

**Part of Issue #875 - Session & Secret Data Migration (#608 Phase 7)**

## Overview

This directory contains migration scripts to add user attribution and ownership to existing chat sessions and secrets.

## Prerequisites

1. **Backup production database** before running any migration
2. Redis must be running and accessible
3. Python 3.10+ with required dependencies
4. All AutoBot backend modules must be in path

## Migration Scripts

### 1. `migrate_sessions_user_attribution.py`

Adds user attribution to existing chat sessions:
- Infers `owner_id` from first message sender
- Adds `created_at` timestamps if missing
- Registers ownership in Redis indices (user:sessions:*, org:sessions:*, team:sessions:*)

**Usage:**
```bash
# Dry run (recommended first)
python3 migrate_sessions_user_attribution.py --dry-run

# Actual migration
python3 migrate_sessions_user_attribution.py
```

**Rollback:** Creates `/tmp/session_migration_rollback.sql`

### 2. `migrate_secrets_ownership.py`

Adds ownership and scope to existing secrets:
- Infers `owner_id` from creation metadata or session owner
- Adds `scope` field (default: 'user')
- Ensures all secret values are encrypted
- Registers ownership in Redis indices (user:secrets:*)

**Usage:**
```bash
# Dry run (recommended first)
python3 migrate_secrets_ownership.py --dry-run

# Actual migration
python3 migrate_secrets_ownership.py
```

**Rollback:** Creates `/tmp/secrets_migration_rollback.sql`

### 3. `cleanup_orphaned_sessions.py`

Removes orphaned/empty chat sessions:
- Sessions with no messages AND no activities
- Sessions with no owner and no messages
- Sessions with corrupt metadata
- Minimum age check (default: 7 days)

**Usage:**
```bash
# Dry run (recommended first)
python3 cleanup_orphaned_sessions.py --dry-run

# Actual cleanup (7+ day old sessions)
python3 cleanup_orphaned_sessions.py

# Custom minimum age
python3 cleanup_orphaned_sessions.py --min-age-days 14
```

**Output:** Creates `/tmp/deleted_sessions.txt` with list of deleted sessions

### 4. `backfill_activity_user_ids.py`

Backfills `user_id` for existing chat messages and activities:
- Adds `user_id` to messages (from metadata or session owner)
- Links activities to users
- Updates memory graph entities

**Usage:**
```bash
# Dry run (recommended first)
python3 backfill_activity_user_ids.py --dry-run

# Actual backfill
python3 backfill_activity_user_ids.py
```

### 5. `validate_migration.py`

Validates migration completion and data integrity:
- Verifies all sessions have `owner_id`
- Verifies all secrets have `owner_id` and `scope`
- Checks encryption status
- Reports orphaned entities
- Generates detailed validation report

**Usage:**
```bash
# Standard validation
python3 validate_migration.py

# Verbose mode (shows details for each entity)
python3 validate_migration.py --verbose
```

**Output:**
- Console report
- `/tmp/migration_validation_report.txt`
- `/tmp/migration_issues.json` (if issues found)

**Exit code:** 1 if errors found, 0 if successful

## Recommended Migration Workflow

### Phase 1: Preparation
```bash
# 1. Backup database
redis-cli BGSAVE

# 2. Run dry-run for all scripts
python3 migrate_sessions_user_attribution.py --dry-run
python3 migrate_secrets_ownership.py --dry-run
python3 backfill_activity_user_ids.py --dry-run
python3 cleanup_orphaned_sessions.py --dry-run

# 3. Review dry-run output
```

### Phase 2: Migration
```bash
# 1. Add user attribution to sessions (74 sessions expected)
python3 migrate_sessions_user_attribution.py

# 2. Add ownership to secrets
python3 migrate_secrets_ownership.py

# 3. Backfill user IDs in messages/activities
python3 backfill_activity_user_ids.py

# 4. Validate migration
python3 validate_migration.py

# 5. If validation passes, cleanup orphaned sessions
python3 cleanup_orphaned_sessions.py
```

### Phase 3: Verification
```bash
# Final validation
python3 validate_migration.py --verbose

# Expected results:
# - All sessions have owner_id: 100%
# - All secrets have owner_id: 100%
# - All secrets have scope: 100%
# - Orphaned sessions removed: ~45
```

## Data Integrity Checks

Each script performs the following safety checks:

1. **Non-destructive operations** (except cleanup script)
2. **Idempotency** - safe to run multiple times
3. **Graceful error handling** - continues on individual failures
4. **Detailed logging** - all operations logged
5. **Statistics reporting** - summary at end
6. **Rollback support** - SQL generated for reversals

## Expected Data Volumes

Based on issue #875:
- **74 sessions** to migrate
- **48 entities** to add user attribution
- **45 empty sessions** to remove
- **Unknown number** of secrets to migrate
- **Unknown number** of messages to backfill

## Troubleshooting

### Redis Connection Failed
```bash
# Check Redis is running
redis-cli ping

# Verify connection settings
echo $REDIS_HOST
echo $REDIS_PORT
```

### Permission Errors
```bash
# Ensure scripts are executable
chmod +x *.py

# Check Python path includes autobot modules
python3 -c "import sys; print(sys.path)"
```

### Migration Partial Success
If a migration partially completes:
1. Review the error messages in the log
2. Run `validate_migration.py` to see current state
3. Re-run the migration script (scripts are idempotent)
4. If needed, use rollback SQL from `/tmp/*_rollback.sql`

### Rollback Procedure
```bash
# Review rollback SQL
cat /tmp/session_migration_rollback.sql
cat /tmp/secrets_migration_rollback.sql

# Apply rollback manually via Redis CLI
# (Rollback SQL contains documentation, manual reversal required)
```

## Support

For issues or questions:
- GitHub Issue: #875
- Parent Issue: #608 - User-Centric Session Tracking

## License

AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss
