## TODO

- [x] **Phase 1: Environment Setup and Bootstrap:** Inspect `setup_agent.sh` for errors and ensure it completes successfully.
- [x] **Phase 2: Agent Initialization and Configuration:** Inspect `main.py` for errors and ensure the agent initializes correctly.
- [x] **Phase 4: GUI Automation Interface (Partial):** Installed necessary dependencies (`pyautogui`, `mouseinfo`, `pillow`, `numpy`) and created `gui_controller.py` with initial `GUIController` class implementation for GUI automation tasks. Further integration with Xvfb and WSL2 compatibility checks are pending.
- [x] **Phase 11: Final Deployment & Service Mode:** Ensure the agent launches with one command: `run_agent.sh`.
- [x] **Create a new frontend:** Moved the `materially-free-react-admin-template-1.0.0` GUI framework to `frontend/admin_gui/`.
- [x] **Create a new frontend design:** Implemented Vue with Vite in `autobot-vue/` with a blue color palette for the dark UI, named AutoBot.
- [x] **Connect frontend to backend:** Ensure the frontend correctly communicates with the backend API via FastAPI endpoints.
- [x] **Frontend control over backend:** Added a terminal modal to the frontend to allow execution of shell commands via the `/api/execute_command` endpoint.
- [x] **LLM Command Execution Capability:** Document that the LLM is equipped with the ability to run commands on the machine as a tool to achieve goals.
- [x] **Integrate Redis:** Implemented Redis for agent memory (short-term) via `ChatHistoryManager` in `src/chat_history_manager.py`, with UI settings in `SettingsPanel.vue`. Task queuing is supported, but RAG caching, key-value state storage, rate limit tracking, and session management are pending.
- [ ] **Define SQLite as Long-Term Memory:** Explicitly establish SQLite as the primary long-term memory backend for the agent, leveraging its performance, portability, and ease of integration. Explore optional enhancements like referencing markdown files and storing embeddings within SQLite.
- [ ] **Implement VNC Session with noVNC:** Integrate a Kex VNC session with noVNC embedded in the Web UI to enable real-time observation and control of the agent's desktop environment, including GUI task automation and human-in-the-loop takeover capabilities.
- [ ] **Implement Project State Tracking System:** Create `docs/status.md` to track project progress, core features, next steps, and phase promotion criteria. Ensure the LLM agent is self-aware of this status and add a visual indicator to the Web UI.

## Frontend Functionality (Current GUI)

- [ ] **Implement "New Chat" functionality.**
- [ ] **Implement "Chat Reset" functionality.**
- [ ] **Fix "Import knowledge" and "Files" button:** Ensure they correctly open the file browser modal and do not redirect to a "Not Found" page.
- [ ] **Implement "Load Chat" functionality.**
- [ ] **Implement "Save Chat" functionality.**
- [ ] **Fix "History" button:** Resolve "Failed to fetch history" error.
- [ ] **Integrate "Context" modal:** Ensure it uses the current generic modal system correctly.
- [ ] **Move Preferences Section:**
    - [ ] Add a "Preferences" section to the left sidebar in the current GUI.
    - [ ] Move existing toggle buttons (Autoscroll, Dark mode, Speech, Show thoughts, Show JSON, Show utility messages) into this new preferences section.

## Frontend Improvements

- [x] **Compatibility:** Add vendor prefixes and modern equivalents for CSS properties like `-webkit-mask-image`, `-webkit-mask-position`, `-webkit-mask-repeat`, `-webkit-mask-size`, `-webkit-text-size-adjust`, `user-select`, `field-sizing`, `forced-color-adjust`, `scrollbar-color`, `scrollbar-width`, `text-size-adjust`, `text-wrap`.
- [x] **Performance:**
  - [x] Ensure resources use cache busting (URL patterns).
  - [x] Remove unneeded headers: `content-security-policy`, `x-xss-protection`.
- [x] **Security:**
  - [x] Include `x-content-type-options` header.
  - [x] Prefer `Cache-Control` over `Expires` header.
  - [x] Replace `X-Frame-Options` with `Content-Security-Policy` and `frame-ancestors` directive.
- [x] **Other:**
  - [x] Ensure CSS properties are listed in the correct order (e.g., `animation` after `-webkit-animation`).
  - [x] Add `id` or `name` attributes to form field elements.
  - [x] Move CSS inline styles to an external CSS file.
