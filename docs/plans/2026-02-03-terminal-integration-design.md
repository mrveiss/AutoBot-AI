# Terminal Integration Finalization - Design Document

**Issue**: #749
**Date**: 2026-02-03
**Priority**: High

## Overview

Finalize terminal integration with full bash-like tab completion, persistent command history, and polished UX using XTerm.js.

## Architecture

```
Frontend: BaseXTerminal.vue + XTerm.js addons
    │
    │ WebSocket (tab_completion, history messages)
    ▼
Backend: terminal_websocket_handler.py
    │
    ├── terminal_completion_service.py (compgen-based)
    └── terminal_history_service.py (Redis storage)
```

## Components

### 1. Tab Completion (compgen-based)
- Commands: `compgen -A alias -A builtin -A command`
- File paths: `compgen -f`
- Environment vars: `compgen -v`

### 2. History Persistence (Redis)
- Key: `terminal:history:{user_id}` (sorted set)
- Supports Ctrl+R reverse search

### 3. Settings
- Font size, theme, cursor style
- Stored in `terminal:settings:{user_id}`

### 4. Keyboard Shortcuts
- Tab: complete, Up/Down: history, Ctrl+R: search
- Ctrl+Shift+C/V: copy/paste

## Files to Create
- `src/services/terminal_completion_service.py`
- `src/services/terminal_history_service.py`
- `autobot-vue/src/components/terminal/TerminalSettings.vue`
- `autobot-vue/src/composables/useTerminalHistory.ts`

## Success Criteria
- Tab completion for commands and paths
- History persists across sessions
- Professional terminal feel
