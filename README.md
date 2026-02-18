# AutoBot - Autonomous Linux Administration Platform

AutoBot is a comprehensive autonomous system for Linux administration, featuring multi-modal AI capabilities, distributed infrastructure, and intelligent automation.

## Quick Start

### Starting AutoBot

**Method 1: CLI Wrapper (Recommended for developers)**
```bash
# Start all services
scripts/start-services.sh start

# Start specific service
scripts/start-services.sh start backend

# Check status
scripts/start-services.sh status

# View logs
scripts/start-services.sh logs backend
```

**Method 2: SLM Orchestration GUI (Recommended for operations)**
```bash
# Open web interface
scripts/start-services.sh gui
# Or visit: https://172.16.168.19/orchestration
```

**Method 3: Direct systemctl commands**
```bash
# Start backend service
sudo systemctl start autobot-backend

# Check status
systemctl status autobot-backend

# View logs
journalctl -u autobot-backend -f
```

See [Service Management Guide](docs/developer/SERVICE_MANAGEMENT.md) for complete documentation.

### Initial Setup
```bash
# Complete initial setup
bash setup.sh

# Setup specific components
bash setup.sh knowledge    # Knowledge base only
bash setup.sh docker       # Docker configuration
bash setup.sh agent        # Agent environment
bash setup.sh system       # System configuration
```

## Infrastructure Overview

**Main Machine (WSL):** 172.16.168.20 - Backend API
**Remote VMs:**
- VM1 Frontend: 172.16.168.21 - Web interface
- VM2 NPU Worker: 172.16.168.22 - Hardware AI acceleration
- VM3 Redis: 172.16.168.23 - Data layer
- VM4 AI Stack: 172.16.168.24 - AI processing
- VM5 Browser: 172.16.168.25 - Web automation

## Redis Database Architecture

AutoBot uses a comprehensive Redis database architecture with specialized databases for different data types. This organization enables individual database repopulation and maintenance.

### Database Allocation

| Database | Purpose | Current Keys | Description |
|----------|---------|--------------|-------------|
| **DB 0** | **Vectors** | 14,047 | LlamaIndex vectors with Redis search index support |
| **DB 1** | **Knowledge Facts** | 27 | Knowledge base facts and metadata |
| **DB 2** | **Prompts** | 0 | AI prompt templates and configurations |
| **DB 3** | **Other System Data** | 200 | Restored system data and miscellaneous |
| **DB 4** | **Metrics** | 1 | Performance and system metrics |
| **DB 5** | **Cache** | 0 | Temporary cached data |
| **DB 6** | **Sessions** | 0 | User session data |
| **DB 7** | **Tasks** | 0 | Task management and workflow data |
| **DB 8** | **Analytics** | 24,803 | Code analytics and indexing data |
| **DB 9** | **Temp** | 0 | Temporary data storage |
| **DB 10** | **Backup** | 20 | Backup and recovery data |
| **DB 11** | **Additional Data** | 6,627 | Extended system data |
| **DB 15** | **Testing** | 0 | Test data and development |

### Key Features

- **Individual Repopulation**: Each database can be cleared and repopulated independently
- **Redis Search Support**: DB 0 supports Redis search indexes for vector operations
- **Logical Separation**: Different data types are isolated for better maintainability
- **Scalable Design**: Easy to add new databases for specific use cases

### Management Commands

```bash
# Check database sizes
for db in {0..15}; do echo -n "DB$db: "; redis-cli -h 172.16.168.23 -p 6379 -n $db DBSIZE; done

# Clear specific database (example: temp data)
redis-cli -h 172.16.168.23 -p 6379 -n 9 FLUSHDB

# Backup specific database
redis-cli -h 172.16.168.23 -p 6379 -n 0 --rdb vectors_backup.rdb
```

### Redis Service Management

AutoBot now includes comprehensive Redis service management capabilities:

- **Web UI Controls**: Start, stop, restart Redis from the frontend interface
- **Health Monitoring**: Real-time health checks and status reporting
- **Auto-Recovery**: Automatic failure detection and recovery
- **Role-Based Access**: Granular permissions for different user roles
- **Audit Logging**: Complete audit trail of all service operations

