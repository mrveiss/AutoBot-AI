# Testing & Deployment Guide

## 🧪 Testing & Quality Assurance

### Pre-commit checks
```bash
flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503
```

### Test Commands
- **Test mode verification**: `./run_agent.sh --test-mode` before full deployment
- **Multi-modal testing**: `python test_multimodal_ai.py` after multi-modal changes
- **NPU worker testing**: `python test_npu_worker.py` after OpenVINO modifications
- **Phase validation**: ON-DEMAND ONLY - use "Load Validation Data" button in GUI
- **ALL test files MUST be in `tests/` folder or subfolders**

## 🧪 Comprehensive Testing Procedures

### **Automated Testing Framework**

The codebase includes a comprehensive automated testing suite that covers:

- **Unit Tests**: Individual function and module testing
- **Integration Tests**: Component interaction validation
- **API Tests**: Endpoint response and performance validation
- **Performance Tests**: Import speed and configuration access timing
- **Security Tests**: Command validation and file upload security
- **Code Quality Tests**: Flake8 compliance and import structure

### **Test Execution Commands**

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

### **Performance Profiling Commands**

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

### **Test Results and Reports**

- **Test Results**: `reports/test_results_<timestamp>.json`
- **Codebase Analysis**: `reports/codebase_analysis_<timestamp>.json`
- **Performance Analysis**: `reports/performance_analysis_report.md`
- **API Performance**: Console output with speed ratings

### **Hardware-Accelerated Testing**

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

### **Continuous Integration Testing**

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

## 📝 Development Workflow Standards

### Regular Commit Strategy
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

### Commit Types & Examples
- `fix: resolve memory leak in NPU worker initialization`
- `feat: add Redis code search indexing capability`
- `test: add unit tests for secrets management`
- `docs: update API documentation for code search endpoints`
- `refactor: extract configuration logic to config.py`
- `security: update dependency versions for CVE fixes`
- `chore: organize test files into tests/ subdirectories`

### When to Commit
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

### Commit Organization
**ALL COMMITS MUST BE ORGANIZED BY TOPIC AND FUNCTIONALITY**
- Group related changes together in logical sequence
- Provide clear, descriptive commit messages
- Ensure each commit represents a complete, working change
- Avoid mixing unrelated modifications in a single commit
- Separate refactoring, bug fixes, and feature additions into different commits

## 📋 Pre-Deployment Checklist

### Before Each Commit

- [ ] Tests pass for affected modules
- [ ] Flake8 checks clean
- [ ] Quick functional test completed
- [ ] Changes are logically complete
- [ ] Commit message is descriptive

### Before Full Deployment

- [ ] All incremental commits verified
- [ ] Integration tests pass
- [ ] Documentation updated
- [ ] Dependencies documented
- [ ] Data backed up (if schema changes)
- [ ] Security review completed
- [ ] All commit messages follow convention
- [ ] Related changes properly sequenced

### Emergency Rollback Plan

- Each commit is atomic and can be reverted independently
- Critical changes have backup commits before implementation
- Database migrations are reversible
- Configuration changes are documented with previous values

## 🚀 Deployment Architecture

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

### Default Deployment Architecture

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

---

**Remember**: Quality and completeness are non-negotiable. Every task started must be completed to production standards.
