---
type: fix
scope: secrets
issue: 20665
pr: 21011
---
The audit record written before a credential delete or rotate (`DELETE`/`PUT /api/secrets/{id}`)
now says `attempted` instead of `success`, so a write that then fails no longer leaves a record
claiming it happened; only the record written after the write says `success`. The two envelope
deletes (`DELETE /api/v2/secrets/{id}` and the service-identity `DELETE /api/v2/secrets/system/{id}`)
now refuse a secret that still has dependents with the main route's 409 and dependents list (the
user route takes `confirm_dependents`; a service identity cannot confirm), and record their intent
and outcome in the audit trail (#20640). The bulk chat-secret delete reaches only legacy file-store
ids, which never have dependents, so it is unchanged.
