---
type: fix
scope: backend
issue: 21559
pr: 21732
---
Secret routes now answer a refusal or a bad request with one shared fixed text and never echo an id, a vault reference or an exception message. Client-visible wording changed, statuses did not: "Secret not found" is now "Not found", and "Not permitted to create this secret", "Not permitted to access this secret" and "You can only share secrets you own" are now "Forbidden".
