---
type: fix
scope: backend
issue: 21992
pr: 0000
---
Viewing an agent's heartbeat settings no longer creates a record for it. An agent with no record now shows the heartbeat as off, and a record created by a later change starts with the heartbeat off until someone turns it on, so an agent nobody enabled is never scheduled.
