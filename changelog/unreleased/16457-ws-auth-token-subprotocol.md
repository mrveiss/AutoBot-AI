---
type: security
scope: backend
issue: 16457
pr: 0000
---
WebSocket auth (`auth_middleware.authenticate_websocket`, used by `/ws/live` and the session-presence socket) now prefers the token from the `Sec-WebSocket-Protocol` subprotocol (`['bearer', '<jwt>']`) over the `?token=` query string, so it no longer lands in server access logs or browser history. The query param remains a fallback for callers not yet migrated. Both `/ws/live` frontend clients (`GlobalWebSocketService` and `LiveEventService`) are migrated to the subprotocol form; every `accept()` in the affected endpoints now echoes the offered subprotocol per RFC 6455 4.2.2.

`useSessionCollaboration.ts` (`/ws/sessions/{id}/presence`) and `TerminalService.ts` (`/ws/{session_id}`) are migrated too -- both leaked a live token into the nginx access log's `$request` until now. `SSHTerminal.vue`'s connection went through the generic `useWebSocket()` composable, which had no way to carry a subprotocol at all; it now takes a `protocols` option. A repo-wide guard (`websocket-auth-transport-guard.test.ts`) fails any WebSocket-related file in either frontend that builds a URL with `buildAuthenticatedWsUrl()` or a literal `?token=`/`&token=` query string.
