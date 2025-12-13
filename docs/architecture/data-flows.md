# AutoBot Data Flow Diagrams

**Last Updated**: 2025-12-13
**Related Issue**: [#251](https://github.com/mrveiss/AutoBot-AI/issues/251)

This document provides visual representations of data flows through the AutoBot distributed system.

---

## 1. Overall System Data Flow

```mermaid
flowchart TB
    subgraph User["User Layer"]
        Browser[Web Browser]
    end

    subgraph Frontend["VM1: Frontend (172.16.168.21)"]
        Vue[Vue 3 Application]
        WS_Client[WebSocket Client]
    end

    subgraph Backend["Main: Backend (172.16.168.20)"]
        API[FastAPI Server]
        WS_Server[WebSocket Server]
        Orchestrator[Enhanced Orchestrator]
        LLM_Interface[LLM Interface]
        KB_Manager[Knowledge Base Manager]
    end

    subgraph Redis["VM3: Redis (172.16.168.23)"]
        DB0[(DB0: Main)]
        DB1[(DB1: Knowledge)]
        DB2[(DB2: Prompts)]
        DB3[(DB3: Analytics)]
    end

    subgraph AI["VM4: AI Stack (172.16.168.24)"]
        Ollama[Ollama Server]
        Models[LLM Models]
    end

    subgraph NPU["VM2: NPU Worker (172.16.168.22)"]
        NPU_API[NPU API]
        OpenVINO[OpenVINO Runtime]
    end

    Browser --> Vue
    Vue --> API
    Vue <--> WS_Client
    WS_Client <--> WS_Server

    API --> Orchestrator
    Orchestrator --> LLM_Interface
    Orchestrator --> KB_Manager

    LLM_Interface --> Ollama
    LLM_Interface --> NPU_API
    Ollama --> Models
    NPU_API --> OpenVINO

    KB_Manager --> DB1
    API --> DB0
    API --> DB3
    LLM_Interface --> DB2
```

---

## 2. Chat Message Flow

This diagram shows how a user message flows through the system to generate a response.

```mermaid
sequenceDiagram
    participant User
    participant Frontend as VM1: Frontend
    participant API as Main: Backend API
    participant Session as Session Manager
    participant Redis as VM3: Redis
    participant KB as Knowledge Base
    participant LLM as LLM Interface
    participant Ollama as VM4: Ollama
    participant NPU as VM2: NPU

    User->>Frontend: Send message
    Frontend->>API: POST /api/chat/message

    API->>Session: Get/Create session
    Session->>Redis: Load session state
    Redis-->>Session: Session data

    API->>KB: Search relevant context
    KB->>Redis: Vector similarity search
    Redis-->>KB: Relevant documents
    KB-->>API: Context documents

    API->>LLM: Generate response

    alt Local Model Available
        LLM->>NPU: Generate embedding
        NPU-->>LLM: Embedding vector
        LLM->>Ollama: Chat completion
        Ollama-->>LLM: Token stream
    else Cloud Fallback
        LLM->>OpenAI: Chat completion
        OpenAI-->>LLM: Token stream
    end

    LLM-->>API: Response tokens
    API->>Session: Save message
    Session->>Redis: Persist session
    API-->>Frontend: Streaming response
    Frontend-->>User: Display response
```

---

## 3. Knowledge Base Ingestion Flow

This diagram shows how documents are processed and indexed into the knowledge base.

```mermaid
flowchart LR
    subgraph Input["Document Sources"]
        Files[Local Files]
        URLs[Web URLs]
        Upload[User Uploads]
    end

    subgraph Processing["Backend Processing"]
        Parser[Document Parser]
        Chunker[Text Chunker]
        Embedder[Embedding Generator]
    end

    subgraph Embedding["Embedding Layer"]
        NPU_Embed[NPU Worker]
        Cloud_Embed[Cloud API]
    end

    subgraph Storage["Redis Storage"]
        Vectors[(DB1: Vectors)]
        Metadata[(DB1: Metadata)]
        Facts[(DB1: Facts)]
    end

    Files --> Parser
    URLs --> Parser
    Upload --> Parser

    Parser --> Chunker
    Chunker --> Embedder

    Embedder --> NPU_Embed
    Embedder -.-> Cloud_Embed

    NPU_Embed --> Vectors
    Cloud_Embed --> Vectors
    Embedder --> Metadata
    Parser --> Facts
```

---

## 4. Workflow Execution Flow

This diagram shows how automated workflows are executed.

```mermaid
flowchart TB
    subgraph Trigger["Workflow Triggers"]
        Chat[Chat Command]
        Schedule[Scheduled Task]
        API_Call[API Request]
        Event[System Event]
    end

    subgraph Orchestrator["Enhanced Orchestrator"]
        Router[Workflow Router]
        Validator[Input Validator]
        Executor[Step Executor]
        Monitor[Progress Monitor]
    end

    subgraph Agents["Agent Pool"]
        KB_Agent[KB Librarian]
        Task_Agent[Task Agent]
        RAG_Agent[RAG Agent]
        Browser_Agent[Browser Agent]
    end

    subgraph External["External Services"]
        Browser_VM[VM5: Playwright]
        AI_VM[VM4: Ollama]
        Redis_VM[VM3: Redis]
    end

    subgraph Output["Results"]
        Response[User Response]
        Storage[Data Storage]
        Logs[Audit Logs]
    end

    Chat --> Router
    Schedule --> Router
    API_Call --> Router
    Event --> Router

    Router --> Validator
    Validator --> Executor
    Executor --> Monitor

    Executor --> KB_Agent
    Executor --> Task_Agent
    Executor --> RAG_Agent
    Executor --> Browser_Agent

    KB_Agent --> Redis_VM
    Task_Agent --> AI_VM
    Browser_Agent --> Browser_VM

    Monitor --> Response
    Monitor --> Storage
    Monitor --> Logs
```

---

## 5. Authentication Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend as VM1: Frontend
    participant API as Main: Backend
    participant Auth as Auth Service
    participant Redis as VM3: Redis
    participant Session as Session Store

    User->>Frontend: Login request
    Frontend->>API: POST /api/auth/login
    API->>Auth: Validate credentials

    alt Valid Credentials
        Auth->>Session: Create session
        Session->>Redis: Store session token
        Redis-->>Session: Token stored
        Session-->>Auth: Session ID
        Auth-->>API: JWT + Session ID
        API-->>Frontend: Auth response
        Frontend->>Frontend: Store token
        Frontend-->>User: Login success
    else Invalid Credentials
        Auth-->>API: Auth failed
        API-->>Frontend: 401 Unauthorized
        Frontend-->>User: Login failed
    end
```

---

## 6. Browser Automation Flow

```mermaid
flowchart LR
    subgraph Backend["Main: Backend"]
        API[API Request]
        Browser_Client[Browser Client]
    end

    subgraph Browser_VM["VM5: Browser (172.16.168.25)"]
        Playwright[Playwright Server]
        Chromium[Chromium Browser]
        Context[Browser Context]
    end

    subgraph Actions["Browser Actions"]
        Navigate[Navigate]
        Click[Click]
        Type[Type]
        Screenshot[Screenshot]
        Extract[Extract Data]
    end

    subgraph Results["Results"]
        Data[Extracted Data]
        Images[Screenshots]
        Status[Status/Errors]
    end

    API --> Browser_Client
    Browser_Client --> Playwright
    Playwright --> Chromium
    Chromium --> Context

    Context --> Navigate
    Context --> Click
    Context --> Type
    Context --> Screenshot
    Context --> Extract

    Navigate --> Status
    Click --> Status
    Type --> Status
    Screenshot --> Images
    Extract --> Data

    Data --> Browser_Client
    Images --> Browser_Client
    Status --> Browser_Client
    Browser_Client --> API
```

---

## 7. VNC Desktop Stream Flow

```mermaid
flowchart LR
    subgraph Main["Main Machine (172.16.168.20)"]
        Xvfb[Xvfb Display]
        x11vnc[x11vnc Server]
        noVNC[noVNC WebSocket]
        Desktop[Desktop Apps]
    end

    subgraph Network["Network"]
        WS[WebSocket :6080]
    end

    subgraph Client["User Browser"]
        VNC_Client[noVNC Client]
        Canvas[HTML5 Canvas]
    end

    Desktop --> Xvfb
    Xvfb --> x11vnc
    x11vnc --> noVNC
    noVNC --> WS
    WS --> VNC_Client
    VNC_Client --> Canvas

    Canvas --> VNC_Client
    VNC_Client --> WS
    WS --> noVNC
    noVNC --> x11vnc
    x11vnc --> Xvfb
```

---

## 8. Redis Database Layout

```mermaid
flowchart TB
    subgraph Redis["VM3: Redis Stack (172.16.168.23:6379)"]
        subgraph DB0["Database 0: Main"]
            Sessions[Sessions]
            Cache[API Cache]
            Queues[Task Queues]
        end

        subgraph DB1["Database 1: Knowledge"]
            Vectors[Vector Embeddings]
            Documents[Document Metadata]
            Facts[Stored Facts]
        end

        subgraph DB2["Database 2: Prompts"]
            Templates[Prompt Templates]
            System[System Prompts]
            Custom[Custom Prompts]
        end

        subgraph DB3["Database 3: Analytics"]
            Metrics[Performance Metrics]
            Usage[Usage Statistics]
            Errors[Error Logs]
        end
    end

    subgraph Clients["Backend Services"]
        API_Client[API Service]
        KB_Client[Knowledge Service]
        LLM_Client[LLM Service]
        Analytics[Analytics Service]
    end

    API_Client --> DB0
    KB_Client --> DB1
    LLM_Client --> DB2
    Analytics --> DB3
```

---

## Data Flow Summary

| Flow | Source | Destination | Protocol | Purpose |
|------|--------|-------------|----------|---------|
| Chat Messages | Frontend | Backend | HTTP/WS | User interaction |
| LLM Inference | Backend | Ollama/NPU | HTTP | AI responses |
| Knowledge Search | Backend | Redis | Redis Protocol | RAG retrieval |
| Browser Automation | Backend | Playwright | HTTP | Web automation |
| Desktop Stream | VNC Server | Browser | WebSocket | Remote desktop |
| Session State | Backend | Redis | Redis Protocol | User sessions |

---

## Related Documentation

- [ADR-001: Distributed VM Architecture](../adr/001-distributed-vm-architecture.md)
- [ADR-002: Redis Database Separation](../adr/002-redis-database-separation.md)
- [ADR-004: Chat Workflow Architecture](../adr/004-chat-workflow-architecture.md)
- [Architecture Overview](README.md)

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
