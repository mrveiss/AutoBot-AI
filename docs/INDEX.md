---
tags:
  - index
  - home
aliases:
  - Home
  - AutoBot Docs
cssclasses:
  - home-note
---

# AutoBot Documentation Index

> **Your data. Your AI.**
>
> AutoBot is a self-hosted AI platform you own: a small, solid core, a management
> layer that runs the hard infrastructure for you, and modules you install on top.
>
> New here? Read **[The AutoBot Platform Model](architecture/PLATFORM_MODEL.md)** —
> the core → SLM → modules picture that everything below builds on.

---

## Quick Start

| Document | Description |
|----------|-------------|
| [Getting Started](GETTING_STARTED_COMPLETE.md) | Complete setup guide |
| [Getting Started Index](getting-started/_index.md) | Installation guides by environment |
| [Install in a VM](getting-started/install-vm.md) | VirtualBox, VMware, Hyper-V, KVM, WSL2 |
| [Browser VNC Quick Start](QUICK_START_BROWSER_VNC.md) | VNC desktop access |
| [System State](system-state.md) | Current system status |
| [Glossary](GLOSSARY.md) | Terminology reference |
| [Changelog](../changelog/_index.md) | Per-version release notes and unreleased fragments |
| [Dependencies](DEPENDENCIES.md) | Dependency reference |
| [Roadmap (2025–2026)](ROADMAP_2025.md) | Product roadmap |

---

## Platform & Modules

| Document | Description |
|----------|-------------|
| [The AutoBot Platform Model](architecture/PLATFORM_MODEL.md) | Core → SLM management layer → modules |
| [Service Lifecycle Manager (SLM)](guides/slm-docker-ansible-deployment.md) | The management layer: deploy, operate, scale your AI infrastructure |
| [AutoBot LLC](llc/_index.md) | Flagship module: an autonomous agent-company you install |

---

## User Guides

| Guide | Description |
|-------|-------------|
| [User Docs Index](user/_index.md) | All user documentation |
| [01 - Installation](user-guide/01-installation.md) | Complete setup instructions |
| [02 - Quick Start](user-guide/02-quickstart.md) | Get running in 5 minutes |
| [03 - Configuration](user-guide/03-configuration.md) | System configuration |
| [04 - Troubleshooting](user-guide/04-troubleshooting.md) | Common issues and solutions |
| [05 - Preferences](user-guide/05-preferences.md) | User preferences guide |
| [06 - Redis Management](user-guide/06-redis-management.md) | Redis service management |

---

## Developer Documentation

| Document | Description |
|----------|-------------|
| [Developer Docs Index](developer/_index.md) | All developer documentation |
| [Developer Setup](developer/DEVELOPER_SETUP.md) | Developer onboarding |
| [Architecture Guide](developer/01-architecture.md) | System design principles |
| [Process Flow](developer/02-process-flow.md) | Request handling flow |
| [API Reference](developer/03-api-reference.md) | Complete API documentation |
| [Configuration Reference](developer/04-configuration.md) | Configuration options |
| [CLAUDE Rules](developer/CLAUDE_RULES.md) | Core development rules |
| [CLAUDE Workflow](developer/CLAUDE_WORKFLOW.md) | Development workflow |
| [AutoBot Reference](developer/AUTOBOT_REFERENCE.md) | IPs, playbooks, quick reference |

---

## Architecture

| Document | Description |
|----------|-------------|
| [Architecture Index](architecture/_index.md) | All architecture documentation |
| [Architecture Overview](architecture/README.md) | System architecture |
| [Agent System Architecture](architecture/AGENT_SYSTEM_ARCHITECTURE.md) | Agent design |
| [Memory Graph Architecture](architecture/AUTOBOT_MEMORY_GRAPH_ARCHITECTURE.md) | Knowledge graph |
| [Distributed Architecture](architecture/DISTRIBUTED_6VM_ARCHITECTURE.md) | Multi-VM design |
| [Communication Architecture](architecture/COMMUNICATION_ARCHITECTURE.md) | Service communication |
| [Monitoring Architecture](architecture/MONITORING_ARCHITECTURE.md) | System monitoring |
| [SSOT Configuration](architecture/SSOT_CONFIGURATION_ARCHITECTURE.md) | Single source of truth |
| [ADR Index](adr/_index.md) | Architecture decision records |

