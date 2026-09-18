---
type: fix
scope: security
issue: 17009
pr: 0000
---
Nine WebSocket endpoints accepted connections without authentication, and the long-running operations API had no authentication at all. The research, overseer, workflow automation, analytics, code-quality, log tail, operation progress and monitoring sockets now require a signed-in user before they accept. The log tail, code-quality, operation progress and every `/api/long-running` route require an administrator. The overseer socket, which runs commands in a session's terminal, accepts only the owner of that chat session. The workflow socket keeps each session to the user who opened it, and lets only an administrator (or, once recorded, a workflow's owner) pause, approve or cancel workflow steps.
