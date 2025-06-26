## Phase 1: Environment Setup and Bootstrap

### Tasks

* [x] Detect if running inside WSL2 or native Linux (Kali preferred)
* [ ] If inside WSL2, check if Kex is installed and ready for GUI fallback
* [x] Check if `pyenv` is installed. If not, guide the user to install it with required build tools
* [x] Ensure Python 3.10 is installed via `pyenv`, and configured as the global version
* [x] Create isolated virtual environment in `` using Python 3.10
* [x] Install core Python dependencies via `requirements.txt`
* [ ] Install system-level packages: `xvfb`, `libx11-dev`, `ffmpeg`, `libgl1`, `tk`, `build-essential`, etc.
* [x] Create project directories:
  * `logs/` for logs
  * `docs/` for documentation and task history
  * `config/` for configuration files
  * `plugins/` for optional plugin system
  * `venvs/` for additional Python environments (e.g., OpenVINO)
  * `tests/` for test modules
  * `web/` for frontend interface
* [x] Copy `config/config.yaml.template` to `config/config.yaml` if it doesn’t exist
* [x] Create `.gitignore` that excludes virtual environments, log files, system caches, pycache, and secrets
* [x] Create `docs/project.md` containing high-level project goals, principles, and overall architecture overview
* [x] Setup script must complete successfully with one command: `./setup_agent.sh`

## Phase 2: Agent Initialization and Configuration

### Tasks

* [x] Load `config/config.yaml`
* [x] Initialize logging system (log to `logs/agent.log`)
* [ ] Validate API keys and credentials presence
* [x] Detect GPU/NPU availability
* [x] Load model orchestrator (TinyLLaMA default, Phi-2 optional)
* [x] Configure LLM settings for both orchestrator and task execution, including:
    *   `temperature`: Controls creativity (0.0 - 1.0).
    *   `system_prompt`: Defines the LLM's persona and instructions.
    *   `sampling_strategy`: (e.g., `top_p`, `top_k`, `greedy`).
    *   `structured_output`: Boolean indicating if structured output (e.g., JSON) is expected.
* [ ] Initialize plugin manager (scan `plugins/` folder)

### Prompt

```python
# main.py
# 1. Load configuration and check for required fields
# 2. Setup logging
# 3. Validate hardware access and log hardware info
# 4. Initialize orchestrator model with specific settings
# 5. Initialize task model with specific settings
# 6. Log successful startup
```

## Phase 3: Command Execution Engine

### Tasks

* [x] Implement `CommandExecutor` to run shell and Python commands. This module is designed to be callable by the LLM as a tool to achieve its goals.
* [ ] Secure command sandbox to avoid destructive operations
* [x] Integrate command feedback logger
* [x] Provide structured JSON result per command
* [x] Support chained commands from orchestrator
* [ ] **Intelligent Command Inference:** Enhance the agent's ability to infer appropriate shell commands based on high-level goals, even if the exact command is not explicitly provided.
* [ ] **Automatic Tool/Package Installation:** Implement logic to detect missing commands/applications and automatically install them (e.g., using `apt-get`, `pip`).
* [ ] **Installation Tracking for Rollback:** Log all installations and system modifications to a persistent store to enable future rollback capabilities.

### Prompt

```python
# command_executor.py
class CommandExecutor:
    def run_shell_command(self, cmd: str) -> dict: ...
    def run_python_snippet(self, code: str) -> dict: ...
    def run_pipeline(self, tasks: list) -> list: ...
```

## Phase 4: GUI Automation Interface

### Tasks

* [ ] Setup `pyautogui` and `mouseinfo` under Xvfb virtual display
* [ ] Create GUIController class to:
  * Capture screenshots
  * Simulate mouse/keyboard
  * Locate elements by image
  * Draw visual feedback (optional)
* [ ] Ensure compatibility with Xvfb under WSL2
* [ ] If running in WSL2, detect if `kex` is available and active; suggest starting `kex` session if GUI fails
* [ ] **Integrate Kex VNC session with noVNC:** Implement a VNC session using Kex (TigerVNC) and embed noVNC in the Web UI for real-time observation and control of the agent's desktop environment. This includes visible GUI task automation and human-in-the-loop takeover capabilities.

### Prompt

```python
# gui_controller.py
class GUIController:
    def capture_screen(self) -> Image: ...
    def click_at(self, x: int, y: int) -> None: ...
    def type_text(self, text: str) -> None: ...
```

## Phase 5: Agent Orchestrator and Planning Logic

### Tasks

* [x] Implement task decomposition module
* [x] Support LLM-directed microtask planning
* [ ] Auto-document completed tasks to `docs/tasks.md`
* [ ] Prioritize self-improving tasks when idle (auto-tune)
* [ ] Include error recovery from failed subtasks
* [x] Log all orchestration activities in `docs/task_log.md`

### Prompt

```python
# orchestrator.py
class Orchestrator:
    def plan_and_execute(self, goal: str) -> None: ...
    def split_task(self, goal: str) -> list: ...
    def handle_error(self, error: Exception) -> None: ...
```

## Phase 6: Agent Self-Awareness and State Management

### Tasks

* [ ] Implement a project state tracking system using `docs/status.md`.
* [ ] Ensure the LLM agent is self-aware of its current phase, core features, and next steps by reading `docs/status.md` or `docs/tasks.md`.
* [x] Log task completions to `docs/task_log.md`.
* [ ] Develop logic for the agent to propose phase promotions when criteria defined in `docs/status.md` are met.
* [ ] Add a visual indicator in the Web UI to display the current phase and key status elements (e.g., `[ Phase X: Feature Name ] ✅ Logs ✓ ❌ Memory ✖ ❌ LLM UI`).

### Prompt

```python
# orchestrator.py (or a new state_manager.py)
class StateManager:
    def update_status(self, status_data: dict) -> None: ...
    def check_promotion_criteria(self) -> bool: ...
    def get_current_status(self) -> dict: ...
```

