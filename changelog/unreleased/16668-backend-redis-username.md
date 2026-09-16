---
type: security
scope: redis
issue: 16668
pr: 0
---
The backend's rendered environment now always sends a Redis username with a Redis password, `default` unless one is configured. Before this, a password set without a username rendered a password-only connection URL. A Redis server whose default user needs no password refuses that URL, so the backend's URL-based clients (Celery) would have been locked out.
