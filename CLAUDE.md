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
17. **CRITICAL**: Any dependency installed needs to reflect in install scripts AND requirements.txt - SECURITY UPDATES MANDATORY

### NPU Worker and Redis Code Search Capabilities
- **YOU ARE AUTHORIZED TO USE NPU WORKER AND REDIS FOR ADVANCED CODE ANALYSIS**
  - Use `src/agents/npu_code_search_agent.py` for high-performance code searching
  - Use `/api/code_search/` endpoints for code analysis tasks
  - NPU acceleration available for semantic code similarity when hardware supports it
  - Redis-based indexing provides fast code element lookup (functions, classes, imports)
  - **APPROVED DEVELOPMENT SPEEDUP TASKS:**
    - Code duplicate detection and removal
    - Cross-codebase pattern analysis and comparisons
    - Semantic code similarity searches
    - Function/class dependency mapping
    - Import optimization and unused code detection
    - Architecture pattern identification
    - Code quality consistency analysis
    - Dead code elimination assistance
    - Refactoring opportunity identification

### Secrets Management Requirements
- **IMPLEMENT COMPREHENSIVE SECRETS MANAGEMENT SYSTEM**
  - **Dual-scope secrets**: Chat-scoped (conversation-only) vs General-scoped (all chats)
  - **Multiple input methods**: GUI secrets management tab + chat-based entry
  - **Secret types**: SSH keys, passwords, API keys for agent resource access
  - **Transfer capability**: Move chat secrets to general pool when needed
  - **Cleanup dialogs**: On chat deletion, prompt for secret/file transfer or deletion
  - **Security isolation**: Chat secrets only accessible within originating conversation
  - **Agent integration**: Seamless access to appropriate secrets based on scope

### Development Workflow Memories
- **ALL COMMITS MUST BE ORGANIZED BY TOPIC AND FUNCTIONALITY**
  - Group related changes together
  - Provide clear, descriptive commit messages
  - Ensure each commit represents a logical, cohesive change
  - Avoid mixing unrelated modifications in a single commit
  - Separate refactoring, bug fixes, and feature additions
