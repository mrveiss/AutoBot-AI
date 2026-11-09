---
type: fix
scope: backend
issue: 21154
pr: 21207
---
A deactivation or password change pushed from the main app to the SLM now revokes the person's SLM sessions that were already issued.
