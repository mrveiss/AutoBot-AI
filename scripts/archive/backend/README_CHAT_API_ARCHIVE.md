# Backend Archive - Chat API

## Archived Files

### `chat_api.py` - Legacy Chat Management API
**Archived Date:** 2025-09-28
**Original Location:** `backend/chat_api.py`
**Archive Reason:** Orphaned legacy file, superseded by consolidated chat APIs

#### Why Archived:
1. **Not actively used** - No imports or references found in codebase
2. **Not registered** - Not included in app_factory.py router registration
3. **Superseded functionality** - All features implemented better in:
   - `backend/api/chat_consolidated.py` (main chat API)
   - `backend/api/chat_knowledge.py` (knowledge management)

#### Unique Features (Historical Reference):
- File-based chat persistence using JSON files in `data/chats/`
- Message cleanup utilities for old file structure:
  - `_cleanup_chat_message_files()` - Session directory cleanup
  - `cleanup_all_message_files()` - Bulk message cleanup
  - `cleanup_all_chat_data()` - Comprehensive cleanup
- Simple CRUD operations with basic validation

#### Modern Replacement:
Current chat system uses:
- Redis-based persistence via `ChatHistoryManager`
- Advanced dependency injection and error handling
- Session management with proper UUIDs
- Streaming responses and knowledge base integration
- Export functionality and health monitoring

This file is preserved for historical reference but should not be restored to active use.