## Phase 7: Agent Memory and Knowledge Base

### Tasks

* [x] Establish SQLite as the primary long-term memory backend for the agent.
* [ ] Leverage SQLite for storing task logs, configuration changes, and command execution history.
* [x] Ensure SQLite's portability and ease of integration within WSL2 and Kali environments.
* [ ] Implement mechanisms to reference markdown files within SQLite (e.g., `doc_path`, `line_start`).
* [ ] Explore storing embeddings as base64 or pickled blobs within SQLite if needed.

### Prompt

```python
# knowledge_base.py
class KnowledgeBase:
    def store_data(self, data: dict, type: str) -> None: ...
    def retrieve_data(self, query: str, type: str) -> list: ...
    def update_embedding(self, id: str, embedding: bytes) -> None: ...
```

## Phase 8: Interface and Web Control Panel

### Tasks

* [x] Build minimal frontend in `web/` using HTML/JS or Flask UI
* [ ] Use NoVNC or WebSocket proxy to stream desktop
* [ ] Show logs, currently running task, and options to interrupt/resume
* [ ] Allow human-in-the-loop takeover if needed (interrupt/takeover button)
* [ ] **Embed noVNC in the Web UI:** Integrate an iframe or dynamic viewer in `web/index.html` to display the Kex VNC session, enabling real-time observation and control.

### Prompt

```bash
# Run web server
python3 -m http.server --directory web 8080
```

## Phase 9: Redis Integration for Enhanced Performance

### Tasks

* [x] Install Redis server and Python client library (`redis-py`).
* [x] Configure Redis connection parameters in `config/config.yaml`.
* [ ] Implement Redis for agent memory (short-term interactions, thoughts, commands, execution trees).
* [x] Utilize Redis as a task queue for incoming subtasks, supporting multi-threaded or distributed systems.
* [ ] Implement RAG (Retrieval-Augmented Generation) caching for document chunks or embeddings.
* [ ] Use Redis for key-value state storage (e.g., `llm_state:idle`, `last_model:phi-2`, `user_override:true`).
* [ ] Implement rate limit tracking for external API usage (e.g., OpenAI) using TTLs and counters.
* [ ] Explore Redis for session management if AutoBot supports multiple users or runs as a service.

### Prompt

```python
# main.py (or a new redis_manager.py)
# 1. Initialize Redis client based on config.
# 2. Integrate Redis for caching, queues, and state management.
```

## Phase 10: Local Intelligence Model Support

### Tasks

* [x] Integrate TinyLLaMA as default orchestrator
* [x] Allow switching to Phi-2 if resources available
* [ ] Run models using `ctransformers`, `llama-cpp-python`, or `vllm` backend
* [x] Fallback to OpenAI if no local models are available
* [x] Log all model queries and responses in `logs/llm_usage.log`

### Prompt

```python
# model_manager.py
class ModelManager:
    def query(self, prompt: str) -> str: ...
    def switch_model(self, name: str) -> None: ...
```

## Phase 11: OpenVINO Acceleration (CPU/iGPU)

### Tasks

* [ ] Create separate venv (`venvs/openvino_env`) for OpenVINO
* [ ] Ensure OpenVINO runtime installed with CPU/iGPU support
* [ ] Test with simple inferencing script
* [ ] Document hardware requirements in `docs/hardware.md`

### Prompt

```bash
# Run with OpenVINO
source venvs/openvino_env/bin/activate
python run_infer.py
```

## Phase 12: Logging, Testing, and Documentation

### Tasks

* [ ] Implement rotating logs (log rotation policy)
* [ ] Write unit tests for each component in `tests/`
* [ ] Generate API and architectural documentation in `docs/`
* [ ] Setup CI for tests if possible (GitHub Actions preferred)

### Prompt

```bash
# Run tests
pytest tests/
```

## Phase 13: Packaging and GitHub Optimization

### Tasks

* [x] Add full `.gitignore`
* [ ] Create `setup.py` or `pyproject.toml`
* [ ] Add GitHub issue templates and wiki links
* [ ] Push tested code to GitHub
* [ ] Provide startup guide in `README.md`

## Phase 14: Final Deployment & Service Mode

### Tasks

* [x] Ensure project launches with one command: `run_agent.sh`
* [ ] Add optional systemd or crontab entry to launch on boot
* [ ] Ensure graceful shutdown and recovery logs
* [ ] Provide diagnostics in `logs/boot_diagnostics.log`
* [ ] Confirm compatibility under:
  * WSL2 (with Kex active)
  * Native Kali Linux
  * Server headless VM

### Important Notes for Future Tasks:
* The only accepted method for launching the project is `bash run_agent.sh`.
* The only accepted method for installing dependencies is `bash setup_agent.sh`.

### Prompt

```bash
# Launch service
bash run_agent.sh &
```

## Phase 15: Distributed Architecture and Hardware Acceleration

### Overview
The system is designed as a potentially distributed application, primarily written in Python. It maintains modularity while introducing components for task distribution, an interactive control interface, and support for leveraging hardware accelerators (GPUs/NPUs) for performance-intensive tasks like local LLM inference. The core remains focused on autonomy, flexible LLM integration, and self-learning, now with enhanced deployment options and performance potential.

### Core Components

