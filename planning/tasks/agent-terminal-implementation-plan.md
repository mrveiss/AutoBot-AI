# Agent Terminal Implementation - Detailed Task Breakdown

**Created:** 2025-10-04
**Status:** Planning Phase
**Research Foundation:** Memory MCP entities (Agent Terminal Architecture Research, Terminal Security Analysis, Terminal Implementation Requirements)

---

## Executive Summary

This plan implements two distinct terminal types for AutoBot:
1. **Chat Terminal**: Agent-accessible, embedded in chat, session-persistent, user-interruptible
2. **Tools Terminal**: User-only bash terminal for direct use

**CRITICAL PREREQUISITE**: Three security vulnerabilities (CVE-AUTOBOT-2025-001, 002, 003) MUST be resolved before agent terminal access is enabled.

---

## Implementation Phases

### Phase 0: Security Remediation (MANDATORY FIRST)
### Phase 1: Backend Foundation
### Phase 2: Frontend Infrastructure
### Phase 3: Chat Terminal Integration
### Phase 4: Tools Terminal Implementation
### Phase 5: Testing & Validation
### Phase 6: Documentation & Deployment

---

# PHASE 0: SECURITY REMEDIATION (CRITICAL)

**BLOCKING STATUS**: Agent terminal access CANNOT be enabled until all three CVEs are resolved.

## Task 0.1: Fix CVE-AUTOBOT-2025-001 (SSH MITM Vulnerability)

**Complexity:** CRITICAL
**Agent:** `security-auditor`
**Depends On:** None
**Blocks:** All agent terminal functionality

**Current Vulnerability:**
```python
# backend/services/remote_executor.py
ssh_command = [
    "ssh",
    "-o", "StrictHostKeyChecking=no",  # ← MITM vulnerability
    "-o", "UserKnownHostsFile=/dev/null",
    f"{user}@{host}"
]
```

**Implementation Tasks:**
- [ ] **0.1.1** Create `~/.ssh/known_hosts` initialization for all 5 VMs
- [ ] **0.1.2** Remove `StrictHostKeyChecking=no` and `UserKnownHostsFile=/dev/null`
- [ ] **0.1.3** Implement first-connection fingerprint verification flow
- [ ] **0.1.4** Add fingerprint mismatch detection and alert system
- [ ] **0.1.5** Create host key rotation procedure documentation
- [ ] **0.1.6** Update `RemoteExecutor` to enforce strict host key checking
- [ ] **0.1.7** Security audit verification and penetration test

**Acceptance Criteria:**
- SSH connections reject MITM attempts
- Known hosts file properly maintained
- User alerted on fingerprint changes
- All 5 VMs have verified host keys

**Parallel Track:** Can work alongside Task 0.2

---

## Task 0.2: Fix CVE-AUTOBOT-2025-002 (Prompt Injection in Command Extraction)

**Complexity:** CRITICAL
**Agent:** `security-auditor` + `senior-backend-engineer`
**Depends On:** None
**Blocks:** Agent command execution safety

**Current Vulnerability:**
```python
# Unsafe regex extraction allows injection
bash_code = re.search(r'```(?:bash|sh)?\n(.*?)\n```', response, re.DOTALL)
```

**Implementation Tasks:**
- [ ] **0.2.1** Design secure command extraction AST parser
- [ ] **0.2.2** Implement command syntax validation layer
- [ ] **0.2.3** Add semantic analysis for dangerous patterns (rm -rf, dd, mkfs, etc.)
- [ ] **0.2.4** Create command sandboxing for agent-generated commands
- [ ] **0.2.5** Implement escape sequence sanitization
- [ ] **0.2.6** Add command length and complexity limits
- [ ] **0.2.7** Create comprehensive injection test suite
- [ ] **0.2.8** Security audit verification

**Acceptance Criteria:**
- Prompt injection attacks fail safely
- Malicious escape sequences blocked
- Command validation prevents dangerous operations
- Test suite covers 20+ injection vectors

**Parallel Track:** Can work alongside Task 0.1

---

## Task 0.3: Fix CVE-AUTOBOT-2025-003 (God Mode Security Bypass)

**Complexity:** CRITICAL
**Agent:** `security-auditor` + `systems-architect`
**Depends On:** None
**Blocks:** Agent permission enforcement

**Current Vulnerability:**
```python
# God mode disables ALL security checks
if god_mode:
    return True  # ← Security bypass
```

**Implementation Tasks:**
- [ ] **0.3.1** Remove god mode security bypass from all code paths
- [ ] **0.3.2** Implement proper admin privilege escalation workflow
- [ ] **0.3.3** Add granular permission system (read, write, execute, admin)
- [ ] **0.3.4** Create audit logging for all elevated operations
- [ ] **0.3.5** Implement time-limited privilege elevation (similar to sudo)
- [ ] **0.3.6** Add MFA requirement for dangerous operations
- [ ] **0.3.7** Create privilege abuse detection system
- [ ] **0.3.8** Security audit verification

**Acceptance Criteria:**
- God mode removed or properly scoped
- Admin actions require explicit authorization
- All privileged operations audited
- Time-limited privilege elevation working

**Parallel Track:** Can work alongside Tasks 0.1 and 0.2

---

## Task 0.4: Enhanced Security Layer Integration

**Complexity:** COMPLEX
**Agent:** `security-auditor` + `senior-backend-engineer`
**Depends On:** Tasks 0.1, 0.2, 0.3
**Blocks:** Agent terminal activation

**Implementation Tasks:**
- [ ] **0.4.1** Integrate fixed security layers with terminal service
- [ ] **0.4.2** Create agent-specific command whitelist/blacklist
- [ ] **0.4.3** Implement rate limiting for agent terminal commands
- [ ] **0.4.4** Add session-based security context tracking
- [ ] **0.4.5** Create user override mechanism for blocked commands
- [ ] **0.4.6** Implement comprehensive audit logging for agent commands
- [ ] **0.4.7** Add real-time security event monitoring
- [ ] **0.4.8** Final security assessment and penetration testing

