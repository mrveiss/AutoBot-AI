---
type: security
scope: backend
issue: 15234
pr: 0000
---
`MultiModalProcessor._store_result` no longer swallows every exception into an identical warning. A tenancy rejection (an unscoped or malformed `user_id`) is now logged distinctly as a refusal rather than a generic warning, and every outcome — persisted, refused, or failed — is now visible to the caller via a boolean return value that `process()` stamps onto the result's metadata, instead of a caller receiving the same "success" object regardless of whether anything was actually stored.
