---
type: security
scope: backend
issue: 16457
pr: 0000
---
WebSocket auth (`auth_middleware.authenticate_websocket`, used by `/ws/live` and the session-presence socket) now prefers the token from the `Sec-WebSocket-Protocol` subprotocol (`['bearer', '<jwt>']`) over the `?token=` query string, so it no longer lands in server access logs or browser history. The query param remains a fallback for callers not yet migrated. Both `/ws/live` frontend clients (`GlobalWebSocketService` and `LiveEventService`) are migrated to the subprotocol form; every `accept()` in the affected endpoints now echoes the offered subprotocol per RFC 6455 4.2.2.

The echo logic is now one shared helper, `autobot_shared.websocket_subprotocol` (`accept_websocket`/`negotiated_subprotocol`/`bearer_subprotocol_token`), used by every authenticating WebSocket endpoint in both `autobot-backend` and `autobot-slm-backend` — including `api/terminal.py`, `api/vnc_proxy.py` and `api/process_management.py`, which previously bare-accepted or echoed on a `startswith("bearer")` match instead of an exact one. A repo guard (`repo_tests/websocket_subprotocol_echo_guard_test.py`) fails any authenticating endpoint across either backend that accepts without going through the shared helper.