**Acceptance Criteria:**
- All three CVEs fully resolved
- Security layers properly integrated
- Agent commands properly restricted
- Audit trail complete and searchable
- Penetration testing passes

**Estimated Duration:** 2-3 weeks
**Risk Level:** CRITICAL - Project blocker

---

# PHASE 1: BACKEND FOUNDATION

**Prerequisites:** Phase 0 complete (all CVEs resolved)

## Task 1.1: Terminal Session Management

**Complexity:** MODERATE
**Agent:** `senior-backend-engineer`
**Depends On:** Phase 0 complete
**Blocks:** All terminal functionality

**Implementation Tasks:**
- [ ] **1.1.1** Create `TerminalSessionManager` class in `backend/services/`
- [ ] **1.1.2** Implement session creation with unique session IDs
- [ ] **1.1.3** Add session persistence (Redis or in-memory store)
- [ ] **1.1.4** Implement session lifecycle (create, suspend, resume, terminate)
- [ ] **1.1.5** Add command history storage per session
- [ ] **1.1.6** Create session ownership and permission model
- [ ] **1.1.7** Implement session timeout and cleanup logic
- [ ] **1.1.8** Add WebSocket connection mapping to sessions

**Data Structures:**
```python
class TerminalSession:
    session_id: str
    host_id: str  # VM identifier (main, vm1-vm5)
    user_type: str  # "human" or "agent"
    command_history: List[Command]
    created_at: datetime
    last_activity: datetime
    state: str  # "active", "suspended", "terminated"
    owner_conversation_id: Optional[str]
```

**Acceptance Criteria:**
- Sessions persist across reconnections
- Command history maintained during session
- Multiple simultaneous sessions supported
- Proper cleanup on timeout

**Parallel Track:** Can work alongside Task 1.2

---

## Task 1.2: Multi-Host SSH Connection Manager

**Complexity:** MODERATE
**Agent:** `senior-backend-engineer` + `devops-engineer`
**Depends On:** Task 0.1 (SSH security fixed)
**Blocks:** Remote command execution

**Implementation Tasks:**
- [ ] **1.2.1** Create `SSHConnectionPool` class for persistent connections
- [ ] **1.2.2** Implement connection configuration for all 6 hosts (main + 5 VMs)
- [ ] **1.2.3** Add connection health monitoring and auto-reconnect
- [ ] **1.2.4** Implement connection pooling and reuse
- [ ] **1.2.5** Add host-specific environment setup (PATH, env vars)
- [ ] **1.2.6** Create connection error handling and fallback
- [ ] **1.2.7** Implement SSH key management integration
- [ ] **1.2.8** Add connection metrics and monitoring

**Host Configuration:**
```python
HOSTS = {
    "main": {"ip": "172.16.168.20", "name": "Main (WSL)", "services": ["backend", "vnc"]},
    "frontend": {"ip": "172.16.168.21", "name": "Frontend", "services": ["vue"]},
    "npu": {"ip": "172.16.168.22", "name": "NPU Worker", "services": ["ai-acceleration"]},
    "redis": {"ip": "172.16.168.23", "name": "Redis", "services": ["database"]},
    "ai-stack": {"ip": "172.16.168.24", "name": "AI Stack", "services": ["ai-processing"]},
    "browser": {"ip": "172.16.168.25", "name": "Browser", "services": ["playwright"]}
}
```

**Acceptance Criteria:**
- All 6 hosts connectable via SSH
- Connection pooling reduces latency
- Auto-reconnect on connection loss
- Proper error handling for network issues

**Parallel Track:** Can work alongside Task 1.1

---

## Task 1.3: Agent Command Execution Interface

**Complexity:** COMPLEX
**Agent:** `senior-backend-engineer` + `ai-ml-engineer`
**Depends On:** Tasks 0.4, 1.1, 1.2
**Blocks:** Agent terminal access

**Implementation Tasks:**
- [ ] **1.3.1** Create `AgentTerminalInterface` class
- [ ] **1.3.2** Implement command extraction from agent responses (secure parsing)
- [ ] **1.3.3** Add command validation against security policies
- [ ] **1.3.4** Implement command queuing and execution tracking
- [ ] **1.3.5** Add user interrupt/override mechanism
- [ ] **1.3.6** Create real-time output streaming to agent
- [ ] **1.3.7** Implement command timeout and resource limits
- [ ] **1.3.8** Add execution result parsing for agent context

**Security Integration:**
```python
class AgentTerminalInterface:
    def execute_command(self, command: str, session: TerminalSession):
        # 1. Validate against security policies (Task 0.4)
        risk_level = self.security_layer.assess_command(command)
        if risk_level >= RiskLevel.HIGH:
            return await self.request_user_approval(command, risk_level)

        # 2. Execute with resource limits
        result = await self.executor.run(command, timeout=30, max_output=1MB)

        # 3. Stream output to agent in real-time
        # 4. Log to audit trail
        # 5. Return structured result
```

**Acceptance Criteria:**
- Agent commands execute safely with security checks
- User can interrupt at any time
- Real-time output streaming works
- Audit logging captures all executions

**Parallel Track:** Cannot parallelize - depends on 0.4, 1.1, 1.2

---

## Task 1.4: Enhanced WebSocket Terminal Service

**Complexity:** MODERATE
**Agent:** `senior-backend-engineer`
**Depends On:** Task 1.1
**Blocks:** Frontend terminal integration

**Implementation Tasks:**
- [ ] **1.4.1** Extend existing `/api/terminal/ws/{session_id}` endpoint
- [ ] **1.4.2** Add session initialization on WebSocket connect
- [ ] **1.4.3** Implement bidirectional command/output streaming
- [ ] **1.4.4** Add session state synchronization
- [ ] **1.4.5** Implement user takeover signaling
- [ ] **1.4.6** Add command history retrieval endpoint
- [ ] **1.4.7** Create session list/management endpoints
- [ ] **1.4.8** Add WebSocket connection recovery