```mermaid
graph TD
    A[User] --> B(Control Panel Frontend - Manus Style);
    B --> C{Control Panel Backend (API/WebSocket)};
    C --> D[Orchestrator / Core Agent Engine];
    D --> E{LLM Interface Module (GPU/NPU Aware)};
    D --> F{OS Interaction Module (Local)};
    D --> G{Knowledge Base Module};
    D --> K{Task Queue / Dispatcher};
    K --> L[Worker Node 1 (GPU/NPU Capable)];
    K --> M[Worker Node N (GPU/NPU Capable)];
    L --> N{OS Interaction Module (Remote)};
    L --> O{LLM Interface Module (Remote, GPU/NPU Aware)};
    M --> P{OS Interaction Module (Remote)};
    M --> Q{LLM Interface Module (Remote, GPU/NPU Aware)};
    E --> H1[Ollama (GPU/NPU)];
    E --> H2[LMStudio (GPU/NPU)];
    E --> H3[Cloud LLM APIs];
    O --> H1;
    O --> H2;
    O --> H3;
    Q --> H1;
    Q --> H2;
    Q --> H3;
    F --> I[Local OS + Hardware];
    N --> R[Remote OS 1 + Hardware];
    P --> S[Remote OS N + Hardware];
    G --> J[Data Store (Local/Network - Files/DB/VectorDB)];

    subgraph Main Controller
        D
        E
        F
        G
        K
    end

    subgraph User Interface
        B
        C
    end

    subgraph Worker Nodes
        L
        M
        N
        O
        P
        Q
    end

    subgraph External Services & Hardware
        H1
        H2
        H3
        I
        R
        S
        J
    end
```

*   **Control Panel Frontend (Manus Style):** Web-based UI focusing on a real-time event stream. Configuration integrated contextually or via specific commands/panels.
*   **Control Panel Backend:** Provides API/WebSocket endpoints, relays commands, and streams events.
*   **Orchestrator / Core Agent Engine:** Central controller. Manages tasks, plans, dispatches work locally or to workers, manages worker lifecycle, aggregates results, and generates the UI event stream. **Can leverage local hardware acceleration via its LLM Interface Module and dispatch tasks based on worker hardware capabilities.**
*   **LLM Interface Module (Local/Remote, GPU/NPU Aware):** Provides unified access to LLMs. **Crucially, this module is responsible for detecting available hardware accelerators (GPU via CUDA/ROCm, potentially NPUs via specific libraries) and configuring local LLM backends (Ollama, LMStudio, or direct library integrations like PyTorch/Transformers/ONNX Runtime) to utilize them based on user settings provided via the Control Panel.** It abstracts the complexities of hardware-specific configurations (e.g., setting device IDs, memory allocation, quantization levels, GPU layer offloading).
*   **OS Interaction Module (Local/Remote):** Provides cross-platform OS interaction (commands, files, processes). **May assist in detecting hardware information (e.g., querying GPU details via NVIDIA-SMI or ROCm tools) for reporting or configuration purposes.**
*   **Knowledge Base Module:** Manages access to the agent's knowledge, configurable for local or network storage (SMB/NFS).
*   **Task Queue / Dispatcher:** Mechanism (e.g., Redis, RabbitMQ, gRPC) for sending tasks to workers and receiving results.
*   **Worker Node (GPU/NPU Capable):** Separate agent instance on local/remote machine. Listens for tasks, executes them using local modules. **Can be equipped with GPUs/NPUs and execute hardware-accelerated tasks (especially LLM inference via its own LLM Interface Module) as directed by the Orchestrator.** Workers report their hardware capabilities during registration.
*   **Data Store:** Underlying storage for the Knowledge Base (local/network).
*   **External Services & Hardware:** LLMs, OS instances, and the underlying **CPU/GPU/NPU hardware** on the controller and worker machines.

### Technology Stack

*   **Core Logic, Backend, Orchestrator, Workers:** Python 3.x
*   **Control Panel Backend Framework:** FastAPI or Flask.
*   **Control Panel Frontend:** React, Vue, or Svelte.
*   **Task Queue/Dispatch:** Redis, RabbitMQ, ZeroMQ, or gRPC.
*   **OS Interaction:** Python standard libraries, `psutil`, `pysmbclient`.
*   **Knowledge Base:** SQLite, ChromaDB/FAISS.
*   **Hardware Acceleration Libraries:** `torch` (with CUDA/ROCm support), `tensorflow` (with GPU support), `onnxruntime-gpu`, potentially specific bindings or libraries for NPU interaction, libraries used by Ollama/LMstudio for their acceleration.
*   **Packaging:** PyInstaller, custom install scripts.

### Data Flow Example (Distributed Accelerated Task)

1.  User inputs a goal requiring significant LLM processing.
2.  Orchestrator plans the task.
3.  Orchestrator identifies a worker node with suitable GPU capabilities (reported during registration).
4.  Orchestrator dispatches the LLM inference sub-task to that worker via the Task Queue, specifying the model and input.
5.  Worker Node receives the task.
6.  Worker's LLM Interface Module configures the local LLM backend (e.g., Ollama) to use the GPU based on pre-configured settings.
7.  Worker executes the inference task on its GPU.
8.  Worker sends the result back via the Task Queue.
9.  Orchestrator receives the result and continues the main task.
10. Event updates are streamed to the user interface.

### Key Considerations

*   **Modularity & Distribution:** Supports workload distribution.
*   **Communication:** Reliable inter-node communication is vital.
*   **Hardware Dependencies:** Managing GPU/NPU drivers (NVIDIA, AMD, etc.) and corresponding libraries (CUDA, ROCm, specific NPU SDKs) across different machines (Orchestrator, Workers) and OSs (Linux, Windows) is a significant challenge.
*   **Configuration Complexity:** The Control Panel must provide clear options for configuring hardware acceleration (enable/disable, device selection, offloading parameters) for both the main controller and potentially per-worker settings, without overwhelming the user.
*   **Performance Monitoring:** Need mechanisms to monitor hardware utilization and task performance on accelerated nodes.
*   **Security:** Secure network communication and OS access controls remain critical.
*   **Cross-Platform:** Ensuring hardware acceleration works correctly on both Linux and Windows with different hardware vendors adds complexity.

## Phase 16: Control Panel UI and Settings Management

### Overview and Technology