---

## API Documentation

| Document | Description |
|----------|-------------|
| [API Index](api/_index.md) | All API documentation |
| [Comprehensive API](api/COMPREHENSIVE_API_DOCUMENTATION.md) | Full API reference |
| [API Endpoint Mapping](api/API_ENDPOINT_MAPPING.md) | Endpoint overview |
| [WebSocket Integration](api/WEBSOCKET_INTEGRATION_GUIDE.md) | Real-time communication |
| [Terminal API](api/Terminal_API_Consolidated.md) | Terminal endpoints |
| [Redis Service API](api/REDIS_SERVICE_MANAGEMENT_API.md) | Redis management |

---

## Agent System

| Document | Description |
|----------|-------------|
| [Agents Index](agents/_index.md) | All agent documentation |
| [Multi-Agent Architecture](agents/multi-agent-architecture.md) | Agent coordination |
| [Helper Agents Guide](agents/helper-agents-guide.md) | Specialized agents |
| [Librarian Agents Guide](agents/librarian-agents-guide.md) | Knowledge agents |

---

## Features

| Document | Description |
|----------|-------------|
| [Capability Catalog](features/CATALOG.md) | Full map of what AutoBot can do — including previously buried capabilities |
| [Features Index](features/_index.md) | All feature documentation |
| [Knowledge Graph](features/KNOWLEDGE_GRAPH.md) | Knowledge management |
| [Advanced Analytics](features/ADVANCED_ANALYTICS.md) | Codebase analytics |
| [Multimodal AI](features/MULTIMODAL_AI_INTEGRATION.md) | Multimodal integration |
| [Log Forwarding](features/LOG_FORWARDING.md) | Centralized logging |
| [MCP Integration](features/mcp-knowledge-base-integration.md) | MCP tools |

---

## Security

| Document | Description |
|----------|-------------|
| [Security Index](security/_index.md) | All security documentation |
| [Security Implementation](security/SECURITY_IMPLEMENTATION_SUMMARY.md) | Core security |
| [Service Auth Enforcement](security/SERVICE_AUTH_ENFORCEMENT_ROLLOUT_PLAN.md) | Authentication |
| [Access Control Guide](security/ACCESS_CONTROL_SAFE_ROLLOUT_GUIDE.md) | Authorization |
| [TLS Certificate Management](security/TLS_CERTIFICATE_MANAGEMENT.md) | Certificate management |

---

## Infrastructure & Deployment

| Document | Description |
|----------|-------------|
| [Infrastructure Index](infrastructure/_index.md) | All infrastructure documentation |
| [Deployment Index](deployment/_index.md) | All deployment documentation |
| [Operations Index](operations/_index.md) | All operations documentation |
| [Deployment Guide](deployment/comprehensive_deployment_guide.md) | Full deployment |
| [CI Pipeline Setup](deployment/CI_PIPELINE_SETUP.md) | Continuous integration |
| [Disaster Recovery](operations/disaster-recovery.md) | Recovery procedures |
| [Scaling Strategy](operations/scaling-strategy.md) | Scaling strategy |

---

## Runbooks

| Document | Description |
|----------|-------------|
| [Runbooks Index](runbooks/_index.md) | All runbooks |
| [Code Update](runbooks/CODE_UPDATE.md) | Code update runbook |
| [Deploy New Node](runbooks/DEPLOY_NEW_NODE.md) | Deploy new node |
| [Emergency Recovery](runbooks/EMERGENCY_RECOVERY.md) | Emergency recovery |
| [Rotate Certs](runbooks/ROTATE_CERTS.md) | Rotate TLS certificates |

---

## How-To Guides

