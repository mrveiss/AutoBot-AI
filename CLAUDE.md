# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🚀 QUICK REFERENCE FOR CLAUDE CODE

### Project Structure & File Organization
```
project_root/
├── src/                    # Source code
├── backend/               # Backend services
├── scripts/               # All scripts (except run_agent.sh)
├── tests/                 # ALL test files (mandatory location)
├── docs/                  # Documentation with proper linking
├── reports/               # Reports by type (max 2 per type)
├── docker/compose/        # Docker compose files
├── data/                  # Data files (backup before schema changes)
└── run_agent.sh          # ONLY script allowed in root
```

### Critical Rules for Autonomous Operations

#### 🔴 ZERO TOLERANCE RULES
1. **NO error left unfixed, NO warning left unfixed** - ZERO TOLERANCE for any linting or compilation errors
2. **NEVER abandon started tasks** - ALWAYS continue working until completion
3. **Group tasks by priority** - errors/warnings ALWAYS take precedence over features
4. **ALWAYS test before committing** - NO EXCEPTIONS
5. **NEVER restart applications** - Application restarts are handled by USER ONLY

#### 🧪 Testing & Quality Assurance
- **Pre-commit checks**: `flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503`
- **Test mode verification**: `./run_agent.sh --test-mode` before full deployment
- **Phase 9 testing**: `python test_phase9_ai.py` after multi-modal changes
- **NPU worker testing**: `python test_npu_worker.py` after OpenVINO modifications
- **Phase validation**: ON-DEMAND ONLY - use "Load Validation Data" button in GUI
- **ALL test files MUST be in `tests/` folder or subfolders**

#### 🏗️ Application Lifecycle Management
- **SETUP**: Application is configured ONCE using `./setup_agent.sh`
- **EXECUTION**: Application runs ONLY via `./run_agent.sh [options]`
- **RESTARTS**: Handled EXCLUSIVELY by user - NEVER restart programmatically
- **CONFIGURATION**: All setup and configuration changes go through `setup_agent.sh`
- **OPTIONS**: Use `./run_agent.sh --help` to see available runtime options

#### 🔐 **CRITICAL: USER RESTART REQUIRED**
**When AutoBot needs restart, ALWAYS ask user to manually restart:**
- `./run_agent.sh` requires sudo password entry for Docker operations
- Claude Code CANNOT automate password entry for security reasons
- **ACTION**: Request user to run `./run_agent.sh` in their terminal
- **REASON**: Docker container management, volume mounting, network setup require elevated privileges

#### 🔴 CRITICAL: STARTUP/SETUP SCRIPT MAINTENANCE
**ALL IMPLEMENTED CHANGES MUST BE REFLECTED IN STARTUP AND SETUP SCRIPTS**

- `run_agent.sh` and `setup_agent.sh` MUST ALWAYS be up to date
- **ZERO TOLERANCE** for missing changes in these scripts
- New features, dependencies, Docker configurations, Redis settings MUST be included
- Any architectural changes MUST be represented in script options and configurations
- Scripts are the SINGLE SOURCE OF TRUTH for application deployment

#### ⚙️ Configuration & Dependencies
- **NEVER hardcode values** - use `src/config.py` for all configuration
- **Update docstrings** following Google style for any function changes
- **Dependencies must reflect in**:
  - Install scripts
  - requirements.txt
  - **SECURITY UPDATES MANDATORY**

#### 🚫 CRITICAL: AVOID HARDCODED VALUES AT ALL COST

**What is a hardcoded value?**
A hardcoded value is any literal data (strings, numbers, URLs, paths) written directly into source code instead of using variables, configuration files, or environment variables.

**Examples of hardcoded values (❌ BAD):**
```python
# ❌ Hardcoded port
app.run(host="0.0.0.0", port=8001)

# ❌ Hardcoded URL
api_url = "http://localhost:8001/api/health"

# ❌ Hardcoded file path
config_file = "/home/user/autobot/config.json"

# ❌ Hardcoded database connection
conn = "redis://localhost:6379/0"

# ❌ Hardcoded API keys or secrets
api_key = "sk-1234567890abcdef"
```

