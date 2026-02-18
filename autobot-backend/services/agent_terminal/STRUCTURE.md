# Agent Terminal Service Modular Structure

## Overview

The `agent_terminal_service.py` (2407 lines) has been refactored into a modular structure under `/backend/services/agent_terminal/`.

## Module Breakdown

### 1. `models.py` (47 lines)
- **AgentSessionState** enum - State machine for agent terminal sessions
- **AgentTerminalSession** dataclass - Session data structure

### 2. `utils.py` (193 lines)
Helper functions:
- `map_risk_to_level()` - Convert CommandRisk to RiskLevel enum
- `extract_terminal_and_chat_ids()` - Extract IDs from session
- `create_command_execution()` - Factory for CommandExecution objects
- `is_interactive_command()` - Detect commands requiring stdin input (Issue #33)
- Interactive command pattern definitions and compilation

### 3. `session_manager.py` (398 lines)
Session lifecycle management:
- `create_session()` - Create PTY-integrated sessions
- `get_session()` - Retrieve from memory or Redis
- `list_sessions()` - Filter sessions by criteria
- `close_session()` - Clean up session resources
- `_persist_session()` - Save to Redis for persistence
- `_restore_pending_approval()` - Restore approval state after restart

### 4. `command_executor.py` (519 lines)
Command execution with intelligent polling:
- `execute_in_pty()` - Execute commands in PTY shell
- `_write_to_pty()` - Write to PTY with auto-recreation
- `cancel_command()` - Graceful command cancellation (SIGINT → SIGKILL)
- `_intelligent_poll_output()` - Adaptive polling with stability detection
- `_detect_return_code()` - UUID-based marker injection for exit codes
- `_analyze_error_patterns()` - Fallback return code detection

### 5. `approval_handler.py` (358 lines)
Approval workflow management:
- `check_agent_permission()` - Verify agent has permission for risk level
- `needs_approval()` - Determine if command requires approval
- `store_auto_approve_rule()` - Save auto-approval rules
- `check_auto_approve_rules()` - Check if command matches rules
- `broadcast_approval_status()` - WebSocket broadcasting via event_manager
- `update_chat_approval_status()` - Persist approval status in chat history
- `update_command_queue_status()` - Update command state in queue
- Per-session approval locks to prevent race conditions

### 6. `service.py` (745 lines)
Main service class that composes all functionality:
- Session management delegation (→ SessionManager)
- Command execution delegation (→ CommandExecutor)
- Approval workflow delegation (→ ApprovalHandler)
- User control management (interrupt/resume)
- Security integration (SecureCommandExecutor)
- Chat integration (ChatHistoryManager)
- Audit logging (TerminalLogger)
- Prometheus metrics recording

### 7. `__init__.py` (26 lines)
Module exports:
- `AgentTerminalService` - Main service class
- `AgentTerminalSession` - Session dataclass
- `AgentSessionState` - State enum

## Total Lines: 2,286 lines (reduced from 2,407)

## Benefits of Modular Structure

1. **Single Responsibility** - Each module has a clear, focused purpose
2. **Easier Testing** - Can test components independently
3. **Better Maintainability** - Smaller files are easier to understand
4. **Improved Reusability** - Utilities and handlers can be used elsewhere
5. **Clearer Dependencies** - Import structure shows relationships
6. **Separation of Concerns** - Session, execution, and approval logic isolated

## Import Pattern

```python
# External usage
from backend.services.agent_terminal import (
    AgentTerminalService,
    AgentSessionState,
    AgentTerminalSession,
)

# Internal usage (within modules)
from .models import AgentSessionState, AgentTerminalSession
from .utils import create_command_execution, is_interactive_command
from .session_manager import SessionManager
from .command_executor import CommandExecutor
from .approval_handler import ApprovalHandler
```

## Migration Completed

All imports in the codebase have been updated from:
```python
from backend.services.agent_terminal_service import ...
```

To:
```python
from backend.services.agent_terminal import ...
```

Updated files:
- `/home/kali/Desktop/AutoBot/backend/api/agent_terminal.py`
- `/home/kali/Desktop/AutoBot/backend/api/websockets.py`
- `/home/kali/Desktop/AutoBot/src/chat_workflow_manager.py`
- `/home/kali/Desktop/AutoBot/src/tools/terminal_tool.py`

Note: `AgentRole` imports changed to:
```python
from backend.services.command_approval_manager import AgentRole
```
