---
type: fix
scope: backend
issue: 16579
pr: 0000
---
SecretsService.get_secret now returns the secret's created_by, so ConnectorCredentialStore's load, rotate and revoke can identify the credential's owner instead of refusing everyone. The single-row read never selected or mapped that column while the list read always did, and ConnectorCredentialStore treats a missing owner as a denial (fail-closed, #13628) — so on the default path every connector credential was unreadable, unrotatable and unrevocable by the user who created it. The column is appended to the query rather than inserted, leaving the existing positional row mapping untouched.
