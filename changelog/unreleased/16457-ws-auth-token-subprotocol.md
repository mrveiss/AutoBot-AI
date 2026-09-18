---
type: security
scope: backend
issue: 16457
pr: 0000
---
WebSocket auth (`auth_middleware.authenticate_websocket`, used by `/ws/live` and the session-presence socket) now prefers the token from the `Sec-WebSocket-Protocol` subprotocol (`['bearer', '<jwt>']`) over the `?token=` query string, so it no longer lands in server access logs or browser history. The query param remains a fallback for callers not yet migrated. Both `/ws/live` frontend clients (`GlobalWebSocketService` and `LiveEventService`) are migrated to the subprotocol form; every `accept()` in the affected endpoints now echoes the offered subprotocol per RFC 6455 4.2.2.

The echo logic is now one shared helper, `autobot_shared.websocket_subprotocol` (`accept_websocket`/`negotiated_subprotocol`/`bearer_subprotocol_token`), used by every authenticating WebSocket endpoint in both `autobot-backend` and `autobot-slm-backend` — including `api/terminal.py`, `api/vnc_proxy.py` and `api/process_management.py`, which previously bare-accepted or echoed on a `startswith("bearer")` match instead of an exact one. A repo guard (`repo_tests/websocket_subprotocol_echo_guard_test.py`) fails any authenticating endpoint across either backend that accepts without going through the shared helper.

`useSessionCollaboration.ts` (`/ws/sessions/{id}/presence`) and `TerminalService.ts` (`/ws/{session_id}`) are migrated too -- both leaked a live token into the nginx access log's `$request` until now. `SSHTerminal.vue`'s connection went through the generic `useWebSocket()` composable, which had no way to carry a subprotocol at all; it now takes a `protocols` option. A repo-wide guard (`websocket-auth-transport-guard.test.ts`) fails any WebSocket-related file in either frontend that builds a URL with `buildAuthenticatedWsUrl()` or a literal `?token=`/`&token=` query string.

Two logging gaps closed on the read side. `autobot-slm-backend`'s reject-path logger used to record the raw `Sec-WebSocket-Protocol` header verbatim (`bearer, <jwt>` for a bearer offer) on every rejected handshake; it now logs only whether `bearer` was offered. And the `?token=` query-param fallback -- kept on purpose during migration -- was invisible in use; both backends now log one warning, naming the route only, whenever a handshake actually authenticates through it rather than the subprotocol. Both live in the shared `autobot_shared.websocket_subprotocol.resolve_ws_token`, used by both backends' token resolution.
