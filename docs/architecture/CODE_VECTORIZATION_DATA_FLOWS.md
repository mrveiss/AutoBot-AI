# Code Vectorization Data Flow Diagrams
**Version**: 1.0
**Date**: 2025-10-25

---

## 1. Overall System Data Flow

### ASCII Diagram
```
┌─────────────────┐
│  Source Code    │
│     Files       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│  File Watcher   │─────►│ Change Queue │
└────────┬────────┘      └──────┬───────┘
         │                       │
         ▼                       ▼
┌─────────────────────────────────────┐
│         Code Parser Service          │
│  ┌─────────┐ ┌─────────┐ ┌────────┐│
│  │ Python  │ │   JS    │ │  Vue   ││
│  │ Parser  │ │ Parser  │ │ Parser ││
│  └─────────┘ └─────────┘ └────────┘│
└────────────────┬────────────────────┘
                 │
                 ▼
         ┌──────────────┐
         │ Code Chunks  │
         │ + Metadata   │
         └──────┬───────┘
                │
                ▼
┌────────────────────────────────┐
│    Embedding Service           │
│  ┌──────────────────────────┐ │
│  │ CodeBERT/GraphCodeBERT   │ │
│  └──────────────────────────┘ │
└───────────────┬────────────────┘
                │
                ▼
        ┌──────────────┐
        │  Embeddings  │
        │   (vectors)  │
        └──────┬───────┘
               │
               ▼
┌──────────────────────────────┐
│         Storage Layer        │
│  ┌─────────┐  ┌────────────┐│
│  │ChromaDB │  │  Redis     ││
│  │(vectors)│  │(metadata)  ││
│  └─────────┘  └────────────┘│
└──────────────────────────────┘
```

### Mermaid Diagram
```mermaid
graph TD
    A[Source Code Files] --> B[File Watcher]
    B --> C{File Changed?}
    C -->|Yes| D[Change Queue]
    C -->|No| E[Skip]
    D --> F[Code Parser Service]

    F --> F1[Python Parser]
    F --> F2[JavaScript Parser]
    F --> F3[Vue Parser]

    F1 --> G[Code Chunks + Metadata]
    F2 --> G
    F3 --> G

    G --> H[Embedding Service]
    H --> H1[CodeBERT Model]
    H1 --> I[Vector Embeddings]

    I --> J[ChromaDB Storage]
    G --> K[Redis Metadata]

    J --> L[Similarity Index]
    K --> M[Analytics Cache]
```

---

## 2. Vectorization Pipeline Flow

### ASCII Diagram
```
┌──────────────────┐
│  API Request:    │
│  POST /vectorize │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Job Manager     │
│  - Create Job ID │
│  - Queue Task    │
└────────┬─────────┘
         │
         ├──────────────┐
         ▼              ▼
┌──────────────┐  ┌─────────────┐
│ WebSocket    │  │  Background │
│ Connection   │  │   Worker    │
└──────┬───────┘  └──────┬──────┘
       │                  │
       │                  ▼
       │         ┌──────────────┐
       │         │ File Scanner │
       │         └──────┬───────┘
       │                │
       │                ▼
       │         ┌──────────────┐
       │         │   Parallel   │
       │         │  Processing  │
       │         │  ┌────┐      │
       │         │  │ T1 │      │
       │         │  ├────┤      │
       │         │  │ T2 │      │
       │         │  ├────┤      │
       │         │  │ T3 │      │
       │         │  └────┘      │
       │         └──────┬───────┘
       │                │
       │                ▼
       │         ┌──────────────┐
       │         │   Embedding  │
       │         │   Generator  │
       │         └──────┬───────┘
       │                │
       │                ▼
       │         ┌──────────────┐
       │         │   Storage    │
       │         │   Writer     │
       │         └──────┬───────┘
       │                │
       └────────────────┤
                       ▼
              ┌──────────────┐
              │  Progress    │
              │   Updates    │
              └──────────────┘
```