**API Endpoints:**
```
WebSocket: /api/terminal/ws/{session_id}
POST /api/terminal/sessions/create
GET /api/terminal/sessions/list
GET /api/terminal/sessions/{id}/history
POST /api/terminal/sessions/{id}/takeover
DELETE /api/terminal/sessions/{id}
GET /api/terminal/hosts (list available hosts)
```

**Acceptance Criteria:**
- WebSocket connection stable and reconnects on failure
- Command history retrievable
- Session takeover works seamlessly
- Multiple concurrent sessions supported

**Parallel Track:** Can work alongside Task 1.2

---

## Task 1.5: Settings Integration for Terminal Configuration

**Complexity:** SIMPLE
**Agent:** `senior-backend-engineer`
**Depends On:** Task 1.2
**Blocks:** User host selection

**Implementation Tasks:**
- [ ] **1.5.1** Add terminal settings schema to backend settings model
- [ ] **1.5.2** Implement default host configuration endpoint
- [ ] **1.5.3** Add per-user terminal preferences storage
- [ ] **1.5.4** Create host selection validation
- [ ] **1.5.5** Implement settings update endpoints
- [ ] **1.5.6** Add settings synchronization with frontend

**Settings Schema:**
```python
class TerminalSettings:
    default_host: str = "main"
    command_timeout: int = 30
    max_history_size: int = 1000
    auto_reconnect: bool = True
    agent_access_enabled: bool = True  # User toggle
    require_approval_threshold: RiskLevel = RiskLevel.MODERATE
```

**Acceptance Criteria:**
- User can select default host in settings
- Settings persist across sessions
- Settings changes apply immediately

**Parallel Track:** Can work alongside Tasks 1.3, 1.4

---

# PHASE 2: FRONTEND INFRASTRUCTURE

**Prerequisites:** Backend foundation (Tasks 1.1-1.5) complete

## Task 2.1: Terminal Component Refactoring

**Complexity:** MODERATE
**Agent:** `frontend-engineer`
**Depends On:** Tasks 1.4, 1.5
**Blocks:** Both terminal types

**Implementation Tasks:**
- [ ] **2.1.1** Refactor `Terminal.vue` to use xterm.js instead of custom rendering
- [ ] **2.1.2** Extract terminal logic into `useTerminal.ts` composable
- [ ] **2.1.3** Implement WebSocket integration using `TerminalService.js`
- [ ] **2.1.4** Add xterm.js FitAddon for responsive sizing
- [ ] **2.1.5** Implement command history with up/down arrow keys
- [ ] **2.1.6** Add copy/paste support
- [ ] **2.1.7** Implement session reconnection UI
- [ ] **2.1.8** Add terminal theme customization

**Component Structure:**
```typescript
// composables/useTerminal.ts
export function useTerminal(sessionId: string, hostId: string) {
  const terminal = ref<Terminal>()
  const ws = ref<WebSocket>()

  const connect = async () => { /* WebSocket setup */ }
  const sendCommand = (cmd: string) => { /* Send to backend */ }
  const disconnect = () => { /* Cleanup */ }
  const takeoverSession = () => { /* User takeover */ }

  return { terminal, connect, sendCommand, disconnect, takeoverSession }
}
```

**Acceptance Criteria:**
- xterm.js rendering working smoothly
- WebSocket connection stable
- Command history functional
- Reconnection seamless

**Parallel Track:** Can work alongside Task 2.2

---

## Task 2.2: Host Selection Settings UI

**Complexity:** SIMPLE
**Agent:** `frontend-engineer`
**Depends On:** Task 1.5
**Blocks:** User host configuration

**Implementation Tasks:**
- [ ] **2.2.1** Add terminal settings section to Settings page
- [ ] **2.2.2** Create host selection dropdown component
- [ ] **2.2.3** Implement settings save/load functionality
- [ ] **2.2.4** Add visual indicators for host connection status
- [ ] **2.2.5** Create host info display (IP, services, status)
- [ ] **2.2.6** Add agent access toggle setting
- [ ] **2.2.7** Implement security threshold configuration
- [ ] **2.2.8** Add settings validation and error handling

**UI Mockup:**
```
Terminal Settings
├── Default Host: [Dropdown: Main, Frontend, NPU, Redis, AI Stack, Browser]
├── Agent Terminal Access: [Toggle: Enabled/Disabled]
├── Command Approval Threshold: [Dropdown: All, Moderate+, High+, Dangerous Only]
└── Connection Settings
    ├── Auto-reconnect: [Toggle]
    └── Command Timeout: [Input: 30s]
```

**Acceptance Criteria:**
- User can select default host
- Settings persist
- Visual feedback on save
- Host status indicators work

**Parallel Track:** Can work alongside Task 2.1

---

## Task 2.3: Terminal State Management

**Complexity:** MODERATE
**Agent:** `frontend-engineer`
**Depends On:** Task 2.1
**Blocks:** Session persistence UI

**Implementation Tasks:**
- [ ] **2.3.1** Create `terminalStore.ts` Pinia store
- [ ] **2.3.2** Implement session state management (active, history, metadata)
- [ ] **2.3.3** Add multi-session support in store
- [ ] **2.3.4** Implement session persistence to localStorage
- [ ] **2.3.5** Add command history state management
- [ ] **2.3.6** Create session lifecycle actions (create, suspend, resume, destroy)
- [ ] **2.3.7** Implement session list/switching UI state
- [ ] **2.3.8** Add connection status tracking

**Store Structure:**
```typescript
// stores/terminalStore.ts
export const useTerminalStore = defineStore('terminal', {
  state: () => ({
    activeSessions: Map<string, TerminalSession>(),
    currentSessionId: string | null,
    connectionStatus: Map<string, ConnectionStatus>(),
    commandHistory: Map<string, string[]>()
  }),
  actions: {
    createSession(hostId: string, type: 'chat' | 'tools'),
    switchSession(sessionId: string),
    closeSession(sessionId: string),
    takeoverSession(sessionId: string)
  }
})
```

**Acceptance Criteria:**
- Multiple sessions manageable
- Session state persists across refreshes
- Session switching smooth
- Connection status accurate

**Parallel Track:** Can work alongside Task 2.2

---

