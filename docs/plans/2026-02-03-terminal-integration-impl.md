# Terminal Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add professional terminal features: bash-like tab completion, persistent command history, and polished UX.

**Architecture:** Backend services (completion + history) communicate via WebSocket with XTerm.js frontend. Redis stores history and settings persistently.

**Tech Stack:** Python/FastAPI backend, Vue 3/TypeScript frontend, XTerm.js, Redis, bash compgen

---

## Task 1: Terminal Completion Service

**Files:**
- Create: `src/services/terminal_completion_service.py`
- Test: `tests/unit/test_terminal_completion_service.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_terminal_completion_service.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for terminal completion service."""

import pytest
from unittest.mock import AsyncMock, patch

from src.services.terminal_completion_service import (
    TerminalCompletionService,
    CompletionResult
)


class TestTerminalCompletionService:
    """Tests for TerminalCompletionService."""

    @pytest.fixture
    def service(self):
        """Create completion service instance."""
        return TerminalCompletionService()

    def test_extract_current_word_simple(self, service):
        """Extract word at cursor position."""
        result = service._extract_current_word("cd /home/user/Doc", 17)
        assert result == "Doc"

    def test_extract_current_word_empty(self, service):
        """Empty word at start."""
        result = service._extract_current_word("", 0)
        assert result == ""

    def test_is_first_word_true(self, service):
        """First word detection - command position."""
        assert service._is_first_word("ls", 2) is True
        assert service._is_first_word("git", 3) is True

    def test_is_first_word_false(self, service):
        """First word detection - argument position."""
        assert service._is_first_word("cd /home", 8) is False
        assert service._is_first_word("ls -la", 5) is False

    def test_find_common_prefix_single(self, service):
        """Common prefix with single completion."""
        result = service._find_common_prefix(["Desktop"])
        assert result == "Desktop"

    def test_find_common_prefix_multiple(self, service):
        """Common prefix with multiple completions."""
        result = service._find_common_prefix(["Desktop", "Documents", "Downloads"])
        assert result == "D"

    def test_find_common_prefix_empty(self, service):
        """Common prefix with no completions."""
        result = service._find_common_prefix([])
        assert result == ""

    @pytest.mark.asyncio
    async def test_complete_paths_mock(self, service):
        """Test path completion with mocked compgen."""
        with patch.object(service, '_run_compgen', new_callable=AsyncMock) as mock:
            mock.return_value = ["Desktop", "Documents"]
            with patch('os.path.isdir', return_value=True):
                result = await service._complete_paths("D", "/home/user")
                assert "Desktop/" in result
                assert "Documents/" in result
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/AutoBot/.worktrees/terminal-749 && pytest tests/unit/test_terminal_completion_service.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.services.terminal_completion_service'"

**Step 3: Write minimal implementation**

```python
# src/services/terminal_completion_service.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal completion service using bash compgen for authentic completion.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CompletionResult:
    """Result of a completion request."""

    completions: List[str]
    prefix: str
    common_prefix: str


