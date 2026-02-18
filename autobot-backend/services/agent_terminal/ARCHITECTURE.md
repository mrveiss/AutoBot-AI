# Agent Terminal Service Architecture

## Module Dependency Graph

```
┌─────────────────────────────────────────────────────────────────┐
│                      service.py (745 lines)                      │
│                    AgentTerminalService                          │
│                                                                   │
│  Main orchestration layer - composes all functionality          │
│  • Security integration (SecureCommandExecutor)                  │
│  • Chat integration (ChatHistoryManager)                         │
│  • Audit logging (TerminalLogger)                                │
│  • Metrics (Prometheus)                                          │
└─────┬────────────────┬─────────────────┬──────────────────────┘
      │                │                 │
      ▼                ▼                 ▼
┌──────────────┐ ┌──────────────┐ ┌────────────────────┐
│ session_     │ │ command_     │ │ approval_          │
│ manager.py   │ │ executor.py  │ │ handler.py         │
│ (398 lines)  │ │ (519 lines)  │ │ (358 lines)        │
│              │ │              │ │                    │
│ • create     │ │ • execute    │ │ • check_permission │
│ • get        │ │ • cancel     │ │ • needs_approval   │
│ • list       │ │ • poll       │ │ • broadcast_status │
│ • close      │ │ • detect_rc  │ │ • auto_approve     │
│ • persist    │ │ • write_pty  │ │ • update_queue     │
└──────┬───────┘ └──────┬───────┘ └────────┬───────────┘
       │                │                  │
       └────────────────┼──────────────────┘
                        │
                        ▼
              ┌──────────────────┐
              │ models.py        │
              │ (47 lines)       │
              │                  │
              │ • AgentSession   │
              │   State          │
              │ • AgentTerminal  │
              │   Session        │
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │ utils.py         │
              │ (193 lines)      │
              │                  │
              │ • map_risk       │
              │ • extract_ids    │
              │ • create_cmd_    │
              │   execution      │
              │ • is_interactive │
              └──────────────────┘
```

## Data Flow

### 1. Command Execution Flow

```
┌──────────────┐
│   API Call   │  execute_command()
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────┐
│ service.py                           │
│ • Validate session                   │
│ • Assess risk (SecureCommandExecutor)│
│ • Check permissions                  │
└──────┬───────────────────────────────┘
       │
       ├─── Need Approval? ──┐
       │                     │
       ▼                     ▼
┌──────────────┐      ┌─────────────────┐
│ Execute      │      │ Queue for       │
│ Immediately  │      │ Approval        │
└──────┬───────┘      └─────────┬───────┘
       │                        │
       ▼                        ▼
┌──────────────────┐   ┌────────────────┐
│ command_         │   │ approval_      │
│ executor.py      │   │ handler.py     │
│ • execute_in_pty │   │ • broadcast    │
└──────────────────┘   └────────────────┘
```

### 2. Session Lifecycle Flow

```
┌──────────────┐
│ Create       │
│ Session      │
└──────┬───────┘
       │
       ▼
┌──────────────────────────┐
│ session_manager.py       │
│ • create_session()       │
│   - Create PTY           │
│   - Register with WS     │
│   - Restore pending      │
│   - Persist to Redis     │
└──────┬───────────────────┘
       │
       ▼
┌──────────────────────────┐
│ Session Active           │
│ • Execute commands       │
│ • Handle approvals       │
│ • Track history          │
└──────┬───────────────────┘
       │
       ▼
┌──────────────────────────┐
│ Close Session            │
│ • Clean up locks         │
│ • Remove from Redis      │
│ • Close PTY              │
└──────────────────────────┘
```

### 3. Approval Workflow Flow

```
┌──────────────┐
│ Command      │
│ Needs        │
│ Approval     │
└──────┬───────┘
       │
       ▼
┌────────────────────────────┐
│ approval_handler.py        │
│ • check_auto_approve_rules │
└──────┬──────────────┬──────┘
       │              │
  Auto │              │ Manual
       │              │
       ▼              ▼
┌────────────┐  ┌─────────────────┐
│ Execute    │  │ Broadcast to    │
│ Immediately│  │ Frontend        │
└────────────┘  └────────┬────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ User         │
                  │ Approves/    │
                  │ Denies       │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ Update Queue │
                  │ & Chat       │
                  └──────┬───────┘
                         │
                    Approved?
                         │
                         ▼
                  ┌──────────────┐
                  │ Execute in   │
                  │ PTY          │
                  └──────────────┘
```

