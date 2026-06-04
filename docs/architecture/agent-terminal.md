---
tags: [type/architecture, status/current, component/backend]
date: 2026-06-04
---

# Agent Terminal Service — Architecture

The Agent Terminal Service provides PTY-based command execution with security controls, session persistence, approval workflows, and audit logging.

**Location:** `autobot-backend/services/agent_terminal/`

---

## Module Dependency Graph

```
┌──────────────────────────────────────────────────────────────┐
│                   service.py (745 lines)                      │
│                  AgentTerminalService                         │
│                                                               │
│  Orchestrates all functionality:                              │
│  • Security (SecureCommandExecutor)                           │
│  • Chat integration (ChatHistoryManager)                      │
│  • Audit logging (TerminalLogger)                             │
│  • Metrics (Prometheus)                                       │
└──────┬─────────────────┬────────────────┬────────────────────┘
       │                 │                │
       ▼                 ▼                ▼
┌─────────────┐  ┌──────────────┐  ┌──────────────────┐
│session_     │  │command_      │  │approval_         │
│manager.py   │  │executor.py   │  │handler.py        │
│(398 lines)  │  │(519 lines)   │  │(358 lines)       │
│             │  │              │  │                  │
│create       │  │execute       │  │check_permission  │
│get          │  │cancel        │  │needs_approval    │
│list         │  │poll          │  │broadcast_status  │
│close        │  │detect_rc     │  │auto_approve      │
│persist      │  │write_pty     │  │update_queue      │
└─────────────┘  └──────────────┘  └──────────────────┘
```

---

## Module Breakdown

### `models.py` (47 lines)
- `AgentSessionState` enum — state machine for terminal sessions
- `AgentTerminalSession` dataclass — session data structure

### `utils.py` (193 lines)
- `map_risk_to_level()` — convert `CommandRisk` to `RiskLevel`
- `extract_terminal_and_chat_ids()` — extract IDs from session
- `create_command_execution()` — factory for `CommandExecution` objects
- `is_interactive_command()` — detect commands requiring stdin (Issue #33)
- Interactive command pattern definitions and compilation

### `session_manager.py` (398 lines)
Session lifecycle:
- `create_session()` — create PTY-integrated sessions
- `get_session()` — retrieve from memory or Redis
- `list_sessions()` — filter sessions by criteria
- `close_session()` — clean up session resources
- `_persist_session()` — save to Redis for durability
- `_restore_pending_approval()` — restore approval state after restart

### `command_executor.py` (519 lines)
Command execution with intelligent polling:
- `execute_in_pty()` — execute commands in PTY shell
- `_write_to_pty()` — write to PTY with auto-recreation on failure
- `cancel_command()` — graceful cancellation (SIGINT → SIGKILL)
- `_intelligent_poll_output()` — adaptive polling with stability detection
- `_detect_return_code()` — UUID-based marker injection for exit codes
- `_analyze_error_patterns()` — fallback return code detection

### `approval_handler.py` (358 lines)
Approval workflow:
- `check_permission()` — evaluate if command needs approval
- `needs_approval()` — classify by risk level
- `broadcast_status()` — push approval state to WebSocket subscribers
- `auto_approve()` — auto-approve low-risk commands
- `update_queue()` — manage pending approval queue

### `service.py` (745 lines)
Main orchestration layer. Composes all modules; exposes the public API consumed by FastAPI routers.

---

## Session State Machine

```
CREATED → ACTIVE → RUNNING → AWAITING_APPROVAL
                           ↓
                        COMPLETED / FAILED / CANCELLED
```

---

## Key Design Decisions

**PTY over subprocess** — PTY gives accurate terminal output including escape codes, interactive prompts, and return codes that subprocess.PIPE cannot reliably capture.

**UUID-based return code detection** — After command completion, executor writes a unique UUID marker then reads the subsequent exit code, eliminating ambiguity from shell prompt parsing.

**Redis persistence** — Sessions survive backend restarts. `_restore_pending_approval()` re-hydrates approval state from Redis on startup.

**Adaptive polling** — `_intelligent_poll_output()` starts with short intervals and backs off once output stabilises, balancing responsiveness with CPU efficiency.
