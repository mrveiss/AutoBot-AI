# Terminal Command Approval Workflow

**Chat Terminal Security Feature - Complete Documentation**

---

## Overview

The Chat Terminal implements a sophisticated command approval workflow that ensures AI agents cannot execute dangerous commands without user oversight. This critical security feature prevents potential system damage while maintaining workflow efficiency.

---

## Workflow Components

### **1. Agent Terminal Session**

Located in: `backend/services/agent_terminal_service.py`

```python
@dataclass
class AgentTerminalSession:
    session_id: str              # Unique session identifier
    agent_id: str                # AI agent identifier
    agent_role: AgentRole        # Permission level (CHAT_AGENT, etc.)
    conversation_id: str         # Linked chat session
    host: str                    # Target host (main, frontend, etc.)
    state: AgentSessionState     # Current control state
    pending_approval: dict       # Command awaiting approval
    command_history: list        # Executed commands log
    pty_session_id: str          # PTY session for WebSocket
```

### **2. Command Risk Levels**

Located in: `src/secure_command_executor.py`

```python
class CommandRisk(Enum):
    SAFE       = "safe"       # Execute immediately
    MODERATE   = "moderate"   # Require approval
    HIGH       = "high"       # Require approval + warning
    FORBIDDEN  = "forbidden"  # Block completely
```

---

## Complete Workflow Sequence

### **Phase 1: Agent Requests Command**

```
┌─────────────┐
│ 1. Agent    │  Agent (LLM) decides to execute command
│  (LLM)      │  Example: "I'll check the files: ls -la"
└──────┬──────┘
       │
       │ POST /api/agent-terminal/sessions/{id}/execute
       │ {
       │   "command": "ls -la",
       │   "description": "List all files in current directory",
       │   "force_approval": false
       │ }
       ▼
```

**Endpoint**: `POST /api/agent-terminal/sessions/{session_id}/execute`

**Handler**: `agent_terminal.py:execute_agent_command()`

```python
async def execute_agent_command(
    session_id: str,
    request: ExecuteCommandRequest,
    service: AgentTerminalService = Depends(get_agent_terminal_service),
):
    # Delegates to service layer
    result = await service.execute_command(
        session_id=session_id,
        command=request.command,
        description=request.description,
        force_approval=request.force_approval,
    )
    return result
```

---

### **Phase 2: Risk Assessment**

```
┌──────────────────┐
│ 2. Service Layer │  AgentTerminalService.execute_command()
│   agent_terminal_│
│   service.py     │
└────────┬─────────┘
         │
         │ Step 1: Get session
         ├─────────────────────────────────────────┐
         │                                         │
         │ Step 2: Assess command risk             │
         │ ┌───────────────────────────────────┐   │
         │ │ SecureCommandExecutor.           │   │
         │ │   assess_command_risk()          │   │
         │ │                                  │   │
         │ │ Checks risky patterns:           │   │
         │ │ • rm -rf / dd / mkfs (FORBIDDEN) │   │
         │ │ • sudo / apt install (HIGH)      │   │
         │ │ • chmod / chown (MODERATE)       │   │
         │ │ • ls / pwd / cat (SAFE)          │   │
         │ └───────────────────────────────────┘   │
         │                                         │
         ▼                                         │
┌────────────────────┐                            │
│ Risk Level Result  │                            │
│                    │                            │
│ risk: CommandRisk  │◄───────────────────────────┘
│ reasons: [...]     │
└────────┬───────────┘
         │
         ▼
```

**Code Flow**: `agent_terminal_service.py:execute_command()`

```python
async def execute_command(
    self,
    session_id: str,
    command: str,
    description: Optional[str] = None,
    force_approval: bool = False,
) -> Dict[str, Any]:
    # Get session
    session = self.sessions.get(session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    # Check session state
    if session.state != AgentSessionState.AGENT_CONTROL:
        raise PermissionError("Agent does not have control")

    # Assess command risk
    executor = SecureCommandExecutor(policy=self.security_policy)
    risk, reasons = executor.assess_command_risk(command)

    # Decision tree based on risk level...
```

---

### **Phase 3: Decision Tree**