**Correct approach (✅ GOOD):**
```python
# ✅ Use environment variables
port = int(os.getenv("AUTOBOT_BACKEND_PORT", "8001"))
app.run(host="0.0.0.0", port=port)

# ✅ Use configuration system
api_url = f"http://{config.get('host')}:{config.get('port')}/api/health"

# ✅ Use relative paths or config
config_file = os.path.join(config.get_config_dir(), "config.json")

# ✅ Use environment variables
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ✅ Use secure configuration
api_key = os.getenv("OPENAI_API_KEY")
```

**Why hardcoded values are dangerous:**
1. **Deployment Issues**: Code breaks when moved between environments (dev/staging/prod)
2. **Security Risks**: Secrets exposed in source code, version control
3. **Maintenance Nightmare**: Changes require code modifications instead of config updates
4. **Testing Problems**: Cannot test different scenarios without code changes
5. **Flexibility Loss**: Cannot adapt to different deployment scenarios
6. **Port Conflicts**: Fixed ports cause conflicts with other services

**AutoBot Configuration Hierarchy (use in this order):**
1. **Environment Variables**: `AUTOBOT_BACKEND_PORT=8003`
2. **Configuration Files**: `src/config.py`, `.env` files
3. **Command Line Arguments**: `--port 8003`
4. **Default Values**: Only as final fallback

**Mandatory Configuration Patterns:**
```python
# ✅ Ports - always configurable
backend_port = int(os.getenv("AUTOBOT_BACKEND_PORT", "8001"))

# ✅ URLs - build from components
api_base = f"http://{os.getenv('BACKEND_HOST', 'localhost')}:{backend_port}"

# ✅ File paths - relative to project or configurable
data_dir = os.getenv("AUTOBOT_DATA_DIR", os.path.join(os.getcwd(), "data"))

# ✅ Feature flags - environment controlled
debug_mode = os.getenv("AUTOBOT_DEBUG", "false").lower() == "true"
```

**Files that MUST use configuration instead of hardcoded values:**
- All port numbers (8001, 8080, 6379, etc.)
- All IP addresses and hostnames
- All file paths (except relative imports)
- All URLs and API endpoints
- All timeout values
- All database connections
- All service names and identifiers

#### 💾 Data Safety
- **CRITICAL**: Backup `data/` before schema changes to:
  - knowledge_base.db
  - memory_system.db

### 🚀 NPU Worker and Redis Code Search Capabilities

**YOU ARE AUTHORIZED TO USE NPU WORKER AND REDIS FOR ADVANCED CODE ANALYSIS**

#### Available Tools
- `src/agents/npu_code_search_agent.py` - High-performance code searching
- `/api/code_search/` endpoints - Code analysis tasks
- NPU acceleration for semantic code similarity (when hardware supports)
- Redis-based indexing for fast code element lookup

#### 🎯 APPROVED DEVELOPMENT SPEEDUP TASKS
- Code duplicate detection and removal
- Cross-codebase pattern analysis and comparisons
- Semantic code similarity searches
- Function/class dependency mapping
- Import optimization and unused code detection
- Architecture pattern identification
- Code quality consistency analysis
- Dead code elimination assistance
- Refactoring opportunity identification

### 🌐 API Development Standards

**CRITICAL: ALWAYS CHECK FOR EXISTING ENDPOINTS BEFORE CREATING NEW ONES**

#### 🔍 Pre-Development API Audit (MANDATORY)
Before creating ANY new API endpoint, you MUST:

1. **Search existing endpoints**:
   ```bash
   # Search all backend API files for similar endpoints
   find backend/api -name "*.py" | xargs grep -h "@router\." | grep -i "keyword"

   # Check for similar functionality
   grep -r "function_name\|endpoint_pattern" backend/api/

   # Verify frontend usage patterns
   find autobot-vue -name "*.js" -o -name "*.vue" | xargs grep -l "api/"
   ```

2. **Audit existing implementations**:
   - Check if similar functionality already exists
   - Identify any duplicate or overlapping endpoints
   - Verify if existing endpoints can be extended instead

3. **Document justification** if new endpoint is truly needed:
   - Why existing endpoints cannot be used/extended
   - What unique functionality this provides
   - How it differs from similar endpoints

#### 🚫 FORBIDDEN: API Duplication Patterns
**NEVER CREATE** these duplicate patterns:

❌ **Multiple health/status endpoints**:
- Use existing `/api/system/health` for all health checks
- Add module-specific details to single response

