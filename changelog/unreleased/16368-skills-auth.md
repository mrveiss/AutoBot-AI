---
type: security
scope: backend
issue: 16368
pr: 16370
---
The skills API now requires sign-in. Every route under `/api/skills` and `/api/skills/hub` used to accept anonymous requests, including enabling, configuring and executing a skill and installing from a catalog or the hub. Reading skill information now needs an authenticated user. Enabling, disabling, configuring or executing a skill, fetching or installing from a catalog, and installing or removing a hub skill need an administrator.