### Mermaid Diagram
```mermaid
sequenceDiagram
    participant Client
    participant API
    participant JobManager
    participant Worker
    participant Parser
    participant Embedder
    participant Storage
    participant WebSocket

    Client->>API: POST /vectorize
    API->>JobManager: Create Job
    JobManager->>API: Return Job ID
    API->>Client: 202 Accepted + Job ID

    Client->>WebSocket: Connect(job_id)

    JobManager->>Worker: Start Processing

    loop For Each File
        Worker->>Parser: Parse File
        Parser->>Parser: Extract Functions/Classes
        Parser->>Worker: Return Chunks

        Worker->>Embedder: Generate Embeddings
        Embedder->>Embedder: Batch Processing
        Embedder->>Worker: Return Vectors

        Worker->>Storage: Store Embeddings
        Storage->>Storage: Update Index

        Worker->>WebSocket: Progress Update
        WebSocket->>Client: Send Progress
    end

    Worker->>JobManager: Mark Complete
    Worker->>WebSocket: Send Completion
    WebSocket->>Client: Job Complete
```

---

## 3. Duplicate Detection Flow

### ASCII Diagram
```
┌────────────────┐
│  GET           │
│  /duplicates   │
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ Load All       │
│ Embeddings     │
└───────┬────────┘
        │
        ▼
┌────────────────────────────┐
│ Similarity Matrix           │
│ ┌──┬──┬──┬──┬──┬──┬──┬──┐│
│ │  │F1│F2│F3│F4│F5│F6│F7││
│ ├──┼──┼──┼──┼──┼──┼──┼──┤│
│ │F1│1 │.2│.9│.3│.1│.8│.2││
│ │F2│.2│1 │.3│.7│.2│.1│.9││
│ │F3│.9│.3│1 │.2│.1│.7│.3││
│ └──┴──┴──┴──┴──┴──┴──┴──┘│
└────────────┬───────────────┘
             │
             ▼
    ┌────────────────┐
    │   Threshold    │
    │   Filter       │
    │   (> 0.85)     │
    └────────┬───────┘
             │
             ▼
    ┌────────────────┐
    │   Clustering   │
    │   Algorithm    │
    └────────┬───────┘
             │
             ▼
    ┌────────────────────┐
    │  Duplicate Groups  │
    │  ┌──────────────┐  │
    │  │ Group 1:     │  │
    │  │ F1, F3, F6   │  │
    │  ├──────────────┤  │
    │  │ Group 2:     │  │
    │  │ F2, F7       │  │
    │  └──────────────┘  │
    └────────┬───────────┘
             │
             ▼
    ┌────────────────┐
    │  Refactoring   │
    │  Suggestions   │
    └────────────────┘
```

### Mermaid Diagram
```mermaid
graph TD
    A[GET /duplicates Request] --> B[Query Parameters]
    B --> C[Load Embeddings from ChromaDB]

    C --> D[Compute Similarity Matrix]
    D --> E{Apply Threshold}

    E -->|Similarity > 0.85| F[Create Candidate Pairs]
    E -->|Similarity <= 0.85| G[Exclude]

    F --> H[Clustering Algorithm]
    H --> I[Group Similar Code]

    I --> J[Analyze Groups]
    J --> K[Pattern Recognition]
    K --> L[Generate Refactoring Suggestions]

    L --> M[Calculate ROI]
    M --> N[Priority Scoring]
    N --> O[Format Response]

    O --> P[Return JSON Result]
```

---

## 4. Similarity Search Flow

### ASCII Diagram
```
┌─────────────────┐
│  Search Query   │
│  "async def..." │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Query Parser   │
│  - Type detect  │
│  - Preprocess   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Embedding    │
│    Generator    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Query Vector   │
│  [0.1, -0.3...] │
└────────┬────────┘
         │
         ▼
┌──────────────────────────┐
│     ChromaDB Query       │
│  ┌────────────────────┐  │
│  │ HNSW Index Search  │  │
│  └────────────────────┘  │
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│    Metadata Filters      │
│  - file_type = "python"  │
│  - complexity < 20       │
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│     Candidate Set        │
│  [Match1, Match2, ...]   │
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│      Re-ranking          │
│  - Semantic similarity   │
│  - Structural similarity │
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│     Top-K Results        │
│  With explanations       │
└──────────────────────────┘
```

### Mermaid Diagram
```mermaid
flowchart TD
    A[Search Query] --> B{Query Type?}

    B -->|Code| C[Code Preprocessor]
    B -->|Natural Language| D[NL Preprocessor]
    B -->|Function Signature| E[Signature Parser]

    C --> F[Generate Query Embedding]
    D --> F
    E --> F

    F --> G[Query Vector]

    G --> H[ChromaDB Vector Search]
    H --> I[HNSW Index Lookup]

    I --> J[Initial Candidates]

    J --> K[Apply Metadata Filters]
    K --> L{Filters Match?}

    L -->|Yes| M[Include in Results]
    L -->|No| N[Exclude]

    M --> O[Calculate Final Scores]
    O --> P[Re-rank by Relevance]

    P --> Q[Generate Explanations]
    Q --> R[Format Top-K Results]

    R --> S[Return JSON Response]
```