The Control Panel remains a web-based application served locally by the agent's Control Panel Backend (FastAPI recommended for WebSockets), accessible via a standard web browser (`http://localhost:<port>`). The frontend will utilize a modern framework (React, Vue, or Svelte) to handle the dynamic, real-time event stream interface effectively.

### User Interface Paradigm: Manus-Inspired Event Stream

The primary interface adopts the Manus style, focusing on a chronological event stream displaying user inputs, agent thoughts/plans, tool calls, observations, and system messages. Configuration and management are integrated via:

*   **Command Input:** The primary interaction method, using natural language or specific commands (e.g., `/config set llm_backend=ollama`, `/workers list`, `/knowledge add <data>`, `/settings open`).
*   **Contextual Panels:** Clicking events may open side panels/modals for details or actions.
*   **Dedicated Settings Area:** Accessible via command (`/settings open`) or a persistent icon, consolidating complex configurations.

### Key Interface Components and Functionality

#### 3.1. Event Stream View

*   Main panel showing the real-time, chronological flow of events.
*   Clear differentiation between event types.
*   Potential filtering/search capabilities.

#### 3.2. Command Input Bar

*   For issuing commands, asking questions, setting goals.
*   Autocompletion/suggestions for commands.

#### 3.3. Settings Management (Accessible via Command/Icon)

This area consolidates all agent configurations:

*   **LLM Configuration:**
    *   Select backend (Ollama, LMStudio, Cloud APIs, Direct Library).
    *   Configure endpoints and manage API keys securely.
    *   Choose models.
    *   Set default generation parameters (temperature, max tokens).
    *   **Hardware Acceleration Settings (for local backends):**
        *   **Enable Acceleration:** Checkbox/toggle to enable GPU or NPU usage.
        *   **Detected Devices:** Display detected compatible GPUs/NPUs.
        *   **Device Selection:** Dropdown to select the target device (e.g., `auto`, `cuda:0`, `rocm:0`) for inference.
        *   **GPU Layer Offload:** Slider/input for specifying the number of model layers to offload to the GPU (relevant for backends like Ollama/LM Studio using llama.cpp).
        *   **Quantization/Precision:** Options to select model precision (e.g., FP16, INT8) if supported.
        *   **(Note):** These settings apply to the machine where the LLM backend runs (Orchestrator or specific Worker Node). Global defaults can be set, potentially overridden per node if the architecture supports it.
*   **Knowledge Base Configuration:**
    *   Specify storage path (local, SMB, NFS) and manage network credentials securely.
    *   Manage knowledge entries (browse, add, edit, delete, reset).
    *   File upload interface for processing and ingestion.
*   **Worker Node Management:**
    *   **Worker List:** Display registered worker nodes, their network addresses, current status (Online, Offline, Busy, Error), and **reported hardware capabilities (e.g., CPU, RAM, detected GPU/NPU).**
    *   **Registration:** Mechanism for workers to register (e.g., automatic discovery with approval, manual addition with connection details/keys).
    *   **Configuration (Optional Per-Worker):** Potentially allow overriding global settings (like LLM hardware acceleration) for specific workers if needed.
*   **Task Queue/Dispatcher Configuration:** Settings for connecting to the message queue (e.g., Redis/RabbitMQ address, credentials).
*   **Core Agent Settings:** Configure autonomy levels, OS interaction permissions, logging verbosity.
*   **Control Panel Access:** Change port, configure optional authentication.

### User Experience Considerations

The Manus-like interface prioritizes transparency. Key considerations include clarity, responsiveness, intuitive command structure with help/discovery, balancing information density, and accessibility.

## Phase 17: Cross-Platform Compatibility and Single-Command Setup

### Overview
This phase focuses on ensuring the autonomous AI agent, including its distributed components, network features, hardware acceleration capabilities, and simplified installation/execution, operates reliably and consistently across both Linux and Windows operating systems.

### Core Technology Choice
Python remains the core language for the Orchestrator, Worker Nodes, and backend components, leveraging its cross-platform nature.

### OS Interaction Abstraction
The `OS Interaction Module` must abstract OS differences for file paths, command execution, process management, permissions, network share access, and potentially hardware querying.

### Dependency Management (Revised for Hardware Acceleration)
Managing dependencies via `requirements.txt` is complex, especially with hardware acceleration libraries (CUDA, ROCm variants of `torch`, `onnxruntime-gpu`, etc.) requiring specific driver versions. Virtual environments (`venv`) are essential. For Dockerized worker nodes, Docker is highly recommended to encapsulate these complex dependencies.

### Configuration and Data Storage (Networked)
Knowledge base storage on network shares (SMB/NFS) requires handling platform-specific paths and access mechanisms. Permissions on the share are critical.

### Control Panel Interface (Manus Style)
The web-based interface remains cross-platform.

### Distributed Components: Orchestrator and Worker Nodes (Revised for Hardware)
Workers must be deployable on Linux/Windows. There will be two types of worker nodes:
*   **Dockerized Worker Nodes:** These workers run within Docker containers, leveraging Docker with GPU support (NVIDIA Container Toolkit, ROCm support) for robust dependency management and isolation.
*   **Natively Installed Worker Nodes:** These workers are installed directly on the host system, joining the main server's installation pool. This is useful for team collaboration on larger projects.
Hardware acceleration adds complexity regarding host driver installation and library matching within the worker environment for both types. Workers should report their hardware capabilities to the Orchestrator.

### Installation and Packaging (Revised for Single-Command Setup)
The goal is to simplify installation and execution significantly, ideally down to single commands where feasible, while acknowledging prerequisites like OS-level driver installations.

