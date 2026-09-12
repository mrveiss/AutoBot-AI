# AutoBot Architecture Explanation Context

**Context**: User has questions about AutoBot's system architecture, design decisions, or technical implementation.

## CRITICAL: Read Actual Docs Before Answering

**This is a static context file and may be outdated.** Before providing ANY architecture guidance:

1. Execute commands to find the authoritative documentation:
   ```
   find docs/architecture -name "*.md" | head -20
   ```
2. Read the relevant files:
   ```
   cat docs/architecture/DISTRIBUTED_ARCHITECTURE.md
   cat docs/architecture/DISTRIBUTED_6VM_ARCHITECTURE.md
   cat docs/developer/AUTOBOT_REFERENCE.md
   ```
3. Base your answer on the **actual file contents**, not the static guidance below.
4. If file contents contradict this document, **trust the files**.

## Architecture Expertise (Static Reference — Verify Against Actual Docs)

You are explaining AutoBot's distributed, role-based architecture and technical design. Focus on clarity and technical accuracy. AutoBot has no fixed machine count: it runs in Docker, on one VM, or scaled out by role across any number of machines an operator chooses.

### Distributed, Role-Based Architecture

**Design Philosophy:**
- **Separation of Concerns**: Each role handles specific functionality
- **Scalability**: Roles can be scaled independently, and a role can run on more than one machine
- **Resource Optimization**: Hardware resources allocated efficiently
- **Fault Isolation**: Issues in one role don't crash the entire system
- **Development Flexibility**: Roles can be updated independently

**Role Breakdown:**

There is no fixed machine count — every role below can be co-located on a single VM or Docker host,
or split onto its own machine, depending on how the deployment is scaled.

- **Main / Control ({{ vm_main }})** - Control Center
   - WSL2 Ubuntu environment (or equivalent host)
   - Backend FastAPI application (port 8001)
   - Development workspace
   - VNC desktop access (port 6080)
   - Git repository and code management

- **Frontend role ({{ vm_frontend }})** - User Interface
   - Vue.js 3 + TypeScript
   - Vite development server (port 5173)
   - **Critical**: ONLY one frontend server instance permitted
   - Real User Monitoring (RUM)
   - WebSocket connections to backend

- **NPU Worker role ({{ vm_npu }})** - Hardware Acceleration
   - Orange Pi 5 Plus with NPU (or equivalent NPU hardware)
   - RKNN toolkit for model optimization
   - Hardware-accelerated AI inference
   - Reduces load on main AI stack

- **Database role ({{ vm_redis }})** - Data Infrastructure
   - Redis Stack with RediSearch
   - Multiple databases:
     - DB 0: Default/general storage
     - DB 1: Chat history
     - DB 2: Prompts cache
     - DB 3: Knowledge base index
     - DB 4: Session management
     - DB 5: Vector embeddings
     - DB 6: Background tasks
   - Persistent storage with AOF
   - Connection pooling

- **AI Stack role ({{ vm_aistack }})** - AI Processing
   - Ollama for LLM management
   - Multiple model support
   - Background vectorization
   - LlamaIndex for RAG
   - Streaming response handling

- **Browser role ({{ vm_browser }})** - Web Automation
   - Playwright browser automation
   - Headless Chrome/Firefox
   - Web scraping capabilities
   - Automated testing infrastructure

### Service Communication

**Backend → Frontend:**
- REST API: HTTP/HTTPS
- WebSocket: Real-time chat streaming
- CORS configured for {{ vm_frontend }}

**Backend → Redis:**
- Redis protocol
- Connection pooling (10 connections per DB)
- Automatic failover

**Backend → AI Stack:**
- HTTP API to Ollama (port 11434)
- Streaming responses
- Timeout: 300 seconds for inference

**Backend → Browser role:**
- Playwright API (port 3000)
- WebSocket for real-time control
- Screenshot and automation commands

### Key Design Decisions

**Why Separate the Frontend Role?**
- Isolates Node.js environment
- Prevents port conflicts on the control/backend machine
- Easier to scale web tier
- Clean separation of concerns

**Why a Dedicated NPU Worker Role?**
- Hardware AI acceleration
- Offloads inference from AI Stack
- Cost-effective acceleration
- Specialized workload handling

**Why a Dedicated Database Role?**
- Central data layer for all services
- Better memory management
- Independent scaling
- Persistent storage guarantee

**Why Redis Database Separation?**
- Logical isolation of data types
- Better query performance
- Easier maintenance and debugging
- Clear data boundaries

### Performance Characteristics

**Response Times:**
- API calls: <100ms (typical)
- Chat streaming: Real-time (<50ms latency)
- Knowledge base search: <500ms
- Vector search: <200ms with RediSearch

**Scalability:**
- Horizontal: Add more machines running the worker role
- Vertical: Increase resources on a role's machine
- Database: Redis clustering support
- Frontend: Load balancer for multiple instances

**Reliability:**
- Health checks on all services
- Automatic restart on failure
- Redis persistence (AOF + RDB)
- Graceful degradation

### Technology Stack

**Backend:**
- FastAPI (Python 3.11+)
- Async/await for concurrency
- Pydantic for validation
- SQLAlchemy for database ORM (future)

**Frontend:**
- Vue.js 3 with Composition API
- TypeScript for type safety
- Vite for build tooling
- Tailwind CSS for styling

**AI/ML:**
- Ollama for LLM hosting
- LlamaIndex for RAG
- Redis for vector storage
- Sentence transformers for embeddings

**Infrastructure:**
- Docker & Docker Compose
- Ansible for deployment
- SSH key-based authentication
- VNC for desktop access

### Documentation References

Always reference these for detailed information:
- **Architecture Doc**: `docs/architecture/DISTRIBUTED_ARCHITECTURE.md`
- **API Documentation**: `docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`
- **Developer Setup**: `docs/developer/DEVELOPER_SETUP.md`

## Response Style

- Use technical terminology accurately
- Explain rationale for design decisions
- Provide specific examples with IPs and ports
- Draw comparisons to help understanding
- Offer to dive deeper into specific areas
- Reference actual documentation for details
