## TODO

- [x] **Phase 1: Environment Setup and Bootstrap:** Inspect `setup_agent.sh` for errors and ensure it completes successfully.
- [x] **Phase 2: Agent Initialization and Configuration:** Inspect `main.py` for errors and ensure the agent initializes correctly.
- [x] **Phase 4: GUI Automation Interface:** Investigate the GUI integration issues and restore basic functionality using `pyautogui` and `Xvfb`.
- [x] **Phase 11: Final Deployment & Service Mode:** Ensure the agent launches with one command: `run_agent.sh`.
- [x] **Create a new frontend:** Moved the `materially-free-react-admin-template-1.0.0` GUI framework to `frontend/admin_gui/`.
- [ ] **Create a new frontend design:**remove all references to "Agent Zero", use a blue color palette for the dark UI, and ensure it is named AutoBot.
- [ ] **Connect frontend to backend:** Ensure the frontend correctly communicates with the backend API.
- [x] **Frontend control over backend:** Added a terminal modal to the frontend to allow execution of shell commands via the `/api/execute_command` endpoint.
- [x] **LLM Command Execution Capability:** Document that the LLM is equipped with the ability to run commands on the machine as a tool to achieve goals.
- [ ] **Integrate Redis:** Implement Redis for agent memory (short-term), task queuing, RAG caching, key-value state storage, rate limit tracking, and session management to enhance performance and real-time capabilities.
- [ ] **Define SQLite as Long-Term Memory:** Explicitly establish SQLite as the primary long-term memory backend for the agent, leveraging its performance, portability, and ease of integration. Explore optional enhancements like referencing markdown files and storing embeddings within SQLite.
- [ ] **Implement VNC Session with noVNC:** Integrate a Kex VNC session with noVNC embedded in the Web UI to enable real-time observation and control of the agent's desktop environment, including GUI task automation and human-in-the-loop takeover capabilities.
- [ ] **Implement Project State Tracking System:** Create `docs/status.md` to track project progress, core features, next steps, and phase promotion criteria. Ensure the LLM agent is self-aware of this status and add a visual indicator to the Web UI.

## Frontend Functionality (New GUI)

- [ ] **Implement "New Chat" functionality.**
- [ ] **Implement "Chat Reset" functionality.**
- [ ] **Fix "Import knowledge" and "Files" button:** Ensure they correctly open the file browser modal and do not redirect to a "Not Found" page.
- [ ] **Implement "Load Chat" functionality.**
- [ ] **Implement "Save Chat" functionality.**
- [ ] **Fix "History" button:** Resolve "Failed to fetch history" error.
- [ ] **Integrate "Context" modal:** Ensure it uses the new generic modal system correctly.
- [ ] **Move Preferences Section:**
    - [ ] Add a "Preferences" section to the left sidebar in the new GUI.
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