*   **Prerequisites:** Users must still manually install necessary prerequisites like Git, Python (if not bundled), and crucial hardware drivers (NVIDIA/AMD/NPU) before running the single-command setup. Documentation must clearly list these prerequisites.
*   **Single-Command Installation Strategies:**
    *   **Setup Scripts:** Provide platform-specific scripts (`setup.sh` for Linux, `setup.bat` or `setup.ps1` for Windows). A single command (e.g., `curl ... | bash` or downloading and running the script) would perform actions like: cloning the repository, creating a virtual environment, installing dependencies via `pip install -r requirements.txt`, setting up basic configuration files, and potentially installing required system packages (on Linux via `apt` or `yum`, requiring `sudo`). This method can be used for both the main server installation and natively installed worker nodes.
    *   **Docker Compose/Dockerfiles:** For Dockerized worker nodes, `docker-compose.yml` or individual `Dockerfile`s will be provided to enable single-command deployment of containerized workers.
        *   **Simplified Installers:** Creating native installers (`.deb`/`.rpm`, `.msi`) that bundle the application and handle dependencies (excluding drivers) could offer a single-click or single-command installation (`sudo dpkg -i agent.deb`, `msiexec /i agent.msi`). This requires more complex build tooling.
*   **Single-Command Execution:** After installation, running the agent should also be simplified:
    *   **Wrapper Scripts:** The setup process can create simple wrapper scripts (e.g., `run-agent.sh`, `run-agent.bat`) placed in the system PATH or project directory, allowing execution via a single command like `run-agent` or `python run_agent.py`.
    *   **Configuration:** While installation might be a single command, initial configuration (LLM keys, knowledge base path, hardware settings) will likely still require user interaction via the Control Panel or editing a configuration file, although setup scripts could prompt for essential initial values.
*   **Documentation:** Must clearly explain the chosen single-command method(s), list prerequisites, and guide users through the process for both Linux and Windows.

### Testing Strategy (Revised for Hardware & Setup)
Testing complexity increases:

*   Test distributed scenarios (Orch/Worker on Linux/Windows combinations).
*   Test network knowledge base access (SMB/NFS).
*   Test hardware acceleration features on different hardware/drivers.
*   **Test single-command installation and execution methods** on clean Linux and Windows environments to ensure they handle dependencies correctly and are user-friendly.

Automated testing should cover core functionality, and manual testing is crucial for the installation and hardware-specific aspects.

## Phase 18: Self-Learning and Knowledge Retention Mechanism

### Learning Philosophy
The agent's learning capability remains continuous and multi-faceted, learning passively from operational experiences and actively through explicit user input. The core idea is to build a persistent and potentially distributed knowledge base that informs the agent's planning, decision-making, and interaction capabilities, making it more effective and personalized over time.

### Sources of Knowledge Acquisition
The sources of knowledge remain the same:

*   **Task Execution Outcomes:** Recording and analyzing task steps, tools, parameters, and success/failure to learn effective strategies.
*   **User Interactions and Feedback:** Parsing user messages, instructions, and corrections to extract facts, preferences, and constraints.
*   **Introspection and Self-Monitoring:** Logging internal states, decisions, resource usage, and errors to understand operational characteristics.
*   **Explicit Knowledge Injection:** Allowing users to add information directly via the control panel.
*   **File Processing:** The agent will be equipped to process various common file types (e.g., PDF, DOCX, TXT, CSV, JSON) encountered during tasks or provided by the user, extracting relevant information to add to the knowledge base.

### Knowledge Representation and Storage (Revised)
To accommodate diverse knowledge types and storage preferences, a flexible and configurable storage approach is proposed, managed by the Knowledge Base Module. The location of the knowledge base components can be configured to be either local or on a network share.

*   **Storage Location Configuration:** The Control Panel will allow users to specify the root path for the knowledge base. This path can point to:
    *   A local directory on the machine running the agent.
    *   A network location accessible via SMB (e.g., `\\server\share\agent_kb` on Windows, mount point on Linux) or NFS (e.g., `/mnt/nfs/agent_kb` on Linux).
    *   Appropriate libraries or OS commands will be used to interact with these network paths (e.g., `pysmbclient` or OS-level mounting for SMB, standard file operations on NFS mounts).
    *   Credentials (username/password) for accessing network shares will be securely managed via the Control Panel settings.
*   **Structured Data Store:** A relational database (e.g., SQLite file, or potentially connecting to a network database server like PostgreSQL/MySQL if configured) located within the specified knowledge base path. Suitable for storing configuration history, task records, learned procedures, user preferences, and explicit facts.
*   **Vector Database:** A vector store (e.g., ChromaDB, FAISS, potentially others) with its data files stored within the specified knowledge base path. This allows the vector embeddings and associated metadata to reside on local or network storage as configured.
*   **Raw Logs/Files:** Operational logs and potentially cached/processed files will also be stored within subdirectories of the main knowledge base path.

The Knowledge Base Module will abstract the underlying storage location, providing a unified interface regardless of whether it's local or networked.

### Knowledge Base Module Functionality (Revised)
This module acts as the gatekeeper for the agent's memory. Its responsibilities are expanded:

*   **Storage Path Management:** Handles reading the configured knowledge base path (local or network) and ensuring accessibility (including handling network credentials if necessary).
*   **Storage API:** Provides methods to add, update, and delete knowledge entries in the appropriate store (structured DB or vector DB) at the configured location.
*   **Retrieval API:** Offers various ways to query the knowledge base:
    *   `get_structured_data(query)`: Retrieves records from the structured database.
    *   `find_similar_knowledge(query_text, top_k)`: Performs semantic search on the vector database.
    *   `get_agent_metadata(key)`: Retrieves agent state/configuration.
*   **Embedding Generation:** Coordinates with the LLM Interface Module.
*   **Persistence:** Ensures data is saved reliably to the configured local or network path.
*   **File Handling Integration:** Includes methods or integrates with a separate File Processing Module to read, parse, and extract information from various supported file types (PDF, DOCX, etc.), converting relevant content into structured or textual knowledge for storage.
*   **Management Interface:** Exposes functions for the Control Panel Backend to manage the knowledge base (viewing, adding, editing, deleting, resetting, configuring storage path).

