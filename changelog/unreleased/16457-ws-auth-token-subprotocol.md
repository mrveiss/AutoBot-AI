---
type: security
scope: backend
issue: 16457
pr: 0000
---
WebSocket auth (`auth_middleware.authenticate_websocket`, used by `/ws/live` and the session-presence socket) now prefers the token from the `Sec-WebSocket-Protocol` subprotocol (`['bearer', '<jwt>']`) over the `?token=` query string, so it no longer lands in server access logs or browser history. The query param remains a fallback for callers not yet migrated. `GlobalWebSocketService`'s `/ws/live` client is migrated to the subprotocol form; every `accept()` in the affected endpoints now echoes the offered subprotocol per RFC 6455 4.2.2.
