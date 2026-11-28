---
type: fix
scope: secrets
issue: 21039
pr: 21196
---
A secret delete now checks the caller's authority before it locks the secret row, waits at most
`AUTOBOT_SECRET_DELETE_LOCK_TIMEOUT_MS` (default 5000) for that lock and otherwise answers 503 with a
`Retry-After` header, and releases the lock before its `denied`/`failed` audit record is written.
The 409 that lists a secret's dependents now carries a `dependents_digest`; the confirmed retry sends it
as the `dependents_digest` query parameter (replacing the bare `confirm_dependents` flag) and is refused
again, with the new list, when a dependent was registered after the person saw the first one.
