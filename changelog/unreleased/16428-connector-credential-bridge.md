---
type: feat
scope: backend
issue: 16428
---
`POST/GET/PUT/DELETE /api/secrets` now bridge transparently to `ConnectorCredentialStore` (ADR-007) when a request names a `connector_id` and `auth_type` — the owner's decision on #13632 that connector credentials come from one store. A new typed `credentials` field carries the sensitive auth fields (single or multi-field, validated against the connector's `auth_schema()`), separately from the legacy `value` field; a bridged secret's GET response is metadata-only, and PUT/DELETE rotate or revoke the credential in place rather than writing a second copy into the page's own store. `SecretCreateRequest` and `SecretUpdateRequest` are extended, not replaced — every existing request shape keeps working unchanged.
