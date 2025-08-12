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

### 📋 MANDATORY PRE-COMMIT WORKFLOW

**Before ANY commit, execute this exact sequence:**

```bash
# 1. TESTING PHASE - Complete system validation
./run_agent.sh --test-mode                    # Test basic system startup
python -m pytest tests/ -v --tb=short         # Run unit tests
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

### Emergency Recovery
```bash
# If system breaks during development
pkill -f uvicorn; docker compose -f docker-compose.hybrid.yml down
./setup_agent.sh --force-reinstall
./run_agent.sh

# NPU worker recovery
docker compose -f docker-compose.hybrid.yml --profile npu down
docker compose -f docker-compose.hybrid.yml --profile npu up -d

# Memory system recovery (if corrupted)
cp data/memory_system.db.backup data/memory_system.db
python -c "from src.enhanced_memory_manager import EnhancedMemoryManager; EnhancedMemoryManager().initialize_database()"
```

## 📋 PROJECT OVERVIEW

AutoBot is an enterprise-grade autonomous AI platform with Vue 3 frontend and FastAPI backend.

**Status**: Production-ready Phase 9 Complete | **Architecture**: Hybrid Multi-Agent + NPU | **Stack**: Python 3.10.13, Vue 3, Redis Stack, OpenVINO

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
./setup_agent.sh

# Start full system
./run_agent.sh

# Development mode (auto-reload)
source venv/bin/activate && python main.py --dev

# Code quality check (REQUIRED before commits)
flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503
black src/ backend/ --line-length=88
isort src/ backend/

# Quick tests
python -m pytest tests/ -v --tb=short
```

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

### Pre-Change Checklist
- [ ] **MANDATORY**: Review MANDATORY PRE-COMMIT WORKFLOW above
- [ ] Verify system is running: `curl -s http://localhost:8001/api/system/health`
- [ ] Check current git status: `git status --porcelain`
- [ ] Run existing tests: `python -m pytest tests/ --tb=short -q`
- [ ] Backup critical data if changing schemas

### Post-Change Validation
- [ ] **MANDATORY**: Execute complete PRE-COMMIT WORKFLOW above - NO SHORTCUTS
- [ ] **MANDATORY**: Update documentation per DOCUMENTATION REQUIREMENTS above  
- [ ] **MANDATORY**: All tests MUST pass before commit
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
