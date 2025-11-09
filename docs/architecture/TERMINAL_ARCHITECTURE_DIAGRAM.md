# Terminal System Architecture Diagram

**AutoBot Terminal Integration - Complete Overview**

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AUTOBOT TERMINAL SYSTEM                           │
│                                                                             │
│  Two Terminal Types:                                                        │
│  1. Tools Terminal  - Standalone system terminal                          │
│  2. Chat Terminal   - AI chat-integrated terminal with approval workflow   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Tools Terminal (Standalone)

### **Architecture Flow**

```
┌─────────────────┐
│  Vue Frontend   │
│ ToolsTerminal.  │
│     vue         │
└────────┬────────┘
         │
         │ 1. Create Session
         │ POST /api/terminal/sessions
         │
         ▼
┌─────────────────────────────────────┐
│  backend/api/terminal.py            │
│  ConsolidatedTerminalManager        │
│                                     │
│  • Creates session ID               │
│  • Stores config                    │
│  • Returns WebSocket URL            │
└────────────┬────────────────────────┘
             │
             │ 2. WebSocket Connect
             │ /api/terminal/ws/{session_id}
             │
             ▼
┌─────────────────────────────────────┐
│  backend/api/terminal.py            │
│  ConsolidatedTerminalWebSocket      │
│                                     │
│  • Accepts WebSocket                │
│  • Initializes PTY                  │
│  • Starts output reader             │
└────────────┬────────────────────────┘
             │
             │ 3. Initialize PTY
             │
             ▼
┌─────────────────────────────────────┐
│  backend/services/simple_pty.py     │
│  SimplePTY + SimplePTYManager       │
│                                     │
│  • Creates master/slave FDs         │
│  • Spawns /bin/bash process         │
│  • Starts reader/writer threads     │
│  • Input/output queues              │
└─────────────────────────────────────┘

         PTY (Pseudo-Terminal)

         /bin/bash ────┐
         (PID: xxxxx)  │
                       │
         ┌─────────────┴──────────────┐
         │   stdin/stdout/stderr      │
         │   connected to slave FD    │
         └────────────────────────────┘
```

### **Data Flow - Tools Terminal**

```
User Input Flow:
┌────────┐  keypress  ┌──────────┐  WebSocket  ┌──────────┐  write()  ┌──────────┐
│ Browser│ ────────> │ Vue/XTerm│ ─────────> │ terminal │ ────────> │SimplePTY │
│        │           │          │  {text: }  │  .py     │           │ .py      │
└────────┘           └──────────┘            └──────────┘           └──────────┘
                                                                           │
                                                                           │ os.write(master_fd)
                                                                           ▼
                                                                     ┌──────────┐
                                                                     │/bin/bash │
                                                                     │  shell   │
                                                                     └──────────┘

Output Flow:
┌────────┐  display  ┌──────────┐  WebSocket  ┌──────────┐  async   ┌──────────┐
│ Browser│ <──────── │ Vue/XTerm│ <───────── │ terminal │ <──────  │SimplePTY │
│        │           │          │  {output:} │  .py     │   task   │ .py      │
└────────┘           └──────────┘            └──────────┘          └──────────┘
                                                                          ▲
                                                                          │ os.read(master_fd)
                                                                          │ + output_queue
                                                                    ┌──────────┐
                                                                    │/bin/bash │
                                                                    │  shell   │
                                                                    └──────────┘
```

---

## Chat Terminal (AI-Integrated)

### **Architecture Flow**

