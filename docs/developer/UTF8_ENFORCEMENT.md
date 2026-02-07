# UTF-8 Encoding Enforcement

**Status**: ⚠️ MANDATORY for all new code
**Last Updated**: 2025-10-31

## Overview

All AutoBot code MUST use UTF-8 encoding consistently across:
- Python source files
- File I/O operations
- HTTP responses
- Database connections
- Terminal output
- Frontend rendering

## Why UTF-8 Matters

### Current Issues Solved:
1. **ANSI escape codes bleeding** - Terminal control sequences display as garbage
2. **Box-drawing characters** - Terminal prompts (┌──, └─) corrupted
3. **Emoji support** - 🤖 and other emojis in UI
4. **International text** - Support for non-ASCII characters
5. **JSON serialization** - Proper handling of Unicode in API responses

## Python Backend Rules

### 1. File I/O - Always Specify UTF-8

```python
# ❌ WRONG - Uses system default
async with aiofiles.open(file_path, "r") as f:
    content = await f.read()

# ✅ CORRECT - Explicit UTF-8
async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
    content = await f.read()

# ❌ WRONG - Synchronous without encoding
with open(file_path, "w") as f:
    f.write(content)

# ✅ CORRECT - Explicit UTF-8
with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
```

### 2. FastAPI Responses - Set Content-Type

```python
from fastapi.responses import JSONResponse

# ✅ CORRECT - Explicit UTF-8 in headers
return JSONResponse(
    content={"message": "Hello 🤖"},
    media_type="application/json; charset=utf-8"
)

# ✅ CORRECT - Streaming with UTF-8
return StreamingResponse(
    generator(),
    media_type="text/event-stream; charset=utf-8"
)
```

### 3. JSON Serialization

```python
import json

# ✅ CORRECT - Ensure ASCII=False for Unicode
json.dumps(data, ensure_ascii=False, indent=2)

# ❌ WRONG - Escapes Unicode characters
json.dumps(data)  # Default ensure_ascii=True
```

### 4. Terminal Output

```python
import subprocess

# ✅ CORRECT - Decode subprocess output
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")

# ✅ CORRECT - Handle PTY output
pty_output.decode("utf-8", errors="replace")  # Replace invalid chars
```

## Frontend Rules

### 1. HTML Meta Tag (MANDATORY)

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />  <!-- ✅ REQUIRED -->
</head>
</html>
```

### 2. HTTP Response Headers

```typescript
// ✅ CORRECT - Fetch with UTF-8
fetch(url, {
  headers: {
    'Content-Type': 'application/json; charset=utf-8',
    'Accept': 'application/json; charset=utf-8'
  }
})
```

### 3. Text Processing

```typescript
// ✅ CORRECT - Use TextDecoder for binary data
const decoder = new TextDecoder('utf-8')
const text = decoder.decode(buffer)
```

## Database Rules

### SQLite Configuration

```python
import sqlite3

# ✅ CORRECT - UTF-8 connection
conn = sqlite3.connect('database.db')
conn.execute("PRAGMA encoding = 'UTF-8'")
```

### Redis Configuration

```python
import redis

# ✅ CORRECT - UTF-8 decode responses
redis_client = redis.Redis(
    host=host,
    port=port,
    decode_responses=True,  # Auto-decode bytes to str using UTF-8
    encoding='utf-8'
)
```

## Testing UTF-8 Support

### Test Characters to Use:

```python
test_strings = [
    "Hello World",                    # ASCII
    "Привет мир",                     # Cyrillic
    "你好世界",                        # Chinese
    "مرحبا بالعالم",                  # Arabic
    "🤖 💻 🚀 ✨",                      # Emoji
    "┌──(venv)──[~/code]",           # Box drawing
    "\x1b[31mRed\x1b[0m",            # ANSI codes (should be stripped)
]

for test in test_strings:
    # Verify round-trip encoding
    encoded = test.encode('utf-8')
    decoded = encoded.decode('utf-8')
    assert decoded == test
