---
type: fix
scope: backend
issue: 20413
pr: 21015
---
STRICT chat routes (turn cancel, session trace, conversation-file owner routes) answer a foreign conversation exactly like an unknown one, so a caller cannot learn which ids exist.
