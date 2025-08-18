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

#### 🧪 Testing & Quality Assurance
- **Pre-commit checks**: `flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503`
- **Test mode verification**: `./run_agent.sh --test-mode` before full deployment
- **Phase 9 testing**: `python test_phase9_ai.py` after multi-modal changes
- **NPU worker testing**: `python test_npu_worker.py` after OpenVINO modifications
- **ALL test files MUST be in `tests/` folder or subfolders**

#### ⚙️ Configuration & Dependencies
- **NEVER hardcode values** - use `src/config.py` for all configuration
- **Update docstrings** following Google style for any function changes
- **Dependencies must reflect in**:
  - Install scripts
  - requirements.txt
  - **SECURITY UPDATES MANDATORY**

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
2. **🟡 Warnings** (potential issues)
3. **🔵 Security Updates** (mandatory)
4. **🟢 Features** (new functionality)
5. **⚪ Refactoring** (code improvement)

### 🛠️ Quick Commands Reference

```bash
# Pre-commit quality check
flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503

# Test mode verification
./run_agent.sh --test-mode

# Phase 9 testing
python test_phase9_ai.py

# NPU worker testing
python test_npu_worker.py

# Code search via NPU
python src/agents/npu_code_search_agent.py --query "your_search_query"
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