# PHASE 3: CHAT TERMINAL INTEGRATION

**Prerequisites:** Backend (Phase 1) and Frontend Infrastructure (Phase 2) complete

## Task 3.1: Chat Workflow Terminal Integration

**Complexity:** COMPLEX
**Agent:** `senior-backend-engineer` + `ai-ml-engineer`
**Depends On:** Tasks 1.3, 1.4
**Blocks:** Agent terminal execution

**Implementation Tasks:**
- [ ] **3.1.1** Extend `ChatWorkflowManager` to detect terminal commands
- [ ] **3.1.2** Implement agent terminal session association with conversations
- [ ] **3.1.3** Add terminal command execution to chat workflow
- [ ] **3.1.4** Implement output capture and streaming to chat context
- [ ] **3.1.5** Add terminal state to conversation context
- [ ] **3.1.6** Create terminal session lifecycle tied to conversation
- [ ] **3.1.7** Implement user interrupt handling in workflow
- [ ] **3.1.8** Add terminal execution to audit logs

**Workflow Integration:**
```python
# src/chat_workflow_manager.py
class ChatWorkflowManager:
    async def process_agent_response(self, response: str, conversation_id: str):
        # Detect terminal command
        if terminal_command := self.extract_terminal_command(response):
            # Get or create session for this conversation
            session = await self.terminal_manager.get_or_create_session(
                conversation_id=conversation_id,
                host_id=self.settings.default_host
            )

            # Execute with security checks
            result = await self.agent_terminal.execute_command(
                command=terminal_command,
                session=session,
                allow_user_interrupt=True
            )

            # Add to chat context
            return self.format_terminal_result(result)
```

**Acceptance Criteria:**
- Agent commands execute within chat flow
- Terminal output appears in chat
- User can interrupt execution
- Session persists during conversation

**Parallel Track:** Can work alongside Task 3.2

---

## Task 3.2: Chat Terminal UI Component

**Complexity:** MODERATE
**Agent:** `frontend-engineer`
**Depends On:** Tasks 2.1, 2.3
**Blocks:** Chat terminal visibility

**Implementation Tasks:**
- [ ] **3.2.1** Create `ChatTerminal.vue` component (embedded in chat)
- [ ] **3.2.2** Implement collapsible terminal widget in chat interface
- [ ] **3.2.3** Add command output display in chat messages
- [ ] **3.2.4** Implement user takeover button/shortcut
- [ ] **3.2.5** Add terminal session indicator in chat UI
- [ ] **3.2.6** Create command history view in chat
- [ ] **3.2.7** Implement terminal expand/collapse with state persistence
- [ ] **3.2.8** Add visual distinction for agent vs user commands

**UI Layout:**
```
Chat Interface
├── Message Thread
│   ├── User Message
│   ├── Agent Response
│   └── Terminal Output Block
│       ├── Command: $ ls -la
│       ├── Output: (terminal output)
│       └── [Take Over Terminal] button
└── Terminal Widget (collapsible)
    ├── Full xterm.js terminal
    ├── Session: conversation-123 @ main
    └── [Expand/Collapse] [Close Session]
```

**Acceptance Criteria:**
- Terminal embedded in chat seamlessly
- User can take over at any time
- Command output formatted properly
- Expand/collapse state persists

**Parallel Track:** Can work alongside Task 3.1

---

## Task 3.3: User Interrupt & Takeover System

**Complexity:** MODERATE
**Agent:** `frontend-engineer` + `senior-backend-engineer`
**Depends On:** Tasks 3.1, 3.2
**Blocks:** User control feature

**Implementation Tasks:**
- [ ] **3.3.1** Implement interrupt signal mechanism (WebSocket message)
- [ ] **3.3.2** Add backend command execution cancellation
- [ ] **3.3.3** Create takeover UI state transition
- [ ] **3.3.4** Implement session ownership transfer
- [ ] **3.3.5** Add visual feedback for takeover action
- [ ] **3.3.6** Create agent notification on takeover
- [ ] **3.3.7** Implement session resume for agent after user done
- [ ] **3.3.8** Add takeover event logging

**Takeover Flow:**
```
User Action: Click "Take Over Terminal"
  ↓
Frontend: Send takeover message via WebSocket
  ↓
Backend: Cancel running command (if any)
Backend: Transfer session ownership to user
  ↓
Frontend: Expand terminal, enable user input
  ↓
Agent: Notified session unavailable
  ↓
User: Executes commands freely
  ↓
User Action: Click "Return to Agent"
  ↓
Backend: Transfer ownership back
  ↓
Agent: Resume session access
```

**Acceptance Criteria:**
- User takeover instant and reliable
- Running commands cancelled safely
- Clear visual feedback
- Agent properly notified
- Resume works smoothly

**Parallel Track:** Cannot parallelize - depends on 3.1, 3.2

---

## Task 3.4: Command History Persistence

**Complexity:** SIMPLE
**Agent:** `senior-backend-engineer`
**Depends On:** Task 1.1
**Blocks:** History feature

**Implementation Tasks:**
- [ ] **3.4.1** Implement command history storage in TerminalSession
- [ ] **3.4.2** Add history size limits and rotation
- [ ] **3.4.3** Create history retrieval API endpoint
- [ ] **3.4.4** Implement history search functionality
- [ ] **3.4.5** Add history clear functionality
- [ ] **3.4.6** Create history export feature
- [ ] **3.4.7** Implement history compression for long sessions
- [ ] **3.4.8** Add history to session serialization

**History Data Structure:**
```python
class CommandHistoryEntry:
    timestamp: datetime
    command: str
    executor: str  # "agent" or "user"
    exit_code: int
    output_snippet: str  # First 500 chars
    duration_ms: int
```

**Acceptance Criteria:**
- Full command history during session
- History searchable
- History export works
- Performance good with 1000+ commands

**Parallel Track:** Can work alongside Tasks 3.1, 3.2, 3.3

---

# PHASE 4: TOOLS TERMINAL IMPLEMENTATION

**Prerequisites:** Chat Terminal (Phase 3) complete (validates core terminal infrastructure)