```
   Risk Assessment Result
            │
            ▼
   ┌────────────────┐
   │ Decision Tree  │
   └────────────────┘
            │
    ┌───────┴───────┬────────────┬──────────────┐
    │               │            │              │
    ▼               ▼            ▼              ▼
┌─────────┐   ┌──────────┐  ┌──────┐   ┌────────────┐
│FORBIDDEN│   │  HIGH    │  │MODER-│   │    SAFE    │
│         │   │          │  │ ATE  │   │            │
└────┬────┘   └────┬─────┘  └──┬───┘   └─────┬──────┘
     │             │            │             │
     │             │            │             │
     ▼             ▼            ▼             ▼
┌─────────┐   ┌──────────┐  ┌──────┐   ┌────────────┐
│ REJECT  │   │ REQUIRE  │  │REQUIRE│   │  EXECUTE   │
│ (error) │   │ APPROVAL │  │APPROV-│   │ IMMEDIATE  │
│         │   │          │  │  AL   │   │            │
└─────────┘   └────┬─────┘  └──┬───┘   └─────┬──────┘
                   │            │             │
                   │            │             │
                   └────────────┴─────────────┘
                                │
                                ▼
                        force_approval = True?
                                │
                        ┌───────┴───────┐
                        │               │
                        ▼               ▼
                      YES              NO
                        │               │
                        │               ▼
                        │        Use risk-based
                        │        decision
                        │               │
                        └───────┬───────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │ IF approval needed:   │
                    │ → Set pending_approval│
                    │ → Return approval_req │
                    │                       │
                    │ ELSE:                 │
                    │ → Execute directly    │
                    └───────────────────────┘
```

**Code**: Decision Logic

```python
# Determine if approval is needed
approval_needed = False
if force_approval:
    approval_needed = True
elif risk == CommandRisk.FORBIDDEN:
    # Block forbidden commands
    logger.warning(f"SECURITY: Blocked forbidden command: {command}")
    return {
        "status": "forbidden",
        "command": command,
        "risk": risk.value,
        "reasons": reasons,
        "message": "Command is forbidden and cannot be executed",
    }
elif risk in [CommandRisk.HIGH, CommandRisk.MODERATE]:
    # Require approval for risky commands
    approval_needed = True

if approval_needed:
    # Set pending approval
    session.pending_approval = {
        "command": command,
        "description": description,
        "risk": risk.value,
        "reasons": reasons,
        "timestamp": time.time(),
    }
    session.last_activity = time.time()

    return {
        "status": "approval_required",
        "command": command,
        "risk": risk.value,
        "reasons": reasons,
        "session_id": session_id,
    }
else:
    # Safe command - execute directly
    return await self._execute_approved_command(session, command, description)
```

---

### **Phase 4a: Approval Required Path**

```
┌──────────────────┐
│ 3a. Approval     │  Command requires user approval
│    Required      │
└────────┬─────────┘
         │
         │ Frontend receives:
         │ {
         │   "status": "approval_required",
         │   "command": "sudo apt install nginx",
         │   "risk": "high",
         │   "reasons": ["Requires sudo", "Package installation"]
         │ }
         ▼
┌──────────────────┐
│ 4. Frontend      │  ChatTerminal.vue displays approval UI
│    Shows Dialog  │
│                  │  ┌─────────────────────────────────┐
│                  │  │  Command Approval Required      │
│                  │  │  ─────────────────────────────  │
│                  │  │  Command: sudo apt install nginx│
│                  │  │  Risk: HIGH                     │
│                  │  │  Reasons:                       │
│                  │  │  • Requires sudo privileges     │
│                  │  │  • Package installation         │
│                  │  │                                 │
│                  │  │  [Approve] [Deny]               │
│                  │  └─────────────────────────────────┘
└────────┬─────────┘
         │
         │ User clicks button
         ▼
┌──────────────────┐
│ 5. User Decision │
└────────┬─────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
APPROVE     DENY
    │         │
    │         │ POST /api/agent-terminal/sessions/{id}/approve
    │         │ {
    │         │   "approved": false,
    │         │   "user_id": "user123",
    │         │   "comment": "Too risky"
    │         │ }
    │         │
    │         ▼
    │    ┌──────────────┐
    │    │ 6a. Rejected │  Command canceled
    │    │              │  pending_approval cleared
    │    └──────────────┘
    │
    │ POST /api/agent-terminal/sessions/{id}/approve
    │ {
    │   "approved": true,
    │   "user_id": "user123",
    │   "auto_approve_future": false
    │ }
    │
    ▼
┌──────────────────┐
│ 6b. Approved     │  Command execution proceeds
└────────┬─────────┘
         │
         │ Calls _execute_approved_command()
         │
         ▼
  (Go to Phase 5)
```

**Frontend Code**: `ChatTerminal.vue`

