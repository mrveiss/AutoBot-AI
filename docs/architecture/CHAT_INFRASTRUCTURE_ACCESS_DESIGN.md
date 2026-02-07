# Chat Infrastructure Access Architecture

> **GitHub Issue**: [#715](https://github.com/mrveiss/AutoBot-AI/issues/715)
> **Status**: Planning
> **Author**: mrveiss
> **Created**: 2026-01-13

---

## Executive Summary

Refactor the Chat Terminal and VNC tabs to use user-configured external hosts via secrets management instead of providing direct access to AutoBot infrastructure. This change improves security through isolation and transforms user-added hosts into a queryable infrastructure knowledge base.

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [Desired State](#2-desired-state)
3. [Security Architecture](#3-security-architecture)
4. [Technical Design](#4-technical-design)
5. [Knowledge Base Integration](#5-knowledge-base-integration)
6. [Implementation Plan](#6-implementation-plan)
7. [File Changes](#7-file-changes)
8. [API Specifications](#8-api-specifications)
9. [Frontend Components](#9-frontend-components)
10. [Migration & Rollout](#10-migration--rollout)

---

## 1. Current State Analysis

### 1.1 Current Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CURRENT STATE                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Tools Terminal ─────────► Local PTY (AutoBot host)             │
│                                                                  │
│  Chat Terminal ──────────► Local PTY (AutoBot host)             │
│                            └─ SECURITY RISK: Direct access      │
│                                                                  │
│  Chat VNC ───────────────► Main Machine VNC (172.16.168.20)     │
│                            └─ Checked on startup                 │
│                            └─ SECURITY RISK: Exposes desktop    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Current Problems

| Problem | Impact |
|---------|--------|
| Chat terminal accesses AutoBot host | Users can modify AutoBot internals |
| Chat VNC exposes AutoBot desktop | Security and privacy risk |
| VNC checked on startup | Adds complexity, delays startup |
| No user infrastructure management | Users can't connect to their own machines |
| No infrastructure knowledge | AI doesn't know user's environment |

### 1.3 Current File Locations

**Backend:**
- VNC Manager: `autobot-user-backend/api/vnc_manager.py`
- Terminal: `autobot-user-backend/api/terminal.py`, `autobot-user-backend/api/terminal_handlers.py`
- Secrets: `backend/services/secrets_service.py`
- Terminal Secrets: `backend/services/terminal_secrets_service.py`

**Frontend:**
- Chat Interface: `autobot-user-frontend/src/components/chat/ChatInterface.vue`
- Chat Tab Content: `autobot-user-frontend/src/components/chat/ChatTabContent.vue`
- Chat Terminal: `autobot-user-frontend/src/components/ChatTerminal.vue`
- NoVNC Viewer: `autobot-user-frontend/src/components/NoVNCViewer.vue`

---

## 2. Desired State

### 2.1 New Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AUTOBOT PLATFORM                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────┐          ┌─────────────────────────────┐  │
│  │   TOOLS SECTION     │          │      CHAT SECTION           │  │
│  │   (Admin Only)      │          │      (All Users)            │  │
│  ├─────────────────────┤          ├─────────────────────────────┤  │
│  │ Terminal            │          │ Terminal Tab                │  │
│  │ • Local PTY         │          │ • Host Selector dropdown    │  │
│  │ • AutoBot host      │          │ • SSH to external hosts     │  │
│  │ • Dev/Infra mgmt    │          │ • NO AutoBot access         │  │
│  │ • UNCHANGED         │          ├─────────────────────────────┤  │
│  └─────────────────────┘          │ VNC Tab                     │  │
│                                   │ • Host Selector dropdown    │  │
│                                   │ • VNC to external hosts     │  │
│                                   │ • NO AutoBot access         │  │
│                                   └─────────────────────────────┘  │
│                                              │                      │
│                                              ▼                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    SECRETS MANAGEMENT                         │  │
│  │  infrastructure_host secrets with SSH/VNC credentials         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                              │                      │
│                                              ▼                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    KNOWLEDGE BASE                             │  │
│  │  • Host metadata (purpose, OS, tags)                          │  │
│  │  • Commands available per host (relations, no duplicates)     │  │
│  │  • Man pages stored once, linked to multiple hosts            │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Access Matrix

| Interface | Access To | Who Uses It | Connection Type |
|-----------|-----------|-------------|-----------------|
| **Tools Terminal** | AutoBot host (local PTY) | Developer/Admin | Local PTY |
| **Chat Terminal** | User's external hosts ONLY | End users | SSH |
| **Chat VNC** | User's external hosts ONLY | End users | VNC protocol |

### 2.3 Key Changes Summary

| Area | Before | After |
|------|--------|-------|
| Chat Terminal | Local PTY to AutoBot | SSH to user-selected external host |
| Chat VNC | Hardcoded main machine VNC | VNC to user-selected external host |
| VNC Startup | Checked on app initialization | On-demand when host selected |
| Tools Terminal | Local PTY | **UNCHANGED** |
| Host Config | Hardcoded IPs | User adds via secrets UI |
| Default Access | Full AutoBot access | NO access until hosts configured |

---

## 3. Security Architecture

### 3.1 Isolation by Default

**Critical Security Change**: Chat Terminal/VNC no longer provides ANY access to AutoBot infrastructure.

```
┌─────────────────────────────────────────────────────────────────┐
│                    SECURITY BOUNDARY                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  AUTOBOT INFRASTRUCTURE          │    USER INFRASTRUCTURE       │
│  (Protected)                     │    (User-controlled)         │
│                                  │                              │
│  ┌──────────────────┐           │    ┌──────────────────┐      │
│  │ AutoBot Host     │           │    │ web-server       │      │
│  │ • File system    │     ✗     │    │ 192.168.1.10    │      │
│  │ • Configuration  │◄────┼─────┼───►│ SSH + VNC       │      │
│  │ • Secrets DB     │     │     │    └──────────────────┘      │
│  └──────────────────┘     │     │                              │
│                           │     │    ┌──────────────────┐      │
│  ┌──────────────────┐     │     │    │ db-server        │      │
│  │ Redis Stack      │     ✗     │    │ 192.168.1.20    │      │
│  │ 172.16.168.23    │◄────┼─────┼───►│ SSH only        │      │
│  └──────────────────┘     │     │    └──────────────────┘      │
│                           │     │                              │
│          NO ACCESS ───────┘     │    User connects via         │
│          from Chat              │    Chat Terminal/VNC         │
│                                 │                              │
└─────────────────────────────────┴──────────────────────────────┘
```

### 3.2 Security Benefits

| Benefit | Description |
|---------|-------------|
| **Isolation** | Chat interface cannot access AutoBot's file system or internals |
| **Explicit Trust** | User must intentionally add hosts they control |
| **No Default Access** | Empty host list = no terminal/VNC capability |
| **Credential Separation** | User's SSH keys are for their infrastructure only |
| **Audit Trail** | All connections logged with host context and user attribution |
| **Attack Surface Reduction** | Removes direct shell access to AutoBot from chat |

### 3.3 UX for New Users (No Hosts Configured)

```
┌─────────────────────────────────────────────────────────────────┐
│  Terminal Tab                                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│     ┌─────────────────────────────────────────────────────┐     │
│     │                                                     │     │
│     │         No SSH hosts configured                     │     │
│     │                                                     │     │
│     │    Add your infrastructure hosts in:                │     │
│     │    Settings → Secrets → Add Infrastructure Host     │     │
│     │                                                     │     │
│     │    [+ Add Host]                                     │     │
│     │                                                     │     │
│     └─────────────────────────────────────────────────────┘     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Technical Design

### 4.1 New Secret Type: `infrastructure_host`

```python
{
    "id": "uuid-here",
    "name": "production-web-server",
    "description": "Production web server running nginx and Node.js API",
    "secret_type": "infrastructure_host",
    "scope": "general",  # or "chat" for chat-specific hosts
    "chat_id": null,     # populated if scope is "chat"

    "metadata": {
        # Connection info (non-sensitive, stored in metadata)
        "host": "192.168.1.100",
        "ssh_port": 22,
        "vnc_port": 5901,
        "capabilities": ["ssh", "vnc"],  # or ["ssh"] only

        # Knowledge base info
        "description": "Production web server running nginx",
        "tags": ["production", "web", "nginx", "nodejs"],
        "os": "Ubuntu 22.04 LTS",
        "purpose": "Hosts main website and REST API",

        # Extraction tracking
        "commands_extracted": false,
        "last_connected": null,
        "connection_count": 0
    },

    "encrypted_value": {
        # Sensitive credentials (encrypted with Fernet)
        "auth_type": "ssh_key",  # or "password"
        "ssh_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n...",
        "ssh_key_passphrase": "optional-passphrase",
        # OR
        "ssh_password": "password-if-not-using-key",
        "vnc_password": "vnc-password-if-vnc-capable",
        "username": "deploy"
    },

    "created_at": "2026-01-13T00:00:00Z",
    "updated_at": "2026-01-13T00:00:00Z",
    "is_active": true
}
```

### 4.2 Data Flow: Adding a Host

```
┌──────────────────────────────────────────────────────────────────┐
│                    ADD HOST WORKFLOW                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. User fills form in Settings → Secrets → Add Infrastructure   │
│     │                                                             │
│     ▼                                                             │
│  2. Frontend validates and sends to backend                       │
│     POST /api/secrets                                             │
│     {                                                             │
│       "name": "web-server",                                       │
│       "secret_type": "infrastructure_host",                       │
│       "value": { credentials },                                   │
│       "metadata": { host info }                                   │
│     }                                                             │
│     │                                                             │
│     ▼                                                             │
│  3. Backend encrypts credentials, stores in secrets DB            │
│     │                                                             │
│     ▼                                                             │
│  4. Backend extracts metadata → Knowledge Base                    │
│     Entity: "web-server" (type: infrastructure_host)              │
│     Observations: [host, os, purpose, tags...]                    │
│     │                                                             │
│     ▼                                                             │
│  5. Host appears in Chat Terminal/VNC host selector               │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 4.3 Data Flow: Connecting to Host

```
┌──────────────────────────────────────────────────────────────────┐
│                    SSH CONNECTION WORKFLOW                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. User selects host from dropdown in Chat Terminal              │
│     │                                                             │
│     ▼                                                             │
│  2. Frontend requests connection                                  │
│     POST /api/terminal/sessions                                   │
│     {                                                             │
│       "connection_type": "ssh",                                   │
│       "host_secret_id": "uuid-of-infrastructure-host"             │
│     }                                                             │
│     │                                                             │
│     ▼                                                             │
│  3. Backend retrieves and decrypts credentials from secrets       │
│     │                                                             │
│     ▼                                                             │
│  4. Backend establishes SSH connection via paramiko/asyncssh      │
│     │                                                             │
│     ▼                                                             │
│  5. WebSocket bridge created for terminal I/O                     │
│     │                                                             │
│     ▼                                                             │
│  6. If first connection: trigger command extraction (background)  │
│     │                                                             │
│     ▼                                                             │
│  7. User interacts with remote shell via WebSocket                │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 4.4 Data Flow: VNC Connection

```
┌──────────────────────────────────────────────────────────────────┐
│                    VNC CONNECTION WORKFLOW                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. User selects VNC-capable host from dropdown in Chat VNC       │
│     │                                                             │
│     ▼                                                             │
│  2. Frontend retrieves host connection info                       │
│     GET /api/infrastructure/hosts/{id}                            │
│     │                                                             │
│     ▼                                                             │
│  3. Frontend constructs noVNC URL with host:vnc_port              │
│     │                                                             │
│     ▼                                                             │
│  4. If VNC password required:                                     │
│     - Backend provides password via secure endpoint               │
│     - noVNC handles authentication                                │
│     │                                                             │
│     ▼                                                             │
│  5. noVNC iframe connects directly to remote VNC server           │
│     (via websockify proxy if needed)                              │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. Knowledge Base Integration

### 5.1 Infrastructure Knowledge Graph

```
┌──────────────────────────────────────────────────────────────────┐
│                    KNOWLEDGE GRAPH STRUCTURE                      │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────┐                    ┌─────────────────┐      │
│  │ HOST ENTITY     │                    │ COMMAND ENTITY  │      │
│  │ ────────────────│                    │ ────────────────│      │
│  │ name: web-srv   │                    │ name: nginx     │      │
│  │ type: infra_host│◄──AVAILABLE_ON────►│ type: linux_cmd │      │
│  │ host: 192...    │                    │ man_page: "..." │      │
│  │ os: Ubuntu      │                    │ synopsis: "..." │      │
│  │ purpose: "..."  │                    └─────────────────┘      │
│  │ tags: [...]     │                            ▲                 │
│  └─────────────────┘                            │                 │
│          ▲                               AVAILABLE_ON             │
│          │                                      │                 │
│   AVAILABLE_ON                          ┌─────────────────┐      │
│          │                              │ HOST ENTITY     │      │
│          ▼                              │ ────────────────│      │
│  ┌─────────────────┐                    │ name: db-srv    │      │
│  │ COMMAND ENTITY  │                    │ type: infra_host│      │
│  │ ────────────────│                    │ host: 192...    │      │
│  │ name: docker    │◄──AVAILABLE_ON────►│ os: Ubuntu      │      │
│  │ type: linux_cmd │                    └─────────────────┘      │
│  │ man_page: "..." │                                              │
│  └─────────────────┘                                              │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 Command Knowledge Extraction

**Triggered on first SSH connection to any Linux host.**

```
┌──────────────────────────────────────────────────────────────────┐
│                    COMMAND EXTRACTION WORKFLOW                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  SSH Connect Success                                              │
│     │                                                             │
│     ▼                                                             │
│  Check: host.metadata.commands_extracted == true?                 │
│     │                                                             │
│     ├─ YES → Skip extraction                                      │
│     │                                                             │
│     └─ NO → Start background extraction task:                     │
│              │                                                    │
│              ▼                                                    │
│           1. Get all commands on host                             │
│              $ compgen -c | sort -u                               │
│              $ ls /usr/bin /usr/sbin /bin /sbin 2>/dev/null       │
│              │                                                    │
│              ▼                                                    │
│           2. For each command:                                    │
│              │                                                    │
│              ├─ Check: command entity exists in KB?               │
│              │     │                                              │
│              │     ├─ YES → Just add relation:                    │
│              │     │        command → AVAILABLE_ON → host         │
│              │     │                                              │
│              │     └─ NO → Create entity + extract man page:      │
│              │              $ man -P cat <command> 2>/dev/null    │
│              │              Store: name, synopsis, man_page       │
│              │              Add relation to host                  │
│              │                                                    │
│              ▼                                                    │
│           3. Update host metadata:                                │
│              commands_extracted = true                            │
│              extraction_date = now()                              │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 5.3 Knowledge Query Examples

| Query | How It's Answered |
|-------|-------------------|
| "Which hosts have nginx?" | Find all AVAILABLE_ON relations pointing to nginx entity |
| "Can I run docker on web-server?" | Check if docker → AVAILABLE_ON → web-server relation exists |
| "What's the man page for systemctl?" | Retrieve man_page observation from systemctl entity |
| "Which server runs the database?" | Search host entities for purpose/tags containing "database" |
| "Show me all production servers" | Filter hosts by tags containing "production" |

### 5.4 Deduplication Strategy

**Commands are stored ONCE globally, with relations to hosts.**

```python
# CORRECT: One entity, multiple relations
Entity: "ifconfig"
Type: "linux_command"
Observations:
  - synopsis: "configure a network interface"
  - man_page: "<full content>"
  - category: "network"

Relations:
  - ifconfig → AVAILABLE_ON → web-server
  - ifconfig → AVAILABLE_ON → db-server
  - ifconfig → AVAILABLE_ON → app-server

# Host-specific info stored on host entity
Entity: "web-server"
Observations:
  - ifconfig_version: "net-tools 2.10-alpha"
  - ifconfig_path: "/sbin/ifconfig"
```

```python
# WRONG: Duplicate entities (DO NOT DO THIS)
Entity: "ifconfig-web-server"  # ❌
Entity: "ifconfig-db-server"   # ❌
Entity: "ifconfig-app-server"  # ❌
```

---

## 6. Implementation Plan

### Phase 1: Backend Infrastructure Host Support

**Duration**: Backend changes for host management

**Tasks**:
- [ ] Add `infrastructure_host` secret type to `secrets_service.py`
- [ ] Create validation schema for infrastructure_host metadata
- [ ] Add `GET /api/infrastructure/hosts` endpoint
- [ ] Add `GET /api/infrastructure/hosts/{id}` endpoint
- [ ] Add `POST /api/infrastructure/hosts/{id}/test-connection` endpoint
- [ ] Update secrets API to handle infrastructure_host type

**Files**:
- `backend/services/secrets_service.py`
- `autobot-user-backend/api/infrastructure_hosts.py` (new)
- `backend/routers/__init__.py` (register new router)

### Phase 2: SSH Connection Support

**Duration**: Terminal SSH connection capability

**Tasks**:
- [ ] Add SSH connection support to terminal service
- [ ] Integrate with secrets service for credential retrieval
- [ ] Create SSH session manager (paramiko/asyncssh)
- [ ] Bridge SSH I/O to WebSocket
- [ ] Handle SSH authentication (key + password)
- [ ] Add connection error handling and retry logic

**Files**:
- `backend/services/ssh_connection_service.py` (new)
- `autobot-user-backend/api/terminal.py` (modify)
- `autobot-user-backend/api/terminal_handlers.py` (modify)

### Phase 3: Command Knowledge Extraction

**Duration**: Background command extraction service

**Tasks**:
- [ ] Create command extraction service
- [ ] Implement background task runner for extraction
- [ ] Add command entity creation with deduplication
- [ ] Add host relation management
- [ ] Extract and parse man pages
- [ ] Handle extraction failures gracefully
- [ ] Add extraction status tracking

**Files**:
- `backend/services/command_extraction_service.py` (new)
- `backend/services/infrastructure_knowledge_service.py` (new)

### Phase 4: Frontend Host Selector

**Duration**: Host selection UI components

**Tasks**:
- [ ] Create `HostSelector.vue` component
- [ ] Add host selector to Chat Terminal tab
- [ ] Add host selector to Chat VNC tab (VNC-capable only)
- [ ] Show "no hosts" state with add host CTA
- [ ] Add host quick-add modal from chat
- [ ] Update terminal service for SSH connections

**Files**:
- `autobot-user-frontend/src/components/HostSelector.vue` (new)
- `autobot-user-frontend/src/components/chat/ChatTabContent.vue`
- `autobot-user-frontend/src/components/ChatTerminal.vue`
- `autobot-user-frontend/src/services/TerminalService.js`

### Phase 5: VNC Dynamic Host Support

**Duration**: Dynamic VNC connections

**Tasks**:
- [ ] Update NoVNCViewer for dynamic host/port
- [ ] Add VNC password handling
- [ ] Create VNC proxy endpoint for external hosts
- [ ] Filter host selector to VNC-capable hosts only

**Files**:
- `autobot-user-frontend/src/components/NoVNCViewer.vue`
- `autobot-user-backend/api/vnc_manager.py`

### Phase 6: Cleanup & Removal

**Duration**: Remove old code and dependencies

**Tasks**:
- [ ] Remove VNC startup check from `ChatInterface.vue`
- [ ] Remove hardcoded infrastructure references
- [ ] Remove local PTY option from chat terminal
- [ ] Update health checks (remove VNC requirement)
- [ ] Clean up unused VNC endpoints

**Files**:
- `autobot-user-frontend/src/components/chat/ChatInterface.vue`
- `backend/initialization/lifespan.py`
- `backend/initialization/health_endpoints.py`

### Phase 7: Secrets UI Enhancement

**Duration**: UI for adding infrastructure hosts

**Tasks**:
- [ ] Add "Infrastructure Host" option to secrets type dropdown
- [ ] Create infrastructure host form with all fields
- [ ] Add connection test button
- [ ] Add capability checkboxes (SSH, VNC)
- [ ] Add tag input for knowledge categorization

**Files**:
- `autobot-user-frontend/src/components/settings/SecretsManager.vue`
- `autobot-user-frontend/src/components/settings/InfrastructureHostForm.vue` (new)

---

## 7. File Changes

### 7.1 Backend Files

| File | Action | Description |
|------|--------|-------------|
| `backend/services/secrets_service.py` | Modify | Add infrastructure_host type handling |
| `autobot-user-backend/api/infrastructure_hosts.py` | Create | Host listing and management endpoints |
| `backend/services/ssh_connection_service.py` | Create | SSH connection management |
| `backend/services/command_extraction_service.py` | Create | Command knowledge extraction |
| `backend/services/infrastructure_knowledge_service.py` | Create | KB integration for hosts |
| `autobot-user-backend/api/terminal.py` | Modify | Add SSH connection type support |
| `autobot-user-backend/api/terminal_handlers.py` | Modify | SSH WebSocket bridging |
| `autobot-user-backend/api/vnc_manager.py` | Modify | Dynamic VNC host support |
| `backend/initialization/lifespan.py` | Modify | Remove VNC startup dependency |
| `backend/initialization/health_endpoints.py` | Modify | Remove VNC from health checks |

### 7.2 Frontend Files

| File | Action | Description |
|------|--------|-------------|
| `autobot-user-frontend/src/components/HostSelector.vue` | Create | Reusable host dropdown |
| `autobot-user-frontend/src/components/chat/ChatTabContent.vue` | Modify | Add host selector to tabs |
| `autobot-user-frontend/src/components/chat/ChatInterface.vue` | Modify | Remove VNC startup check |
| `autobot-user-frontend/src/components/ChatTerminal.vue` | Modify | SSH connection support |
| `autobot-user-frontend/src/components/NoVNCViewer.vue` | Modify | Dynamic host/port |
| `autobot-user-frontend/src/services/TerminalService.js` | Modify | SSH session creation |
| `autobot-user-frontend/src/components/settings/SecretsManager.vue` | Modify | Infrastructure host type |
| `autobot-user-frontend/src/components/settings/InfrastructureHostForm.vue` | Create | Host configuration form |

---

## 8. API Specifications

### 8.1 Infrastructure Hosts API

#### List Hosts
```
GET /api/infrastructure/hosts
Query params:
  - capability: "ssh" | "vnc" | null (filter by capability)
  - scope: "general" | "chat" | null
  - chat_id: string (if scope is "chat")

Response:
{
  "hosts": [
    {
      "id": "uuid",
      "name": "web-server",
      "host": "192.168.1.100",
      "ssh_port": 22,
      "vnc_port": 5901,
      "capabilities": ["ssh", "vnc"],
      "description": "Production web server",
      "tags": ["production", "web"],
      "os": "Ubuntu 22.04",
      "last_connected": "2026-01-13T00:00:00Z",
      "commands_extracted": true
    }
  ]
}
```

#### Get Host Details
```
GET /api/infrastructure/hosts/{id}

Response:
{
  "id": "uuid",
  "name": "web-server",
  "host": "192.168.1.100",
  ...full host details...
}
```

#### Test Connection
```
POST /api/infrastructure/hosts/{id}/test-connection

Response:
{
  "success": true,
  "ssh_available": true,
  "vnc_available": true,
  "ssh_error": null,
  "vnc_error": null,
  "latency_ms": 45
}
```

### 8.2 Terminal Session API (Modified)

#### Create SSH Session
```
POST /api/terminal/sessions
{
  "connection_type": "ssh",           // NEW: "local" | "ssh"
  "host_secret_id": "uuid",           // NEW: required if ssh
  "chat_id": "optional-chat-id",
  "setup_ssh_keys": false
}

Response:
{
  "session_id": "uuid",
  "connection_type": "ssh",
  "host": "web-server",
  "status": "connected",
  "websocket_url": "/api/terminal/ws/uuid"
}
```

### 8.3 VNC Proxy API (Modified)

#### Get VNC Connection Info
```
GET /api/vnc/connection/{host_secret_id}

Response:
{
  "host": "192.168.1.100",
  "port": 5901,
  "requires_password": true,
  "websocket_proxy_url": "/api/vnc/proxy/{host_secret_id}"
}
```

---

## 9. Frontend Components

### 9.1 HostSelector Component

```vue
<!-- HostSelector.vue -->
<template>
  <div class="host-selector">
    <select v-model="selectedHostId" @change="onHostSelect">
      <option value="" disabled>Select a host...</option>
      <option
        v-for="host in filteredHosts"
        :key="host.id"
        :value="host.id"
      >
        {{ host.name }} ({{ host.host }})
      </option>
    </select>

    <button @click="showAddHost" class="add-host-btn">
      + Add Host
    </button>
  </div>

  <!-- Empty state -->
  <div v-if="hosts.length === 0" class="no-hosts">
    <p>No {{ capabilityLabel }} hosts configured</p>
    <button @click="showAddHost">+ Add Infrastructure Host</button>
  </div>
</template>

<script setup>
const props = defineProps({
  capability: {
    type: String,
    default: null,  // 'ssh', 'vnc', or null for all
    validator: (v) => [null, 'ssh', 'vnc'].includes(v)
  },
  modelValue: String  // selected host ID
})

const emit = defineEmits(['update:modelValue', 'host-selected'])
</script>
```

### 9.2 Chat Tab Content Integration

```vue
<!-- ChatTabContent.vue (modified) -->
<template>
  <!-- Terminal Tab -->
  <div v-show="activeTab === 'terminal'" class="tab-content">
    <HostSelector
      v-model="selectedTerminalHost"
      capability="ssh"
      @host-selected="onTerminalHostSelected"
    />

    <ChatTerminal
      v-if="selectedTerminalHost"
      :host-id="selectedTerminalHost"
      :session-id="sessionId"
    />
  </div>

  <!-- VNC Tab -->
  <div v-show="activeTab === 'novnc'" class="tab-content">
    <HostSelector
      v-model="selectedVncHost"
      capability="vnc"
      @host-selected="onVncHostSelected"
    />

    <NoVNCViewer
      v-if="selectedVncHost"
      :host-id="selectedVncHost"
    />
  </div>
</template>
```

---

## 10. Migration & Rollout

### 10.1 Migration Steps

1. **Deploy backend changes first** (non-breaking)
2. **Add infrastructure_host secret type** (additive)
3. **Deploy frontend with feature flag** (hidden by default)
4. **Enable feature for testing**
5. **Remove old VNC startup code**
6. **Full rollout**

### 10.2 Backwards Compatibility

During migration period:
- Old terminal behavior available via feature flag
- VNC startup check can be re-enabled if needed
- No data migration required (new secret type)

### 10.3 Rollback Plan

If issues arise:
1. Disable feature flag
2. Re-enable VNC startup check
3. Old terminal behavior restored
4. Infrastructure hosts remain in secrets (unused)

---

## Appendix A: Dependencies

### Backend
- `paramiko` or `asyncssh` - SSH connections
- `websockets` - WebSocket bridging (existing)
- `cryptography` - Fernet encryption (existing)

### Frontend
- No new dependencies required

---

## Appendix B: Related Issues

- GitHub Issue: [#715](https://github.com/mrveiss/AutoBot-AI/issues/715)

---

## Appendix C: Acceptance Criteria

- [ ] User can add SSH/VNC hosts via secrets management
- [ ] Chat terminal tab shows host selector dropdown
- [ ] Chat VNC tab shows host selector (VNC-capable hosts only)
- [ ] Terminal connects to selected host via SSH
- [ ] VNC connects to selected host
- [ ] Host metadata stored as infrastructure knowledge
- [ ] Commands extracted on first SSH connection
- [ ] Commands stored once with relations (no duplicates)
- [ ] AI can query infrastructure knowledge
- [ ] VNC startup check removed from app initialization
- [ ] Tools terminal unchanged (direct main machine access)
- [ ] No default access to AutoBot from chat (security)