## Task 4.1: Tools Terminal Backend Service

**Complexity:** SIMPLE
**Agent:** `senior-backend-engineer`
**Depends On:** Tasks 1.1, 1.2, 1.4
**Blocks:** Tools terminal functionality

**Implementation Tasks:**
- [ ] **4.1.1** Create dedicated session type for tools terminal
- [ ] **4.1.2** Implement user-only access control (no agent access)
- [ ] **4.1.3** Add unrestricted command execution (user has full control)
- [ ] **4.1.4** Create session isolation from chat terminals
- [ ] **4.1.5** Implement persistent tools terminal session option
- [ ] **4.1.6** Add host switching support during session
- [ ] **4.1.7** Create tools terminal specific settings
- [ ] **4.1.8** Add tools terminal to audit logs

**Implementation Notes:**
```python
class ToolsTerminalSession(TerminalSession):
    user_type = "human"  # FIXED - never agent
    access_control = "user_only"
    security_checks = "none"  # User has full control
    session_type = "tools"
```

**Acceptance Criteria:**
- User-only access enforced
- No security restrictions for user
- Independent from chat sessions
- Host switching works
- Session persistence optional

**Parallel Track:** Can work alongside Task 4.2

---

## Task 4.2: Tools Terminal UI Component

**Complexity:** SIMPLE
**Agent:** `frontend-engineer`
**Depends On:** Tasks 2.1, 2.3
**Blocks:** Tools terminal user interface

**Implementation Tasks:**
- [ ] **4.2.1** Create `ToolsTerminal.vue` page component
- [ ] **4.2.2** Add route to Tools section in router
- [ ] **4.2.3** Implement full-page terminal layout
- [ ] **4.2.4** Add host selection dropdown in terminal header
- [ ] **4.2.5** Implement session persistence toggle
- [ ] **4.2.6** Create terminal toolbar (clear, export history, settings)
- [ ] **4.2.7** Add connection status indicator
- [ ] **4.2.8** Implement session reconnection UI

**UI Layout:**
```
Tools Terminal Page
├── Header
│   ├── Host: [Dropdown: Main, Frontend, NPU, Redis, AI Stack, Browser]
│   ├── Status: [Connected/Disconnected indicator]
│   └── Actions: [Clear] [Export History] [Settings]
└── Terminal Area (fullscreen xterm.js)
    └── (User has full bash terminal experience)
```

**Acceptance Criteria:**
- Full-page terminal experience
- Host selection works
- Terminal responsive and performant
- Clear, export, settings functional

**Parallel Track:** Can work alongside Task 4.1

---

## Task 4.3: Host Switching During Session

**Complexity:** MODERATE
**Agent:** `frontend-engineer` + `senior-backend-engineer`
**Depends On:** Tasks 4.1, 4.2
**Blocks:** Multi-host workflow

**Implementation Tasks:**
- [ ] **4.3.1** Implement session suspension on host switch
- [ ] **4.3.2** Create new session on target host
- [ ] **4.3.3** Add session history merge/separation logic
- [ ] **4.3.4** Implement UI confirmation for host switch
- [ ] **4.3.5** Add visual transition animation
- [ ] **4.3.6** Create host switch history tracking
- [ ] **4.3.7** Implement quick host switch shortcuts
- [ ] **4.3.8** Add error handling for connection failures

**Host Switch Flow:**
```
User: Select new host from dropdown
  ↓
Frontend: Confirm host switch (dialog)
  ↓
Backend: Suspend current session
Backend: Create new session on target host
  ↓
Frontend: Disconnect from old WebSocket
Frontend: Connect to new WebSocket
  ↓
Terminal: Clear and show new host prompt
```

**Acceptance Criteria:**
- Host switch smooth and fast
- No data loss during switch
- Clear visual feedback
- Previous session resumable

**Parallel Track:** Cannot parallelize - depends on 4.1, 4.2

---

## Task 4.4: Advanced Tools Terminal Features

**Complexity:** SIMPLE
**Agent:** `frontend-engineer`
**Depends On:** Task 4.2
**Blocks:** Enhanced user experience

**Implementation Tasks:**
- [ ] **4.4.1** Implement terminal tabs for multiple sessions
- [ ] **4.4.2** Add split pane support (horizontal/vertical)
- [ ] **4.4.3** Create command history search UI
- [ ] **4.4.4** Implement custom keybindings
- [ ] **4.4.5** Add file upload/download integration
- [ ] **4.4.6** Create command snippets/bookmarks
- [ ] **4.4.7** Implement terminal session naming
- [ ] **4.4.8** Add collaborative session sharing (optional future)

**Advanced Features:**
```
Tools Terminal Advanced
├── Tabs: [Session 1] [Session 2] [+]
├── Split View: [Horizontal] [Vertical] [Grid]
├── History Search: [Ctrl+R] fuzzy find
├── Snippets: Saved command templates
└── File Transfer: Drag-drop upload/download
```

**Acceptance Criteria:**
- Multiple terminal tabs work
- Split view functional
- History search fast and accurate
- File transfer convenient

**Parallel Track:** Can work alongside Task 4.3

---

# PHASE 5: TESTING & VALIDATION

**Prerequisites:** All implementation phases complete

## Task 5.1: Security Testing

**Complexity:** CRITICAL
**Agent:** `security-auditor` + `testing-engineer`
**Depends On:** All Phase 0, 1, 3, 4 tasks
**Blocks:** Production deployment

**Implementation Tasks:**
- [ ] **5.1.1** Penetration testing for all three fixed CVEs
- [ ] **5.1.2** Agent prompt injection attack testing
- [ ] **5.1.3** Command injection vulnerability scanning
- [ ] **5.1.4** SSH security verification (MITM attempts)
- [ ] **5.1.5** Permission boundary testing (agent vs user)
- [ ] **5.1.6** Audit log completeness verification
- [ ] **5.1.7** Session hijacking attempt testing
- [ ] **5.1.8** Security regression test suite