```
┌──────────────────┐
│  Vue Frontend    │
│ ChatTerminal.vue │
│                  │
│ Props:           │
│  chatSessionId   │ ← Links to active chat conversation
└────────┬─────────┘
         │
         │ 1. Create Agent Session
         │ POST /api/agent-terminal/sessions
         │ {
         │   agent_id: "chat_agent_{chatSessionId}",
         │   agent_role: "chat_agent",
         │   conversation_id: chatSessionId,  ← KEY LINK
         │   host: "main"
         │ }
         ▼
┌─────────────────────────────────────────────┐
│  backend/api/agent_terminal.py              │
│  create_agent_terminal_session()            │
│                                             │
│  • Validates agent_role                     │
│  • Creates AgentTerminalSession             │
│  • Links to conversation_id                 │
│  • Returns session_id + pty_session_id      │
└────────────┬────────────────────────────────┘
             │
             │ Delegates to
             ▼
┌─────────────────────────────────────────────┐
│  backend/services/                          │
│    agent_terminal_service.py                │
│  AgentTerminalService                       │
│                                             │
│  • create_session()                         │
│  • Initializes ChatHistoryManager           │
│  • Initializes CommandApprovalManager       │
│  • Creates PTY session via terminal.py      │
│  • Sets state: AGENT_CONTROL                │
└────────────┬────────────────────────────────┘
             │
             │ 2. Frontend connects WebSocket
             │ /api/terminal/ws/{pty_session_id}
             │                    └─ Use PTY session ID!
             ▼
┌─────────────────────────────────────────────┐
│  backend/api/terminal.py                    │
│  ConsolidatedTerminalWebSocket              │
│  (SAME as Tools Terminal)                   │
│                                             │
│  • Accepts WebSocket                        │
│  • Initializes SimplePTY                    │
│  • Links to conversation_id if provided     │
│  • Starts output buffering for chat         │
└────────────┬────────────────────────────────┘
             │
             │ 3. Initialize PTY (shared)
             ▼
┌─────────────────────────────────────────────┐
│  backend/services/simple_pty.py             │
│  (SAME PTY as Tools Terminal)               │
└─────────────────────────────────────────────┘

         PTY + /bin/bash (shared infrastructure)
```

### **Key Difference: Chat Integration**

```
┌─────────────────────────────────────────────────────────────────┐
│                     CHAT TERMINAL ADDITIONS                     │
└─────────────────────────────────────────────────────────────────┘

AgentTerminalSession (in-memory state):
┌────────────────────────────────────┐
│ session_id: "agent-abc123"         │
│ agent_id: "chat_agent_xyz"         │
│ conversation_id: "xyz"  ← Chat link│
│ pty_session_id: "pty-456"          │
│ state: AGENT_CONTROL / USER_CONTROL│
│ pending_approval: {...}             │
│ command_history: [...]             │
└────────────────────────────────────┘

ConsolidatedTerminalWebSocket (enhanced):
┌────────────────────────────────────┐
│ conversation_id: "xyz"             │
│ chat_history_manager: instance     │ ← Saves output to chat
│ terminal_logger: instance          │ ← Logs commands
│ _output_buffer: ""                 │ ← Buffers for batching
└────────────────────────────────────┘
```

### **Command Execution Flow - Chat Terminal**

```
Agent Requests Command:
┌────────┐  execute  ┌──────────┐  POST     ┌──────────┐  assess  ┌──────────┐
│ Agent  │ ────────> │agent_    │ /execute  │agent_    │ risk ──> │Secure    │
│ (LLM)  │  "ls -la" │terminal  │           │terminal_ │          │Command   │
│        │           │.py       │           │service   │          │Executor  │
└────────┘           └──────────┘           └──────────┘          └──────────┘
                                                   │                      │
                                                   │                      ▼
                                                   │            ┌──────────────────┐
                                                   │            │ Risk = MODERATE  │
                                                   │            │ Reason: File ops │
                                                   │            └──────────────────┘
                                                   │
                                                   ▼
                                          ┌─────────────────┐
                                          │ IF HIGH/MODERATE│
                                          │  → User Approval│
                                          │ ELSE            │
                                          │  → Execute      │
                                          └─────────────────┘

User Approval Required:
┌────────┐  approve  ┌──────────┐  update   ┌──────────┐  execute  ┌──────────┐
│ User   │ ────────> │agent_    │  state ─> │session   │ ────────> │SimplePTY │
│        │ POST      │terminal  │           │state:    │  write()  │          │
│        │ /approve  │.py       │           │APPROVED  │           │          │
└────────┘           └──────────┘           └──────────┘           └──────────┘
                                                                          │
                                                                          ▼
                                                                    ┌──────────┐
                                                                    │/bin/bash │
                                                                    └──────────┘

Output Saved to Chat:
┌──────────┐  output  ┌──────────┐  buffer   ┌──────────┐  save    ┌──────────┐
│/bin/bash │ ──────> │terminal  │ ────────> │_output_  │ ──────> │ChatHistory│
│          │         │WebSocket │           │buffer    │  batch  │Manager   │
└──────────┘         └──────────┘           └──────────┘         └──────────┘
                                                   │                      │
                                                   │ Every 500ms OR       │
                                                   │ Buffer > 1000 chars  │
                                                   │                      ▼
                                                   └──────────────> add_message(
                                                                       sender="terminal",
                                                                       text=buffer,
                                                                       session_id=xyz
                                                                    )
```

