---
title: Glossary
nav_order: 5
tags:
  - reference
  - glossary
aliases:
  - Glossary
  - Terminology
  - Terms and Definitions
status: current
---

This glossary defines terms, acronyms, and concepts used throughout AutoBot documentation and codebase. For how the platform-level terms fit together, see [The AutoBot Platform Model](architecture/PLATFORM_MODEL.md).

---

## A

### ADR (Architecture Decision Record)
A document that captures an important architectural decision along with its context and consequences. See [docs/adr/](adr/README.md).

### Agent
An autonomous AI component that can perform specific tasks. AutoBot uses multiple specialized agents including KB Librarian, RAG Agent, and Task Agents.

### API Gateway
The central entry point for all API requests, handling routing, authentication, and rate limiting. Located at `<backend-ip>:8443` (HTTPS).

### Async Client
A non-blocking Redis or HTTP client that allows concurrent operations. Used for high-performance data access.

---

## B

### Backend API
The FastAPI-based REST API service running on the main machine. Handles all business logic, LLM orchestration, and data management.

### Browser VM
VM5 (`<browser-ip>:3000`) dedicated to Playwright browser automation. Isolated for security and stability.

---

## C

### Chat Workflow
The message processing pipeline from user input to AI response. Includes intent routing, context retrieval, LLM inference, and streaming output.

### ChromaDB
Vector database used for code analysis and duplicate detection. Separate from the main knowledge base which uses Redis.

### Circuit Breaker
A design pattern that prevents cascading failures by stopping requests to failing services. Implemented in `src/circuit_breaker.py`.

### Context Window
The maximum amount of text an LLM can process in a single request. Varies by model (4K to 200K tokens).

---

## D

### Distributed Architecture
AutoBot's 6-VM infrastructure design where each VM serves a specific purpose. See [ADR-001](adr/001-distributed-vm-architecture.md).

### DR (Disaster Recovery)
Procedures and documentation for recovering from system failures. Critical for production deployments.

---

## E

### Embedding
A numerical vector representation of text or code. Used for similarity search, RAG, and duplicate detection.

### Enhanced Search
Advanced search functionality with filtering, reranking, clustering, and query expansion. See `src/knowledge/search.py`.

---

## F

### FastAPI
The Python web framework used for the backend API. Provides async support, automatic OpenAPI docs, and type validation.

### Feature Envy
A code smell where a method accesses data from another object more than its own. Indicates misplaced logic.

### Fleet
The set of nodes (machines or containers) that AutoBot's [Service Lifecycle Manager (SLM)](#service-lifecycle-manager-slm) deploys, operates, and scales — vector DB, cache, database, inference, and workers across one or more hosts.

### Frontend VM
VM1 (`<frontend-ip>:5173`) - the **only** machine allowed to run the Vite frontend server.

---

## G

### God Class
A code smell where a class has too many responsibilities. Should be refactored into smaller, focused classes.

### Governance
The platform-core controls that every layer above inherits: role-based access control (RBAC), review/approval gates, and budgets. Modules such as [AutoBot LLC](llc/_index.md) rely on this rather than implementing their own.

### Graceful Degradation
The ability to continue operating at reduced functionality when components fail.

---

## H

### HMR (Hot Module Replacement)
Vite's ability to update modules in the browser without full page reload during development.

### Hooks
The platform's extension points — places where modules and plugins attach behavior to core events and workflows. Part of how a [module](#module) is built on the platform's bones.

### Horizontal Scaling
Adding more instances of a service to handle increased load. Contrast with vertical scaling.

---

## I

### Institutional Memory
The platform's persistent, shared knowledge: the [RAG](#rag-retrieval-augmented-generation) knowledge base plus the memory/knowledge graph. It survives across sessions and is shared by everything running on the core, so [modules](#module) and agents start with organizational context instead of a blank slate.

### Intel NPU
Neural Processing Unit - dedicated AI acceleration hardware in Intel CPUs. Used for local embedding generation.

---

## K

### KB (Knowledge Base)
The vector-indexed document store containing project documentation, facts, and learned information.

### KB Librarian
The agent responsible for maintaining the knowledge base, indexing documents, and managing facts.

---

## L

### LlamaIndex
The RAG (Retrieval-Augmented Generation) framework used for knowledge base queries and document indexing.

### LLC (AutoBot LLC Module)
AutoBot's flagship [module](#module): an autonomous *agent-company* you install on the platform. It adds companies, org charts, goals, backlogs, sprints, heartbeat scheduling, and board governance, while its agents inherit [institutional memory](#institutional-memory), local inference, [hooks](#hooks), and [governance](#governance) from the core. Here "LLC" names the module — not a legal "limited liability company." See [AutoBot LLC](llc/_index.md).