**Test Cases:**
```python
# tests/security/test_terminal_security.py
def test_prompt_injection_blocked()
def test_mitm_attack_rejected()
def test_agent_permission_boundaries()
def test_dangerous_command_blocked()
def test_user_override_logged()
def test_session_isolation()
def test_host_key_verification()
```

**Acceptance Criteria:**
- All CVEs verified fixed
- Injection attacks fail safely
- Permission model enforced
- Audit logs complete
- No security regressions

**Parallel Track:** Can work alongside Task 5.2

---

## Task 5.2: Functional Testing

**Complexity:** MODERATE
**Agent:** `testing-engineer`
**Depends On:** All Phase 3, 4 tasks
**Blocks:** Feature validation

**Implementation Tasks:**
- [ ] **5.2.1** Chat terminal integration tests
- [ ] **5.2.2** Tools terminal functionality tests
- [ ] **5.2.3** Multi-host connection tests
- [ ] **5.2.4** User takeover/interrupt tests
- [ ] **5.2.5** Command history persistence tests
- [ ] **5.2.6** WebSocket connection/reconnection tests
- [ ] **5.2.7** Session management tests
- [ ] **5.2.8** Settings integration tests

**Test Coverage:**
```python
# tests/functional/test_chat_terminal.py
def test_agent_command_execution()
def test_user_takeover()
def test_session_persistence()
def test_command_history()

# tests/functional/test_tools_terminal.py
def test_user_only_access()
def test_host_switching()
def test_multiple_sessions()
def test_terminal_tabs()
```

**Acceptance Criteria:**
- All features tested and passing
- Edge cases covered
- Error handling verified
- User flows validated

**Parallel Track:** Can work alongside Task 5.1

---

## Task 5.3: Performance Testing

**Complexity:** MODERATE
**Agent:** `performance-engineer` + `testing-engineer`
**Depends On:** Tasks 5.1, 5.2
**Blocks:** Production readiness

**Implementation Tasks:**
- [ ] **5.3.1** WebSocket connection load testing
- [ ] **5.3.2** Multiple simultaneous sessions testing
- [ ] **5.3.3** Command execution latency measurement
- [ ] **5.3.4** Large output streaming performance
- [ ] **5.3.5** Command history with 10k+ entries
- [ ] **5.3.6** Memory leak detection
- [ ] **5.3.7** Connection pool optimization
- [ ] **5.3.8** Frontend rendering performance

**Performance Targets:**
```
WebSocket Connection: < 100ms
Command Execution Start: < 50ms
Output Streaming: Real-time (< 10ms lag)
History Search 10k entries: < 200ms
Memory per Session: < 50MB
Max Concurrent Sessions: 50+
```

**Acceptance Criteria:**
- All performance targets met
- No memory leaks detected
- Scales to 50+ concurrent sessions
- UI remains responsive under load

**Parallel Track:** Can work alongside Task 5.4

---

## Task 5.4: User Acceptance Testing

**Complexity:** SIMPLE
**Agent:** `testing-engineer` + user feedback
**Depends On:** Tasks 5.1, 5.2
**Blocks:** Production approval

**Implementation Tasks:**
- [ ] **5.4.1** Create UAT test plan and scenarios
- [ ] **5.4.2** Conduct user testing with sample workflows
- [ ] **5.4.3** Collect usability feedback
- [ ] **5.4.4** Test accessibility compliance
- [ ] **5.4.5** Verify documentation accuracy
- [ ] **5.4.6** Test error messages clarity
- [ ] **5.4.7** Validate keyboard shortcuts
- [ ] **5.4.8** Create UAT report with findings

**UAT Scenarios:**
```
Scenario 1: Agent executes multi-step task via chat terminal
Scenario 2: User takes over terminal mid-execution
Scenario 3: User works in tools terminal across multiple hosts
Scenario 4: User configures terminal settings and preferences
Scenario 5: Agent and user collaborate on debugging task
```

**Acceptance Criteria:**
- User workflows intuitive
- Error messages helpful
- Documentation complete
- Accessibility requirements met
- User satisfaction high

**Parallel Track:** Can work alongside Task 5.3

---

# PHASE 6: DOCUMENTATION & DEPLOYMENT

**Prerequisites:** All testing phases complete and passing

## Task 6.1: Technical Documentation

**Complexity:** SIMPLE
**Agent:** `documentation-engineer`
**Depends On:** All Phase 5 tasks
**Blocks:** Developer onboarding

**Implementation Tasks:**
- [ ] **6.1.1** Create terminal architecture documentation
- [ ] **6.1.2** Document security fixes and CVE resolutions
- [ ] **6.1.3** Write API documentation for terminal endpoints
- [ ] **6.1.4** Create WebSocket protocol specification
- [ ] **6.1.5** Document session management internals
- [ ] **6.1.6** Write troubleshooting guide
- [ ] **6.1.7** Create code examples and snippets
- [ ] **6.1.8** Update CLAUDE.md with terminal guidelines

**Documentation Files:**
```
docs/features/AGENT_TERMINAL.md
docs/architecture/TERMINAL_ARCHITECTURE.md
docs/security/TERMINAL_SECURITY_FIXES.md
docs/api/TERMINAL_API_REFERENCE.md
docs/troubleshooting/TERMINAL_ISSUES.md
```

**Acceptance Criteria:**
- Architecture fully documented
- API reference complete
- Security fixes explained
- Troubleshooting guide comprehensive

**Parallel Track:** Can work alongside Task 6.2

---

## Task 6.2: User Documentation

**Complexity:** SIMPLE
**Agent:** `documentation-engineer`
**Depends On:** Task 5.4 (UAT feedback)
**Blocks:** User onboarding

**Implementation Tasks:**
- [ ] **6.2.1** Create user guide for chat terminal
- [ ] **6.2.2** Write tools terminal usage guide
- [ ] **6.2.3** Document settings and configuration
- [ ] **6.2.4** Create video tutorials (optional)
- [ ] **6.2.5** Write FAQ document
- [ ] **6.2.6** Create quick start guide
- [ ] **6.2.7** Document keyboard shortcuts
- [ ] **6.2.8** Add in-app help tooltips

