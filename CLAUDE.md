# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🚀 QUICK REFERENCE FOR CLAUDE CODE

### Critical Rules for Autonomous Operations
1. **ALWAYS** test and document before committing - NO EXCEPTIONS
2. **ALWAYS** run flake8 checks before committing: `flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503`
3. **NEVER** hardcode values - use `src/config.py` for all configuration
4. **ALWAYS** test changes with: `./run_agent.sh --test-mode` before full deployment
5. **REQUIRED**: Update docstrings following Google style for any function changes
6. **CRITICAL**: Backup `data/` before schema changes to knowledge_base.db or memory_system.db
7. **MANDATORY**: Test Phase 9 components with `python test_phase9_ai.py` after multi-modal changes
8. **MANDATORY**: Verify NPU worker with `python test_npu_worker.py` after OpenVINO modifications
9. **CRITICAL**: All test-related files MUST be stored in `tests/` folder or subfolders - NO EXCEPTIONS
10. **CRITICAL**: Only `run_agent.sh` allowed in project root - all other scripts in `scripts/` subdirectories
11. **CRITICAL**: All reports in `reports/` subdirectories by type - maximum 2 per type for comparison
12. **CRITICAL**: All docker-compose files in `docker/compose/` - update all references when moving
13. **CRITICAL**: All documentation in `docs/` with proper linking - no orphaned documents
14. **CRITICAL**: NO error left unfixed, NO warning left unfixed - ZERO TOLERANCE for any linting or compilation errors
15. **CRITICAL**: ALWAYS continue working on started tasks - NO task abandonment without completion
16. **CRITICAL**: Group all tasks by priority in TodoWrite - errors/warnings ALWAYS take precedence over features

### Immediate Safety Checks
```bash
# Before any code changes - verify system state
curl -s "http://localhost:8001/api/system/health" || echo "Backend not running"
docker ps | grep autobot-redis || echo "Redis Stack not running"
ls data/knowledge_base.db || echo "Knowledge base missing"
ls data/memory_system.db || echo "Memory system missing"

# Phase-specific health checks
curl -s "http://localhost:8001/api/memory/health" || echo "Memory system API not accessible"
curl -s "http://localhost:8001/api/control/status" || echo "Control panel API not accessible"
docker ps | grep npu-worker || echo "NPU worker not running (optional)"
```

### ⚠️ IMPORTANT: USER INTERACTION REQUIRED

**CRITICAL**: The `run_agent.sh` script requires root password entry for certain operations and CANNOT be executed autonomously by Claude Code. When testing or starting the application is needed:

```bash
# ❌ CLAUDE CODE CANNOT RUN THESE COMMANDS - USER MUST EXECUTE:
./run_agent.sh                     # Requires root password for Docker/system operations
./run_agent.sh --test-mode         # Requires root password for container management

# ✅ CLAUDE CODE CAN RUN THESE ALTERNATIVES:
python main.py                     # Direct Python startup (no Docker containers)
python -m pytest tests/           # Test execution
flake8 src/ backend/              # Code quality checks
curl http://localhost:8001/api/system/health  # Health checks (if app running)
```

**When you need to test the application:**
1. **Ask the user to run**: `./run_agent.sh --test-mode`
2. **Wait for user confirmation** that the app started successfully
3. **Then proceed** with API health checks and other validation

**Never attempt to run `run_agent.sh` directly - it will fail due to password requirements.**

### 🧪 CURRENT TEST STATUS

**Frontend Tests**: Currently failing due to Vitest mocking and Vue component dependency issues. These are test implementation problems, not application functionality issues.

**Known Frontend Test Issues**:
- Vitest module mocking hoisting problems (`vi.mock` factory issues)
- Vue component circular dependency errors
- Router mocking issues in component tests
- API service constructor mocking problems

**CI Pipeline Status**: ✅ **Fully functional** - all infrastructure issues resolved. Tests fail gracefully without breaking CI execution.

**Next Steps for Test Fixes**:
1. Refactor component tests to avoid problematic mocking patterns
2. Fix Vue router dependency injection in test environment
3. Simplify API service mocking for integration tests
4. Consider using shallow mounting for complex component dependencies

### 📋 MANDATORY PRE-COMMIT WORKFLOW

**Before ANY commit, execute this exact sequence:**

```bash
# 1. TESTING PHASE - Complete system validation (see TESTING ORGANIZATION section)
# NOTE: Ask user to run: ./run_agent.sh --test-mode    # Test basic system startup (requires root password)
python -m pytest tests/unit/ -v --tb=short    # Run unit tests
python -m pytest tests/integration/ -v        # Run integration tests
python -m pytest tests/security/ -v           # Run security tests
python test_phase9_ai.py                      # Test Phase 9 components (if modified)
python test_npu_worker.py                     # Test NPU worker (if modified)
python validate_chat_knowledge.py             # Validate knowledge integration

# 2. CODE QUALITY PHASE - Ensure standards compliance
flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503
black src/ backend/ --line-length=88 --check  # Verify formatting
isort src/ backend/ --check-only               # Verify import sorting

# 2.1. OPTIONAL: Run comprehensive code analysis (see CODE ANALYSIS SUITE section)
# cd code-analysis-suite && python scripts/analyze_code_quality.py

# 3. DOCUMENTATION PHASE - Update documentation
# Update relevant docstrings for modified functions (Google style)
# Update docs/ files if new features added
# Update README.md if user-facing changes
# Update CLAUDE.md if development workflow changes

# 4. INTEGRATION TESTING - Verify component integration
curl -s "http://localhost:8001/api/system/health" || echo "FAIL: Backend"
curl -s "http://localhost:8001/api/memory/health" || echo "FAIL: Memory system"
curl -s "http://localhost:8001/api/control/status" || echo "FAIL: Control panel"

# 5. FINAL VERIFICATION - All systems operational
docker ps | grep autobot                      # Verify containers running
tail -n 20 logs/autobot.log                   # Check for errors
```

