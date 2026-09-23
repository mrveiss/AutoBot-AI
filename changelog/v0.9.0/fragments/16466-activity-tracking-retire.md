---
type: fix
scope: backend
issue: 16466
pr: 0
---
Removed the terminal/file/browser activity-tracking hooks and their schema definitions — they had zero callers anywhere in the backend and their intended integration points were never built, unlike the desktop-tracking path which remains live and unchanged.