---

## 5. Incremental Update Flow

### ASCII Diagram
```
┌──────────────┐
│ File Change  │
│   Detected   │
└──────┬───────┘
       │
       ▼
┌──────────────────────┐
│  Dependency Graph    │
│  ┌─────────────────┐ │
│  │ file.py imports │ │
│  │ - module_a      │ │
│  │ - module_b      │ │
│  └─────────────────┘ │
└──────────┬───────────┘
           │
           ▼
    ┌──────────────┐
    │ Impact       │
    │ Analysis     │
    └──────┬───────┘
           │
           ├───────────────┐
           ▼               ▼
  ┌──────────────┐  ┌──────────────┐
  │ Direct       │  │ Dependent    │
  │ Updates      │  │ Updates      │
  └──────┬───────┘  └──────┬───────┘
         │                  │
         ▼                  ▼
  ┌──────────────────────────────┐
  │      Update Queue             │
  │  1. file.py (changed)        │
  │  2. dependent_1.py (imports) │
  │  3. dependent_2.py (imports) │
  └───────────────┬───────────────┘
                  │
                  ▼
         ┌──────────────┐
         │   Process    │
         │   Updates    │
         └──────┬───────┘
                │
                ▼
         ┌──────────────┐
         │ Invalidate   │
         │   Caches     │
         └──────────────┘
```

### Mermaid Diagram
```mermaid
stateDiagram-v2
    [*] --> FileWatcher: File System Event

    FileWatcher --> ChangeDetection: File Modified

    ChangeDetection --> DiffAnalysis: Calculate Changes

    DiffAnalysis --> ImpactAnalysis: Determine Scope

    ImpactAnalysis --> DirectUpdate: Changed Functions
    ImpactAnalysis --> DependentUpdate: Importing Modules

    DirectUpdate --> ParseChanges: Parse Modified Code
    DependentUpdate --> ParseDependents: Parse Dependent Code

    ParseChanges --> GenerateEmbeddings: New Embeddings
    ParseDependents --> GenerateEmbeddings

    GenerateEmbeddings --> UpdateStorage: Update ChromaDB

    UpdateStorage --> InvalidateCache: Clear Old Data

    InvalidateCache --> UpdateIndex: Rebuild Indexes

    UpdateIndex --> NotifyClients: WebSocket Update

    NotifyClients --> [*]: Complete
```

---

## 6. Cache Flow

### ASCII Diagram
```
┌─────────────┐
│   Request   │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│   Cache Check       │
│  ┌───────────────┐  │
│  │ Key: hash(q)  │  │
│  └───────────────┘  │
└──────┬──────────────┘
       │
       ├──────────────┐
       ▼              ▼
┌─────────────┐  ┌─────────────┐
│  Cache Hit  │  │ Cache Miss  │
└──────┬──────┘  └──────┬──────┘
       │                 │
       │                 ▼
       │         ┌─────────────┐
       │         │   Compute   │
       │         │   Result    │
       │         └──────┬──────┘
       │                 │
       │                 ▼
       │         ┌─────────────┐
       │         │ Store in    │
       │         │   Cache     │
       │         └──────┬──────┘
       │                 │
       └─────────────────┤
                        ▼
                ┌─────────────┐
                │   Return    │
                │   Result    │
                └─────────────┘

Cache Structure:
┌──────────────────────────────┐
│      Redis DB 12             │
│  ┌────────────────────────┐  │
│  │ Embedding Cache        │  │
│  │ - TTL: 1 hour         │  │
│  ├────────────────────────┤  │
│  │ Similarity Cache       │  │
│  │ - TTL: 30 minutes     │  │
│  ├────────────────────────┤  │
│  │ Query Result Cache     │  │
│  │ - TTL: 5 minutes      │  │
│  └────────────────────────┘  │
└──────────────────────────────┘
```

### Mermaid Diagram
```mermaid
graph TD
    A[Incoming Request] --> B{Check Cache}

    B -->|Key Exists| C[Cache Hit]
    B -->|Key Missing| D[Cache Miss]

    C --> E[Retrieve from Redis]
    E --> F{Valid TTL?}

    F -->|Yes| G[Return Cached Result]
    F -->|No| H[Invalidate Entry]

    H --> D

    D --> I[Compute Result]
    I --> J[Generate Cache Key]
    J --> K[Store in Redis]

    K --> L[Set TTL]
    L --> M[Return Result]

    G --> N[Update Hit Counter]
    M --> O[Update Miss Counter]

    N --> P[Metrics Collection]
    O --> P
```