❌ **Similar endpoint names**:
- `/api/chat` vs `/api/chats` (confusing!)
- `/api/config` vs `/api/settings` vs `/api/configuration`
- `/api/status` vs `/api/health` vs `/api/info`

❌ **Functional duplicates**:
- Multiple terminal implementations
- Multiple workflow systems
- Multiple WebSocket handlers for same purpose

❌ **Version confusion**:
- `/api/endpoint` vs `/api/v1/endpoint` vs `/api/v2/endpoint`
- Keep single versioned API pattern

#### ✅ REQUIRED: API Design Standards
**ALWAYS FOLLOW** these patterns:

✅ **RESTful naming conventions**:
```
GET    /api/{resource}           # List all
POST   /api/{resource}           # Create new
GET    /api/{resource}/{id}      # Get specific
PUT    /api/{resource}/{id}      # Update specific
DELETE /api/{resource}/{id}      # Delete specific
```

✅ **Consistent response format**:
```json
{
  "status": "success|error",
  "data": {...},
  "message": "descriptive message",
  "timestamp": "ISO-8601",
  "request_id": "unique-id"
}
```

✅ **Single responsibility per endpoint**:
- One endpoint = one clear purpose
- Avoid kitchen-sink endpoints that do multiple things
- Use query parameters for filtering/options

✅ **Logical grouping by functionality**:
```
/api/chat/*          # All chat operations
/api/terminal/*      # All terminal operations
/api/workflow/*      # All workflow operations
/api/system/*        # All system operations
```

#### 🔧 API Consolidation Process
When you find duplicate endpoints:

1. **Immediate action**:
   - Document the duplication in `/docs/API_Duplication_Analysis.md`
   - Do NOT create additional duplicates
   - Use existing endpoint or consolidate first

2. **Consolidation steps**:
   - Identify which implementation is most complete/used
   - Plan migration for deprecated endpoints
   - Add deprecation warnings to old endpoints
   - Update frontend to use consolidated endpoint
   - Remove deprecated code after grace period

3. **Prevention measures**:
   - Update this CLAUDE.md with any new patterns found
   - Add API design review to commit checklist
   - Document API decision rationale in code comments

#### 📋 API Development Checklist
Before creating new API endpoints:

- [ ] Searched for existing similar endpoints
- [ ] Verified no functional duplicates exist
- [ ] Checked frontend usage patterns
- [ ] Followed RESTful naming conventions
- [ ] Implemented consistent response format
- [ ] Added proper error handling
- [ ] Updated API documentation
- [ ] Added appropriate tests
- [ ] Verified no breaking changes to existing endpoints

#### 🚨 API Emergency Procedures
If you discover major API duplications:

1. **Stop development** on duplicate endpoints
2. **Create consolidation plan** (see `/docs/API_Consolidation_Priority_Plan.md`)
3. **Fix critical missing endpoints** first (broken functionality)
4. **Implement backward compatibility** during consolidation
5. **Test thoroughly** before removing old endpoints

### 🔐 Secrets Management Requirements

**IMPLEMENT COMPREHENSIVE SECRETS MANAGEMENT SYSTEM**

#### Dual-Scope Architecture
- **Chat-scoped**: Conversation-only secrets
- **General-scoped**: Available across all chats

#### Features Required
- **Multiple input methods**: GUI secrets management tab + chat-based entry
- **Secret types**: SSH keys, passwords, API keys for agent resource access
- **Transfer capability**: Move chat secrets to general pool when needed
- **Cleanup dialogs**: On chat deletion, prompt for secret/file transfer or deletion
- **Security isolation**: Chat secrets only accessible within originating conversation
- **Agent integration**: Seamless access to appropriate secrets based on scope

### 📝 Development Workflow Standards

#### Regular Commit Strategy
**COMMIT EARLY AND OFTEN AFTER VERIFICATION**
- **Commit frequency**: After every logical unit of work (function, fix, feature component)
- **Maximum change threshold**: No more than 50-100 lines per commit unless absolutely necessary
- **Verification before each commit**:
  ```bash
  # 1. Run tests for affected areas
  python -m pytest tests/test_relevant_module.py -v

  # 2. Lint check
  flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503

  # 3. Quick functional test
  ./run_agent.sh --test-mode

  # 4. Commit with descriptive message
  git add . && git commit -m "type: brief description of change"
  ```