---

## State Machine - Chat Terminal Control

```
┌─────────────────────────────────────────────────────────────────┐
│                 Agent Terminal State Machine                    │
└─────────────────────────────────────────────────────────────────┘

Initial State: AGENT_CONTROL

┌───────────────┐
│ AGENT_CONTROL │  ← Agent can execute commands (with approval)
└───────┬───────┘
        │
        │ User clicks "Take Control"
        │ POST /interrupt
        │
        ▼
┌───────────────┐
│USER_INTERRUPT │  ← User requested control
└───────┬───────┘
        │
        │ Agent pauses
        │ Terminal ownership transfers
        │
        ▼
┌───────────────┐
│ USER_CONTROL  │  ← User has full control (no approval needed)
└───────┬───────┘
        │
        │ User clicks "Release Control"
        │ POST /release
        │
        ▼
┌───────────────┐
│ AGENT_RESUME  │  ← Agent resumes control
└───────┬───────┘
        │
        │ Transition complete
        │
        ▼
┌───────────────┐
│ AGENT_CONTROL │  ← Back to agent control
└───────────────┘

Command Execution Permission:
┌───────────────┬─────────────────┬──────────────┐
│ State         │ Agent Commands  │ User Commands│
├───────────────┼─────────────────┼──────────────┤
│AGENT_CONTROL  │ ✅ With approval│ ❌ Blocked   │
│USER_INTERRUPT │ ❌ Blocked      │ ⏸️ Pending   │
│USER_CONTROL   │ ❌ Blocked      │ ✅ Direct    │
│AGENT_RESUME   │ ⏸️ Transition   │ ❌ Blocked   │
└───────────────┴─────────────────┴──────────────┘
```