```

## Common Pitfalls

### ❌ Pitfall 1: Assuming Default Encoding
```python
# System default might NOT be UTF-8 on Windows
with open('file.txt', 'w') as f:  # Could use cp1252 on Windows!
    f.write('Hello')
```

### ❌ Pitfall 2: Not Handling Decode Errors
```python
# Raises UnicodeDecodeError if file has invalid UTF-8
data = subprocess.check_output(cmd).decode('utf-8')
```

### ✅ Solution: Always Handle Errors
```python
data = subprocess.check_output(cmd).decode('utf-8', errors='replace')
# Or: errors='ignore', errors='backslashreplace'
```

### ❌ Pitfall 3: Mixing Bytes and Strings
```python
# Can cause encoding issues
content = b'some bytes' + 'some string'  # TypeError!
```

### ✅ Solution: Explicit Conversion
```python
content = b'some bytes'.decode('utf-8') + 'some string'
# Or: content = b'some bytes' + 'some string'.encode('utf-8')
```

## Migration Plan

### Phase 1: Audit (COMPLETED)
- ✅ Identified all `open()` calls without encoding
- ✅ Found FastAPI responses without explicit charset
- ✅ Located terminal output handling

### Phase 2: Fix Critical Paths (IN PROGRESS)
- 🔄 Add UTF-8 to all aiofiles operations in chat_history_manager.py
- 🔄 Add charset to FastAPI JSONResponse
- 🔄 Add UTF-8 to subprocess/PTY operations

### Phase 3: Pre-commit Enforcement (PLANNED)
- ⏳ Add pre-commit hook to check for `open()` without encoding
- ⏳ Lint for missing charset in HTTP responses
- ⏳ Verify all JSON uses ensure_ascii=False

### Phase 4: Testing (PLANNED)
- ⏳ Add UTF-8 test suite with international characters
- ⏳ Test emoji handling end-to-end
- ⏳ Verify ANSI code stripping

## Files to Fix

### High Priority (User-Facing)
- [ ] `src/chat_history_manager.py` - 10+ aiofiles.open() calls
- [ ] `autobot-user-backend/api/chat.py` - JSONResponse media_type
- [ ] `backend/services/agent_terminal_service.py` - PTY output
- [ ] `autobot-user-frontend/src/components/chat/ChatMessages.vue` - Text rendering

### Medium Priority (Internal)
- [ ] All backend API endpoints - Explicit charset
- [ ] All file I/O utilities - UTF-8 encoding
- [ ] Database connection modules - UTF-8 config

### Low Priority (Already Working)
- ✅ Frontend HTML - Has UTF-8 meta tag
- ✅ Vue components - Render UTF-8 correctly
- ✅ Some file operations - Already have encoding specified

## Enforcement

### Pre-commit Hook Rule
```bash
# Detect open() without encoding in Python files
if git diff --cached --name-only | grep '\.py$'; then
  if git diff --cached | grep -E 'open\([^)]*\)' | grep -v 'encoding='; then
    echo "ERROR: Found open() without encoding parameter"
    echo "Always use: open(file, mode, encoding='utf-8')"
    exit 1
  fi
fi
```

### Code Review Checklist
- [ ] All `open()` calls have `encoding='utf-8'`
- [ ] All `aiofiles.open()` calls have `encoding='utf-8'`
- [ ] FastAPI responses have `media_type="...; charset=utf-8"`
- [ ] JSON dumps use `ensure_ascii=False`
- [ ] Subprocess output decoded with UTF-8
- [ ] Test with non-ASCII characters

## References

- [PEP 597 - Default Encoding](https://peps.python.org/pep-0597/)
- [FastAPI Unicode](https://fastapi.tiangolo.com/advanced/custom-response/#jsonresponse)
- [aiofiles Documentation](https://github.com/Tinche/aiofiles)

---

**REMEMBER**: When in doubt, **ALWAYS specify UTF-8 explicitly**. Better safe than mojibake! 🤖
