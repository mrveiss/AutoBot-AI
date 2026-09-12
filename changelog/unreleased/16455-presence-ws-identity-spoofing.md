---
type: security
scope: collaboration
issue: 16455
pr: 0
---
The session-presence WebSocket (`/ws/sessions/{id}/presence`) previously trusted a client-supplied `user_id` with no verification, letting any caller join any session's presence channel as any user and broadcast under a spoofed identity. It now requires a verified session token and confirms the caller is an actual participant (owner, editor, or viewer) of that session before connecting.