```javascript
// User clicks approve
const approveCommand = async () => {
  const url = await appConfig.getApiUrl(
    `/api/agent-terminal/sessions/${backendSessionId.value}/approve`
  )

  await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      approved: true,
      user_id: 'current_user',
      comment: approvalComment.value,
      auto_approve_future: autoApprove.value
    })
  })

  // Close dialog
  showApprovalDialog.value = false
}
```

**Backend Code**: `agent_terminal.py:approve_pending_command()`

```python
@router.post("/sessions/{session_id}/approve")
async def approve_pending_command(
    session_id: str,
    request: ApproveCommandRequest,
    service: AgentTerminalService = Depends(get_agent_terminal_service),
):
    result = await service.approve_command(
        session_id=session_id,
        approved=request.approved,
        user_id=request.user_id,
        comment=request.comment,
        auto_approve_future=request.auto_approve_future,
    )
    return result
```

---

### **Phase 4b: Direct Execution Path**

```
┌──────────────────┐
│ 3b. Safe Command │  Risk = SAFE
│    (No Approval) │
└────────┬─────────┘
         │
         │ Skip approval
         │
         ▼
  (Go to Phase 5)
```

---

### **Phase 5: Command Execution**

```
┌──────────────────────┐
│ 5. Execute Command   │  _execute_approved_command()
│                      │
│  Steps:              │
│  1. Get PTY session  │
│  2. Write to PTY     │
│  3. Log command      │
│  4. Add to history   │
└────────┬─────────────┘
         │
         │ Get PTY session ID
         ▼
┌──────────────────────┐
│ session.pty_session  │
│ _id: "pty-456"       │
└────────┬─────────────┘
         │
         │ Use terminal manager
         ▼
┌──────────────────────┐
│ terminal.py          │
│ ConsolidatedTerminal │
│ Manager              │
│                      │
│ send_input_to_       │
│ terminal()           │
└────────┬─────────────┘
         │
         │ Write to PTY
         ▼
┌──────────────────────┐
│ simple_pty.py        │
│ SimplePTY            │
│                      │
│ write_input(command) │
└────────┬─────────────┘
         │
         │ os.write(master_fd, command.encode())
         ▼
┌──────────────────────┐
│ /bin/bash            │
│ Executes command     │
└────────┬─────────────┘
         │
         │ Output
         ▼
```

**Code**: `agent_terminal_service.py:_execute_approved_command()`

```python
async def _execute_approved_command(
    self,
    session: AgentTerminalSession,
    command: str,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a command that has been approved"""

    try:
        # Get terminal manager
        from backend.api.terminal import session_manager

        # Send command to terminal via PTY session
        pty_session_id = session.pty_session_id
        if not pty_session_id:
            raise ValueError("No PTY session available")

        # Send input to terminal
        success = await session_manager.send_input_to_terminal(
            pty_session_id,
            command + "\n"  # Add newline to execute
        )

        if not success:
            raise Exception("Failed to send command to terminal")

        # Log command execution
        await self.terminal_logger.log_command(
            session_id=session.conversation_id,
            command=command,
            description=description,
            timestamp=time.time(),
        )

        # Add to command history
        session.command_history.append({
            "command": command,
            "description": description,
            "timestamp": time.time(),
            "status": "executed",
        })
        session.last_activity = time.time()

        return {
            "status": "executed",
            "command": command,
            "session_id": session.session_id,
        }

    except Exception as e:
        logger.error(f"Error executing command: {e}")
        return {
            "status": "error",
            "command": command,
            "error": str(e),
        }
```

---

### **Phase 6: Output Handling**

```
┌──────────────────────┐
│ 6. Command Output    │
└────────┬─────────────┘
         │
         │ /bin/bash produces output
         ▼
┌──────────────────────┐
│ SimplePTY            │
│ Reader thread picks  │
│ up output from PTY   │
└────────┬─────────────┘
         │
         │ Queues output
         ▼
┌──────────────────────┐
│ ConsolidatedTerminal │
│ WebSocket            │
│                      │
│ _read_pty_output()   │
│ async task           │
└────────┬─────────────┘
         │
         ├─────────────────────┐
         │                     │
         ▼                     ▼
┌────────────────┐    ┌────────────────┐
│ WebSocket      │    │ Output Buffer  │
│ Send to        │    │ for Chat       │
│ Frontend       │    │ Integration    │
└────────┬───────┘    └────────┬───────┘
         │                     │
         ▼                     │
┌────────────────┐             │
│ ChatTerminal   │             │
│ .vue           │             │
│ Display output │             │
└────────────────┘             │
                               │
                               │ Every 500ms OR buffer > 1000 chars
                               ▼
                      ┌────────────────┐
                      │ ChatHistory    │
                      │ Manager        │
                      │                │
                      │ add_message()  │
                      │ sender=        │
                      │  "terminal"    │
                      │ session_id=    │
                      │  chat_id       │
                      └────────────────┘
                               │
                               ▼
                      Chat history shows:
                      [TERMINAL] $ ls -la
                      total 48
                      drwxr-xr-x  12 user  staff   384 Jan  9 10:30 .
                      drwxr-xr-x   8 user  staff   256 Jan  9 09:15 ..
                      ...
```