## Component Responsibilities

### SessionManager (session_manager.py)
- **Purpose**: Manage session lifecycle and persistence
- **Dependencies**: Redis, ChatHistoryManager, SimplePTY
- **Key Features**:
  - PTY session creation and management
  - Redis persistence for restarts
  - Pending approval restoration from chat history
  - Session state tracking

### CommandExecutor (command_executor.py)
- **Purpose**: Execute commands in PTY with intelligent polling
- **Dependencies**: ChatHistoryManager, SimplePTY
- **Key Features**:
  - PTY write with auto-recreation
  - Intelligent output polling with stability detection
  - UUID-based return code detection (security fix)
  - Graceful command cancellation (SIGINT → SIGKILL)
  - Error pattern analysis fallback

### ApprovalHandler (approval_handler.py)
- **Purpose**: Manage approval workflow and rules
- **Dependencies**: CommandApprovalManager, ChatHistoryManager, CommandQueue
- **Key Features**:
  - Permission checking (agent role vs risk level)
  - Auto-approval rule management
  - WebSocket broadcast via event_manager
  - Chat message metadata updates
  - Command queue status synchronization
  - Per-session approval locks (race condition prevention)

### AgentTerminalService (service.py)
- **Purpose**: Main orchestration and integration point
- **Dependencies**: All other modules, SecureCommandExecutor, ChatWorkflowManager
- **Key Features**:
  - Delegates to specialized managers
  - Security integration (risk assessment)
  - Chat integration (command interpretation)
  - Audit logging (TerminalLogger)
  - Prometheus metrics
  - User control management (interrupt/resume)

## Design Principles Applied

1. **Single Responsibility Principle**
   - Each module has ONE clear purpose
   - SessionManager → sessions, CommandExecutor → execution, etc.

2. **Dependency Injection**
   - All dependencies passed via constructors
   - Easy to test and mock

3. **Composition over Inheritance**
   - Service.py composes functionality from managers
   - No complex inheritance hierarchies

4. **Separation of Concerns**
   - Session, execution, and approval logic isolated
   - Each can be modified independently

5. **DRY (Don't Repeat Yourself)**
   - Helper functions in utils.py
   - Shared models in models.py
   - Reusable patterns across modules

6. **Factory Pattern**
   - create_command_execution() factory in utils.py
   - Encapsulates object creation logic

## Testing Strategy

Each module can be tested independently:

```python
# Test SessionManager
session_manager = SessionManager(
    redis_client=mock_redis,
    chat_history_manager=mock_chat
)
session = await session_manager.create_session(...)

# Test CommandExecutor
executor = CommandExecutor(chat_history_manager=mock_chat)
result = await executor.execute_in_pty(session, "ls")

# Test ApprovalHandler
handler = ApprovalHandler(
    approval_manager=mock_approval,
    chat_history_manager=mock_chat,
    command_queue=mock_queue
)
allowed = handler.check_agent_permission(role, risk)
```

## Performance Considerations

1. **Session Management**
   - In-memory cache with Redis fallback
   - Async locks prevent race conditions
   - O(1) session lookup

2. **Command Execution**
   - Intelligent polling with exponential backoff
   - Stability detection avoids unnecessary waits
   - Output streaming via chat history (pub/sub)

3. **Approval Workflow**
   - Per-session locks (not global)
   - Auto-approve rules reduce latency
   - Async WebSocket broadcasts

## Security Features

1. **Risk Assessment**
   - SecureCommandExecutor integration
   - Permission-based blocking
   - Mandatory approval for high-risk commands

2. **Return Code Detection**
   - UUID-based markers prevent injection
   - Fallback to error pattern analysis

3. **Command Cancellation**
   - Graceful SIGINT first
   - Forceful SIGKILL if needed
   - Orphaned process prevention

## Future Enhancements

1. **Command Chaining**
   - Execute multiple commands sequentially
   - Conditional execution based on return codes

2. **Output Streaming**
   - Real-time output display
   - Progress indicators for long commands

3. **Command Templates**
   - Pre-approved command patterns
   - Parameter validation

4. **Session Sharing**
   - Multiple agents in same session
   - Collaborative command execution
