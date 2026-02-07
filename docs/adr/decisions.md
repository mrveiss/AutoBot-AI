# Decisions Log

## 2025-06-14 - LLM Fallback and Rate Limiting Strategy

**Decision:** Implement `safe_query` function within `src/llm_interface.py` to manage Google Cloud API usage and provide a robust fallback to a local LLM (TinyLLaMA).

**Rationale:**
- **Resilience:** Ensures continuous operation even when external API quotas are exceeded or services are unavailable.
- **Efficiency:** Prioritizes local resources when external API limits are approached, reducing reliance on external services and potential costs.
- **Maintainability:** Centralizes LLM interaction logic, making it easier to manage and extend.
- **User Experience:** Provides clear logging and potential user notifications regarding API usage and fallbacks.

**Implementation Details:**
- The `safe_query` function will wrap calls to Google's Generative Language API.
- A mock `palm.get_quota_status()` will be used initially to simulate quota checks.
- Exponential backoff will be applied for retries on `QuotaExceededError`.
- A placeholder `local_llm.generate()` will represent the local TinyLLaMA model.
- Logging will be directed to `logs/llm_usage.log` for monitoring.

## 2025-06-17 - Frontend Terminal for Backend Control

**Decision:** Implement a terminal modal in the frontend to allow direct execution of shell commands via the `/api/execute_command` endpoint.

**Rationale:**
- **Enhanced Control:** Provides users with direct command-line access to the backend, enabling more granular control and debugging capabilities.
- **Improved Workflow:** Streamlines development and operational tasks by centralizing command execution within the UI.
- **Flexibility:** Allows for quick execution of various system commands without needing to switch contexts to a separate terminal.

**Implementation Details:**
- A new "Terminal" button was added to `frontend/index.html`.
- An Alpine.js store (`terminalModal`) was created in `frontend/index.js` to manage the modal's state, input, and output.
- The modal interacts with the existing `/api/execute_command` endpoint in `main.py` using `fetch` API.
- Corresponding CSS styles were added to `frontend/index.css` for the modal's appearance.

## 2025-06-17 - LLM Command Execution Capability

**Decision:** Explicitly document that the LLM, through the orchestrator, is equipped with the capability to execute shell commands on the machine as a tool to achieve its goals.

**Rationale:**
- **Clarity:** Provides clear understanding of the system's capabilities, especially regarding the LLM's interaction with the underlying operating system.
- **Alignment with Goals:** Reinforces the core objective of enabling the LLM to use tools for task accomplishment.
- **Transparency:** Ensures that the functionality is well-documented for future development and auditing.

**Implementation Details:**
- The `CommandExecutor` module (`src/command_executor.py`) is designed to be invoked by the orchestrator based on the LLM's planning and task decomposition.
- This capability is now explicitly mentioned in `docs/project.md` (Phase 3: Command Execution Engine) and tracked in `docs/tasks.md`.

## 2025-06-17 - Redis Integration for Enhanced Performance

**Decision:** Integrate Redis into the AutoBot system to enhance performance, memory management, and real-time capabilities.

**Rationale:**
- **Agent Memory (short-term):** Provides a fast in-memory store for recent interactions, thoughts, commands, and execution trees, significantly faster than disk I/O.
- **Task Queue:** Enables efficient queuing of incoming subtasks for orchestration, crucial for multi-threaded or distributed systems.
- **RAG Cache:** Allows caching of recent document chunks or embeddings in-memory for instant retrieval during Retrieval-Augmented Generation (RAG), improving response times.
- **Key-Value State Storage:** Offers a very fast mechanism to store and update flags and critical state information (e.g., `llm_state:idle`, `last_model:phi-2`, `user_override:true`).
- **Rate Limit Tracking:** Facilitates tracking of external API usage (e.g., OpenAI) with TTLs and counters, ensuring compliance and preventing service interruptions.
- **Session Management:** Ideal for managing session and user state if AutoBot supports multiple users or runs as a service.

**Implementation Details:**
- Redis server will be installed and configured.
- The `redis-py` Python client library will be used for interaction.
- Configuration parameters for Redis connection will be added to `config/config.yaml`.
- Specific modules (e.g., orchestrator, knowledge base, LLM interface) will be updated to leverage Redis for their respective use cases.

## 2025-06-17 - SQLite as Long-Term Memory Backend

**Decision:** Establish SQLite as the primary long-term memory backend for the AutoBot agent.

**Rationale:**
- **Performance:** Extremely fast for single-user, local use, whether in-RAM or SSD-backed.
- **Portability:** Operates as a file-based database, requiring no server or services, making it ideal for deployment in WSL2, Kali, laptops, and servers.
- **Data Types:** Well-suited for storing various types of agent data, including task logs, configuration changes, and command execution history.
- **Ease of Integration:** Standard Python libraries (`sqlite3`, SQLAlchemy) provide straightforward integration without requiring additional tools.
- **Storage Footprint:** Minimal footprint, as it's just a file, allowing for trivial backup and movement between systems.
- **Offline First:** Aligns perfectly with the local-first performance philosophy.
- **Works With Other Layers:** Can easily reference external data like file paths, markdown document locations, and store embeddings (as base64 or pickled blobs) directly within the database.

**Implementation Details:**
- The `KnowledgeBase` module will primarily interact with SQLite for persistent storage.
- Data such as task logs, execution history, and configuration changes will be stored in SQLite.
- Mechanisms will be explored to link to external markdown documentation, potentially storing `doc_path` and `line_start` references.
- The feasibility and benefits of storing embeddings directly within SQLite will be evaluated.

## 2025-06-17 - VNC Session with noVNC for Agent Observation and Control

**Decision:** Implement a Kex VNC session with noVNC embedded in the Web UI to provide real-time observation and control capabilities for the AutoBot agent's desktop environment.