| Document | Description |
|----------|-------------|
| [Guides Index](guides/_index.md) | All guides |
| [SLM Bash Execution](guides/slm-bash-execution.md) | Execute bash commands via SLM |
| [Visual Workflow Execution](guides/visual-workflow-parallel-execution.md) | Parallel shell script workflows |
| [RAG PDF Workflow](guides/rag-pdf-workflow.md) | RAG pipeline with PDF documents |
| [Vision VNC UI Testing](guides/vision-vnc-ui-testing.md) | Automated UI testing via Vision |
| [Distributed Task Failover](guides/distributed-task-failover-redis.md) | Redis-backed task failover |
| [Ansible Playbook Reference](guides/ANSIBLE_PLAYBOOK_REFERENCE.md) | Ansible playbook reference |

---

## Workflow Management

| Document | Description |
|----------|-------------|
| [Workflow Index](workflow/_index.md) | All workflow documentation |
| [Workflow API](workflow/WORKFLOW_API_DOCUMENTATION.md) | API reference |
| [Advanced Features](workflow/ADVANCED_WORKFLOW_FEATURES.md) | Advanced capabilities |
| [Workflow Orchestration](workflow/WORKFLOW_ORCHESTRATION_SUMMARY.md) | System overview |

---

## Testing & Quality

| Document | Description |
|----------|-------------|
| [Testing Index](testing/_index.md) | All testing documentation |
| [Testing Framework](testing/TESTING_FRAMEWORK_SUMMARY.md) | Test infrastructure |
| [Performance Benchmarks](testing/PERFORMANCE_BENCHMARKS.md) | Performance benchmarks |
| [Frontend Tests](testing/FRONTEND_TEST_REPORT.md) | UI/UX validation |

---

## Troubleshooting

| Document | Description |
|----------|-------------|
| [Troubleshooting Index](troubleshooting/_index.md) | All troubleshooting guides |
| [Comprehensive Guide](troubleshooting/COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md) | All issues |
| [Ansible Deployment Failures](troubleshooting/guides/ansible-role-deployment-failures.md) | Ansible failures |
| [Frontend 404/401 Errors](troubleshooting/guides/frontend-api-calls-404-401-errors.md) | Frontend errors |

---

## Migration Guides

| Document | Description |
|----------|-------------|
| [Error Handling Migration](migration/ERROR_HANDLING_MIGRATION_GUIDE.md) | Error handling |
| [Async System Migration](migration/Async_System_Migration.md) | Async updates |
| [LLM Interface Migration](migration/LLM_Interface_Migration_Guide.md) | LLM changes |

---

## SDK

| Document | Description |
|----------|-------------|
| [SDK Index](sdk/_index.md) | All SDK documentation |
| [Python Quickstart](sdk/python-quickstart.md) | Python SDK quickstart |
| [TypeScript Quickstart](sdk/typescript-quickstart.md) | TypeScript SDK quickstart |

---

## Frontend

| Document | Description |
|----------|-------------|
| [Frontend Index](frontend/_index.md) | All frontend documentation |
| [Design System](frontend/DESIGN_SYSTEM_COMPLETE.md) | Design system |
| [Settings Panel Guide](frontend/settings-panel-guide.md) | Settings panel guide |

---

## Implementation Reports

| Document | Description |
| --- | --- |
| [Implementation Index](implementation/_index.md) | All implementation reports |
| [Reports Index](reports/_index.md) | All reports |
| [Refactoring Index](refactoring/_index.md) | All refactoring documentation |

---

## Planning & Historical

| Document | Description |
| --- | --- |
| [Planning Index](planning/_index.md) | Historical planning documents |
| [Development Index](development/_index.md) | Development documentation |
| [Plans Archive](archives/plans/_index.md) | Dated implementation plans (Jan–Mar 2026) |
| [ADR Index](adr/_index.md) | Architecture decision records |

---

## Configuration

| Document | Description |
| --- | --- |
| [Environment Variables](configuration/environment-variables.md) | Environment config |
| [VNC Port Configuration](configuration/VNC_PORT_CONFIGURATION.md) | VNC port config |

---

## Key Directories

| Directory | Purpose |
| --- | --- |
| `autobot-backend/` | Main backend API |
| `autobot-frontend/` | User chat interface |
| `autobot-slm-backend/` | SLM backend |
| `autobot-slm-frontend/` | SLM dashboard |
| `autobot_shared/` | Shared utilities |
| `autobot-infrastructure/` | Deployment infrastructure |
