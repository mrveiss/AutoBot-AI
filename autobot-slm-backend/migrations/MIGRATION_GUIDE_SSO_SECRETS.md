# SSO Secrets Migration Guide

## Overview

The `migrate_sso_secrets_to_system_secret.py` script migrates SSO provider credentials from plaintext JSONB config to encrypted SystemSecret storage (addresses MVA-1737).

## Pre-requisites

1. **Encryption key must be set:**
   ```bash
   export SLM_ENCRYPTION_KEY="<32+ character secure key>"
   # OR
   export SLM_SECRET_KEY="<32+ character secure key>"
   ```

2. **Database backup recommended:**
   ```bash
   pg_dump autobot_db > backup_before_sso_migration.sql
   ```

## Running the Migration

### Dry Run (Recommended First)

Test the migration without making changes:

```bash
cd autobot-slm-backend
python3 migrations/migrate_sso_secrets_to_system_secret.py --dry-run
```

The dry run will:
- Validate encryption key
- Copy secrets to encrypted storage
- Verify all secrets can be decrypted
- Roll back changes (no permanent modification)
- Report what would be migrated

### Production Run

After verifying dry run succeeds:

```bash
python3 migrations/migrate_sso_secrets_to_system_secret.py
```

You can also specify a database URL:

```bash
python3 migrations/migrate_sso_secrets_to_system_secret.py postgresql://user:pass@host/db
```

## Migration Process

The migration uses a **three-phase approach** for safety:

### Phase 1: Copy (Non-destructive)
- Extracts `client_secret` and `bind_password` from SSO provider configs
- Encrypts each secret using AES-256-GCM
- Stores in `system_secrets` table with key pattern `sso:provider:{id}:{field}`
- **Original plaintext values remain unchanged**

### Phase 2: Verify
- Retrieves each encrypted secret from database
- Decrypts and compares with original value
- **Migration aborts if any verification fails**

### Phase 3: Remove Plaintext
- Only executed after ALL providers verified
- Updates provider config to remove plaintext fields
- Adds reference fields (`client_secret_ref`, `bind_password_ref`)

## Error Handling

The migration handles:

1. **Missing encryption key** - Fails immediately with clear error
2. **Encryption failure** - Logs specific provider/field and aborts
3. **Verification failure** - Rolls back all changes
4. **Partial success** - Rolls back entire migration (all-or-nothing)
5. **Retry safety** - Updates existing secrets if rerun

## Retry Safety

The migration can be safely rerun if it fails:

- Detects existing encrypted secrets
- Updates them instead of creating duplicates
- Skips providers with no secrets to migrate
- Same transaction safety on retry

## Verification After Migration

1. **Check secret count:**
   ```sql
   SELECT COUNT(*) FROM system_secrets WHERE category = 'sso';
   ```

2. **Verify plaintext removed:**
   ```sql
   SELECT id, config 
   FROM sso_providers 
   WHERE config ? 'client_secret' OR config ? 'bind_password';
   ```
   Should return zero rows.

3. **Check references added:**
   ```sql
   SELECT id, config->'client_secret_ref', config->'bind_password_ref'
   FROM sso_providers 
   WHERE config ? 'client_secret_ref';
   ```

4. **Test SSO login** to confirm encrypted secrets work

## Rollback

If issues discovered after migration:

```sql
BEGIN;

-- Restore plaintext from backup
UPDATE sso_providers 
SET config = backup.config 
FROM backup_sso_providers backup
WHERE sso_providers.id = backup.id;

-- Remove encrypted secrets
DELETE FROM system_secrets WHERE category = 'sso';

COMMIT;
```

## Logging

The migration provides detailed logging:

- `INFO`: Progress updates, secrets migrated per provider
- `WARNING`: Short encryption keys (still functional)
- `ERROR`: Specific failures with provider/field context
- `DEBUG`: Per-secret verification details

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Acceptance Criteria Met

✅ **Encryption key validation** - Pre-flight check before any DB operations
✅ **Correct import path** - Absolute import from `autobot_slm_backend.services.encryption`
✅ **Non-destructive migration** - Two-phase copy-verify-remove approach
✅ **Detailed error handling** - Logs provider ID and field name on all failures
✅ **Safely retryable** - Detects and updates existing secrets on retry

## Related Issues

- **MVA-1737**: SSO credentials stored in plaintext
- **MVA-3882**: Harden migration script (this implementation)
- **PR #9676**: Original SSO encryption implementation