#### Commit Types & Examples
- `fix: resolve memory leak in NPU worker initialization`
- `feat: add Redis code search indexing capability`
- `test: add unit tests for secrets management`
- `docs: update API documentation for code search endpoints`
- `refactor: extract configuration logic to config.py`
- `security: update dependency versions for CVE fixes`
- `chore: organize test files into tests/ subdirectories`

#### When to Commit
✅ **DO COMMIT**:
- Single function implementation complete
- Bug fix verified and tested
- Configuration change tested
- Documentation update complete
- Test suite addition/modification
- Dependency update with verification

❌ **DON'T COMMIT**:
- Broken or partially working code
- Untested changes
- Mixed unrelated modifications
- Code with linting errors/warnings
- Changes without updated documentation

#### Commit Organization
**ALL COMMITS MUST BE ORGANIZED BY TOPIC AND FUNCTIONALITY**
- Group related changes together in logical sequence
- Provide clear, descriptive commit messages
- Ensure each commit represents a complete, working change
- Avoid mixing unrelated modifications in a single commit
- Separate refactoring, bug fixes, and feature additions into different commits

#### Priority Hierarchy
1. **🔴 Critical Errors** (blocking functionality)
2. **🟡 API Duplications** (technical debt, maintenance burden)
3. **🟡 Warnings** (potential issues)
4. **🔵 Security Updates** (mandatory)
5. **🟢 Features** (new functionality)
6. **⚪ Refactoring** (code improvement)

### 🏗️ Default Deployment Architecture

**AutoBot uses a HYBRID deployment model by default:**
- **Backend/Frontend**: Run on host system (localhost)
- **Services**: Run in Docker containers with exposed ports
- **Connection**: Host processes connect to containerized services via localhost ports

**Default Architecture:**
```
Host System (localhost)
├── Backend API           → http://localhost:8001 (host process)
├── Frontend UI           → http://localhost:5173 (host process)
└── Docker Containers     → Exposed on localhost ports
    ├── Redis             → redis://localhost:6379
    ├── AI Stack          → http://localhost:8080
    ├── NPU Worker        → http://localhost:8081
    └── Playwright VNC    → http://localhost:3000
```

### 🛠️ Quick Commands Reference

```bash
# APPLICATION LIFECYCLE (USER CONTROLLED)
./setup_agent.sh              # Initial setup and configuration
./run_agent.sh                # Start application (centralized logging by default)
./run_agent.sh --test-mode     # Start in test mode
./run_agent.sh --help          # Show available options

# CENTRALIZED LOGGING ACCESS
# Log Viewer (Seq): http://localhost:5341
# Credentials: admin / Autobot123!

# DISTRIBUTED DEPLOYMENT
./run_agent.sh --distributed --config=production.yml  # Distributed mode
export AUTOBOT_DEPLOYMENT_MODE=distributed           # Set deployment mode
export AUTOBOT_DOMAIN=autobot.prod                  # Set production domain

# SERVICE REGISTRY & DISCOVERY
# Location: src/utils/service_registry.py
# Modes: local, docker_local, distributed, kubernetes
# Health checks: Circuit breakers, automatic failover
# Config files: config/deployment/{mode}.yml

# DEVELOPMENT & TESTING
flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503  # Quality check
python test_phase9_ai.py                                             # Phase 9 testing
python test_npu_worker.py                                           # NPU testing

# API DUPLICATION PREVENTION (MANDATORY BEFORE NEW ENDPOINTS)
find backend/api -name "*.py" | xargs grep -h "@router\." | grep -i "keyword"  # Search existing endpoints
find autobot-vue -name "*.js" -o -name "*.vue" | xargs grep -l "api/"         # Check frontend usage

# PHASE VALIDATION (ON-DEMAND ONLY)
# NO programmatic phase validation - use GUI "Load Validation Data" button
# Located: Web UI → Validation tab → "Load Validation Data" button
# Purpose: On-demand system phase validation for performance optimization

# CODE ANALYSIS & PROFILING
python src/agents/npu_code_search_agent.py --query "search_term"    # NPU code search
python scripts/comprehensive_code_profiler.py                       # Codebase analysis
python scripts/automated_testing_procedure.py                       # Test suite
python scripts/profile_api_endpoints.py                            # API performance

# IMPORTANT: ALL APPLICATION RESTARTS MUST BE DONE BY USER
# Do not programmatically restart, stop, or kill application processes
# Phase validation is ON-DEMAND ONLY - do not trigger programmatically
```