**User Documentation:**
```
docs/user-guide/CHAT_TERMINAL.md
docs/user-guide/TOOLS_TERMINAL.md
docs/user-guide/TERMINAL_SETTINGS.md
docs/user-guide/TERMINAL_FAQ.md
```

**Acceptance Criteria:**
- User guides clear and comprehensive
- Screenshots/examples included
- FAQ covers common questions
- Quick start enables fast adoption

**Parallel Track:** Can work alongside Task 6.1

---

## Task 6.3: Deployment Preparation

**Complexity:** MODERATE
**Agent:** `devops-engineer` + `senior-backend-engineer`
**Depends On:** All Phase 5 tasks
**Blocks:** Production deployment

**Implementation Tasks:**
- [ ] **6.3.1** Update Docker configurations for terminal services
- [ ] **6.3.2** Create database migrations for session storage
- [ ] **6.3.3** Update Ansible playbooks for deployment
- [ ] **6.3.4** Create rollback procedures
- [ ] **6.3.5** Add monitoring and alerting for terminal services
- [ ] **6.3.6** Configure production security settings
- [ ] **6.3.7** Create deployment runbook
- [ ] **6.3.8** Setup health checks and readiness probes

**Deployment Checklist:**
```
✓ Database migrations tested
✓ Security configurations verified
✓ SSH keys deployed to all VMs
✓ WebSocket reverse proxy configured
✓ Monitoring dashboards created
✓ Rollback plan tested
✓ Health checks passing
✓ Load balancing configured
```

**Acceptance Criteria:**
- Deployment automated via Ansible
- Rollback plan tested
- Monitoring in place
- Health checks working

**Parallel Track:** Can work alongside Tasks 6.1, 6.2

---

## Task 6.4: Production Deployment

**Complexity:** MODERATE
**Agent:** `devops-engineer` + `project-manager`
**Depends On:** Tasks 6.1, 6.2, 6.3
**Blocks:** Feature activation

**Implementation Tasks:**
- [ ] **6.4.1** Deploy to staging environment
- [ ] **6.4.2** Run full smoke tests on staging
- [ ] **6.4.3** Deploy to production (blue-green deployment)
- [ ] **6.4.4** Enable feature flags gradually
- [ ] **6.4.5** Monitor performance and errors
- [ ] **6.4.6** Conduct post-deployment verification
- [ ] **6.4.7** Enable agent terminal access (phased rollout)
- [ ] **6.4.8** Create post-deployment report

**Deployment Plan:**
```
Phase 1: Deploy backend services (0% traffic)
Phase 2: Deploy frontend changes (0% users)
Phase 3: Enable tools terminal (10% users)
Phase 4: Enable chat terminal (10% users)
Phase 5: Gradual rollout to 50% users
Phase 6: Full rollout to 100% users
Phase 7: Monitor for 72 hours
Phase 8: Mark deployment complete
```

**Acceptance Criteria:**
- Zero-downtime deployment
- No critical errors during rollout
- Performance within targets
- User feedback positive
- Monitoring shows healthy state

**Parallel Track:** Cannot parallelize - sequential deployment

---

# DEPENDENCIES & EXECUTION TRACKS

## Critical Path (Must Complete in Order)

```
Phase 0 (Security) → Phase 1 (Backend) → Phase 2 (Frontend) → Phase 3 (Chat) → Phase 4 (Tools) → Phase 5 (Testing) → Phase 6 (Deploy)
```

## Parallel Execution Tracks

### Track 1: Security Remediation (CRITICAL - BLOCKS EVERYTHING)
```
0.1 Fix SSH MITM
0.2 Fix Prompt Injection    } Can run in parallel
0.3 Fix God Mode Bypass     }
  ↓
0.4 Enhanced Security Layer (depends on 0.1, 0.2, 0.3)
```

### Track 2: Backend Foundation
```
1.1 Session Management
1.2 SSH Connection Manager  } Can run in parallel
1.5 Settings Integration    }
  ↓
1.3 Agent Command Interface (depends on 0.4, 1.1, 1.2)
1.4 WebSocket Service (depends on 1.1)
```

### Track 3: Frontend Infrastructure
```
2.1 Terminal Component
2.2 Settings UI             } Can run in parallel
2.3 Terminal State          }
```

### Track 4: Chat Terminal
```
3.1 Chat Workflow Integration
3.2 Chat Terminal UI         } Can run in parallel
3.4 Command History         }
  ↓
3.3 User Interrupt System (depends on 3.1, 3.2)
```

### Track 5: Tools Terminal
```
4.1 Tools Backend
4.2 Tools UI                } Can run in parallel
  ↓
4.3 Host Switching (depends on 4.1, 4.2)
4.4 Advanced Features (depends on 4.2)
```

### Track 6: Testing
```
5.1 Security Testing
5.2 Functional Testing      } Can run in parallel
5.3 Performance Testing     }
5.4 User Acceptance Testing }
```

### Track 7: Documentation & Deployment
```
6.1 Technical Docs
6.2 User Docs               } Can run in parallel
6.3 Deployment Prep         }
  ↓
6.4 Production Deployment (sequential)
```

---

# RISK ASSESSMENT & MITIGATION

## High-Risk Tasks (Require Extra Attention)

### 🔴 CRITICAL RISK: Task 0.1-0.4 (Security Remediation)
**Risk:** Security vulnerabilities persist if fixes incomplete
**Mitigation:**
- Independent security audit after each fix
- Penetration testing before proceeding to Phase 1
- Code review by multiple security experts
- Automated security regression tests

### 🔴 CRITICAL RISK: Task 1.3 (Agent Command Interface)
**Risk:** Agent could execute dangerous commands
**Mitigation:**
- Comprehensive command validation testing
- User override mechanism always available
- Command whitelist/blacklist enforcement
- Real-time security monitoring
- Kill switch for agent terminal access

### 🟡 MODERATE RISK: Task 3.3 (User Interrupt System)
**Risk:** Interrupt mechanism fails, user loses control
**Mitigation:**
- Redundant interrupt signals (WebSocket + API endpoint)
- Frontend timeout if interrupt not acknowledged
- Force-kill capability as fallback
- Extensive testing of interrupt edge cases