class TerminalCompletionService:
    """Bash-like tab completion using compgen subprocess."""

    async def get_completions(
        self,
        text: str,
        cursor_pos: int,
        cwd: str,
        env: Optional[dict] = None
    ) -> CompletionResult:
        """
        Get completions based on context.

        Args:
            text: Full command line text
            cursor_pos: Cursor position in text
            cwd: Current working directory
            env: Environment variables

        Returns:
            CompletionResult with matching completions
        """
        word = self._extract_current_word(text, cursor_pos)
        env = env or os.environ.copy()

        if self._is_first_word(text, cursor_pos):
            completions = await self._complete_commands(word, env)
        elif word.startswith('$'):
            completions = await self._complete_env_vars(word[1:], env)
        else:
            completions = await self._complete_paths(word, cwd)

        return CompletionResult(
            completions=completions,
            prefix=word,
            common_prefix=self._find_common_prefix(completions)
        )

    def _extract_current_word(self, text: str, cursor_pos: int) -> str:
        """Extract the word being completed at cursor position."""
        text_before_cursor = text[:cursor_pos]
        last_space = text_before_cursor.rfind(' ')
        return text_before_cursor[last_space + 1:]

    def _is_first_word(self, text: str, cursor_pos: int) -> bool:
        """Check if cursor is in the first word (command position)."""
        text_before_cursor = text[:cursor_pos]
        return ' ' not in text_before_cursor.strip()

    async def _complete_commands(self, prefix: str, env: dict) -> List[str]:
        """Complete commands using compgen."""
        cmd = f'compgen -A alias -A builtin -A command -- "{prefix}" 2>/dev/null'
        return await self._run_compgen(cmd, env)

    async def _complete_env_vars(self, prefix: str, env: dict) -> List[str]:
        """Complete environment variable names."""
        cmd = f'compgen -v -- "{prefix}" 2>/dev/null'
        completions = await self._run_compgen(cmd, env)
        return ['$' + c for c in completions]

    async def _complete_paths(self, prefix: str, cwd: str) -> List[str]:
        """Complete file and directory paths."""
        expanded_prefix = os.path.expanduser(prefix)
        cmd = f'compgen -f -- "{expanded_prefix}" 2>/dev/null'
        completions = await self._run_compgen(
            cmd,
            {'HOME': os.environ.get('HOME', '')},
            cwd
        )

        result = []
        for c in completions:
            full_path = os.path.join(cwd, c) if not os.path.isabs(c) else c
            if os.path.isdir(full_path):
                result.append(c + '/')
            else:
                result.append(c)
        return result

    async def _run_compgen(
        self,
        cmd: str,
        env: dict,
        cwd: Optional[str] = None
    ) -> List[str]:
        """Run compgen command and return results."""
        try:
            proc = await asyncio.create_subprocess_shell(
                f'bash -c \'{cmd}\'',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
            lines = stdout.decode().strip().split('\n')
            return [line for line in lines if line]
        except asyncio.TimeoutError:
            logger.warning("Completion command timed out")
            return []
        except Exception as e:
            logger.error("Completion error: %s", e)
            return []

    def _find_common_prefix(self, completions: List[str]) -> str:
        """Find longest common prefix among completions."""
        if not completions:
            return ''
        if len(completions) == 1:
            return completions[0]

        prefix = completions[0]
        for completion in completions[1:]:
            while not completion.startswith(prefix):
                prefix = prefix[:-1]
                if not prefix:
                    return ''
        return prefix
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/AutoBot/.worktrees/terminal-749 && pytest tests/unit/test_terminal_completion_service.py -v`
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
cd /home/kali/Desktop/AutoBot/.worktrees/terminal-749
git add src/services/terminal_completion_service.py tests/unit/test_terminal_completion_service.py
git commit -m "feat(#749): add terminal completion service with compgen"
```

---

## Task 2: Terminal History Service

**Files:**
- Create: `src/services/terminal_history_service.py`
- Test: `tests/unit/test_terminal_history_service.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_terminal_history_service.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for terminal history service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestTerminalHistoryService:
    """Tests for TerminalHistoryService."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        mock = MagicMock()
        mock.zadd = AsyncMock()
        mock.zcard = AsyncMock(return_value=5)
        mock.zrevrange = AsyncMock(return_value=["ls -la", "cd ..", "git status"])
        mock.zremrangebyrank = AsyncMock()
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def service(self, mock_redis):
        """Create history service with mocked Redis."""
        with patch('src.services.terminal_history_service.get_redis_client', return_value=mock_redis):
            from src.services.terminal_history_service import TerminalHistoryService
            svc = TerminalHistoryService()
            svc.redis = mock_redis
            return svc

    @pytest.mark.asyncio
    async def test_add_command(self, service, mock_redis):
        """Add command to history."""
        await service.add_command("user1", "ls -la")
        mock_redis.zadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_command_empty_ignored(self, service, mock_redis):
        """Empty commands should be ignored."""
        await service.add_command("user1", "   ")
        mock_redis.zadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_history(self, service, mock_redis):
        """Get recent history."""
        result = await service.get_history("user1", limit=10)
        assert result == ["ls -la", "cd ..", "git status"]
        mock_redis.zrevrange.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_history(self, service, mock_redis):
        """Search history by query."""
        mock_redis.zrevrange.return_value = ["git status", "git commit", "ls -la"]
        result = await service.search_history("user1", "git")
        assert "git status" in result
        assert "git commit" in result
        assert "ls -la" not in result

    @pytest.mark.asyncio
    async def test_clear_history(self, service, mock_redis):
        """Clear all history."""
        await service.clear_history("user1")
        mock_redis.delete.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/AutoBot/.worktrees/terminal-749 && pytest tests/unit/test_terminal_history_service.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/services/terminal_history_service.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal history service for persistent command history in Redis.
"""

import logging
import time
from typing import List

from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class TerminalHistoryService:
    """Manages persistent command history in Redis."""

    def __init__(self, max_entries: int = 10000):
        """Initialize history service.

        Args:
            max_entries: Maximum commands to store per user
        """
        self.redis = get_redis_client(database="main", async_client=True)
        self.max_entries = max_entries

    async def add_command(self, user_id: str, command: str) -> None:
        """Add command to history with current timestamp.

        Args:
            user_id: User identifier
            command: Command string to store
        """
        if not command.strip():
            return

        key = f"terminal:history:{user_id}"
        timestamp = time.time()

        await self.redis.zadd(key, {command: timestamp})

        count = await self.redis.zcard(key)
        if count > self.max_entries:
            await self.redis.zremrangebyrank(key, 0, count - self.max_entries - 1)

    async def get_history(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[str]:
        """Get recent commands (most recent first).

        Args:
            user_id: User identifier
            limit: Maximum commands to return
            offset: Number of commands to skip

        Returns:
            List of command strings
        """
        key = f"terminal:history:{user_id}"
        return await self.redis.zrevrange(key, offset, offset + limit - 1)

    async def search_history(
        self,
        user_id: str,
        query: str,
        limit: int = 50
    ) -> List[str]:
        """Search history for commands containing query.

        Args:
            user_id: User identifier
            query: Search string
            limit: Maximum results

        Returns:
            Matching commands
        """
        all_commands = await self.get_history(user_id, limit=self.max_entries)
        matches = [cmd for cmd in all_commands if query in cmd]
        return matches[:limit]

    async def clear_history(self, user_id: str) -> None:
        """Clear all history for user.

        Args:
            user_id: User identifier
        """
        key = f"terminal:history:{user_id}"
        await self.redis.delete(key)
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/AutoBot/.worktrees/terminal-749 && pytest tests/unit/test_terminal_history_service.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
cd /home/kali/Desktop/AutoBot/.worktrees/terminal-749
git add src/services/terminal_history_service.py tests/unit/test_terminal_history_service.py
git commit -m "feat(#749): add terminal history service with Redis storage"
```

---

## Task 3: WebSocket Handler Updates

**Files:**
- Modify: `src/websocket/terminal_handler.py` (or equivalent handler)
- Reference: `backend/api/base_terminal.py`

**Step 1: Locate the WebSocket handler**

Run: `grep -r "tab_completion\|terminal.*websocket" src/ backend/ --include="*.py" -l`

**Step 2: Add completion message handling**

Add to the WebSocket message handler:

```python
# Add imports at top of file
from src.services.terminal_completion_service import TerminalCompletionService
from src.services.terminal_history_service import TerminalHistoryService

# Initialize services (in class __init__ or module level)
completion_service = TerminalCompletionService()
history_service = TerminalHistoryService()

# Add to message handler switch/if-else:
elif message_type == "tab_completion":
    text = data.get("text", "")
    cursor = data.get("cursor", len(text))
    cwd = data.get("cwd", os.getcwd())

    result = await completion_service.get_completions(text, cursor, cwd)

    await websocket.send_json({
        "type": "tab_completion",
        "completions": result.completions,
        "prefix": result.prefix,
        "common_prefix": result.common_prefix
    })

elif message_type == "history_get":
    limit = data.get("limit", 100)
    user_id = session.get("user_id", "default")

    commands = await history_service.get_history(user_id, limit)

    await websocket.send_json({
        "type": "history",
        "commands": commands
    })

elif message_type == "history_search":
    query = data.get("query", "")
    user_id = session.get("user_id", "default")

    matches = await history_service.search_history(user_id, query)

    await websocket.send_json({
        "type": "history_search",
        "matches": matches
    })

# Add command history recording when processing commands:
# After executing a command successfully:
await history_service.add_command(user_id, command)
```

**Step 3: Test manually**

Test via WebSocket client or frontend.

**Step 4: Commit**

```bash
cd /home/kali/Desktop/AutoBot/.worktrees/terminal-749
git add src/websocket/ backend/api/
git commit -m "feat(#749): add WebSocket handlers for tab completion and history"
```

---

## Task 4: Frontend - Tab Completion Integration

**Files:**
- Modify: `autobot-vue/src/components/terminal/BaseXTerminal.vue`
- Modify: `autobot-vue/src/services/TerminalService.js`

**Step 1: Add completion message handling to TerminalService.js**

Add to handleMessage switch:

```javascript
case 'tab_completion':
  this.triggerCallback(sessionId, 'onTabCompletion', {
    completions: message.completions,
    prefix: message.prefix,
    common_prefix: message.common_prefix
  });
  break;
```

**Step 2: Add sendTabCompletion method**

```javascript
sendTabCompletion(sessionId, text, cursor, cwd) {
  const connection = this.connections.get(sessionId);
  if (!connection || connection.readyState !== WebSocket.OPEN) {
    return false;
  }

  try {
    connection.send(JSON.stringify({
      type: 'tab_completion',
      text: text,
      cursor: cursor,
      cwd: cwd
    }));
    return true;
  } catch (error) {
    logger.error('Failed to send tab completion:', error);
    return false;
  }
}
```

**Step 3: Handle Tab key in BaseXTerminal.vue**

Add to script section:

```typescript
// State for current line buffer
const currentLine = ref('')
const cursorPosition = ref(0)

// Handle terminal data including Tab
terminal.value.onData((data) => {
  if (data === '\t') {
    // Tab key pressed - request completion
    emit('tabCompletion', {
      text: currentLine.value,
      cursor: cursorPosition.value
    })
    return
  }
  // ... rest of handler
})

// Method to apply completion
const applyCompletion = (prefix: string, completion: string) => {
  // Calculate replacement
  const beforePrefix = currentLine.value.slice(0, cursorPosition.value - prefix.length)
  const afterCursor = currentLine.value.slice(cursorPosition.value)
  const newLine = beforePrefix + completion + afterCursor

  // Clear current line and write new one
  // (Implementation depends on terminal state management)
}
```

**Step 4: Commit**

```bash
cd /home/kali/Desktop/AutoBot/.worktrees/terminal-749
git add autobot-vue/src/
git commit -m "feat(#749): add tab completion support to frontend terminal"
```

---

## Task 5: Frontend - History Integration

**Files:**
- Create: `autobot-vue/src/composables/useTerminalHistory.ts`
- Modify: `autobot-vue/src/components/terminal/BaseXTerminal.vue`

**Step 1: Create history composable**

```typescript
// autobot-vue/src/composables/useTerminalHistory.ts
import { ref } from 'vue'
import terminalService from '@/services/TerminalService.js'

export function useTerminalHistory(sessionId: string) {
  const history = ref<string[]>([])
  const historyIndex = ref(-1)
  const searchMode = ref(false)
  const searchQuery = ref('')

  const syncHistory = () => {
    terminalService.sendInput(sessionId, JSON.stringify({
      type: 'history_get',
      limit: 100
    }))
  }

  const navigateHistory = (direction: 'up' | 'down'): string => {
    if (history.value.length === 0) return ''

    if (direction === 'up') {
      if (historyIndex.value < history.value.length - 1) {
        historyIndex.value++
      }
    } else {
      if (historyIndex.value > -1) {
        historyIndex.value--
      }
    }

    return historyIndex.value >= 0 ? history.value[historyIndex.value] : ''
  }

  const resetHistoryIndex = () => {
    historyIndex.value = -1
  }

  const setHistory = (commands: string[]) => {
    history.value = commands
  }

  const reverseSearch = (query: string) => {
    searchMode.value = true
    searchQuery.value = query
    // Send search request via WebSocket
  }

  return {
    history,
    historyIndex,
    searchMode,
    searchQuery,
    syncHistory,
    navigateHistory,
    resetHistoryIndex,
    setHistory,
    reverseSearch
  }
}
```

**Step 2: Integrate in BaseXTerminal**

Add history handling for arrow keys in the terminal.

**Step 3: Commit**

```bash
cd /home/kali/Desktop/AutoBot/.worktrees/terminal-749
git add autobot-vue/src/composables/useTerminalHistory.ts autobot-vue/src/components/terminal/
git commit -m "feat(#749): add history navigation and persistence to frontend"
```

---

## Task 6: Terminal Settings Component

**Files:**
- Create: `autobot-vue/src/components/terminal/TerminalSettings.vue`

**Step 1: Create settings component**

```vue
<!-- autobot-vue/src/components/terminal/TerminalSettings.vue -->
<template>
  <div class="terminal-settings p-4 bg-gray-800 rounded-lg">
    <h3 class="text-white text-lg mb-4">Terminal Settings</h3>

    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <label class="text-gray-300">Font Size</label>
        <input
          type="range"
          v-model.number="settings.fontSize"
          min="10"
          max="24"
          class="w-32"
        />
        <span class="text-gray-400 w-8">{{ settings.fontSize }}</span>
      </div>

      <div class="flex items-center justify-between">
        <label class="text-gray-300">Theme</label>
        <select v-model="settings.theme" class="bg-gray-700 text-white rounded px-2 py-1">
          <option value="dark">Dark</option>
          <option value="light">Light</option>
        </select>
      </div>

      <div class="flex items-center justify-between">
        <label class="text-gray-300">Cursor Style</label>
        <select v-model="settings.cursorStyle" class="bg-gray-700 text-white rounded px-2 py-1">
          <option value="block">Block</option>
          <option value="underline">Underline</option>
          <option value="bar">Bar</option>
        </select>
      </div>

      <div class="flex items-center justify-between">
        <label class="text-gray-300">Cursor Blink</label>
        <input type="checkbox" v-model="settings.cursorBlink" />
      </div>
    </div>

    <button
      @click="saveSettings"
      class="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
    >
      Save Settings
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

interface TerminalSettings {
  fontSize: number
  theme: 'dark' | 'light'
  cursorStyle: 'block' | 'underline' | 'bar'
  cursorBlink: boolean
}

const emit = defineEmits<{
  update: [settings: TerminalSettings]
}>()

const settings = ref<TerminalSettings>({
  fontSize: 14,
  theme: 'dark',
  cursorStyle: 'block',
  cursorBlink: true
})

watch(settings, (newSettings) => {
  emit('update', newSettings)
}, { deep: true })

const saveSettings = () => {
  localStorage.setItem('terminal-settings', JSON.stringify(settings.value))
}

// Load settings on mount
const stored = localStorage.getItem('terminal-settings')
if (stored) {
  settings.value = JSON.parse(stored)
}
</script>
```

**Step 2: Commit**

```bash
cd /home/kali/Desktop/AutoBot/.worktrees/terminal-749
git add autobot-vue/src/components/terminal/TerminalSettings.vue
git commit -m "feat(#749): add terminal settings component"
```

---

## Task 7: Final Integration and Testing

**Step 1: Run all tests**

```bash
cd /home/kali/Desktop/AutoBot/.worktrees/terminal-749
pytest tests/unit/test_terminal_completion_service.py tests/unit/test_terminal_history_service.py -v
```

**Step 2: Manual E2E testing**

1. Start backend: `python main.py`
2. Start frontend: `cd autobot-vue && npm run dev`
3. Open terminal in UI
4. Test Tab completion
5. Test history navigation (Up/Down)
6. Test settings changes

**Step 3: Final commit**

```bash
cd /home/kali/Desktop/AutoBot/.worktrees/terminal-749
git add -A
git commit -m "feat(#749): complete terminal integration finalization"
```

**Step 4: Update GitHub issue**

Add comment with completion summary and mark subtasks complete.

---

## Success Criteria Checklist

- [ ] Tab completion works for commands
- [ ] Tab completion works for file paths
- [ ] Tab completion works for env vars ($)
- [ ] History persists in Redis
- [ ] Up/Down arrow navigates history
- [ ] Settings component works
- [ ] All tests passing