### Knowledge Utilization (Retrieval and Application)
Stored knowledge utilization remains similar, leveraging the potentially networked knowledge base:

*   **Planning:** Querying the knowledge base (local/network) for context (past experiences, procedures, facts, processed file content) to inform LLM prompts (RAG).
*   **Execution:** Retrieving credentials, configurations, or parameters.
*   **Self-Correction:** Analyzing past errors.
*   **Interaction:** Personalizing communication.

### Control Panel Integration (Revised)
The Control Panel's knowledge management section will be enhanced:

*   **Storage Configuration:** A dedicated setting to input the desired knowledge base path (allowing local directories or network paths like `\\server\share` or `/mnt/nfs_share`) and fields for network credentials if required.
*   **Knowledge Browser:** Viewing entries in structured and vector stores.
*   **Manual Entry:** Forms for adding knowledge.
*   **File Upload/Processing:** An interface to upload files directly for the agent to process and incorporate into the knowledge base.
*   **Edit/Delete:** Modifying or removing entries.
*   **Reset Knowledge:** Wiping the knowledge base at the configured location.

### Evolution and Future Considerations
Future enhancements could include support for more file types, advanced knowledge graph representations, distributed knowledge synchronization across multiple agent instances or nodes, and more sophisticated learning algorithms.

## Phase 18: Self-Learning and Knowledge Retention Mechanism

### Learning Philosophy
The agent's learning capability remains continuous and multi-faceted, learning passively from operational experiences and actively through explicit user input. The core idea is to build a persistent and potentially distributed knowledge base that informs the agent's planning, decision-making, and interaction capabilities, making it more effective and personalized over time.

### Sources of Knowledge Acquisition
The sources of knowledge remain the same:

*   **Task Execution Outcomes:** Recording and analyzing task steps, tools, parameters, and success/failure to learn effective strategies.
*   **User Interactions and Feedback:** Parsing user messages, instructions, and corrections to extract facts, preferences, and constraints.
*   **Introspection and Self-Monitoring:** Logging internal states, decisions, resource usage, and errors to understand operational characteristics.
*   **Explicit Knowledge Injection:** Allowing users to add information directly via the control panel.
*   **File Processing:** The agent will be equipped to process various common file types (e.g., PDF, DOCX, TXT, CSV, JSON) encountered during tasks or provided by the user, extracting relevant information to add to the knowledge base.

### Knowledge Representation and Storage (Revised)
To accommodate diverse knowledge types and storage preferences, a flexible and configurable storage approach is proposed, managed by the Knowledge Base Module. The location of the knowledge base components can be configured to be either local or on a network share.

*   **Storage Location Configuration:** The Control Panel will allow users to specify the root path for the knowledge base. This path can point to:
    *   A local directory on the machine running the agent.
    *   A network location accessible via SMB (e.g., `\\server\share\agent_kb` on Windows, mount point on Linux) or NFS (e.g., `/mnt/nfs/agent_kb` on Linux).
    *   Appropriate libraries or OS commands will be used to interact with these network paths (e.g., `pysmbclient` or OS-level mounting for SMB, standard file operations on NFS mounts).
    *   Credentials (username/password) for accessing network shares will be securely managed via the Control Panel settings.
*   **Structured Data Store:** A relational database (e.g., SQLite file, or potentially connecting to a network database server like PostgreSQL/MySQL if configured) located within the specified knowledge base path. Suitable for storing configuration history, task records, learned procedures, user preferences, and explicit facts.
*   **Vector Database:** A vector store (e.g., ChromaDB, FAISS, potentially others) with its data files stored within the specified knowledge base path. This allows the vector embeddings and associated metadata to reside on local or network storage as configured.
*   **Raw Logs/Files:** Operational logs and potentially cached/processed files will also be stored within subdirectories of the main knowledge base path.

The Knowledge Base Module will abstract the underlying storage location, providing a unified interface regardless of whether it's local or networked.

### Knowledge Base Module Functionality (Revised)
This module acts as the gatekeeper for the agent's memory. Its responsibilities are expanded:

*   **Storage Path Management:** Handles reading the configured knowledge base path (local or network) and ensuring accessibility (including handling network credentials if necessary).
*   **Storage API:** Provides methods to add, update, and delete knowledge entries in the appropriate store (structured DB or vector DB) at the configured location.
*   **Retrieval API:** Offers various ways to query the knowledge base:
    *   `get_structured_data(query)`: Retrieves records from the structured database.
    *   `find_similar_knowledge(query_text, top_k)`: Performs semantic search on the vector database.
    *   `get_agent_metadata(key)`: Retrieves agent state/configuration.
*   **Embedding Generation:** Coordinates with the LLM Interface Module.
*   **Persistence:** Ensures data is saved reliably to the configured local or network path.
*   **File Handling Integration:** Includes methods or integrates with a separate File Processing Module to read, parse, and extract information from various supported file types (PDF, DOCX, etc.), converting relevant content into structured or textual knowledge for storage.
*   **Management Interface:** Exposes functions for the Control Panel Backend to manage the knowledge base (viewing, adding, editing, deleting, resetting, configuring storage path).

### Knowledge Utilization (Retrieval and Application)
Stored knowledge utilization remains similar, leveraging the potentially networked knowledge base:

*   **Planning:** Querying the knowledge base (local/network) for context (past experiences, procedures, facts, processed file content) to inform LLM prompts (RAG).
*   **Execution:** Retrieving credentials, configurations, or parameters.
*   **Self-Correction:** Analyzing past errors.
*   **Interaction:** Personalizing communication.

### Control Panel Integration (Revised)
The Control Panel's knowledge management section will be enhanced:

