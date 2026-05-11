# Chat State — Single Source of Truth

**Issue:** #6746  
**Status:** Phase 1 complete — design doc  
**Author:** mrveiss

---

## Problem

Three concurrently-filed bugs (#6743 Redis TTL, #6744 add_message signature, #6745 session_id churn) share one root cause: chat state is stored in **five independent stores** with **six sync/race paths** between them.

### Current stores

| Store | Key/Path | TTL | Authority |
|-------|----------|-----|-----------|
| Frontend localStorage | `autobot-chat-store` | Browser-permanent | Pinia persist snapshot |
| Frontend Pinia (`useChatStore`) | In-memory | Tab lifetime | Mutable by every component |
| Backend Redis session cache | `chat:session:{id}` | 24 h (AUTOBOT_CHAT_SESSION_CACHE_TTL) | Hot cache |
| Backend Redis recent-list | `chat:recent` (sorted set) | **None** (grows unbounded) | Listing index |
| Backend disk | `data/chats/{id}_chat.json` | Permanent | Intended canonical store |

### Race paths

1. `ChatController.enableAutoSave()` — fires every 30 s; calls `POST /api/chat/save` which runs `merge_messages()` then overwrites disk+Redis. Race with concurrent tab.
2. `useChatStore.syncSessionsWithBackend()` — overwrites entire Pinia sessions array from backend list on mount. Defensive guard (skip on 0-session response) is incomplete.
3. `process_chat_message()` + `process_enhanced_chat_message()` — mint a new session ID when `message.session_id` is absent (`session_id = message.session_id or generate_chat_session_id()`). Frontend session ≠ backend session.
4. `ChatController.sendMessage()` + `createNewSession()` — two-phase: local session created immediately, server create races with first message send.
5. `addMessage()` side-effect (pre-fix) — created a new session when `currentSession` was null. Fixed by #6744/#6745; `addMessage()` now fails if no current session.
6. WebSocket push vs HTTP response ordering — no sequence number; concurrent delivery creates ambiguous state.

### What is already fixed

| Issue | Fix | Status |
|-------|-----|--------|
| #6743 | `AUTOBOT_CHAT_SESSION_CACHE_TTL` env override; default raised 1 h → 24 h | ✅ merged |
| #6744 | `add_message(session_id, dict)` wrong-signature silent no-op → `add_messages_batch()` | ✅ merged |
| #6745 | Backend `create_session` accepts client-supplied `session_id` when well-formed | ✅ merged |
| #6781 | `useAppStore.sessions` deleted; `useChatStore` is now the sole frontend session store | ✅ merged |

---

## Decision

### Canonical store: disk

`data/chats/{session_id}_chat.json` is the **only** persistent store. Rationale:

- Already atomic-written with `fcntl` lock in `ChatHistoryManager.save_session()`.
- Survives Redis restart; Redis is already treated as a warm cache in `load_session()`.
- Simple to back up and inspect; no TTL expiry risk.

### Redis role: read-through cache only

`chat:session:{id}` stays as a 24 h warm cache. Rule: **write to disk first, then update Redis**. No caller writes to Redis without writing to disk. Cache misses always fall back to disk; never a data loss event.

`chat:recent` sorted set must get a TTL equal to the session cache TTL to prevent unbounded growth (discovery: #NNNN filed separately).

### Frontend role: render-only mirror

Pinia `useChatStore` holds the last-fetched snapshot from the backend. It is a **display buffer**, not a source of truth. Rules:

- localStorage persists sidebar state (session titles + IDs) only — not message bodies.
- Message bodies are always fetched fresh on session-click via `GET /api/chat/sessions/{id}`.
- No autosave poller; all writes go through backend API calls triggered by user actions.
- No message poller; WebSocket push (`/api/ws/live`) is the notification mechanism.

### Session ID ownership: client-mints, server-validates

1. Frontend generates a UUID4 via `crypto.randomUUID()` before the first API call.
2. `POST /api/chat/sessions` accepts that ID via `validate_chat_session_id()`.
3. Server echoes the accepted ID in the response; frontend uses it as-is.
4. `process_chat_message` and `process_enhanced_chat_message` **reject** requests without a `session_id` (HTTP 422 — no silent minting).

---

## Target architecture

```
Frontend                              Backend
────────                              ───────

useChatStore (display buffer)         disk: data/chats/{id}_chat.json  ← canonical
  sessions: [{id, title}]  ←─────────     ↑ write-first (fcntl atomic)
  currentSessionId                         │
  messages (current session)          Redis: chat:session:{id}  ← warm cache (24 h TTL)
                                           ↑ updated after disk write
ChatController
  sendMessage()                       FastAPI routes
    → crypto.randomUUID() if !id        POST /api/chat/sessions    → create_session()
    → POST /api/chat/sessions           POST /api/chat/send        → process_chat_message()
    → POST /api/chat/send               REJECT if session_id absent (HTTP 422)
    → updateMessage() on response

GlobalWebSocketService                Redis Pub/Sub
  receives chat_message events   ←── backend publishes after save_session()
  → chatStore.addOrUpdateMessage()
```

---

## Implementation phases

### Phase 2 — Backend persistence consolidation (sub-issue #NNNN)

1. **`process_chat_message` and `process_enhanced_chat_message`**: remove `or generate_chat_session_id()` fallback; return HTTP 422 when `session_id` is absent.
2. **`chat:recent` TTL**: set `EXPIRE chat:recent {session_count * cache_ttl}` after each `zadd`, or switch to per-key sorted-set entries with TTL. File discovery issue for unbounded growth.
3. **`add_messages_batch` audit**: verify no other call sites use the old positional signature.
4. **`save_session()` write ordering**: confirm disk write always precedes Redis update (already true in `session.py`; add assertion/test).
5. **Tests**: one pytest per rule — reject missing session_id, cache-miss-loads-from-disk, disk-write-before-cache.

### Phase 3 — Frontend store consolidation (sub-issue #NNNN)

1. **Remove autosave poller**: delete `enableAutoSave()` / `disableAutoSave()` from `ChatController`. Remove `autoSave` from `useChatStore.settings`. Update all callers.
2. **Remove message poller** (if any): replace with WebSocket event listener.
3. **`syncSessionsWithBackend()` → lightweight**: fetch only `[{id, title, updatedAt}]` — never overwrite message bodies. Guard strengthened: only overwrite when `intentionalEmpty=true` (explicit logout).
4. **localStorage persist scope**: narrow `pick` to `['currentSessionId', 'sidebarCollapsed', 'sessionTitles']` — drop `sessions` (message bodies).
5. **`createNewSession()`**: use `crypto.randomUUID()` for client-side ID; call `POST /api/chat/sessions` immediately (no local-first create).
6. **Tests**: Vitest unit tests for store actions; Playwright E2E for send-message → exact-one-session-id invariant.

### Phase 4 — Observability & rollout (sub-issue #NNNN)

1. **Telemetry**: log `session_id` at message-send entry and at AI response store. Assert same ID appears twice (count distinct session_ids per send-event = 1).
2. **`chat:recent` cardinality alert**: Grafana/Prometheus alert when sorted set `ZCARD chat:recent` exceeds expected session count by 2×.
3. **Monitor disk file count**: `ls data/chats/ | wc -l` sampled nightly; alert on unexpected spike.
4. **Rollout gate**: run Phase 2+3 behind `AUTOBOT_CHAT_SSOT_STRICT=true` feature flag for one week; default-on after no incidents.

---

## Acceptance criteria

- [ ] Phase 2 merged: `process_chat_message` returns 422 on missing `session_id`; `chat:recent` gets TTL; tests pass.
- [ ] Phase 3 merged: autosave poller deleted; localStorage does not persist message bodies; `createNewSession` is server-round-trip-first.
- [ ] Phase 4 merged: telemetry shows `distinct_session_ids_per_send = 1.0` (P99) in staging.
- [ ] `sending a message produces exactly one session_id in backend logs end-to-end`.
- [ ] GitHub issue #6746 closed with proof comment linking all merged PRs.

---

## Discovery issues filed

| # | Title |
|---|-------|
| TBD | discovery(chat): `chat:recent` sorted set has no TTL — grows unbounded |
| TBD | arch(chat): Phase 2 — backend persistence consolidation (#6746) |
| TBD | arch(chat): Phase 3 — frontend store consolidation (#6746) |
| TBD | arch(chat): Phase 4 — observability and rollout gate (#6746) |

*(Numbers filled in after filing.)*
