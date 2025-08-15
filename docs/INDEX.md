# AutoBot Documentation Index

This is the comprehensive documentation index for AutoBot - Enterprise-Grade Autonomous AI Platform.

## 📚 Documentation Categories

### 🚀 Getting Started
- [Installation Guide](user_guide/01-installation.md) - Complete setup instructions
- [Quick Start Guide](user_guide/02-quickstart.md) - Get running in 5 minutes
- [Configuration Guide](user_guide/03-configuration.md) - System configuration
- [Troubleshooting Guide](user_guide/04-troubleshooting.md) - Common issues and solutions

### 🏗️ Architecture & Development
- [System Architecture](architecture/NPU_WORKER_ARCHITECTURE.json) - NPU worker and system design
- [GPU Recommendations](architecture/gpu_model_recommendations.json) - Hardware optimization
- [Architecture Guide](developer/01-architecture.md) - System design principles
- [Process Flow](developer/02-process-flow.md) - Request handling flow
- [API Reference](developer/03-api-reference.md) - Complete API documentation
- [Configuration Reference](developer/04-configuration.md) - Configuration options

### 🤖 Multi-Agent System
- [Multi-Agent Architecture](agents/multi-agent-architecture.md) - Agent coordination system
- [Helper Agents Guide](agents/helper-agents-guide.md) - Specialized agent development
- [Librarian Agents Guide](agents/librarian-agents-guide.md) - Knowledge management agents
- [Multi-Agent Setup](guides/MULTI_AGENT_SETUP.md) - Deployment configuration

### 🛠️ Deployment & Operations
- [Hybrid Deployment Guide](deployment/HYBRID_DEPLOYMENT_GUIDE.md) - Multi-container deployment
- [Docker Architecture](deployment/DOCKER_ARCHITECTURE.md) - Container orchestration
- [Docker Migration Notes](deployment/DOCKER_MIGRATION_NOTES.md) - Migration strategies
- [CI Pipeline Setup](deployment/CI_PIPELINE_SETUP.md) - Continuous integration

### 🔄 Workflow Management
- [Workflow API Documentation](workflow/WORKFLOW_API_DOCUMENTATION.md) - API reference
- [Advanced Workflow Features](workflow/ADVANCED_WORKFLOW_FEATURES.md) - Advanced capabilities
- [Workflow Orchestration Summary](workflow/WORKFLOW_ORCHESTRATION_SUMMARY.md) - System overview
- [Workflow Success Demo](workflow/WORKFLOW_SUCCESS_DEMO.md) - Success metrics
- [Redis Classification Demo](workflow/REDIS_CLASSIFICATION_DEMO.md) - Classification system

### 🛡️ Security
- [Security Implementation Summary](security/SECURITY_IMPLEMENTATION_SUMMARY.md) - Core security features
- [Security Agents Summary](security/SECURITY_AGENTS_SUMMARY.md) - Automated security monitoring
- [Session Takeover Demo](security/SESSION_TAKEOVER_DEMO.md) - Security capabilities demo
- [Session Takeover User Guide](security/SESSION_TAKEOVER_USER_GUIDE.md) - User instructions

### 🧪 Testing & Quality Assurance
- [Testing Framework Summary](testing/TESTING_FRAMEWORK_SUMMARY.md) - Test infrastructure
- [Frontend Test Report](testing/FRONTEND_TEST_REPORT.md) - UI/UX validation
- [GUI Test Summary](testing/GUI_TEST_SUMMARY.md) - End-to-end testing
- [Test Results Summary](testing/TEST_RESULTS_SUMMARY.md) - Comprehensive test results
- [Edge Browser Fix Report](testing/EDGE_BROWSER_FIX_REPORT.md) - Browser compatibility

### 📊 Monitoring & Features
- [Metrics Monitoring Summary](features/METRICS_MONITORING_SUMMARY.md) - Performance tracking
- [System Status](features/SYSTEM_STATUS.md) - Health monitoring
- [System Optimization Report](features/SYSTEM_OPTIMIZATION_REPORT.md) - Performance tuning

### 🔄 Migration & Procedures
- [Error Handling Migration Guide](migration/ERROR_HANDLING_MIGRATION_GUIDE.md) - Error handling updates

### 🗂️ Configuration & Templates
- [Environment Template](guides/env_template.txt) - Environment configuration template
- [Port Mappings](guides/PORT_MAPPINGS.md) - Network port assignments
- [Requirements (Local)](guides/requirements-local.txt) - Local development dependencies

### 📈 Analysis & Reports (Legacy)
- [Frontend Fixes Completion Summary](reports/legacy/FRONTEND_FIXES_COMPLETION_SUMMARY.md)
- [Security Audit Report](reports/legacy/SECURITY_AUDIT_REPORT.md)
- [Testing Framework Summary](reports/legacy/TESTING_FRAMEWORK_SUMMARY.md)
- [Test Results Summary](reports/legacy/TEST_RESULTS_SUMMARY.md)
- [Accessibility Fix Report](reports/legacy/accessibility-fix-report.md)
- [Console Cleanup Report](reports/legacy/console-cleanup-report.md)
- [Error Handling Analysis Report](reports/legacy/error_handling_analysis_report.md)

### 🗃️ Legacy Logs
- [Legacy Log Files](logs/legacy/) - Historical system logs

## 🔍 Quick Reference

### Essential Commands
```bash
# Setup and start
./scripts/setup/setup_agent.sh
./run_agent.sh

# Development
./scripts/deployment/start_all_containers.sh
./scripts/testing/run-playwright-tests.sh

# Report management
python scripts/utilities/report_manager.py --list
```

### Key Configuration Files
- `config/config.yaml` - Main system configuration
- `docker-compose.hybrid.yml` - Hybrid deployment configuration
- `requirements.txt` - Python dependencies
- `autobot-vue/package.json` - Frontend dependencies

### Important Directories
- `src/` - Core Python source code
- `backend/api/` - FastAPI endpoints
- `autobot-vue/src/` - Vue 3 frontend
- `scripts/` - Organized shell scripts
- `tests/` - Test suites and validation
- `reports/` - Organized report storage

## 📝 Documentation Standards

1. **Linking**: All documents must link to related documentation
2. **Organization**: Files organized by purpose in appropriate subdirectories
3. **Consistency**: Follow established naming conventions
4. **Maintenance**: Keep documentation up-to-date with code changes
5. **Accessibility**: Clear navigation and cross-references

## 🔄 Regular Updates

This documentation index is automatically maintained and should reflect the current state of the AutoBot platform. For the most recent updates, see:

- [Project Status](status.md) - Current development status
- [Changes Log](CHANGES.md) - Recent modifications
- [Task Tracking](tasks.md) - Ongoing development tasks

---

**Last Updated**: Auto-generated based on current documentation structure
**Maintained By**: AutoBot Development Team