### 🧪 Comprehensive Testing Procedures

#### **Automated Testing Framework**

The codebase includes a comprehensive automated testing suite that covers:

- **Unit Tests**: Individual function and module testing
- **Integration Tests**: Component interaction validation
- **API Tests**: Endpoint response and performance validation
- **Performance Tests**: Import speed and configuration access timing
- **Security Tests**: Command validation and file upload security
- **Code Quality Tests**: Flake8 compliance and import structure

#### **Test Execution Commands**

```bash
# Run full automated test suite
python scripts/automated_testing_procedure.py

# Run specific test categories
python -c "
from scripts.automated_testing_procedure import AutomatedTestingSuite
import asyncio
tester = AutomatedTestingSuite()

# Integration tests only
tester.run_integration_tests()

# Security tests only
tester.run_security_tests()

# Performance tests only
tester.run_performance_tests()
"

# Quick critical tests (fast)
timeout 60s python -c "
import asyncio, sys
sys.path.insert(0, '.')
from scripts.automated_testing_procedure import AutomatedTestingSuite

async def quick_test():
    tester = AutomatedTestingSuite()
    integration = tester.run_integration_tests()
    api = await tester.run_api_tests()
    security = tester.run_security_tests()
    print('✅ Integration:', len([r for r in integration if r.status == 'PASS']))
    print('✅ API:', len([r for r in api if r.status == 'PASS']))
    print('✅ Security:', len([r for r in security if r.status == 'PASS']))

asyncio.run(quick_test())
"
```

#### **Performance Profiling Commands**

```bash
# Full codebase analysis (AST, complexity, patterns)
python scripts/comprehensive_code_profiler.py

# Quick API performance check
python scripts/profile_api_endpoints.py

# Backend startup profiling
python scripts/profile_backend.py

# Generate performance report
ls reports/codebase_analysis_*.json | tail -1 | xargs cat | jq '.performance_hotspots'
```

#### **Test Results and Reports**

- **Test Results**: `reports/test_results_<timestamp>.json`
- **Codebase Analysis**: `reports/codebase_analysis_<timestamp>.json`
- **Performance Analysis**: `reports/performance_analysis_report.md`
- **API Performance**: Console output with speed ratings

#### **Hardware-Accelerated Testing**

```bash
# NPU-accelerated code search testing
python test_npu_worker.py

# GPU/CUDA testing (if available)
python -c "
from src.llm_interface import TORCH_AVAILABLE
from src.worker_node import TORCH_AVAILABLE as WORKER_TORCH
print(f'LLM Interface CUDA: {TORCH_AVAILABLE}')
print(f'Worker Node CUDA: {WORKER_TORCH}')
"

# Redis performance testing
python -c "
from src.utils.redis_client import get_redis_client
import time
client = get_redis_client()
start = time.time()
for i in range(1000): client.ping()
print(f'Redis 1000 pings: {(time.time()-start)*1000:.0f}ms')
"
```

#### **Continuous Integration Testing**

```bash
# Pre-commit testing pipeline
flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503
python scripts/profile_api_endpoints.py
./run_agent.sh --test-mode

# Full CI/CD simulation
python scripts/automated_testing_procedure.py
python scripts/comprehensive_code_profiler.py
npm run build --prefix autobot-vue
```

### 📋 Pre-Deployment Checklist

#### Before Each Commit

- [ ] Tests pass for affected modules
- [ ] Flake8 checks clean
- [ ] Quick functional test completed
- [ ] Changes are logically complete
- [ ] Commit message is descriptive

#### Before Full Deployment

- [ ] All incremental commits verified
- [ ] Integration tests pass
- [ ] Documentation updated
- [ ] Dependencies documented
- [ ] Data backed up (if schema changes)
- [ ] Security review completed
- [ ] All commit messages follow convention
- [ ] Related changes properly sequenced

#### Emergency Rollback Plan

- Each commit is atomic and can be reverted independently
- Critical changes have backup commits before implementation
- Database migrations are reversible
- Configuration changes are documented with previous values

---

**Remember**: Quality and completeness are non-negotiable. Every task started must be completed to production standards.
