# API Endpoint Cleanup Plan

## Current Issues Identified

### 1. Duplicate Message Sending Endpoints
- `POST /chat` (legacy)
- `POST /chat/conversation` (enhanced)
- `POST /chat/direct` (direct)
- `POST /chats/{chat_id}/message` (specific chat)

**Problem**: Multiple ways to send messages causing confusion

### 2. Duplicate Save Operations
- `POST /chats/{chat_id}` (save messages)
- `POST /chats/{chat_id}/save` (save chat data)

**Problem**: Two similar save endpoints with unclear differences

### 3. Inconsistent Naming
- `/chat` vs `/chats` patterns
- Some endpoints use singular, some plural

## Recommended Cleanup

### Phase 1: Consolidate Message Endpoints
**Keep**: `POST /chats/{chat_id}/message` (most specific)
**Deprecate**:
- `POST /chat` (legacy)
- `POST /chat/conversation`
- `POST /chat/direct`

### Phase 2: Merge Save Endpoints
**Keep**: `POST /chats/{chat_id}/save` (more descriptive)
**Deprecate**: `POST /chats/{chat_id}` (ambiguous POST to chat ID)

### Phase 3: Standardize Naming
**Recommended Pattern**: `/chats/` for all chat operations
- `GET /chats` (list)
- `POST /chats` (create new)
- `GET /chats/{id}` (get specific)
- `POST /chats/{id}/message` (send message)
- `POST /chats/{id}/save` (save data)
- `DELETE /chats/{id}` (delete)

### Phase 4: Add Deprecation Headers
For legacy endpoints, add HTTP headers:
```
Deprecated: true
Sunset: 2024-12-31
Link: </api/v2/chats>; rel="successor-version"
```

## Implementation Strategy

1. **Immediate**: Document current endpoint purposes
2. **Short-term**: Add deprecation warnings to legacy endpoints
3. **Medium-term**: Update frontend to use standardized endpoints
4. **Long-term**: Remove deprecated endpoints after 6-month grace period

## Benefits

- **Reduced confusion** for developers
- **Cleaner API surface**
- **Better maintenance** with fewer duplicate code paths
- **Improved documentation** clarity
- **Frontend simplification**
