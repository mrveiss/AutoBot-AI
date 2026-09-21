# Rotating the audit worker's GitHub filing credential (#13859)

The audit worker (`autobot-backend/workers/audit_tasks.py`) files GitHub issues
through a token it reads from the SYSTEM vault under the key
`github_issue_filing_token`, via `EnvelopeSecretsService`
(`autobot_shared/secrets_vault.py`, `autobot-backend/services/envelope_secrets_service.py`).
This is the only store the worker reads — see `_read_filing_token()` in
`audit_tasks.py`. Nothing else in AutoBot's own code paths shells out to `gh`.

## Before you start: which UI, and which one does *not* work here

The general **Secrets Manager** page (`/secrets`, `SecretsManager.vue`) has a
"System" visibility option in its create-secret form. **Do not use it for this
credential.** That form posts to the legacy secrets store
(`autobot-backend/api/secrets.py`), which is a separate system from the vault
`EnvelopeSecretsService` reads. A secret named `github_issue_filing_token`
created there is mirrored into the SYSTEM vault only if its name matches a
known LLM provider key (`_mirror_llm_provider_key`, #10088 Task 7) — this name
never does, so the worker would never see it, silently. This is a real gap
between the two secrets UIs and is filed separately (see the note at the
bottom of this doc); until it's closed, this credential must be created,
rotated, and revoked through the API directly, by an admin, as below.

## Granting or rotating the token (human-approved step)

There is no point-and-click form for this specific action yet, so an admin
performs it as an authenticated API call — still a human action, still
requiring the admin's own session, never an automated or scripted rotation.

1. **Create a fine-grained GitHub Personal Access Token**, scoped to the
   `mrveiss/AutoBot-AI` repository, with exactly:
   - Issues: **Read and write** (needed to file new issues — see the note
     below on the umbrella's stricter read+comment-only role, which is a
     *different*, not-yet-built credential: #17090)
   - No other repository or account permissions.
2. **Find whether a `github_issue_filing_token` secret already exists**, as an
   admin, authenticated in the browser (or with an admin session cookie/token
   for a direct API call):
   ```
   GET /api/v2/secrets
   ```
   Look for `name == "github_issue_filing_token"` in the response; note its
   `id` if present.
3. **First grant** (nothing exists yet):
   ```
   POST /api/v2/secrets
   {
     "owner_vault": "system",
     "name": "github_issue_filing_token",
     "secret_type": "api_key",
     "value": "<the PAT from step 1>"
   }
   ```
4. **Rotation** (a secret already exists, and step 2 found its `id`):
   ```
   PUT /api/v2/secrets/{id}
   {
     "value": "<the new PAT from step 1>"
   }
   ```
   The worker re-reads the vault at the start of every task run
   (`reset_gh_env_cache()`, called first thing in every audit task) — a
   rotated token takes effect on the very next run, not "whenever the worker
   next restarts."
5. Both calls require the caller's RBAC facts to include admin
   (`services/secrets_authz.py::authorize` grants SYSTEM-vault write only when
   `facts.is_admin`) — a non-admin session gets a 403, and there is no path
   around that check.

## Revocation

Revoking is two independent actions — doing only one leaves a gap:

1. **Revoke the GitHub-side PAT** itself (GitHub → Settings → Developer
   settings → Personal access tokens → revoke). This is what actually stops
   the credential from working, including anywhere it might have leaked to.
2. **Delete the vault entry**, so a future worker restart or vault re-read
   doesn't keep offering the dead token as if it were live:
   ```
   DELETE /api/v2/secrets/{id}
   ```
   Same admin-only gate as creation and rotation.

After revocation with no replacement token stored, the worker falls back to
ambient `gh` CLI auth for whichever account the Celery process runs as — and
says so, loudly, on every single run (`_gh_available()`'s WARNING log), never
silently. This ambient fallback is a deliberate, reviewed design decision
(#14057) for dev-host friendliness, not an oversight — it is not removed by
revoking the vault-owned token.

## Verifying a rotation or revocation took effect

Query the worker's own recorded status rather than trusting a log line:

```
GET redis key `audit:filing_status` (database: knowledge)
```

`credential_source` reads `"system vault"` after a successful grant/rotation,
and `"ambient CLI auth"` after a revocation with nothing re-granted. This key
is written by `_record_filing_status()` at the start of every task and at
worker startup — it reflects the current run, not a stale one.

## Known gap: no dedicated UI form for this credential

Filed separately: wiring the Secrets Manager UI (or a small admin-only page)
to `POST /api/v2/secrets` / `PUT /api/v2/secrets/{id}` / `DELETE
/api/v2/secrets/{id}` so this doesn't require a direct API call. Until that
lands, the steps above are the only correct path — the existing "System"
visibility option in `SecretsManager.vue` looks like it should work and does
not, silently, for any secret name outside the LLM-provider-key list.