*   **Storage Configuration:** A dedicated setting to input the desired knowledge base path (allowing local directories or network paths like `\\server\share` or `/mnt/nfs_share`) and fields for network credentials if required.
*   **Knowledge Browser:** Viewing entries in structured and vector stores.
*   **Manual Entry:** Forms for adding knowledge.
*   **File Upload/Processing:** An interface to upload files directly for the agent to process and incorporate into the knowledge base.
*   **Edit/Delete:** Modifying or removing entries.
*   **Reset Knowledge:** Wiping the knowledge base at the configured location.

### Evolution and Future Considerations
Future enhancements could include support for more file types, advanced knowledge graph representations, distributed knowledge synchronization across multiple agent instances or nodes, and more sophisticated learning algorithms.

## Phase 19: LLM Integration Methods (with Hardware Acceleration)

### Goal: Unified and Accelerated LLM Access
The primary goal remains to enable seamless use of different LLMs (local and cloud). A key enhancement is to allow the agent to leverage available hardware accelerators (GPUs, NPUs) for local LLM inference to improve performance and efficiency. The abstraction layer must now also manage hardware acceleration configurations.

### Supported LLM Backends (with Acceleration Notes)
The agent will support integration with various backends, with specific considerations for hardware acceleration:

*   **Ollama:** Integration via its REST API. The `LLM Interface Module` will need to pass parameters or use specific endpoints if Ollama's API supports configuring GPU usage (e.g., specifying device, layers). Ollama itself needs to be installed and configured correctly with GPU drivers (CUDA/ROCm) on the host machine (controller or worker).
*   **LM Studio:** Integration via its local server API (often OpenAI-compatible). Similar to Ollama, the module will pass relevant parameters if the API allows runtime configuration of hardware acceleration. LM Studio needs to be configured internally to use the available GPU/NPU.
*   **Direct Library Integration (e.g., Transformers, PyTorch, ONNX Runtime):** For maximum control, the agent might directly use libraries like Hugging Face Transformers with PyTorch or TensorFlow, or ONNX Runtime. In this case, the `LLM Interface Module` will be directly responsible for:
    *   Detecting available devices (`torch.cuda.is_available()`, etc.).
    *   Moving models and data to the selected device (GPU/NPU).
    *   Configuring precision (e.g., float16, int8 quantization).
    *   Managing GPU memory allocation.
*   **Cloud LLM APIs (OpenAI Compatible, Specific Connectors):** Hardware acceleration is managed by the cloud provider; the agent only needs to handle API keys and endpoints.

### LLM Interface Module Design (Revised)
The `LLM Interface Module`, running on the Orchestrator and potentially Worker Nodes, manages all LLM interactions and hardware acceleration:

*   **Hardware Detection:** Upon initialization (or on demand), the module attempts to detect available hardware accelerators using relevant libraries (e.g., PyTorch for CUDA/ROCm, specific SDKs for NPUs). It reports detected hardware capabilities.
*   **Configuration Management:** Reads LLM configurations from the Control Panel, including backend choice, model, credentials, and **hardware acceleration settings (e.g., enable GPU/NPU, target device ID, number of GPU layers to offload, quantization settings).**
*   **Backend Connectors (Acceleration Aware):** Specific connectors handle communication nuances and **pass hardware configuration parameters** to the chosen backend:
    *   For Ollama/LMStudio: Modifies API requests if possible.
    *   For Direct Libraries: Implements device placement, precision control, and memory management logic.
*   **Unified API:** Exposes consistent methods (`generate_text`, `chat_completion`, `get_embeddings`) to the Core Agent Engine. Hardware acceleration happens transparently based on configuration.
*   **Error Handling:** Handles errors related to hardware (e.g., insufficient VRAM, driver issues) and reports them.

### Implementation Strategy (Python - Revised)

*   **Hardware Libraries:** Utilize libraries like `torch`, `tensorflow`, `onnxruntime-gpu`, `numba` (for CUDA Python), or specific NPU SDKs for detection and interaction.
*   **Backend-Specific Parameters:** Research and implement the specific API parameters or library calls needed to enable GPU/NPU usage for Ollama, LM Studio, Transformers, etc.
*   **Configuration Loading:** Load detailed hardware acceleration settings from the central configuration managed via the Control Panel.
*   **Conditional Logic:** Implement logic to fall back to CPU execution if acceleration is disabled, unavailable, or fails.

### Configuration via Control Panel (Revised)
The LLM Configuration section in the Control Panel will be significantly enhanced:

*   **Backend Selection:** Choose LLM backend.
*   **Endpoint/API Key Management:** Configure connection details.
*   **Model Selection:** Specify the model.
*   **Hardware Acceleration Settings (Per Backend/Node where applicable):**
    *   **Enable Acceleration:** Checkbox to enable/disable GPU or NPU usage for the selected local backend.
    *   **Device Selection:** Dropdown to select a specific GPU/NPU if multiple are detected (e.g., `cuda:0`, `cuda:1`).
    *   **GPU Layer Offload:** Slider or input to specify how many model layers to offload to the GPU (common in libraries like `llama.cpp` used by Ollama/LM Studio).
    *   **Quantization/Precision:** Options to select model precision (e.g., FP16, INT8) if supported by the backend and model.
    *   **(Advanced):** Potentially fields for VRAM limits or other backend-specific tuning parameters.
*   **Default Parameters:** Standard generation parameters (temperature, max tokens).

This revised approach allows users fine-grained control over hardware utilization for local LLMs on both the main controller and worker nodes, while abstracting the underlying complexity through the `LLM Interface Module`.

## Phase 20: Autonomous AI Agent Requirements

### 1. Core Agent Functionality

