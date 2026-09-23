---
type: fix
scope: database
issue: 16464
pr: 0
---
Fixed a class of bug where several database tables (multi-user session collaboration, and activity/audit logging) were declared in code but never actually created on a real deployment. This was silently breaking the collaboration feature and, in some cases, causing hard-deleting a user or organization to fail outright.