**⚠️ COMMIT ONLY IF ALL TESTS PASS - NO EXCEPTIONS**

### 📚 DOCUMENTATION REQUIREMENTS

**For ANY code changes, update documentation as follows:**

#### Function/Method Changes:
```python
# ✅ REQUIRED: Google-style docstrings for all new/modified functions
def new_function(param1: str, param2: int = 5) -> Dict[str, Any]:
    """Brief description of what the function does.

    Args:
        param1: Description of param1
        param2: Description of param2 with default value

    Returns:
        Dict containing the result with keys 'status' and 'data'

    Raises:
        ValueError: If param1 is empty
        ConnectionError: If external service unavailable

    Example:
        >>> result = new_function("test", 10)
        >>> print(result['status'])
        'success'
    """
```

#### New Features/Components:
- **Add to main README.md** - Feature description and usage
- **Create docs/ file** - Detailed documentation in appropriate subfolder
- **Update CLAUDE.md** - If development workflow changes
- **Add test file** - Comprehensive test coverage

#### API Endpoint Changes:
- **Update API documentation** in docs/features/
- **Add example requests/responses**
- **Document authentication requirements**
- **Include error codes and messages**

#### Configuration Changes:
- **Update docs/deployment/** guides
- **Document environment variables**
- **Update docker-compose examples**
- **Add configuration validation**

### 🔧 PROJECT ORGANIZATION RULES

**CRITICAL: All auxiliary files must be properly organized**

#### Shell Script Organization
- **ONLY `run_agent.sh` allowed in project root**
- All other `*.sh` scripts organized in appropriate folders:
  - `scripts/setup/` - Setup and installation scripts (setup_agent.sh, setup_repair.sh, etc.)
  - `scripts/deployment/` - Deployment and container management (start_all_containers.sh, etc.)
  - `scripts/environment/` - Environment configuration scripts (set-env-*.sh, *_env_config.sh)
  - `scripts/testing/` - Testing and validation scripts (run-playwright-tests.sh, etc.)
  - `scripts/utilities/` - General utility scripts and tools

#### Docker Compose Organization
- **ALL docker-compose files in `docker/compose/` directory**:
  - `docker/compose/docker-compose.hybrid.yml` - Main hybrid deployment
  - `docker/compose/docker-compose.playwright-vnc.yml` - Playwright with VNC
  - `docker/compose/docker-compose.playwright.yml` - Standard Playwright
  - `docker/compose/docker-compose.yml` - Base configuration
- **ALWAYS update references** when moving docker-compose files
- **Reference pattern**: `docker-compose -f docker/compose/docker-compose.hybrid.yml`

#### Report Organization
- **NO reports in project root** - use `reports/` folder structure:
  - `reports/security/` - Security audits and vulnerability reports
  - `reports/dependency/` - Dependency and package analysis
  - `reports/performance/` - Performance analysis and benchmarks
  - `reports/code-quality/` - Code quality and analysis reports
- **Maximum 2 reports per type** for comparison purposes
- **Use `scripts/utilities/report_manager.py`** for automated report management:
```bash
# Organize existing reports from project root
python scripts/utilities/report_manager.py --cleanup

# Add new report with automatic classification
python scripts/utilities/report_manager.py --add security_audit_results.json

# List all organized reports
python scripts/utilities/report_manager.py --list
```

#### Documentation Organization
- **ALL documentation in `docs/` with proper linking**:
  - `docs/INDEX.md` - Comprehensive navigation index
  - `docs/user_guide/` - Installation and setup guides
  - `docs/deployment/` - Docker and deployment configurations
  - `docs/features/` - Feature-specific documentation
  - `docs/security/` - Security implementation guides
  - `docs/workflow/` - Workflow orchestration documentation
  - `docs/testing/` - Testing frameworks and reports
  - `docs/migration/` - Migration guides and procedures
  - `docs/architecture/` - System architecture and design
  - `docs/guides/` - Configuration templates and guides
  - `docs/reports/legacy/` - Historical analysis reports
- **NO orphaned documents** - all files must be linked from `docs/INDEX.md` or `README.md`
- **Cross-reference related documentation** for better navigation

#### File Organization Rules
1. **Only essential files in project root**: `run_agent.sh`, `README.md`, `CLAUDE.md`, `requirements.txt`, core config files
2. **All scripts in `scripts/` subdirectories by purpose**
3. **All reports in `reports/` subdirectories by type**
4. **All tests in `tests/` subdirectories by category**
5. **All docker-compose files in `docker/compose/` directory**
6. **All documentation in `docs/` with comprehensive linking**
7. **All generated files in appropriate subdirectories or `.gitignore`**

### Emergency Recovery
```bash
# If system breaks during development (USER MUST RUN final command)
pkill -f uvicorn; docker compose -f docker/compose/docker-compose.hybrid.yml down
./scripts/setup/setup_agent.sh --force-reinstall
# ./run_agent.sh    # USER MUST RUN - requires root password

# NPU worker recovery
docker compose -f docker/compose/docker-compose.hybrid.yml --profile npu down
docker compose -f docker/compose/docker-compose.hybrid.yml --profile npu up -d

# Memory system recovery (if corrupted)
cp data/memory_system.db.backup data/memory_system.db
python -c "from src.enhanced_memory_manager import EnhancedMemoryManager; EnhancedMemoryManager().initialize_database()"
```

## 📋 PROJECT OVERVIEW

AutoBot is a revolutionary autonomous AI platform representing a paradigm shift toward artificial general intelligence (AGI). Built with Vue 3 frontend and FastAPI backend, it features sophisticated multi-modal processing, advanced multi-agent orchestration, and cutting-edge AI model integration.

**Status**: Production-ready Phase 9 Complete | **Architecture**: Hybrid Multi-Agent + NPU | **Stack**: Python 3.10.13, Vue 3, Redis Stack, OpenVINO

## 🤖 AGENT SYSTEM ARCHITECTURE

AutoBot's revolutionary multi-agent system features intelligent orchestration with 20+ specialized agents:

### Agent Development Rules
1. **ALWAYS** extend `BaseAgent` class for standardized interface
2. **ALWAYS** implement `process_request()` and `get_capabilities()` methods
3. **ALWAYS** use `AgentRequest`/`AgentResponse` for communication
4. **NEVER** access system resources directly - use security validation
5. **ALWAYS** implement health checks and performance tracking
6. **REQUIRED**: Add new agents to agent registry in `src/agents/__init__.py`
7. **CRITICAL**: Test agent with `python test_agent_[name].py` before deployment

### Agent Tier Classification

#### **Tier 1: Core Agents (Always Available)**
- `chat_agent.py` - Conversational AI (Llama 3.2 1B)
- `kb_librarian_agent.py` - Knowledge retrieval (always-on search)
- `enhanced_system_commands_agent.py` - System operations with security

#### **Tier 2: Processing Agents (On-Demand)**
- `rag_agent.py` - Document synthesis (Llama 3.2 3B)
- `research_agent.py` - Web research coordination (Playwright)
- `containerized_librarian_assistant.py` - Advanced web research pipeline

#### **Tier 3: Specialized Agents (Task-Specific)**
- `security_scanner_agent.py` - Vulnerability assessment
- `network_discovery_agent.py` - Network reconnaissance
- `interactive_terminal_agent.py` - Full terminal access with PTY
- `classification_agent.py` - Request type classification

#### **Tier 4: Advanced Multi-Modal Agents**
- `advanced_web_research.py` - Playwright automation with CAPTCHA solving
- `multimodal_processor.py` - Vision + Voice + Text processing
- `computer_vision_system.py` - Screenshot analysis & UI understanding
- `voice_processing_system.py` - Speech recognition & command parsing

### Agent Security Classifications
- **🟢 Low Risk**: Chat, KB Librarian, RAG (read-only operations)
- **🟡 Medium Risk**: System Commands, Research, Classification (controlled access)
- **🔴 High Risk**: Security Scanner, Network Discovery (active reconnaissance)
- **⚫ Critical Risk**: Interactive Terminal, Advanced Web Research (system access)

### Agent Communication Patterns
```python
# Standard Agent Request Flow
AgentRequest → Agent.process_request() → AgentResponse
    ↓
Health Monitoring → Circuit Breaker → Performance Tracking
```

### Multi-Agent Orchestration
```python
# Complex Workflow Example:
Classification Agent → Complexity Analysis → Agent Selection
    ↓
Research Agent → Knowledge Manager → RAG Agent → User Approval → System Commands
```

### Key Components for Code Changes
```
src/
├── orchestrator.py                      # ⚠️  CRITICAL - Task planning engine
├── enhanced_orchestrator.py            # 🚀 NEW - Phase 8+ orchestration
├── llm_interface.py                     # 🔧 COMMON - LLM integrations
├── llm_interface_extended.py            # 🔧 NEW - Extended LLM capabilities
├── knowledge_base.py                    # 📊 DATA - RAG + ChromaDB
├── enhanced_memory_manager.py           # 🧠 NEW - Phase 7 memory system
├── task_execution_tracker.py            # 📋 NEW - Automatic task tracking
├── markdown_reference_system.py         # 📚 NEW - Documentation management
├── desktop_streaming_manager.py         # 🖥️  NEW - Phase 8 desktop streaming
├── takeover_manager.py                  # 🎮 NEW - Human-in-the-loop control
├── multimodal_processor.py              # 🎭 NEW - Phase 9 multi-modal AI
├── computer_vision_system.py            # 👁️  NEW - Screen analysis & UI understanding
├── voice_processing_system.py           # 🎤 NEW - Voice commands & speech
├── context_aware_decision_system.py     # 🧠 NEW - Intelligent decision making
├── modern_ai_integration.py             # 🤖 NEW - GPT-4V, Claude-3, Gemini
├── config.py                           # ⚙️  CONFIG - All settings
└── agents/                             # 🤖 SUB-AGENTS
    ├── agent_orchestrator.py           #    Multi-agent coordination
    ├── base_agent.py                   #    Agent interface & deployment
    ├── chat_agent.py                   #    Conversational agent (1B)
    ├── enhanced_system_commands_agent.py #  System operations (1B)
    ├── rag_agent.py                    #    Document synthesis (3B)
    └── research_agent.py               #    Web research (3B + Playwright)

backend/api/
├── chat.py                             # 💬 API - Chat endpoints
├── workflow.py                         # 🔄 API - Multi-agent workflow orchestration
├── enhanced_memory.py                   # 🧠 NEW - Phase 7 memory API
├── advanced_control.py                  # 🎮 NEW - Phase 8 streaming & control API
├── advanced_workflow_orchestrator.py   # 🚀 NEW - Advanced orchestration
├── elevation.py                        # 🔐 NEW - Privilege management
├── security.py                         # 🛡️  NEW - Security layer
└── secure_terminal_websocket.py        # 🔒 NEW - Secure terminal access

docker/
├── npu-worker/                         # 🔥 NEW - Intel NPU acceleration
│   ├── Dockerfile                      #    OpenVINO + Intel Graphics
│   ├── npu_model_manager.py            #    NPU hardware detection
│   └── npu_inference_server.py         #    FastAPI inference server
└── ai-stack/                          # 🤖 AI Services Container
    └── requirements-ai.txt             #    Enhanced with Redis Stack support

docs/                                   # 📚 NEW - Organized documentation
├── deployment/                         #    Deployment guides
├── features/                          #    Feature documentation
├── security/                          #    Security guidelines
└── workflow/                          #    Workflow documentation
```

## 🛠️ DEVELOPMENT COMMANDS

### Essential Operations
```bash
# Complete setup (run once)
./scripts/setup/setup_agent.sh

# Start full system (USER MUST RUN - requires root password)
# ./run_agent.sh

# Development mode (auto-reload)
source venv/bin/activate && python main.py --dev

# Code quality check (REQUIRED before commits)
flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503
black src/ backend/ --line-length=88
isort src/ backend/

# Quick tests (see TESTING ORGANIZATION section for details)
python -m pytest tests/unit/ -v --tb=short
python -m pytest tests/integration/ -v
python -m pytest tests/e2e/ -v
```

## 🧪 TESTING ORGANIZATION

### **CRITICAL RULE: All test-related files MUST be stored in `tests/` folder structure**

```
tests/
├── unit/                    # Unit tests (isolated component testing)
│   ├── test_*.py           # Python unit tests
│   ├── *.test.js           # JavaScript unit tests
│   └── testing_coverage_analyzer.py
├── integration/            # Integration tests (component interaction)
│   ├── test_phase*.py      # Phase integration tests
│   ├── test_system_integration.py
│   ├── debug-frontend-*.js # Frontend integration debugging
│   └── playwright-server.js
├── e2e/                    # End-to-end tests (full user workflows)
│   ├── comprehensive-user-flow-test.js
│   ├── enhanced-user-flow-test.js
│   ├── fixed-comprehensive-test.js
│   ├── parallel-dual-browser-test.js
│   └── frontend-*.spec.js  # Playwright E2E specs
├── security/               # Security-focused tests
│   ├── test_security_*.py  # Security validation tests
│   ├── test_enhanced_security_layer.py
│   └── security_port_audit.py
├── performance/            # Performance and load tests
│   ├── distributed-testing-pipeline.js
│   └── load-test-*.js
├── api/                    # API-specific tests
│   ├── frontend-test-via-playwright-api.js
│   └── test_workflow_api_fix.js
├── gui/                    # GUI automation tests
│   ├── comprehensive_gui_test.js
│   ├── simple_gui_test.js
│   └── quick_frontend_test.js
└── external/               # External library tests (noVNC, etc.)
    └── novnc-tests/
```

### **TEST-GENERATED FILES DIRECTIVE**

**MANDATORY**: Any test-generated files (reports, outputs, temporary files, logs, screenshots, recordings, etc.) MUST be stored in the `test_results/` folder, which is automatically added to `.gitignore`.

**GENERAL GITIGNORE RULE**: If a file can be regenerated, it MUST be in `.gitignore`. This includes:
- Test output files and reports
- Build artifacts and compiled code
- Generated documentation
- Log files and temporary data
- Cache files and directories
- Database files created during testing
- Screenshots and recordings from automated tests
- Any files produced by scripts or automation tools

### Test Execution Commands

```bash
# Run all tests
python -m pytest tests/ -v

# Run by category
python -m pytest tests/unit/ -v --tb=short      # Unit tests only
python -m pytest tests/integration/ -v          # Integration tests only
python -m pytest tests/security/ -v             # Security tests only
python -m pytest tests/e2e/ -v                  # E2E tests only

# Frontend tests (from autobot-vue/)
npm run test:unit                                # Vue component tests
npm run test:playwright                          # Playwright E2E tests

# Manual test execution
node tests/e2e/comprehensive-user-flow-test.js  # Manual E2E testing
node tests/gui/simple_gui_test.js               # GUI automation testing
```

### Test File Naming Conventions

- **Python tests**: `test_*.py` (pytest compatible)
- **JavaScript tests**: `*.test.js` or `test-*.js`
- **E2E specs**: `*.spec.js` (Playwright compatible)
- **Integration**: Prefix with component name (e.g., `debug-frontend-*.js`)
- **Performance**: Include "performance" or "load" in filename

### When Creating New Tests

1. **ALWAYS place in appropriate `tests/` subfolder**
2. **Use descriptive filenames** indicating test purpose
3. **Follow naming conventions** for your test framework
4. **Include test documentation** in file header comments
5. **Update this section** if adding new test categories

### Test Categories Explained

- **Unit Tests**: Test individual functions/classes in isolation
- **Integration Tests**: Test component interaction and API integration
- **E2E Tests**: Test complete user workflows from frontend to backend
- **Security Tests**: Test security measures and vulnerability detection
- **Performance Tests**: Test system performance, load, and scalability
- **API Tests**: Test API endpoints and data flow
- **GUI Tests**: Test frontend user interface and interactions
- **External Tests**: Tests for third-party libraries and dependencies

**❌ NEVER CREATE TEST FILES OUTSIDE `tests/` FOLDER**
**✅ ALWAYS ORGANIZE BY TEST TYPE AND PURPOSE**

### Frontend Development
```bash
cd autobot-vue
npm run dev          # Development server
npm run lint         # ESLint + oxlint
npm run format       # Prettier
npm run type-check   # TypeScript validation
npm run test:unit    # Vitest tests

# GUI Testing (Playwright)
npm run test:playwright           # Run all GUI tests
npm run test:playwright:headed    # Run GUI tests with browser UI
npm run test:playwright:ui        # Run GUI tests with Playwright UI
npm run test:playwright:report    # View test results report
```

### NPU Worker Development
```bash
# NPU worker operations (Intel hardware acceleration)
docker compose -f docker-compose.hybrid.yml --profile npu up -d  # Start NPU worker
./start_npu_worker.sh                                            # Manual NPU startup
python test_npu_worker.py                                        # Test NPU functionality

# NPU model management
docker exec autobot-npu-worker python npu_model_manager.py list  # List available models
docker logs autobot-npu-worker                                   # Check NPU worker logs
```

### Phase Testing Commands
```bash
# Phase 7: Enhanced Memory & Knowledge Base
python test_enhanced_memory.py                    # Test memory system
python validate_chat_knowledge.py                 # Validate knowledge integration

# Phase 8: Enhanced Interface & Web Control
python test_desktop_streaming.py                  # Test desktop streaming
python test_session_takeover_system.py            # Test takeover system

# Phase 9: Advanced AI Integration & Multi-Modal
python test_phase9_ai.py                          # Test all Phase 9 components
python test_multimodal_processor.py               # Test multi-modal processing
python test_computer_vision.py                    # Test computer vision
python test_voice_processing.py                   # Test voice commands
```

## 🚀 PROJECT STATUS - PHASE 9 COMPLETE

### ✅ **Completed Phases:**

**Phase 7: Enhanced Memory & Knowledge Base** *(Completed)*
- SQLite-based comprehensive memory system with task execution tracking
- Automatic context management with embedding storage
- Markdown reference system for documentation cross-referencing
- Enhanced memory API endpoints with statistics and health monitoring

**Phase 8: Enhanced Interface & Web Control Panel** *(Completed)*
- Desktop streaming with NoVNC integration and WebSocket support
- Human-in-the-loop takeover system with interrupt capabilities
- Advanced control panel API for monitoring and session management
- Secure terminal access with privilege elevation

**Phase 9: Advanced AI Integration & Multi-Modal Capabilities** *(Completed)*
- Multi-modal input processing (text, image, audio, combined)
- Computer vision system for screen analysis and UI understanding
- Voice processing with speech recognition and natural language commands
- Context-aware decision making with comprehensive context collection
- Modern AI model integration framework (GPT-4V, Claude-3, Gemini)

### 🔥 **Key New Capabilities:**

**NPU Hardware Acceleration:**
- Intel OpenVINO integration for NPU model optimization
- Automatic hardware detection with CPU/GPU/NPU fallback
- Dockerized NPU worker with FastAPI inference server
- Model management with dynamic loading and optimization

**Sub-Agent Architecture:**
- Hybrid local/container agent deployment
- Intelligent routing with LLM-powered decision making
- Multi-agent coordination with result synthesis
- Performance monitoring and health checks
- Base agent interface supporting local and remote deployment

**Advanced Multi-Modal AI:**
- Vision: Screenshot analysis, UI element detection, automation opportunities
- Audio: Speech recognition, command parsing, text-to-speech synthesis
- Combined: Multi-modal input processing with confidence scoring
- Context: Comprehensive context collection for decision making

## 🔄 MULTI-AGENT WORKFLOW ORCHESTRATION

### Workflow System Overview
AutoBot now features comprehensive multi-agent workflow orchestration that intelligently coordinates specialized agents instead of providing generic responses.

**Transformation Example:**
- **Before**: "find tools for network scanning" → "Port Scanner, Sniffing Software, Password Cracking Tools"
- **After**: 8-step coordinated workflow with research, knowledge management, user approvals, and system operations

### Workflow API Endpoints
```bash
# Core workflow orchestration endpoints
GET    /api/workflow/workflows                    # List active workflows
POST   /api/workflow/execute                      # Execute new workflow
GET    /api/workflow/workflow/{id}/status         # Get workflow status
POST   /api/workflow/workflow/{id}/approve        # Approve workflow steps
DELETE /api/workflow/workflow/{id}                # Cancel workflow
GET    /api/workflow/workflow/{id}/pending_approvals # Get pending approvals
```

### Testing Workflow Orchestration
```bash
# Test workflow API endpoints
python3 test_workflow_api.py

# Test end-to-end workflow execution
python3 test_complete_system.py

# Test live workflow coordination
python3 test_live_workflow.py

# Verify backend workflow integration
python3 verify_backend_config.py
```

### Workflow Types and Classification
1. **Simple** - Direct conversational responses (e.g., "What is 2+2?")
2. **Research** - Web research + knowledge base storage
3. **Install** - System commands and installation workflows
4. **Complex** - Full 8-step multi-agent coordination

### Example Complex Workflow: Network Scanning Tools
```
🎯 Classification: complex
🤖 Agents: research, librarian, knowledge_manager, system_commands, orchestrator
⏱️  Duration: 3 minutes
👤 Approvals: 2

📋 Workflow Steps:
   1. Librarian: Search Knowledge Base
   2. Research: Research Tools
   3. Orchestrator: Present Tool Options (requires approval)
   4. Research: Get Installation Guide
   5. Knowledge_Manager: Store Tool Info
   6. Orchestrator: Create Install Plan (requires approval)
   7. System_Commands: Install Tool
   8. System_Commands: Verify Installation
```

### Frontend Workflow Components
```vue
<!-- Main workflow integration in ChatInterface.vue -->
<WorkflowProgressWidget
  v-if="activeWorkflowId"
  :workflow-id="activeWorkflowId"
  @open-full-view="openFullWorkflowView"
  @workflow-cancelled="onWorkflowCancelled"
/>

<WorkflowApproval /> <!-- Full workflow management dashboard -->
```

### WebSocket Workflow Events
```javascript
// Workflow event types for real-time updates
workflow_step_started    // Step execution begins
workflow_step_completed  // Step finished successfully
workflow_approval_required // User approval needed
workflow_completed      // All steps finished
workflow_failed        // Error occurred
```

### Development Guidelines for Workflow Features

#### Adding New Workflow Steps
```python
# In src/orchestrator.py - plan_workflow_steps()
WorkflowStep(
    id="new_step_id",
    agent_type="agent_name",
    action="action_description",
    inputs={"param": "value"},
    user_approval_required=False,  # Set True for approval steps
    dependencies=["previous_step_id"]  # Optional dependencies
)
```

#### Adding New Agent Types
```python
# 1. Register in src/orchestrator.py agent_registry
self.agent_registry = {
    "new_agent": "Agent description and capabilities"
}

# 2. Implement in backend/api/workflow.py execute_single_step()
elif agent_type == "new_agent":
    # Agent implementation
    result = await new_agent_implementation(step, orchestrator)
    return result
```

#### Testing New Workflows
```python
# Add test cases in test_workflow_orchestration.py
def test_new_workflow_type():
    orchestrator = Orchestrator()
    complexity = orchestrator.classify_request_complexity("new request type")
    assert complexity == TaskComplexity.NEW_TYPE

    steps = orchestrator.plan_workflow_steps("test request", complexity)
    assert len(steps) > 0
```

## 🏗️ CODE QUALITY REQUIREMENTS

### Flake8 Configuration (.flake8 file)
```ini
[flake8]
max-line-length = 88
extend-ignore =
    E203,  # Whitespace before ':'
    W503,  # Line break before binary operator
    F401,  # Module imported but unused (in __init__.py)
exclude =
    .git,
    __pycache__,
    venv,
    build,
    dist,
    *.egg-info
```

### Python Code Standards
```python
# ✅ CORRECT: Function with proper docstring and typing
def process_knowledge_query(
    query: str,
    limit: int = 5,
    similarity_threshold: float = 0.7
) -> List[Dict[str, Any]]:
    """Search knowledge base with vector similarity.

    Args:
        query: Search query string
        limit: Maximum results to return
        similarity_threshold: Minimum similarity score (0.0-1.0)

    Returns:
        List of matching documents with metadata

    Raises:
        ValueError: If similarity_threshold not in valid range
    """
    if not 0.0 <= similarity_threshold <= 1.0:
        raise ValueError("similarity_threshold must be between 0.0 and 1.0")

    # Implementation here...
    return results

# ❌ INCORRECT: No typing, hardcoded values, no docstring
def search_kb(q, n=5):
    return chroma_client.query(q, n_results=n, where={"db": "main"})
```

### Import Organization (isort compatible)
```python
# Standard library
import asyncio
import json
from typing import Dict, List, Optional

# Third-party packages
import redis
import uvicorn
from fastapi import FastAPI, HTTPException

# Local imports
from src.config import Config
from src.llm_interface import LLMInterface
```

## 🔧 COMMON DEVELOPMENT SCENARIOS

### Adding New API Endpoints
1. **Create route handler** in `backend/api/[module].py`:
```python
@router.post("/new-endpoint")
async def new_endpoint(request: NewRequest) -> Dict[str, Any]:
    """Handle new functionality.

    Args:
        request: Validated request model

    Returns:
        Response with operation results
    """
    try:
        result = await some_operation(request.data)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"New endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

2. **Add request/response models** in same file:
```python
class NewRequest(BaseModel):
    data: str
    options: Optional[Dict[str, Any]] = None
```

3. **Update frontend service** in `autobot-vue/src/services/api.ts`:
```typescript
export const newEndpoint = async (data: NewRequest): Promise<ApiResponse> => {
  return apiClient.post('/new-endpoint', data);
};
```

### Modifying Database Schema
```python
# ALWAYS backup before schema changes
import shutil
from datetime import datetime

# Backup database
backup_path = f"data/knowledge_base.db.backup.{datetime.now().isoformat()}"
shutil.copy("data/knowledge_base.db", backup_path)

# Make changes with proper migration
def migrate_database():
    """Migrate database to new schema version."""
    conn = sqlite3.connect("data/knowledge_base.db")
    cursor = conn.cursor()

    try:
        # Check current schema version
        cursor.execute("PRAGMA user_version")
        current_version = cursor.fetchone()[0]

        if current_version < 2:
            # Apply migration
            cursor.execute("ALTER TABLE documents ADD COLUMN new_field TEXT")
            cursor.execute("PRAGMA user_version = 2")

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
```

### Adding LLM Models
```python
# In src/llm_interface.py
def add_new_llm_provider(self, provider_name: str, config: Dict[str, Any]):
    """Add new LLM provider configuration.

    Args:
        provider_name: Unique identifier for provider
        config: Provider configuration dict

    Raises:
        ValueError: If provider already exists
    """
    if provider_name in self.providers:
        raise ValueError(f"Provider {provider_name} already exists")

    # Validate required config keys
    required_keys = ["api_key", "base_url", "model_name"]
    if not all(key in config for key in required_keys):
        raise ValueError(f"Missing required config keys: {required_keys}")

    self.providers[provider_name] = LLMProvider(config)
```

## 🚨 TROUBLESHOOTING GUIDE

### Backend Issues

**Import Errors**
```bash
# Symptom: ModuleNotFoundError
# Fix: Check Python path and virtual environment
source venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH="$PWD:$PYTHONPATH"
```

**Port Already in Use**
```bash
# Find and kill process using port 8001
lsof -ti:8001 | xargs kill -9
# Or use different port
export AUTOBOT_BACKEND_PORT=8002
```

**Redis Connection Failed**
```bash
# Check Redis container status
docker ps | grep redis
# Restart Redis
docker stop autobot-redis && docker rm autobot-redis
./run_agent.sh  # Will recreate Redis container
```

**Database Corruption**
```bash
# Restore from backup
cp data/knowledge_base.db.backup.* data/knowledge_base.db
# Or reinitialize
rm data/knowledge_base.db && python -c "from src.knowledge_base import KnowledgeBase; KnowledgeBase()"
```

### Frontend Issues

**Build Failures**
```bash
cd autobot-vue
rm -rf node_modules package-lock.json
npm install
npm run type-check  # Fix TypeScript errors first
```

**WebSocket Connection Issues**
```javascript
// Check connection status in browser console
const ws = new WebSocket('ws://localhost:8001/ws');
ws.onopen = () => console.log('Connected');
ws.onerror = (e) => console.error('WebSocket error:', e);
```

### Performance Issues

**Slow Knowledge Base Queries**
```python
# Add query logging to identify bottlenecks
import time
start_time = time.time()
results = chroma_collection.query(query_texts=[query], n_results=limit)
query_time = time.time() - start_time
logger.info(f"Query took {query_time:.2f}s for '{query}'")
```

**Memory Leaks**
```bash
# Monitor memory usage
ps aux | grep python | grep autobot
# Check for unclosed connections
lsof -p $(pgrep -f "python main.py")
```

## ⚠️ COMMON PITFALLS AND BEST PRACTICES

### Configuration Management
```python
# ❌ NEVER hardcode values
api_key = "sk-1234567890abcdef"  # pragma: allowlist secret
redis_host = "localhost"

# ✅ ALWAYS use config system
from src.config import Config
config = Config()
api_key = config.get("openai.api_key")
redis_host = config.get("redis.host", "localhost")
```

### Error Handling
```python
# ❌ NEVER catch all exceptions silently
try:
    result = risky_operation()
except:
    pass

# ✅ ALWAYS log errors and handle specifically
try:
    result = risky_operation()
except SpecificException as e:
    logger.error(f"Operation failed: {e}")
    raise HTTPException(status_code=400, detail=f"Operation failed: {e}")
except Exception as e:
    logger.critical(f"Unexpected error: {e}")
    raise HTTPException(status_code=500, detail="Internal server error")
```

### Async/Await Patterns
```python
# ❌ INCORRECT: Blocking operations in async functions
async def bad_example():
    time.sleep(5)  # Blocks event loop

# ✅ CORRECT: Non-blocking operations
async def good_example():
    await asyncio.sleep(5)  # Non-blocking
```

### Database Connections
```python
# ❌ INCORRECT: Not closing connections
def query_database():
    conn = sqlite3.connect("data/knowledge_base.db")
    return conn.execute("SELECT * FROM documents").fetchall()

# ✅ CORRECT: Always use context managers
def query_database():
    with sqlite3.connect("data/knowledge_base.db") as conn:
        return conn.execute("SELECT * FROM documents").fetchall()
```

## 🔍 TESTING STRATEGIES

### Unit Tests
```python
# Test file: tests/test_knowledge_base.py
import pytest
from src.knowledge_base import KnowledgeBase

@pytest.fixture
def kb():
    """Create test knowledge base instance."""
    return KnowledgeBase(db_path=":memory:")  # In-memory for tests

def test_search_functionality(kb):
    """Test knowledge base search returns expected results."""
    # Add test document
    kb.add_document("Test content", {"source": "test"})

    # Search and verify
    results = kb.search("Test", limit=1)
    assert len(results) == 1
    assert "Test content" in results[0]["content"]
```

### Integration Tests
```bash
# Test API endpoints
curl -X POST "http://localhost:8001/api/knowledge_base/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "limit": 1}' | \
  python3 -c "import sys,json; data=json.load(sys.stdin); exit(0 if data['success'] else 1)"
```

## 🔍 CODE ANALYSIS SUITE

AutoBot includes a comprehensive code analysis suite in the `code-analysis-suite/` directory for enterprise-grade code quality monitoring.

### 🚀 Quick Start with Analysis Suite

```bash
# Install the analysis suite
cd code-analysis-suite
./install.sh

# Activate virtual environment
source venv/bin/activate

# Run comprehensive analysis
python scripts/analyze_code_quality.py

# Run specific analyzers
python scripts/analyze_security.py      # Security vulnerabilities
python scripts/analyze_performance.py  # Performance issues
python scripts/analyze_duplicates.py   # Code duplication
python scripts/analyze_architecture.py # Architectural patterns

# Generate automated fixes
python scripts/generate_automated_fixes.py
```

### 📊 Analysis Suite Components

**Core Analyzers:**
1. **Security Analyzer** - OWASP vulnerabilities, CWE classifications
2. **Performance Analyzer** - Memory leaks, blocking calls, inefficiencies
3. **Code Duplication Analyzer** - AST-based similarity detection
4. **Environment Analyzer** - Hardcoded configurations
5. **API Consistency Analyzer** - Endpoint design patterns
6. **Testing Coverage Analyzer** - Test gap identification
7. **Architectural Analyzer** - Design patterns, SOLID principles
8. **Automated Fix Generator** - Specific code fixes with patches

### 🎯 When to Use Analysis Suite

**During Development:**
```bash
# Before major commits
cd code-analysis-suite
python scripts/analyze_code_quality.py --quick

# Security-focused review
python scripts/analyze_security.py

# Performance optimization
python scripts/analyze_performance.py
```

**Quality Gates:**
```bash
# Pre-commit hook integration
cd code-analysis-suite
python scripts/analyze_code_quality.py
# Fail if overall score < 80
```

**Continuous Integration:**
```yaml
# .github/workflows/quality.yml
- name: Code Quality Analysis
  run: |
    cd code-analysis-suite
    python scripts/analyze_code_quality.py
    # Parse results and set quality gates
```

### 🛡️ Security Analysis Integration

**Critical Security Checks:**
```bash
# Run before any deployment
cd code-analysis-suite
python scripts/analyze_security.py

# Check for specific vulnerabilities
grep -i "critical" security_analysis_report.json

# Apply security fixes automatically
python scripts/generate_automated_fixes.py --security-only
```

### ⚡ Performance Analysis Integration

**Performance Monitoring:**
```bash
# Detect memory leaks and blocking calls
cd code-analysis-suite
python scripts/analyze_performance.py

# Apply performance fixes
python scripts/generate_automated_fixes.py --performance-only
```

### 📋 Analysis Reports Location

All analysis reports are generated in:
- `code-analysis-suite/comprehensive_quality_report.json` - Full analysis
- `code-analysis-suite/security_analysis_report.json` - Security findings
- `code-analysis-suite/performance_analysis_report.json` - Performance issues
- `code-analysis-suite/automated_fixes_report.json` - Generated fixes
- `code-analysis-suite/generated_patches.patch` - Ready-to-apply patches

### 🔧 Configuration for AutoBot

**Redis Integration:**
The analysis suite uses the same Redis instance as AutoBot for caching.

**Custom Patterns:**
Add AutoBot-specific patterns in `code-analysis-suite/src/` analyzers.

**CI/CD Integration:**
Include analysis suite checks in AutoBot's deployment pipeline.

## 🎯 CLAUDE CODE SPECIFIC GUIDANCE

### 🚨 MANDATORY TASK WORKFLOW AND PRIORITY SYSTEM

**CRITICAL WORKFLOW RULE**: All task management MUST follow this strict hierarchy:

#### Task Priority Hierarchy (NEVER DEVIATE):
1. **🔴 HIGH PRIORITY** (IMMEDIATE ACTION REQUIRED):
   - **Errors** - Any compilation, runtime, or linting errors
   - **Warnings** - Any linting warnings or deprecation notices
   - **Security Issues** - Any security vulnerabilities or unsafe code patterns

2. **🟡 MEDIUM PRIORITY** (AFTER ALL HIGH PRIORITY RESOLVED):
   - **Bug Fixes** - Functional issues in existing features
   - **Performance Issues** - Memory leaks, slow queries, inefficient code

3. **🟢 LOW PRIORITY** (ONLY AFTER MEDIUM PRIORITY COMPLETED):
   - **New Features** - Adding new functionality
   - **Enhancements** - Improving existing features
   - **Documentation** - Non-critical documentation updates

#### Mandatory TodoWrite Workflow:
```markdown
**REQUIRED WHENEVER USER PROVIDES NEW TASKS DURING ACTIVE WORK:**

1. **IMMEDIATELY** update TodoWrite with new tasks using proper priority classification
2. **ALWAYS** group tasks by priority level in TodoWrite
3. **NEVER** start work on lower priority tasks while higher priority tasks exist
4. **ALWAYS** complete current in_progress task before switching (unless emergency)
5. **IMMEDIATELY** switch to HIGH priority tasks if errors/warnings are discovered

**Example TodoWrite Structure:**
🔴 HIGH PRIORITY:
- Fix TypeScript compilation error in ChatInterface.vue
- Resolve flake8 warning in orchestrator.py line 245
- Fix security vulnerability in API authentication

🟡 MEDIUM PRIORITY:
- Fix memory leak in knowledge base queries
- Optimize slow database connection pooling

🟢 LOW PRIORITY:
- Add new user preferences feature
- Enhance UI with dark mode toggle
- Update documentation for new API endpoints
```

#### Workflow Interruption Protocol:
**IF USER PROVIDES NEW TASKS WHILE WORKING ON FEATURE:**
1. **IMMEDIATELY** pause current work (mark as in_progress but note interruption)
2. **IMMEDIATELY** add new tasks to TodoWrite with proper priority
3. **IF** new tasks are HIGH priority (errors/warnings): switch immediately
4. **IF** new tasks are MEDIUM/LOW priority: finish current high-priority task first
5. **ALWAYS** return to interrupted tasks after higher priorities resolved

#### Task Continuation Rules:
- **NEVER abandon started tasks** - always return to complete them
- **ALWAYS mark interrupted tasks** with clear status in TodoWrite
- **ALWAYS complete error/warning fixes** before continuing feature work
- **ALWAYS update TodoWrite status** in real-time as work progresses

### Pre-Change Checklist
- [ ] **MANDATORY**: Review MANDATORY PRE-COMMIT WORKFLOW above
- [ ] **MANDATORY**: Check TodoWrite for any HIGH priority tasks - fix ALL before proceeding
- [ ] Verify system is running: `curl -s http://localhost:8001/api/system/health`
- [ ] Check current git status: `git status --porcelain`
- [ ] Run existing tests: `python -m pytest tests/ --tb=short -q`
- [ ] Backup critical data if changing schemas

### Post-Change Validation
- [ ] **MANDATORY**: Execute complete PRE-COMMIT WORKFLOW above - NO SHORTCUTS
- [ ] **MANDATORY**: Update documentation per DOCUMENTATION REQUIREMENTS above
- [ ] **MANDATORY**: All tests MUST pass before commit
- [ ] **MANDATORY**: Verify NO errors/warnings remain - run flake8, TypeScript checks
- [ ] **MANDATORY**: Update TodoWrite to mark completed tasks as completed
- [ ] Verify API endpoints affected by changes work correctly
- [ ] Test full system restart: `./run_agent.sh --test-mode`
- [ ] Verify frontend compilation: `cd autobot-vue && npm run build`
- [ ] Check logs for new errors: `tail -n 50 logs/autobot.log`

### Safe Change Patterns
1. **Add new functionality** without modifying existing working code
2. **Use feature flags** for experimental features
3. **Implement gradual rollouts** with configuration switches
4. **Always provide rollback paths** for database changes
5. **Log all significant operations** for debugging
6. **ALWAYS prioritize error/warning fixes** over feature development

### File Priority for Changes
**🔴 HIGH RISK** (require extra testing):
- `src/orchestrator.py` - Core task planning
- `src/knowledge_base.py` - Data layer
- `backend/app_factory.py` - Application bootstrap

**🟡 MEDIUM RISK** (standard testing):
- `backend/api/*.py` - API endpoints
- `src/llm_interface.py` - LLM integrations
- `src/config.py` - Configuration

**🟢 LOW RISK** (basic testing):
- `src/diagnostics.py` - Monitoring
- Documentation files
- Frontend components (isolated)

## 📚 ENVIRONMENT SETUP

### Development Environment
```bash
# Set development mode
export AUTOBOT_DEBUG=true
export AUTOBOT_LOG_LEVEL=DEBUG
export AUTOBOT_BACKEND_RELOAD=true

# Development database (separate from production)
export AUTOBOT_DATABASE_PATH=data/knowledge_base_dev.db
```

### Production Environment
```bash
# Optimize for production
export AUTOBOT_DEBUG=false
export AUTOBOT_LOG_LEVEL=INFO
export AUTOBOT_WORKERS=4
export AUTOBOT_BACKEND_RELOAD=false
```

### Testing Environment
```bash
# Isolated testing setup
export AUTOBOT_DATABASE_PATH=:memory:
export AUTOBOT_REDIS_DB=15  # Separate Redis DB for tests
export AUTOBOT_FILE_ROOT=tests/fixtures/files
```

---

**Remember**: This AutoBot platform handles sensitive operations. Always prioritize stability and data integrity over speed of implementation.
