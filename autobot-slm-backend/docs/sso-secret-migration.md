# SSO Secret Migration Guide

Moves OAuth `client_secret` and LDAP `bind_password` from plaintext JSONB in
`sso_providers.config` to AES-256-GCM-encrypted rows in the `system_secrets`
table. Introduced in PR #9676 (MVA-1737).

## Overview

Before migration, SSO provider secrets are stored in plaintext in the
`sso_providers.config` JSONB column. After migration, each secret is encrypted
and stored in `system_secrets` under a key like:

```
sso:provider:<provider_uuid>:client_secret
sso:provider:<provider_uuid>:bind_password
```

The config column retains only a `*_ref` pointer:
```json
{ "client_secret_ref": "sso:provider:<uuid>:client_secret" }
```

The migration is **idempotent** — it is safe to run multiple times. Secrets
that already exist in `system_secrets` are updated rather than duplicated.

---

## Prerequisites

### 1. Encryption key must be set

The migration encrypts secrets using `SLM_ENCRYPTION_KEY` (falls back to
`SLM_SECRET_KEY` if absent). This key must be set in the environment before
running the migration **and** must be the same key used by the running backend.

Generate a key (once, keep it secret):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Store it in `/etc/autobot/slm-secrets.env` on the backend host (the same file
Ansible manages for the backend service):

```env
SLM_ENCRYPTION_KEY=<your-generated-key>
```

**Verify the key is present before continuing:**

```bash
grep SLM_ENCRYPTION_KEY /etc/autobot/slm-secrets.env
# should print a non-empty value
```

### 2. Database access

The migration connects to PostgreSQL via the `DATABASE_URL` environment
variable, `/etc/autobot/db-credentials.env`, or the `config.settings` module
(tried in that order). Ensure the running user can read one of those sources.

### 3. Python environment

Run from inside the backend virtual environment:

```bash
source /opt/autobot/autobot-slm-backend/venv/bin/activate
cd /opt/autobot/autobot-slm-backend
```

---

## When to Run

Run the migration **before** deploying the new backend code that uses
`SSOSecretsManager`. The migration is a data transform, not a schema change —
no table alterations are required first.

Recommended order:

1. Set `SLM_ENCRYPTION_KEY` on the backend host.
2. Run the migration (see below) while the **old** backend is still running.
   The old code reads only `config`; migrated rows add `*_ref` keys that the
   old code ignores.
