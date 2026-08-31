# AutoBot System Diagrams

> **Freshness:** current — 2026-08-30. Structural description of the system as built; classified and location-reviewed under #15192, not re-verified claim-by-claim.

A reference for AutoBot's architecture, data flows, and deployment topologies using Mermaid diagrams.

---

## System Overview

```mermaid
graph TB
    User["User (Browser)"]
    Frontend["Frontend\n(Vue.js + nginx)"]
    Backend["Backend\n(FastAPI)"]

    Redis["Redis\n(Cache / Queue)"]
    PostgreSQL["PostgreSQL\n(Relational Data)"]
    ChromaDB["ChromaDB\n(Vector Embeddings)"]
    Ollama["Ollama\n(Local LLM)"]
    Ansible["Ansible\n(Fleet Ops)"]
    Browser["Browser Worker\n(Chromium)"]

    User -->|HTTP / WebSocket| Frontend
    Frontend -->|REST API| Backend

    Backend --> Redis
    Backend --> PostgreSQL
    Backend -->|Vector Search| ChromaDB
    Backend -->|Inference| Ollama
    Backend -->|Playbooks| Ansible
    Backend -->|Automation| Browser
```

---

## Chat Request Data Flow

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant BE as Backend
    participant DB as ChromaDB
    participant LLM as Ollama

    U->>FE: Send message
    FE->>BE: POST /api/v1/chat/message (WebSocket)
    BE->>DB: Vector search (if KB attached)
    DB-->>BE: Relevant document chunks
    BE->>LLM: Prompt + context + history
    LLM-->>BE: Stream response tokens
    BE-->>FE: Stream tokens via WebSocket
    FE-->>U: Render streaming response
    BE->>BE: Save message to PostgreSQL
```

---

## Knowledge Base Indexing Flow

```mermaid
sequenceDiagram
    participant U as User
    participant BE as Backend
    participant PG as PostgreSQL
    participant CB as ChromaDB

    U->>BE: Upload document
    BE->>PG: Store file metadata
    BE->>BE: Chunk document
    BE->>BE: Generate embeddings (Ollama embed model)
    BE->>CB: Store embedding vectors
    CB-->>BE: Indexed
    BE-->>U: Ready for search
```

---

## Fleet Operation Flow

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant BE as Backend
    participant AN as Ansible
    participant N as Fleet Nodes

    U->>FE: "Deploy v2 to all prod servers"
    FE->>BE: Chat message
    BE->>BE: Parse intent, select playbook
    BE-->>FE: Show plan + confirm prompt
    U->>FE: Confirm
    FE->>BE: Execute confirmed
    BE->>AN: Run playbook on target nodes
    AN->>N: SSH + execute tasks
    N-->>AN: stdout / stderr
    AN-->>BE: Job output stream
    BE-->>FE: Real-time progress
    BE->>BE: Write audit log to PostgreSQL
```

---

## Deployment Topology (Single Node)

```mermaid
graph TB
    Internet["Internet"]
    nginx["nginx\n:80 / :443"]

    subgraph Docker["Docker Network (internal)"]
        FE["Frontend\n(Vue.js)"]
        BE["Backend\n(FastAPI :8000)"]
        PG["PostgreSQL\n(:5432)"]
        RD["Redis\n(:6379)"]
        CB["ChromaDB\n(:8001)"]
        OL["Ollama\n(:11434)"]
    end

    Internet --> nginx
    nginx --> FE
    nginx -->|/api/*| BE
    BE --> PG
    BE --> RD
    BE --> CB
    BE --> OL
```

---

## Deployment Topology (Multi-Node HA)

```mermaid
graph TB
    Internet["Internet"]
    LB["Load Balancer\n(nginx / HAProxy)"]

    subgraph "Backend Cluster"
        BE1["Backend\nInstance 1"]
        BE2["Backend\nInstance 2"]
    end

    subgraph "Data Layer"
        PG_P["PostgreSQL\nPrimary"]
        PG_R["PostgreSQL\nRead Replica"]
        RD["Redis\nSentinel"]
        CB["ChromaDB\nDedicated"]
    end

    subgraph "AI Layer"
        OL["Ollama\n(GPU Node)"]
    end

    subgraph "Fleet"
        N1["Node 1"]
        N2["Node 2"]
        N3["Node N"]
    end

    Internet --> LB
    LB --> BE1
    LB --> BE2
    BE1 --> PG_P
    BE2 --> PG_P
    BE1 --> PG_R
    BE2 --> PG_R
    BE1 --> RD
    BE2 --> RD
    BE1 --> CB
    BE2 --> CB
    BE1 --> OL
    BE2 --> OL
    BE1 -->|Ansible| N1
    BE1 -->|Ansible| N2
    BE1 -->|Ansible| N3
```

---

## Component Responsibilities

| Component | Technology | Responsibility |
|-----------|-----------|----------------|
| Frontend | Vue.js 3, nginx | UI, TLS termination, static assets |
| Backend | FastAPI, Python | Business logic, auth, orchestration |
| PostgreSQL | PostgreSQL 15+ | Users, sessions, fleet inventory, audit logs |
| Redis | Redis 7+ | Task queue, caching, session state |
| ChromaDB | ChromaDB | Vector embeddings for RAG search |
| Ollama | Ollama | Local LLM inference and embeddings |
| Ansible | Ansible | Fleet playbook execution |
| Browser Worker | Chromium | Browser automation, screenshots, scraping |