### LLM (Large Language Model)
AI models that generate text responses (run locally or via a provider). AutoBot routes all of them through one LLM gateway with provider fallback. **Note:** an LLM is *not* the SLM — see [Service Lifecycle Manager (SLM)](#service-lifecycle-manager-slm).

### Local Inference
Running model inference on hardware you own (CPU, GPU, or NPU) instead of a remote API. A platform-core capability that gives modules and agents inference at **zero marginal cost per request**.

### Long-Running Operations
Tasks that exceed normal request timeouts. Managed by the async task framework with progress tracking.

---

## M

### MCP (Memory Context Protocol)
The system for storing and retrieving context, decisions, and findings across sessions.

### Module
An installable capability built on the AutoBot [platform core](#platform-core). A module inherits the core's primitives — [institutional memory](#institutional-memory), [local inference](#local-inference), [hooks](#hooks), and [governance](#governance) — so it stays small relative to what it delivers. [AutoBot LLC](#llc-autobot-llc-module) is the flagship module. See [The AutoBot Platform Model](architecture/PLATFORM_MODEL.md).

### Multi-Modal
AI capabilities that span multiple modalities: text, image, voice, and desktop interaction.

---

## N

### Named Database
Redis database accessed by logical name (e.g., "knowledge") rather than number (e.g., db=1). See [ADR-002](adr/002-redis-database-separation.md).

### NPU Worker
VM2 (`<npu-ip>:8081`) - dedicated service for Intel NPU-accelerated AI inference.

---

## O

### Ollama
Local LLM inference server running on VM4. Provides self-hosted model inference.

### OpenVINO
Intel's toolkit for optimizing AI models for Intel hardware including NPUs.

---

## P

### Platform Core
AutoBot's small, stable core — chat/streaming, the knowledge base ([RAG](#rag-retrieval-augmented-generation) + memory graph), the LLM gateway, [local inference](#local-inference), [hooks](#hooks), and [governance](#governance). It changes slowly so the [SLM](#service-lifecycle-manager-slm) and [modules](#module) can depend on it. Embodies the platform's promise: your data stays on your machines and the AI stays yours.

### Playwright
Browser automation framework running on VM5. Used for web scraping and UI testing.

### Pre-commit Hook
Scripts that run before git commits to enforce code quality, formatting, and security checks.

---

## R

### RAG (Retrieval-Augmented Generation)
AI technique that retrieves relevant context before generating responses, reducing hallucinations.

### Redis Stack
Enhanced Redis with modules for vectors, JSON, and search. Running on VM3.

### Reranking
Post-processing search results to improve relevance ranking using AI models.

### RTO (Recovery Time Objective)
Maximum acceptable time to restore service after failure.

### RPO (Recovery Point Objective)
Maximum acceptable data loss measured in time.

---

## S

### Service Lifecycle Manager (SLM)
AutoBot's management layer. It deploys, operates, and scales the infrastructure behind private AI — vector DB, cache, database, inference server, and workers — across a [fleet](#fleet): **deploy** (stand up the stack, via Ansible) → **operate** (upgrade, monitor, recover, rotate certs) → **scale** (add nodes, add NPU workers, assign roles). **SLM always means *Service Lifecycle Manager* — never "small language model"** (for on-device models, see [Local Inference](#local-inference) and [LLM](#llm-large-language-model)). See [The AutoBot Platform Model](architecture/PLATFORM_MODEL.md).

### Session
A user's conversation context including message history and state. Persisted in Redis.

### Streaming Response
Real-time token-by-token output from LLMs via WebSocket.

### Sync Script
Utilities (`sync-to-vm.sh`) that synchronize code from local development to VMs.

---

## T

### Task Context
Dataclass pattern for bundling multiple parameters into a single context object. Reduces long parameter lists.

### TodoWrite
Claude Code's task tracking tool for managing immediate work items.

---

## U

### UTF-8
Character encoding standard. All AutoBot file I/O must use explicit UTF-8 encoding.

---

## V

### Vector Store
Database optimized for storing and searching embedding vectors. Redis (knowledge base) and ChromaDB (code analysis).

### Vertical Scaling
Increasing resources (CPU, RAM) on existing machines. Contrast with horizontal scaling.

### Vite
Frontend build tool and development server. Only runs on VM1.

### VNC
Virtual Network Computing - desktop streaming protocol. AutoBot exposes VNC at port 6080.

### VM (Virtual Machine)
Isolated computing environments. AutoBot is hypervisor-agnostic and can deploy onto one or more hosts or VMs (co-located or distributed); it requires only a supported OS and hardware.

### Vue
Frontend JavaScript framework (Vue 3) used for the AutoBot web interface.

---

## W

### WebSocket
Bidirectional communication protocol used for chat streaming and real-time updates.

### Workflow
Automated multi-step task execution. Managed by the Enhanced Orchestrator.

### WSL
Windows Subsystem for Linux - where the main AutoBot backend runs.

---

## Acronym Quick Reference

| Acronym | Full Form |
|---------|-----------|
| ADR | Architecture Decision Record |
| API | Application Programming Interface |
| DR | Disaster Recovery |
| HMR | Hot Module Replacement |
| KB | Knowledge Base |
| LLC | AutoBot LLC (autonomous agent-company module) |
| LLM | Large Language Model |
| MCP | Memory Context Protocol |
| NPU | Neural Processing Unit |
| RAG | Retrieval-Augmented Generation |
| RTO | Recovery Time Objective |
| RPO | Recovery Point Objective |
| SLM | Service Lifecycle Manager (**not** small language model) |
| VM | Virtual Machine |
| VNC | Virtual Network Computing |
| WSL | Windows Subsystem for Linux |

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
