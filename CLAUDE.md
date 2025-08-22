# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 📚 PROJECT INFORMATION SOURCES

**IMPORTANT: Always refer to these primary sources for project information:**

- **[README.md](README.md)** - Primary project documentation, architecture overview, and getting started guide
- **[docs/](docs/)** - Comprehensive documentation folder with detailed guides and specifications
- **[docs/INDEX.md](docs/INDEX.md)** - Complete documentation index and navigation
- **[Executive Summary](EXECUTIVE_SUMMARY.md)** - Business overview and value proposition

## 📚 DEVELOPMENT GUIDES

**For focused guidance, refer to these area-specific guides:**

- **[Core Rules & Standards](docs/development/CORE_RULES.md)** - Zero tolerance rules, application lifecycle, configuration standards
- **[Backend & API Development](docs/development/BACKEND_API.md)** - API design, backend architecture, NPU worker, secrets management
- **[Frontend Development](docs/development/FRONTEND.md)** - Vue.js, WebSocket integration, UI/UX standards, error handling
- **[Testing & Deployment](docs/development/TESTING_DEPLOYMENT.md)** - Testing procedures, commit workflow, deployment architecture
- **[Logs](docs/logs)** - Project Logs, always check logs

## 🚀 QUICK REFERENCE

### Critical Commands

```bash
# Quality Check
flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503

# Application Lifecycle
./setup_agent.sh              # Initial setup
./run_agent.sh                # Start application
./run_agent.sh --test-mode     # Test mode

# Testing
python scripts/automated_testing_procedure.py  # Full test suite
python test_npu_worker.py                      # NPU testing
```

### Project Structure

```
project_root/
├── src/                    # Source code
├── backend/               # Backend services
├── autobot-vue/           # Frontend Vue.js app
├── tests/                 # ALL test files
├── docs/                  # Comprehensive documentation
├── scripts/               # Utility scripts
├── docker/                # Docker infrastructure
│   ├── compose/           # Docker compose configurations
│   ├── agents/            # Agent-specific Dockerfiles
│   ├── base/              # Base container configurations
│   └── volumes/           # Volume configurations
├── data/                  # Data files
└── run_agent.sh          # Main entry point
```

### Emergency Contacts

- **Application Restart**: User must run `./run_agent.sh` (requires sudo)
- **API Duplications**: See [Backend API Guide](docs/development/BACKEND_API.md#-api-consolidation-process)
- **Testing Failures**: See [Testing Guide](docs/development/TESTING_DEPLOYMENT.md#-comprehensive-testing-procedures)
- **Configuration Issues**: Use `src/config.py` - NO hardcoded values

## 🔴 ZERO TOLERANCE RULES

1. **NO error left unfixed, NO warning left unfixed**
2. **NEVER abandon started tasks**
3. **ALWAYS test before committing**
4. **NEVER restart applications programmatically**
5. **NO hardcoded values** - use environment variables/config

---

**📖 For detailed guidance on specific areas, always refer to the focused guides above.**