**Documentation:**
- [Redis Service Management API](docs/api/REDIS_SERVICE_MANAGEMENT_API.md) - Complete API reference
- [Redis Service Management User Guide](docs/user-guides/REDIS_SERVICE_MANAGEMENT_GUIDE.md) - How to use service controls
- [Redis Service Operations Runbook](docs/operations/REDIS_SERVICE_RUNBOOK.md) - Operational procedures
- [Redis Service Architecture](docs/architecture/REDIS_SERVICE_MANAGEMENT_ARCHITECTURE.md) - Technical architecture

## Access Points

- **SLM Orchestration:** https://172.16.168.19/orchestration (Service management GUI)
- **User Frontend:** https://172.16.168.21 (Vue.js interface)
- **Backend API:** https://172.16.168.20:8443 (FastAPI with TLS)
- **VNC Desktop:** http://localhost:6080 (when enabled)

## Documentation

### Core Documentation
- [**System Configuration**](CLAUDE.md) - Complete development notes, fixes, and architecture
- [**Infrastructure**](autobot-infrastructure/README.md) - Per-role infrastructure and deployment scripts
- [**Scripts & Utilities**](autobot-infrastructure/shared/scripts/README.md) - All scripts and utilities documentation
- [**Troubleshooting Guide**](docs/troubleshooting/INDEX.md) - Searchable index of 15+ troubleshooting guides organized by component and symptom

### MCP & Agent Integration
- [**LangChain MCP Integration Guide**](docs/developer/LANGCHAIN_MCP_INTEGRATION.md) - How to integrate AutoBot MCP tools with LangChain agents
- [**MCP Security Testing**](docs/security/MCP_SECURITY_TESTING.md) - Security penetration testing for MCP bridges
- [**MCP Agent Workflow Examples**](examples/mcp_agent_workflows/) - Working examples for research, code analysis, and VNC monitoring

### Technical Reports
- [**Network Configuration**](reports/NETWORK_STANDARDIZATION_REPORT.md) - Infrastructure standardization
- [**Configuration Remediation**](reports/COMPREHENSIVE_CONFIGURATION_REMEDIATION_FINAL_REPORT.md) - Config fixes and improvements
- [**Setup & Deployment**](reports/SUBAGENT_HOTEL_PHASE2_COMPLETION_REPORT.md) - Phase 2 completion details
- [**Project Cleanup**](reports/ROOT_CLEANUP_COMPLETE.md) - File organization and cleanup
- [**Native VM Setup**](reports/NATIVE_VM_SETUP.md) - VM deployment procedures

### Analysis & Audit Reports
- [**Hardcoded Values Audit**](reports/HARDCODED_VALUES_AUDIT.md) - Code quality improvements
- [**Configuration Migration**](reports/CONFIGURATION_MIGRATION_GUIDE.md) - Migration procedures
- [**Config Refactor Plan**](reports/CONFIG_REFACTOR_PLAN.md) - Refactoring strategy

### Test Results
- Test results are stored in [tests/results/](tests/results/) directory
- API testing reports and comprehensive test outputs

## Key Features

- **Multi-Modal AI:** Vision, voice, and text processing capabilities
- **Distributed Architecture:** Multi-VM deployment with service isolation
- **Intelligent Automation:** Context-aware task execution
- **Knowledge Base:** RAG-powered documentation and learning system
- **Real-time Monitoring:** Comprehensive system and service monitoring
- **Redis Service Management:** Web UI controls with auto-recovery and health monitoring
- **Security-First:** Enhanced security layers and audit capabilities
- **Hardware Acceleration:** NPU and GPU optimization support

## Development Guidelines

- Use service management methods (CLI wrapper, SLM GUI, or systemctl) - see [Service Management Guide](docs/developer/SERVICE_MANAGEMENT.md)
- All reports and documentation are organized in appropriate folders
- Follow the established file organization structure
- See [CLAUDE.md](CLAUDE.md) for complete development procedures and fixes

## Current Status: Production Ready ✅

All critical issues resolved with permanent architectural fixes:
- ✅ Chat persistence across sessions
- ✅ 100% API endpoint functionality
- ✅ Knowledge base fully operational (14,047 vectors with search support)
- ✅ Distributed VM infrastructure stable
- ✅ Multi-service coordination working
- ✅ Hardware optimization active
- ✅ Redis service management with auto-recovery

For detailed technical information, troubleshooting, and architectural details, see [CLAUDE.md](CLAUDE.md).
