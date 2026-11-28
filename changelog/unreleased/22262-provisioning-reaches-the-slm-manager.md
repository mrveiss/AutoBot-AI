---
type: fix
scope: backend
issue: 22262
pr: 22367
---
Role provisioning (manual and the fleet update's pending-role step) no longer aborts with the SLM manager UNREACHABLE: its inventory now carries the manager host exactly as the fleet update inventory does, so tasks delegated to the SLM run and the vnc role creates its account.