---

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND LAYER                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌────────────────────┐              ┌────────────────────┐        │
│  │  ToolsTerminal.vue │              │  ChatTerminal.vue  │        │
│  │                    │              │                    │        │
│  │  • Multi-tab       │              │  • Chat-linked     │        │
│  │  • Host switching  │              │  • Agent control   │        │
│  │  • Standalone      │              │  • User takeover   │        │
│  └──────────┬─────────┘              └──────────┬─────────┘        │
│             │                                   │                  │
│             └───────────────┬───────────────────┘                  │
│                             │                                      │
│                  ┌──────────▼──────────┐                           │
│                  │  BaseXTerminal.vue  │                           │
│                  │  (xterm.js wrapper) │                           │
│                  └──────────┬──────────┘                           │
│                             │                                      │
│                  ┌──────────▼──────────┐                           │
│                  │ TerminalService.js  │                           │
│                  │  (WebSocket client) │                           │
│                  └─────────────────────┘                           │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ WebSocket
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                         BACKEND LAYER                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  REST API Layer:                                                    │
│  ┌────────────────────┐              ┌────────────────────┐        │
│  │  terminal.py       │              │agent_terminal.py   │        │
│  │                    │              │                    │        │
│  │  • POST /sessions  │              │  • POST /sessions  │        │
│  │  • WS /ws/{id}     │◄─────────────┤  • POST /execute   │        │
│  │  • GET /sessions   │  Shares WS   │  • POST /approve   │        │
│  └──────────┬─────────┘              └──────────┬─────────┘        │
│             │                                   │                  │
│             │                        ┌──────────▼─────────┐        │
│             │                        │agent_terminal_     │        │
│             │                        │  service.py        │        │
│             │                        │                    │        │
│             │                        │ • create_session() │        │
│             │                        │ • execute_command()│        │
│             │                        │ • approve_command()│        │
│             │                        │ • interrupt_agent()│        │
│             │                        └────────────────────┘        │
│             │                                                      │
│  WebSocket Handler:                                                │
│  ┌────────────────────────────────────────────┐                   │
│  │  ConsolidatedTerminalWebSocket             │                   │
│  │                                            │                   │
│  │  • Accepts WebSocket connection            │                   │
│  │  • Links to conversation_id (if Chat)      │                   │
│  │  • Initializes SimplePTY                   │                   │
│  │  • Buffers output for chat integration     │                   │
│  │  • Sends to ChatHistoryManager             │                   │
│  └──────────────────┬─────────────────────────┘                   │
│                     │                                              │
│  PTY Layer:         │                                              │
│  ┌──────────────────▼──────────┐                                  │
│  │  simple_pty.py              │                                  │
│  │  SimplePTY + Manager        │                                  │
│  │                             │                                  │
│  │  • pty.openpty()            │                                  │
│  │  • subprocess.Popen(bash)   │                                  │
│  │  • Reader/writer threads    │                                  │
│  │  • Input/output queues      │                                  │
│  │  • Terminal echo config     │                                  │
│  └─────────────────────────────┘                                  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                         SYSTEM LAYER                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────┐                       │
│  │  /bin/bash (shell process)              │                       │
│  │                                         │                       │
│  │  • PID: xxxxx                           │                       │
│  │  • Connected to PTY slave FD            │                       │
│  │  • Executes commands                    │                       │
│  │  • Produces output                      │                       │
│  └─────────────────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Integration Points - Chat Terminal

```
┌──────────────────────────────────────────────────────────────────────┐
│             CHAT TERMINAL INTEGRATION ECOSYSTEM                      │
└──────────────────────────────────────────────────────────────────────┘

┌────────────────┐
│ ChatInterface  │  User sends message "run ls -la"
│ .vue           │
└────────┬───────┘
         │
         │ LLM interprets intent
         ▼
┌────────────────┐
│ Agent (LLM)    │  Decides: Need to run command
└────────┬───────┘
         │
         │ POST /api/agent-terminal/sessions/{id}/execute
         │ { command: "ls -la", description: "List files" }
         ▼
┌────────────────────────┐
│ agent_terminal_service │  1. Assess risk
│                        │  2. Check if approval needed
│                        │  3. IF YES → Set pending_approval
│                        │     ELSE → Execute directly
└────────┬───────────────┘
         │
         ├─────────────┐
         │             │
         ▼             ▼
   LOW RISK      HIGH/MODERATE RISK
         │             │
         │             ▼
         │       ┌────────────────┐
         │       │ Wait for user  │
         │       │ POST /approve  │
         │       └────────┬───────┘
         │                │
         └────────┬───────┘
                  │
                  ▼
         ┌────────────────┐
         │ Execute via    │
         │ SimplePTY      │
         └────────┬───────┘
                  │
                  ▼
         ┌────────────────┐
         │ /bin/bash      │
         │ runs command   │
         └────────┬───────┘
                  │
                  │ Output
                  ▼
         ┌────────────────┐
         │ WebSocket      │
         │ sends to       │
         │ ChatTerminal   │
         └────────┬───────┘
                  │
                  ├──────────────┐
                  │              │
                  ▼              ▼
         ┌────────────┐  ┌────────────┐
         │ Display in │  │ Save to    │
         │ terminal   │  │ ChatHistory│
         │ UI         │  │ Manager    │
         └────────────┘  └────────────┘
                                │
                                ▼
                         Chat history shows:
                         [TERMINAL] $ ls -la
                         [OUTPUT] (files...)
```

