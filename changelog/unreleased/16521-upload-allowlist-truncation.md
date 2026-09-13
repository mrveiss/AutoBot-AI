---
type: fix
scope: backend
issue: 16521
pr: 0
---
Conversation uploads accept PDF and GIF again: the allowlist listed the truncated ".pd" and ".gi", which no real filename's suffix matches.
