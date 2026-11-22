---
type: fix
scope: backend
issue: 18478
---
Rolling back a config revision now writes the snapshot to the live settings or agent config before the rollback is recorded. A failed apply records nothing, an unknown entity type answers 400, and redacted placeholders in the snapshot keep the current live secret.
