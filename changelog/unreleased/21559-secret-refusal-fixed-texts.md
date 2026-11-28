---
type: fix
scope: backend
issue: 21559
pr: 21732
---
Mapped validation, permission and not-found failures on the secret routes now answer with one shared fixed text and never echo an id, a vault reference or an exception message. HTTP errors a delete route builds itself still pass through unchanged (decision pending on #21559). Client-visible wording changed, statuses did not: "Secret not found" is now "Not found", and "Not permitted to create this secret", "Not permitted to access this secret" and "You can only share secrets you own" are now "Forbidden".
