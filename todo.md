## TODO

- [ ] **Phase 1: Environment Setup and Bootstrap:**
    - [ ] If inside WSL2, check if Kex is installed and ready for GUI fallback
    - [ ] Install system-level packages: `xvfb`, `libx11-dev`, `ffmpeg`, `libgl1`, `tk`, `build-essential`, etc.

- [ ] **Phase 2: Agent Initialization and Configuration:**
    - [ ] Validate API keys and credentials presence
    - [ ] Initialize plugin manager (scan `plugins/` folder)

- [ ] **Phase 3: Command Execution Engine:**
    - [ ] Secure command sandbox to avoid destructive operations
    - [ ] **Intelligent Command Inference:** Enhance the agent's ability to infer appropriate shell commands based on high-level goals, even if the exact command is not explicitly provided.
    - [ ] **Automatic Tool/Package Installation:** Implement logic to detect missing commands/applications and automatically install them (e.g., using `apt-get`, `pip`).
    - [ ] **Installation Tracking for Rollback:** Log all installations and system modifications to a persistent store to enable future rollback capabilities.

- [ ] **Phase 4: GUI Automation Interface:**
    - [ ] Setup `pyautogui` and `mouseinfo` under Xvfb virtual display
    - [ ] Create GUIController class to:
        - Capture screenshots
        - Simulate mouse/keyboard
        - Locate elements by image
        - Draw visual feedback (optional)
    - [ ] Ensure compatibility with Xvfb under WSL2
    - [ ] If running in WSL2, detect if `kex` is available and active; suggest starting `kex` session if GUI fails
    - [ ] **Integrate Kex VNC session with noVNC:** Implement a VNC session using Kex (TigerVNC) and embed noVNC in the Web UI for real-time observation and control of the agent's desktop environment, including visible GUI task automation and human-in-the-loop takeover capabilities.

- [ ] **Phase 5: Agent Orchestrator and Planning Logic:**
    - [ ] Auto-document completed tasks to `docs/tasks.md`
    - [ ] Prioritize self-improving tasks when idle (auto-tune)
    - [ ] Include error recovery from failed subtasks

- [ ] **Phase 6: Agent Self-Awareness and State Management:**
    - [ ] Implement a project state tracking system using `docs/status.md`.
    - [ ] Ensure the LLM agent is self-aware of its current phase, core features, and next steps by reading `docs/status.md` or `docs/tasks.md`.
    - [ ] Develop logic for the agent to propose phase promotions when criteria defined in `docs/status.md` are met.
    - [ ] Add a visual indicator in the Web UI to display the current phase and key status elements (e.g., `[ Phase X: Feature Name ] ✅ Logs ✓ ❌ Memory ✖ ❌ LLM UI`).

- [ ] **Phase 7: Agent Memory and Knowledge Base:**
    - [ ] Leverage SQLite for storing task logs, configuration changes, and command execution history.
    - [ ] Implement mechanisms to reference markdown files within SQLite (e.g., `doc_path`, `line_start`).
    - [ ] Explore storing embeddings as base64 or pickled blobs within SQLite if needed.

- [ ] **Phase 8: Interface and Web Control Panel:**
    - [ ] Use NoVNC or WebSocket proxy to stream desktop
    - [x] Show logs, currently running task, and options to interrupt/resume
    - [ ] Allow human-in-the-loop takeover if needed (interrupt/takeover button)
    - [ ] **Embed noVNC in the Web UI:** Integrate an iframe or dynamic viewer in `autobot-vue/index.html` to display the Kex VNC session, enabling real-time observation and control.

- [ ] **Phase 9: Redis Integration for Enhanced Performance:**
    - [x] Implement Redis for agent memory (short-term interactions, thoughts, commands, execution trees) via `ChatHistoryManager` in `src/chat_history_manager.py`.
    - [ ] Implement RAG (Retrieval-Augmented Generation) caching for document chunks or embeddings.
    - [ ] Use Redis for key-value state storage (e.g., `llm_state:idle`, `last_model:phi-2`, `user_override:true`).
    - [ ] Implement rate limit tracking for external API usage (e.g., OpenAI) using TTLs and counters.
    - [ ] Explore Redis for session management if AutoBot supports multiple users or runs as a service.

- [ ] **Phase 10: Local Intelligence Model Support:**
    - [ ] Run models using `ctransformers`, `llama-cpp-python`, or `vllm` backend

- [ ] **Phase 11: OpenVINO Acceleration (CPU/iGPU):**
    - [ ] Create separate venv (`venvs/openvino_env`) for OpenVINO
    - [ ] Ensure OpenVINO runtime installed with CPU/iGPU support
    - [ ] Test with simple inferencing script
    - [ ] Document hardware requirements in `docs/hardware.md`

- [ ] **Phase 12: Logging, Testing, and Documentation:**
    - [ ] Implement rotating logs (log rotation policy)
    - [ ] Write unit tests for each component in `tests/`
    - [ ] Generate API and architectural documentation in `docs/`
    - [ ] Setup CI for tests if possible (GitHub Actions preferred)

- [ ] **Phase 13: Packaging and GitHub Optimization:**
    - [ ] Create `setup.py` or `pyproject.toml`
    - [ ] Add GitHub issue templates and wiki links
    - [ ] Push tested code to GitHub
    - [ ] Provide startup guide in `README.md`

- [ ] **Phase 14: Final Deployment & Service Mode:**
    - [ ] Add optional systemd or crontab entry to launch on boot
    - [ ] Ensure graceful shutdown and recovery logs
    - [ ] Provide diagnostics in `logs/boot_diagnostics.log`
    - [ ] Confirm compatibility under:
        - WSL2 (with Kex active)
        - Native Kali Linux
        - Server headless VM

## Frontend Improvements (General)

- [x] **Create a new frontend design:** Implemented Vue with Vite in `autobot-vue/` with a blue color palette for the dark UI, named AutoBot.
- [x] **Connect frontend to backend:** Ensure the frontend correctly communicates with the backend API via FastAPI endpoints.

## Phase 15: Web Interaction

### Tasks
- [ ] **Implement Terminal Web Browsing:** Integrate a text-based web browser (e.g., `lynx`, `w3m`) to allow the agent to browse the web and extract information via the terminal.
    - [ ] Identify and install a suitable terminal-based web browser.
    - [ ] Create a new task type (`terminal_web_browse`) to execute the browser with a given URL and capture its output.
    - [ ] Process the captured webpage content for LLM consumption.
    - [ ] Ensure the LLM can intelligently use this tool for information gathering.