---

## Security & Validation Layers

```
┌──────────────────────────────────────────────────────────────────────┐
│                    COMMAND SECURITY PIPELINE                         │
└──────────────────────────────────────────────────────────────────────┘

Command Submitted (Agent or User):
         │
         ▼
┌────────────────────┐
│ SecureCommand      │  1. Risk Assessment
│ Executor           │
│                    │  Patterns checked:
│ assess_command_    │  • Destructive ops (rm -rf)
│   risk()           │  • Disk ops (dd, mkfs)
│                    │  • Network changes
│                    │  • System modifications
│                    │  • Package installs
│                    │  • User/permission changes
└────────┬───────────┘
         │
         ▼
   ┌─────────────────────────┐
   │  Risk Level Determined  │
   └─────────────────────────┘
              │
    ┌─────────┼─────────┬─────────┐
    │         │         │         │
    ▼         ▼         ▼         ▼
┌──────┐ ┌────────┐ ┌──────┐ ┌───────────┐
│ SAFE │ │MODERATE│ │ HIGH │ │ FORBIDDEN │
└──┬───┘ └───┬────┘ └──┬───┘ └─────┬─────┘
   │         │          │           │
   │         │          │           ▼
   │         │          │      ❌ BLOCKED
   │         │          │       (reject)
   │         │          │
   │         ▼          ▼
   │    ⚠️ APPROVAL REQUIRED
   │     (user must approve)
   │         │
   ▼         │
 ✅ EXECUTE  │
  (directly) │
         ◄───┘
            │
            ▼
    ┌────────────────┐
    │ Log & Audit    │
    │                │
    │ • Command text │
    │ • Risk level   │
    │ • Timestamp    │
    │ • User/Agent   │
    │ • Result       │
    └────────────────┘
```

---

## File Structure

```
AutoBot/
├── autobot-vue/src/components/
│   ├── ToolsTerminal.vue           ← Tools Terminal UI
│   ├── ChatTerminal.vue            ← Chat Terminal UI
│   └── terminal/
│       ├── BaseXTerminal.vue       ← xterm.js wrapper
│       ├── TerminalInput.vue
│       ├── TerminalOutput.vue
│       ├── TerminalHeader.vue
│       └── HostSelector.vue
│
├── autobot-vue/src/services/
│   └── TerminalService.js          ← WebSocket client
│
├── backend/api/
│   ├── terminal.py                 ← Tools Terminal API (REST + WebSocket)
│   └── agent_terminal.py           ← Chat Terminal API (REST)
│
├── backend/services/
│   ├── simple_pty.py               ← PTY implementation (ACTIVE)
│   ├── agent_terminal_service.py   ← Chat Terminal business logic
│   ├── command_approval_manager.py ← Approval workflow
│   └── archive/                    ← Archived implementations
│       ├── base_terminal.py.unused
│       ├── pty_terminal.py.unused
│       └── remote_terminal.py.feature
│
└── docs/architecture/
    ├── TERMINAL_ARCHITECTURE_DIAGRAM.md  ← This file
    └── TERMINAL_CONSOLIDATION_ANALYSIS.md
```

---

## Summary

**Shared Infrastructure**:
- Both terminals use **same PTY layer** (`simple_pty.py`)
- Both terminals use **same WebSocket transport** (`terminal.py`)

**Key Differences**:
- **Tools Terminal**: Direct session creation, no approval, no chat link
- **Chat Terminal**: Agent session → approval workflow → chat integration

**Integration Points**:
- Chat Terminal saves all output to `ChatHistoryManager`
- Command execution logged to chat history
- Agent/user control state tracked in `AgentTerminalSession`
- Approval workflow via `CommandApprovalManager` + `SecureCommandExecutor`

---