**Rationale:**
- **GUI Access over Web:** noVNC enables full GUI access directly through a web browser using WebSockets and a browser canvas for VNC.
- **Full Linux Desktop Environment:** Kex (TigerVNC) provides a persistent TigerVNC session with a full Linux GUI (XFCE or KDE) in WSL2/Kali, allowing the agent to interact with a real desktop.
- **Visible GUI Task Automation:** The agent's GUI automation tasks become visible to the user, enhancing transparency and understanding of its actions.
- **Ability to Take Control:** VNC offers full keyboard and mouse override, enabling human-in-the-loop takeover when needed.
- **Browser-Embedded Viewer:** noVNC can be easily embedded as an iframe or dynamic viewer within the AutoBot frontend.
- **Cross-Platform Compatibility:** Kex runs equally well on WSL2 and native Kali Linux, with or without an X11 system display.

**Implementation Details:**
- Kex will be started in VNC mode (`kex --win -s`) to create a persistent TigerVNC session.
- A `websockify` server will be run to connect to Kex's VNC port (e.g., `6080` for web access, `5901` for Kex/TigerVNC's display). Self-signed certificates may be used for development.
- An `<iframe>` or dynamic viewer will be added to `frontend/index.html` to display the noVNC interface.
- noVNC provides built-in control capabilities, including the option to toggle "readonly" mode via query parameters.
- Optional enhancements like a transparent overlay for current task, click targets, and streamed logs can be considered for future development.
- Security considerations for external access (password protection, Nginx with auth, HTTPS, IP restrictions) will be addressed for multi-user or production environments.

## 2025-06-18 - Project State Tracking System

**Decision:** Implement a comprehensive project state tracking system using `docs/status.md` to provide a single source of truth for project progress and enable agent self-awareness.

**Rationale:**
- **Current Progress Visibility:** `docs/status.md` will clearly outline the current phase, completed core features, and immediate next steps, offering a quick overview of the project's state.
- **Agent Self-Awareness:** By reading `docs/status.md` or `docs/tasks.md`, the LLM agent can understand its current context, prioritize tasks, and make informed decisions about its workflow.
- **Systematic Advancement:** Defines clear phase promotion criteria, ensuring a structured and verifiable progression through development milestones.
- **Improved Communication:** Provides a standardized format for tracking and communicating project status to both human users and the agent itself.
- **Enhanced Debugging/Auditing:** A centralized status log aids in understanding the agent's operational context and historical progress.

**Implementation Details:**
- A new file, `docs/status.md`, will be created with a predefined structure including sections for "Current Phase," "Core Features (Baseline MVP)," "What Needs to be Done (Next)," "Phase Promotion Criteria," and "Project Logs."
- The LLM agent's core logic (e.g., within `orchestrator.py` or a new `state_manager.py`) will be modified to:
    - Read and parse the content of `docs/status.md` at startup or periodically.
    - Update its internal understanding of the current project phase and pending tasks.
    - Log task completions to `docs/task_log.md`.
    - Evaluate phase promotion criteria and propose advancement when met.
- A visual indicator will be added to the Web UI (e.g., a top bar or sidebar) to display the current phase and key status elements (e.g., `[ Phase X: Feature Name ] ✅ Logs ✓ ❌ Memory ✖ ❌ LLM UI`).

## 2025-07-13 - LangChain and LlamaIndex Integration

**Decision:** Integrate LangChain and LlamaIndex into the AutoBot workflow to create a hybrid architecture for enhanced orchestration and knowledge retrieval, leveraging Redis for all memory and logging.

**Rationale:**
- **Advanced Orchestration:** LangChain provides a robust framework for building intelligent agents, offering sophisticated tools for reasoning, planning, and tool use. This will allow for more complex and flexible task execution compared to a custom orchestrator.
- **Enhanced Knowledge Retrieval (RAG):** LlamaIndex specializes in data ingestion, indexing, and retrieval-augmented generation (RAG). Integrating it will significantly improve the agent's ability to access and utilize its knowledge base, reducing hallucination and providing more accurate responses.
- **Unified Memory and Logging:** Using Redis for all memory (chat history, agent scratchpad) and LlamaIndex's vector/document store ensures a high-performance, centralized, and persistent state. This simplifies data management and improves overall system responsiveness.
- **Modularity and Extensibility:** Both LangChain and LlamaIndex are highly modular, allowing for easier integration of new tools, LLMs, and data sources in the future.
- **Industry Best Practices:** Adopting these widely used frameworks aligns AutoBot with current best practices in LLM application development, making the codebase more maintainable and understandable for new contributors.

**Design Choices:**
- **LangChain Agent as Orchestrator:** The existing `Orchestrator` will be refactored to wrap a LangChain Agent. This agent will be responsible for the high-level decision-making, tool selection, and task decomposition.
- **LlamaIndex for Knowledge Base:** The `KnowledgeBase` module will be re-implemented using LlamaIndex components. This includes using LlamaIndex's `VectorStoreIndex` and `ServiceContext` for managing embeddings and document storage.
- **Redis as Backend for LlamaIndex and Memory:** LlamaIndex will be configured to use a `RedisVectorStore` and Redis for its document store. The `ChatHistoryManager` will continue to use Redis for conversational memory, and all logs will be directed to Redis.
- **Existing Functionalities as LangChain Tools:** Current functionalities like OS command execution (`SystemIntegration`) and LLM interactions (`LLMInterface`) will be exposed as custom LangChain `Tools` for the agent to utilize.
- **LangChain-Compatible LLMs:** The `LLMInterface` will be updated to provide LLM instances (e.g., `ChatOllama`, `OllamaLLM`) that are directly compatible with LangChain and LlamaIndex.