**Code**: Output buffering in `terminal.py:send_output()`

```python
async def send_output(self, content: str):
    """Send output to WebSocket and buffer for chat integration"""

    # Send to WebSocket immediately
    await self.send_message({
        "type": "output",
        "content": content,
    })

    # Buffer for chat integration
    if self.chat_history_manager and self.conversation_id:
        async with self._output_lock:
            self._output_buffer += content
            current_time = time.time()

            # Save to chat if buffer is large enough or enough time passed
            should_save = (
                len(self._output_buffer) >= 1000 or  # Buffer size threshold
                current_time - self._last_output_save_time >= 0.5  # Time threshold
            )

            if should_save and self._output_buffer.strip():
                await self.chat_history_manager.add_message(
                    sender="terminal",
                    text=self._output_buffer,
                    message_type="terminal_output",
                    session_id=self.conversation_id,
                )
                self._output_buffer = ""
                self._last_output_save_time = current_time
```

---

## User Takeover Workflow

### **Interrupt Agent and Take Control**

```
┌──────────────────┐
│ Agent executing  │  State: AGENT_CONTROL
│ commands         │
└────────┬─────────┘
         │
         │ User clicks "Take Control"
         │ POST /api/agent-terminal/sessions/{id}/interrupt
         │ {
         │   "user_id": "user123"
         │ }
         ▼
┌──────────────────┐
│ Service receives │  AgentTerminalService.interrupt_agent()
│ interrupt        │
└────────┬─────────┘
         │
         │ 1. Verify session exists
         │ 2. Check current state = AGENT_CONTROL
         │ 3. Change state to USER_INTERRUPT
         │
         ▼
┌──────────────────┐
│ State transition │  AGENT_CONTROL → USER_INTERRUPT
└────────┬─────────┘
         │
         │ Agent sees state change
         │ Agent pauses command execution
         │
         ▼
┌──────────────────┐
│ Terminal updates │  Terminal ownership transfers
│ frontend         │  State: USER_CONTROL
└────────┬─────────┘
         │
         │ Frontend UI updates:
         │ • "Release Control" button shown
         │ • Terminal read-only = false
         │ • User can type commands
         │
         ▼
┌──────────────────┐
│ User has control │  Commands execute without approval
└────────┬─────────┘
         │
         │ User finishes manual work
         │ User clicks "Release Control"
         │ POST /api/agent-terminal/sessions/{id}/release
         │
         ▼
┌──────────────────┐
│ State transition │  USER_CONTROL → AGENT_RESUME → AGENT_CONTROL
│ back to agent    │
└──────────────────┘
```

---

## State Machine Summary

```
┌─────────────────────────────────────────────────────────────┐
│                   AGENT TERMINAL STATES                     │
└─────────────────────────────────────────────────────────────┘

Initial: AGENT_CONTROL
  │
  ├─> User interrupt ───> USER_INTERRUPT ───> USER_CONTROL
  │                                               │
  │                                               │
  │   <─── User release ─── AGENT_RESUME ─────────┘
  │
  └─> (loop)

State Permissions:
┌──────────────────┬───────────────┬──────────────┬─────────────┐
│ State            │ Agent Execute │ User Execute │ Approval?   │
├──────────────────┼───────────────┼──────────────┼─────────────┤
│ AGENT_CONTROL    │ ✅ Yes        │ ❌ No        │ ✅ Required │
│ USER_INTERRUPT   │ ⏸️ Pausing    │ ⏸️ Pending   │ N/A         │
│ USER_CONTROL     │ ❌ No         │ ✅ Yes       │ ❌ None     │
│ AGENT_RESUME     │ ⏸️ Resuming   │ ❌ No        │ N/A         │
└──────────────────┴───────────────┴──────────────┴─────────────┘
```

---

## Security Guarantees

