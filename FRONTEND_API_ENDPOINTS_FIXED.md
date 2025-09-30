# Frontend API Endpoints Fixed - Resolved 405 Method Not Allowed Errors

## Problem Summary

The frontend was making API calls to non-existent backend endpoints, causing 405 Method Not Allowed errors. The frontend API calls did not match the actual backend endpoints.

## Backend Endpoints Available

Based on `/home/kali/Desktop/AutoBot/backend/api/chat.py`, the following endpoints exist:

### Chat Endpoints
- `GET /api/chats` - List chat sessions
- `POST /api/chat` - Send message (expects ChatMessage format)
- `POST /api/chat/stream` - Stream message response
- `GET /api/chat/sessions/{session_id}` - Get session messages
- `POST /api/chat/sessions` - Create new session
- `PUT /api/chat/sessions/{session_id}` - Update session (title/metadata)
- `DELETE /api/chat/sessions/{session_id}` - Delete session
- `GET /api/chat/sessions/{session_id}/export` - Export session
- `GET /api/chat/health` - Chat service health check
- `GET /api/chat/stats` - Chat service statistics

## Frontend Endpoint Issues Fixed

### 1. ApiClient.js - Fixed Multiple Issues

**BEFORE (Incorrect):**
```javascript
// Line 434: Wrong endpoint
const response = await this.post('/api/chat/message', {...});

// Line 472: Non-existent endpoint
const response = await this.post(`/api/chat/sessions/${chatId}`, { messages });

// Line 611: Non-existent endpoints
const response = await this.post('/api/chats/cleanup_messages');
const response = await this.post('/api/chats/cleanup_all');
```

**AFTER (Fixed):**
```javascript
// Correct endpoint for sending messages
const response = await this.post('/api/chat', {
  content: message,
  role: "user",
  session_id: options.chatId || options.session_id || null,
  message_type: options.message_type || "text",
  metadata: options.metadata || {}
});

// Deprecated saveChatMessages - now sends individual messages
// Removed non-existent cleanup methods
```

### 2. ApiClient.ts - Fixed TypeScript Version

**BEFORE (Incorrect):**
```typescript
// Line 287: Wrong endpoint
const response = await this.post('/api/chat/message', {...});

// Line 326: Non-existent endpoint
const response = await this.post(`/api/chat/sessions/${chatId}`, { messages });
```

**AFTER (Fixed):**
```typescript
// Correct endpoint for sending messages
const response = await this.post('/api/chat', {
  content: message,
  role: "user",
  session_id: options.chatId || options.session_id || null,
  message_type: options.message_type || "text",
  metadata: options.metadata || {}
});
```

### 3. BatchApiService.ts - Removed Non-existent Batch Endpoints

**BEFORE (Incorrect):**
```typescript
// Lines 81, 98: Non-existent batch endpoints
const response = await this.apiClient.post('/api/batch/chat-init');
const response = await this.apiClient.get(`/api/batch/chat-init/${sessionId}`);
```

**AFTER (Fixed):**
```typescript
// Replaced with individual API calls and proper fallback handling
async initializeChatInterface(): Promise<any> {
  console.warn('Batch chat initialization endpoint does not exist. Using fallback individual API calls.');
  return await this.fallbackChatInitialization();
}
```

### 4. useChatHistory.js - Fixed New Chat Creation

**BEFORE (Incorrect):**
```javascript
// Line 139: Wrong endpoint
const newChatData = await apiClient.post('/api/chat/chats/new');
```

**AFTER (Fixed):**
```javascript
// Use correct endpoint via helper method
const newChatData = await apiClient.createNewChat(); // Uses POST /api/chat/sessions
```

## Key Changes Made

### 1. Message Sending Fixed
- **OLD**: `POST /api/chat/message` ❌ (doesn't exist)
- **NEW**: `POST /api/chat` ✅ (correct endpoint)
- **Payload**: Now uses proper ChatMessage format with `content`, `role`, `session_id`, `message_type`, `metadata`

### 2. Session Creation Fixed
- **OLD**: `POST /api/chat/chats/new` ❌ (doesn't exist)
- **NEW**: `POST /api/chat/sessions` ✅ (correct endpoint)

### 3. Message Saving Deprecated
- **OLD**: `POST /api/chat/sessions/{id}` with bulk messages ❌ (doesn't exist)
- **NEW**: Individual message sending via `POST /api/chat` ✅
- Added deprecation warnings and fallback behavior

### 4. Batch Endpoints Removed
- **OLD**: `POST /api/batch/chat-init` ❌ (doesn't exist)
- **OLD**: `GET /api/batch/chat-init/{sessionId}` ❌ (doesn't exist)
- **NEW**: Individual parallel API calls with proper error handling

### 5. Cleanup Methods Removed
- **OLD**: `POST /api/chats/cleanup_messages` ❌ (doesn't exist)
- **OLD**: `POST /api/chats/cleanup_all` ❌ (doesn't exist)
- **NEW**: Use individual `DELETE /api/chat/sessions/{id}` calls

## Files Modified

1. `/home/kali/Desktop/AutoBot/autobot-vue/src/utils/ApiClient.js` - Complete rewrite with correct endpoints
2. `/home/kali/Desktop/AutoBot/autobot-vue/src/utils/ApiClient.ts` - TypeScript version fixed
3. `/home/kali/Desktop/AutoBot/autobot-vue/src/services/BatchApiService.ts` - Removed non-existent batch endpoints
4. `/home/kali/Desktop/AutoBot/autobot-vue/src/composables/useChatHistory.js` - Fixed chat creation endpoint

## Backward Compatibility

- All deprecated methods are maintained with warning logs
- LocalStorage fallbacks preserved for offline functionality
- Existing component interfaces remain unchanged

## Expected Results

After these fixes:
- ✅ No more 405 Method Not Allowed errors
- ✅ Chat messages send successfully via `POST /api/chat`
- ✅ Chat sessions create properly via `POST /api/chat/sessions`
- ✅ Chat lists load via `GET /api/chats`
- ✅ Session messages load via `GET /api/chat/sessions/{id}`
- ✅ Proper error handling and fallback mechanisms
- ✅ Console warnings for deprecated methods guide developers

## Testing Recommendations

1. Test chat message sending and receiving
2. Test chat session creation and loading
3. Test chat session deletion
4. Verify all API calls use correct endpoints
5. Check browser console for any remaining 405 errors
6. Verify error handling and fallback behavior

The frontend now correctly matches the backend API structure and should resolve all 405 Method Not Allowed errors.