---

## 7. WebSocket Real-time Update Flow

### ASCII Diagram
```
┌──────────────┐
│   Browser    │
│   Client     │
└──────┬───────┘
       │
       │ WS Connect
       ▼
┌──────────────────────┐
│  WebSocket Server    │
│  ┌────────────────┐  │
│  │ Connection     │  │
│  │ Handler        │  │
│  └────────────────┘  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Job Subscription    │
│  job_id: xxx         │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────┐
│      Message Queue            │
│  ┌────────────────────────┐  │
│  │ Progress Events        │  │
│  ├────────────────────────┤  │
│  │ 1. File: api.py (10%) │  │
│  │ 2. File: chat.py (20%)│  │
│  │ 3. Error: syntax.py   │  │
│  └────────────────────────┘  │
└───────────┬──────────────────┘
            │
            ▼
     ┌──────────────┐
     │  Broadcast   │
     │  to Client   │
     └──────────────┘
```

### Mermaid Diagram
```mermaid
sequenceDiagram
    participant Browser
    participant WSServer
    participant JobManager
    participant Worker
    participant MessageQueue

    Browser->>WSServer: Connect WebSocket
    WSServer->>Browser: Accept Connection

    Browser->>WSServer: Subscribe to Job
    WSServer->>JobManager: Register Subscription

    loop Processing Files
        Worker->>MessageQueue: Publish Progress
        MessageQueue->>WSServer: Deliver Message
        WSServer->>Browser: Send Progress Update

        Browser->>Browser: Update UI
    end

    Worker->>MessageQueue: Publish Completion
    MessageQueue->>WSServer: Deliver Completion
    WSServer->>Browser: Send Complete Status

    Browser->>WSServer: Close Connection
    WSServer->>JobManager: Unregister Subscription
```

---

## 8. Error Handling Flow

### Mermaid Diagram
```mermaid
flowchart TD
    A[Operation Start] --> B{Try Operation}

    B -->|Success| C[Continue Processing]
    B -->|Error| D[Catch Exception]

    D --> E{Error Type?}

    E -->|Syntax Error| F[Log & Skip File]
    E -->|Timeout| G[Retry with Backoff]
    E -->|Storage Error| H[Failover to Backup]
    E -->|Model Error| I[Use Fallback Model]
    E -->|Unknown| J[Log & Alert]

    F --> K[Add to Error Report]
    G --> L{Retry Count}

    L -->|< 3| B
    L -->|>= 3| M[Mark as Failed]

    H --> N{Backup Available?}
    N -->|Yes| O[Use Backup Storage]
    N -->|No| P[Queue for Later]

    I --> Q[Continue with Degraded Mode]
    J --> R[Send Alert to Admin]

    K --> S[Continue Next Item]
    M --> S
    O --> C
    P --> S
    Q --> C
    R --> S
```

---

## Performance Optimization Points

### Critical Path Optimization
```
┌─────────────┐
│   Input     │
└──────┬──────┘
       │
       ▼
┌─────────────────────────┐
│  🔥 Bottleneck:         │
│  Embedding Generation   │
│  Solution: Batch + GPU  │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  🔥 Bottleneck:         │
│  ChromaDB Writes        │
│  Solution: Bulk Insert  │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  🔥 Bottleneck:         │
│  Similarity Computation │
│  Solution: FAISS Index  │
└──────────┬──────────────┘
           │
           ▼
┌─────────────┐
│   Output    │
└─────────────┘
```

---

## Summary

These data flow diagrams illustrate the complete lifecycle of code vectorization operations:

1. **Overall Flow**: Shows how code moves from files to embeddings
2. **Vectorization Pipeline**: Details the processing pipeline
3. **Duplicate Detection**: Explains similarity computation and clustering
4. **Similarity Search**: Shows query processing and ranking
5. **Incremental Updates**: Handles file changes efficiently
6. **Cache Flow**: Optimizes repeated operations
7. **WebSocket Updates**: Provides real-time feedback
8. **Error Handling**: Ensures robust operation

Each flow is designed for:
- **Efficiency**: Minimal latency and resource usage
- **Scalability**: Handles large codebases
- **Reliability**: Graceful error handling
- **Real-time**: Immediate feedback to users