### 🟡 MODERATE RISK: Task 4.3 (Host Switching)
**Risk:** Session data loss or corruption during switch
**Mitigation:**
- Atomic session state transitions
- Session backup before switch
- Rollback mechanism on failure
- Comprehensive error handling

### 🟢 LOW RISK: Most UI/UX tasks (2.x, 4.2, 4.4)
**Risk:** User experience issues
**Mitigation:**
- User testing throughout development
- Iterative design improvements
- Clear error messages and feedback

---

# AGENT ASSIGNMENTS & SPECIALIZATIONS

## Phase 0: Security Remediation
- **Primary:** `security-auditor` (all tasks)
- **Support:** `senior-backend-engineer` (implementation), `systems-architect` (design)

## Phase 1: Backend Foundation
- **Primary:** `senior-backend-engineer` (1.1, 1.3, 1.4, 1.5)
- **Primary:** `devops-engineer` (1.2)
- **Support:** `database-engineer` (session storage), `performance-engineer` (optimization)

## Phase 2: Frontend Infrastructure
- **Primary:** `frontend-engineer` (all tasks)
- **Support:** `ui-ux-designer` (design review)

## Phase 3: Chat Terminal Integration
- **Primary:** `senior-backend-engineer` + `ai-ml-engineer` (3.1)
- **Primary:** `frontend-engineer` (3.2, 3.3)
- **Support:** `testing-engineer` (validation)

## Phase 4: Tools Terminal
- **Primary:** `senior-backend-engineer` (4.1)
- **Primary:** `frontend-engineer` (4.2, 4.3, 4.4)

## Phase 5: Testing
- **Primary:** `testing-engineer` (all tasks)
- **Primary:** `security-auditor` (5.1)
- **Primary:** `performance-engineer` (5.3)

## Phase 6: Documentation & Deployment
- **Primary:** `documentation-engineer` (6.1, 6.2)
- **Primary:** `devops-engineer` (6.3, 6.4)
- **Support:** `project-manager` (coordination)

---

# ESTIMATED TIMELINE

## Phase 0: Security Remediation
**Duration:** 2-3 weeks
**Tasks:** 0.1-0.4 (8 tasks total, 4 parallel tracks)
**Critical Path:** Task 0.4 blocks all subsequent work

## Phase 1: Backend Foundation
**Duration:** 2 weeks
**Tasks:** 1.1-1.5 (5 tasks, 3 parallel tracks)
**Critical Path:** Task 1.3 (most complex)

## Phase 2: Frontend Infrastructure
**Duration:** 1 week
**Tasks:** 2.1-2.3 (3 tasks, all can run in parallel)

## Phase 3: Chat Terminal Integration
**Duration:** 1.5 weeks
**Tasks:** 3.1-3.4 (4 tasks, 2 parallel tracks)
**Critical Path:** Task 3.3 (depends on 3.1, 3.2)

## Phase 4: Tools Terminal Implementation
**Duration:** 1 week
**Tasks:** 4.1-4.4 (4 tasks, 2 parallel tracks)

## Phase 5: Testing & Validation
**Duration:** 1.5 weeks
**Tasks:** 5.1-5.4 (4 tasks, 4 parallel tracks)
**Critical Path:** Task 5.1 (security testing)

## Phase 6: Documentation & Deployment
**Duration:** 1 week
**Tasks:** 6.1-6.4 (4 tasks, 3 parallel + sequential deploy)

## **TOTAL ESTIMATED DURATION: 10-12 weeks**

---

# SUCCESS METRICS

## Security Metrics
- ✅ All 3 CVEs fully resolved and verified
- ✅ Zero security vulnerabilities in penetration testing
- ✅ 100% audit log coverage for agent commands
- ✅ User override mechanism 100% reliable

## Performance Metrics
- ✅ WebSocket connection < 100ms
- ✅ Command execution start < 50ms
- ✅ Output streaming real-time (< 10ms lag)
- ✅ Support 50+ concurrent sessions
- ✅ Memory per session < 50MB

## Functionality Metrics
- ✅ Agent can execute commands in chat terminal
- ✅ User can interrupt agent at any moment
- ✅ Command history persists during session
- ✅ Multi-host support working (all 6 hosts)
- ✅ Tools terminal provides full bash experience

## User Experience Metrics
- ✅ User satisfaction > 8/10
- ✅ Terminal responsive and performant
- ✅ Error messages clear and helpful
- ✅ Documentation comprehensive
- ✅ Onboarding < 5 minutes

---

# BLOCKERS & DEPENDENCIES SUMMARY

## Phase 0 BLOCKS:
- **Everything** - Agent terminal access impossible without security fixes

## Phase 1 BLOCKS:
- Phase 2 (frontend needs backend APIs)
- Phase 3 (chat terminal needs backend)
- Phase 4 (tools terminal needs backend)

## Phase 2 BLOCKS:
- Phase 3 (chat terminal needs UI components)
- Phase 4 (tools terminal needs UI components)

## Phase 3 BLOCKS:
- Phase 5 (testing needs chat terminal complete)
- Phase 6 (deployment needs features complete)

## Phase 4 BLOCKS:
- Phase 5 (testing needs tools terminal complete)
- Phase 6 (deployment needs features complete)

## Phase 5 BLOCKS:
- Phase 6 (cannot deploy without testing)

---

# NEXT STEPS

1. **Store this plan in Memory MCP** as implementation roadmap
2. **Begin Phase 0 (Security Remediation)** immediately
3. **Launch parallel security agents** for Tasks 0.1, 0.2, 0.3
4. **Weekly progress reviews** to track against timeline
5. **Adjust plan based on findings** during implementation

---

**Plan Created By:** Manager AI (following Research → Plan → Implement workflow)
**Research Foundation:** Memory MCP entities (Terminal Architecture, Security Analysis, Requirements)
**Plan Status:** Ready for execution pending user approval
**Estimated Completion:** 10-12 weeks from start