3. Deploy the new backend code (PR #9676).
4. Verify (see Verification section).

---

## Running the Migration

### Manual (recommended for first migration)

```bash
# On the backend host, source the secrets file and run:
set -o allexport
source /etc/autobot/slm-secrets.env
set +o allexport

cd /opt/autobot/autobot-slm-backend
source venv/bin/activate

python migrations/migrate_sso_secrets_to_system_secret.py
# Pass DATABASE_URL explicitly if the env var is not already set:
# python migrations/migrate_sso_secrets_to_system_secret.py postgresql://user:pass@host/dbname
```

Expected output (no SSO providers is also fine):

```
INFO Found 3 SSO providers to migrate
INFO Created secret: sso:provider:<uuid>:client_secret
INFO Created secret: sso:provider:<uuid>:bind_password
INFO Migrated 2 secrets for provider <uuid>
...
INFO Migration completed successfully! Migrated secrets for 3 providers
```

### Via Ansible

The migration can be embedded in the deployment playbook as a one-shot task.
Add this task to `ansible/deploy-slm-backend.yml` (or equivalent) **before**
the service restart:

```yaml
- name: Run SSO secret migration
  command: >
    /opt/autobot/autobot-slm-backend/venv/bin/python
    migrations/migrate_sso_secrets_to_system_secret.py
  args:
    chdir: /opt/autobot/autobot-slm-backend
  environment:
    SLM_ENCRYPTION_KEY: "{{ slm_encryption_key }}"
    DATABASE_URL: "{{ database_url }}"
  register: sso_migration_result
  changed_when: "'Migrated secrets for' in sso_migration_result.stdout"

- name: Show migration output
  debug:
    var: sso_migration_result.stdout_lines
```

Where `slm_encryption_key` and `database_url` come from Ansible Vault or
`group_vars/backend.yml`.

---

## Verification

After the migration, confirm secrets are stored correctly:

```bash
# Count migrated secrets (should be ≥ 1 per SSO provider that had credentials)
psql "$DATABASE_URL" -c "SELECT count(*) FROM system_secrets WHERE category = 'sso';"

# Inspect a secret entry (encrypted_value should not be human-readable)
psql "$DATABASE_URL" -c \
  "SELECT key, left(encrypted_value, 20) || '...' AS encrypted_preview, updated_at
   FROM system_secrets WHERE category = 'sso' ORDER BY updated_at DESC LIMIT 5;"

# Confirm plaintext secrets are gone from sso_providers
psql "$DATABASE_URL" -c \
  "SELECT id,
          (config ? 'client_secret') AS has_plaintext_secret,
          (config ? 'bind_password') AS has_plaintext_password,
          (config ? 'client_secret_ref') AS has_secret_ref
   FROM sso_providers;"
# All rows should show: has_plaintext_secret=f, has_plaintext_password=f, has_secret_ref=t (when applicable)
```

Then smoke-test SSO login end-to-end to confirm the backend can decrypt and use
the credentials:

```bash
# Hit the SLM health endpoint
curl -s http://localhost:8000/health | jq .

# If you have an SSO provider configured, attempt an OAuth flow or LDAP bind
# through the AutoBot UI to confirm authentication still works.
```

---

## Rollback

The migration updates `sso_providers.config` (replaces plaintext fields with
`*_ref` keys) and inserts rows into `system_secrets`. To roll back:

> **Warning:** Rolling back re-exposes plaintext secrets in the database.
> Only do this in a controlled environment and rotate credentials afterward.

```sql
-- For each affected provider, restore the plaintext secret from system_secrets.
-- Replace <provider_id> and <field> with actual values.

BEGIN;

UPDATE sso_providers
SET config = jsonb_set(
    config - 'client_secret_ref',
    '{client_secret}',
    (SELECT to_jsonb(decrypt_field(encrypted_value))
     FROM system_secrets
     WHERE key = 'sso:provider:' || id::text || ':client_secret')
)
WHERE config ? 'client_secret_ref';

-- Repeat for bind_password if applicable.

-- Remove the now-restored system_secrets rows:
DELETE FROM system_secrets WHERE category = 'sso';

COMMIT;
```

> **Note:** `decrypt_field` is a PostgreSQL function only if you have loaded a
> custom extension. In practice, run the Python decryption helper instead and
> apply the values via an UPDATE statement manually, or restore from a
> pre-migration database backup.

Simplest rollback: **restore from a database backup taken before the
migration**, then redeploy the old backend code.

---

## Environment Variable Reference

| Variable | Required | Description |
|---|---|---|
| `SLM_ENCRYPTION_KEY` | **Yes** | AES-256 master key; minimum 32 chars recommended. Falls back to `SLM_SECRET_KEY`. |
| `DATABASE_URL` | No (auto-detected) | PostgreSQL connection URL. Falls back to `/etc/autobot/db-credentials.env` then `config.settings`. |

`SLM_ENCRYPTION_KEY` is the same key used by the running backend service. If
you generate a new key for this migration, you must also update the backend's
environment and restart the service.

---

## Related

- PR #9676 — implementation of `SystemSecret` storage and `SSOSecretsManager`
- MVA-1737 — security hardening issue that drove this change
- `autobot-slm-backend/services/encryption.py` — `EncryptionService` class
- `autobot-slm-backend/user_management/services/sso_secrets.py` — runtime secret access
- `autobot-slm-backend/migrations/migrate_sso_secrets_to_system_secret.py` — migration script