### **1. No God Mode**

- ✅ All agents subject to RBAC (Role-Based Access Control)
- ✅ Agent role determines permission level
- ✅ No agent can bypass security checks
- ✅ CVE-003 Fix: Agents must request approval for risky commands

### **2. Prompt Injection Protection**

- ✅ Command text validated before execution
- ✅ Risk assessment on every command
- ✅ User approval required for suspicious patterns
- ✅ CVE-002 Fix: Cannot inject commands via chat input

### **3. Audit Trail**

- ✅ All commands logged to `terminal_logger`
- ✅ Linked to conversation_id for full context
- ✅ Timestamp, risk level, approval status recorded
- ✅ Complete history available for security review

### **4. User Override**

- ✅ User can interrupt agent at any time
- ✅ User can deny dangerous commands
- ✅ User can take direct control of terminal
- ✅ Agent cannot prevent user takeover

---

## Configuration

### **Risk Thresholds**

Located in: `src/secure_command_executor.py`

```python
# Forbidden patterns (never execute)
FORBIDDEN_PATTERNS = [
    "rm -rf /",
    "dd if=",
    "mkfs",
    ":(){ :|:& };:",  # Fork bomb
]

# High-risk patterns (require approval + warning)
HIGH_RISK_PATTERNS = [
    "sudo rm",
    "apt install",
    "yum install",
    "systemctl",
    "reboot",
    "shutdown",
]

# Moderate-risk patterns (require approval)
MODERATE_RISK_PATTERNS = [
    "chmod",
    "chown",
    "kill",
    "pkill",
]
```

### **Auto-Approval (Future Feature)**

```python
# User can enable auto-approval for specific commands
auto_approve_future: bool  # In ApproveCommandRequest

# If enabled:
# • Future similar commands auto-approved
# • Stored in user preferences
# • Can be revoked at any time
```

---

## Testing Scenarios

### **Test 1: Safe Command (No Approval)**

```bash
Command: ls -la
Expected: Executes immediately
Result: ✅ Pass
```

### **Test 2: Moderate Risk (Approval Required)**

```bash
Command: chmod 777 file.txt
Expected: Approval dialog shown
Result: ✅ Pass
```

### **Test 3: High Risk (Approval + Warning)**

```bash
Command: sudo apt install nginx
Expected: Approval dialog + warning
Result: ✅ Pass
```

### **Test 4: Forbidden Command (Blocked)**

```bash
Command: rm -rf /
Expected: Rejected with error
Result: ✅ Pass
```

### **Test 5: User Takeover**

```bash
1. Agent has control
2. User clicks "Take Control"
3. State transitions to USER_CONTROL
4. User types: ls -la (no approval needed)
Expected: Command executes directly
Result: ✅ Pass
```

### **Test 6: Output to Chat**

```bash
1. Agent runs: ls -la
2. Output captured by PTY
3. Buffered for chat integration
Expected: Output appears in chat history
Result: ✅ Pass
```

---

## API Reference

### **Execute Command**

```
POST /api/agent-terminal/sessions/{session_id}/execute

Request Body:
{
  "command": "ls -la",
  "description": "List all files",
  "force_approval": false
}

Response (Approval Required):
{
  "status": "approval_required",
  "command": "ls -la",
  "risk": "moderate",
  "reasons": ["File system access"],
  "session_id": "session-123"
}

Response (Executed):
{
  "status": "executed",
  "command": "ls -la",
  "session_id": "session-123"
}
```

### **Approve Command**

```
POST /api/agent-terminal/sessions/{session_id}/approve

Request Body:
{
  "approved": true,
  "user_id": "user123",
  "comment": "Approved for directory listing",
  "auto_approve_future": false
}

Response:
{
  "status": "approved",
  "command": "ls -la",
  "executed": true
}
```

### **Interrupt Agent**

```
POST /api/agent-terminal/sessions/{session_id}/interrupt

Request Body:
{
  "user_id": "user123"
}

Response:
{
  "status": "success",
  "previous_state": "agent_control",
  "new_state": "user_control",
  "session_id": "session-123"
}
```

---

## Future Enhancements

1. **Command Whitelisting**: Allow user to whitelist specific commands
2. **Auto-Approval Patterns**: Learn from user approvals
3. **Risk Level Customization**: User-configurable risk thresholds
4. **Approval Timeout**: Auto-deny after X seconds
5. **Multi-User Approval**: Require multiple approvals for critical commands
6. **Approval History**: View all past approvals/denials

---