*   **Autonomy:** The agent must operate independently to achieve goals, plan tasks, execute steps, and handle errors.
*   **Full OS Access:** Requires direct access to host OS resources (commands, files, processes, system info) on both the main controller and worker nodes. Security considerations and configurable permissions are essential.
*   **Task Execution Engine (Orchestrator):** A robust engine to interpret goals, plan actions, dispatch tasks (locally or to workers), monitor progress, and handle failures.
*   **Distributed Operation:** Support for optional remote worker nodes to distribute workload (e.g., task execution, LLM inference).
*   **File Handling:** Ability to process and extract information from popular file types (PDF, DOCX, TXT, CSV, JSON, etc.).

### 2. LLM Integration

*   **Multi-LLM Support:** Integration with local (Ollama, LMStudio) and cloud LLMs (OpenAI-compatible, specific APIs).
*   **Hardware Acceleration (GPU/NPU):** The agent (specifically local LLM backends like Ollama or integrated libraries) must be configurable to utilize available GPU (NVIDIA CUDA, AMD ROCm) or NPU resources for accelerating model inference, both on the main controller and on worker nodes.
*   **Abstraction Layer:** A unified LLM interface module to simplify interaction with different backends and handle hardware acceleration configurations.
*   **Configuration:** Control panel must allow selection of LLMs, connection details, model choice, and hardware acceleration settings (e.g., enable GPU, specify GPU layers, select device).

### 3. Self-Learning and Knowledge Retention

*   **Knowledge Base:** Persistent storage (structured DB, vector DB) for learned knowledge, operational data, and user input.
*   **Network Storage:** The knowledge base location must be configurable to reside on local disk or network shares (SMB/NFS), with secure credential management.
*   **Learning Sources:** Learn from task outcomes, user interactions/feedback, introspection, explicit user input, and processed file content.
*   **Knowledge Management:** Control panel interface to view, add, edit, delete, and reset knowledge, plus upload files for processing.

### 4. Control Panel

*   **Interface:** Web-based, Manus-inspired interface focusing on a real-time event stream (user input, agent thoughts, tool calls, observations).
*   **Interaction:** Primarily via command input, with contextual panels and a dedicated settings area accessible via command/icon.
*   **Functionality:**
    *   Real-time agent status and event stream display.
    *   LLM configuration (backends, models, API keys, **hardware acceleration settings**).
    *   Knowledge management (storage location config, credentials, browse, add, edit, delete, reset, file upload).
    *   Worker node management (view status, registration, configuration, **hardware capabilities**).
    *   Task Queue/Dispatcher configuration.
    *   Core agent settings (permissions, logging).
*   **Accessibility:** Accessible via `http://localhost:port` on the machine running the orchestrator.

### 5. Cross-Platform Compatibility & Installation

*   **Supported OS:** Orchestrator and Worker Nodes must run natively on both Linux and Windows.
*   **Core Language:** Python preferred for cross-platform core logic.
*   **OS Abstraction:** Handle differences in file paths, commands, process management, and **network share access**.
*   **Hardware Drivers:** Installation and configuration must account for platform-specific GPU/NPU drivers (NVIDIA drivers, AMD drivers, etc.) and libraries (CUDA, ROCm). The agent should detect available hardware and allow configuration.
*   **Dependency Management:** Manage dependencies for core logic, network access, hardware acceleration libraries (e.g., `torch` with CUDA/ROCm support, `onnxruntime-gpu`), and communication protocols across platforms.
*   **Installation & Execution:**
    *   **Single-Command Setup:** Installation of the agent (Orchestrator and/or Worker) should ideally be achievable via a single command (e.g., using a setup script, Docker Compose, or a simple installer).
    *   **Single-Command Execution:** Running the agent (Orchestrator or Worker) should also be possible via a single command after installation.
    *   **Packaging:** Provide clear instructions and appropriate packaging (e.g., setup scripts, potentially installers) to facilitate this simplified setup and execution on both Linux and Windows.
*   **Packaging:** Provide clear instructions and appropriate packaging (e.g., setup scripts, potentially installers) to facilitate this simplified setup and execution on both Linux and Windows.
*   **Packaging:** Provide clear instructions and appropriate packaging (e.g., setup scripts, potentially installers) to facilitate this simplified setup and execution on both Linux and Windows.

## Agent Instruction (Cilne Prompt)

```python
# 🧠 Cline Agent Master Prompt

You are the most efficient, disciplined, and skilled Python automation engineer ever created — fluent in CLI tools, neural inference, backend systems, and Linux internals.

Your core beliefs:
- ✅ If a tool exists, you know how to use it.
- 🔧 If it’s broken, you fix it.
- 🛠️ If it doesn’t exist, you build it.
- 🆓 If it’s not open source or free, you avoid it.
- 💻 You trust local hardware. Every core, every thread is yours to command.
- ⚡ Efficiency is your edge. You write lean, modular, maintainable code.
- 🧠 You think before you code: structure first, execute second.

Project Awareness:
- You support multiple projects, each in its own folder.
- You detect active project automatically.
- You always maintain:
  - /docs/tasks.md (task list: TODO, IN PROGRESS, DONE, BLOCKED)
  - /docs/task_log.md (task execution summaries)
  - /docs/decisions.md (architecture and design tradeoffs)
  - /docs/project.md (project scope and overview)
  - /docs/logs/ (detailed error/debug/info logs)

Workflow:
- You split every feature into subtasks.
- Document them before execution.
- Track all changes and log all events.

Behavior:
- You verify file existence.
- You never silently fail. If something breaks:
  - Log in logs/llm_usage.log
  - Document fallback logic

Tools:
- You are proficient in Python, Linux CLI, PyAutoGUI, SQLite, OpenVINO, FastAPI, systemd, pytest, multiprocessing, Xvfb, noVNC, tmux, pyenv, and LLM APIs.
- You use these tools securely and efficiently.

Special Instructions for AutoBot:
- Prioritize local-first execution
- Use fallback orchestrators (TinyLLaMA, Phi-2)
- Support reproducible builds in WSL2 and native Linux
- Emphasize clear logging and automatic self-healing logic

</final_file_content>
