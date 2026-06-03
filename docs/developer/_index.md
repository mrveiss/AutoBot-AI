---
tags:
  - index
  - developer
aliases:
  - Developer Index
---

# Developer Documentation

## Subdirectories

| Directory | Description |
| --- | --- |
| [[audits/_index\|audits/]] | Code quality and architecture audits |
| [[i18n/_index\|i18n/]] | Internationalization and translation docs |
| [[skills/_index\|skills/]] | Skills system documentation |

## Core References

| Document | Description |
| --- | --- |
| [CLAUDE_RULES](CLAUDE_RULES.md) | Core development rules (check before writing, reuse, verify) |
| [CLAUDE_WORKFLOW](CLAUDE_WORKFLOW.md) | Full development workflow |
| [AUTOBOT_REFERENCE](AUTOBOT_REFERENCE.md) | IPs, playbooks, quick reference |
| [DEVELOPER_SETUP](DEVELOPER_SETUP.md) | Developer onboarding |
| [HARDCODING_PREVENTION](HARDCODING_PREVENTION.md) | Rules against hardcoded values |

## Architecture & Design

| Document | Description |
| --- | --- |
| [01-architecture](01-architecture.md) | System architecture overview |
| [02-process-flow](02-process-flow.md) | Request handling flow |
| [03-api-reference](03-api-reference.md) | API documentation |
| [04-configuration](04-configuration.md) | Configuration options |
| [SSOT_CONFIG_GUIDE](SSOT_CONFIG_GUIDE.md) | Single source of truth config |
| [ROLES](ROLES.md) | Role definitions |
| [TIERED_MODEL_ROUTING](TIERED_MODEL_ROUTING.md) | LLM tier routing |
| [THINKING_TOOLS_CONFIGURATION](THINKING_TOOLS_CONFIGURATION.md) | Thinking tools setup |
| [VNC_MCP_ARCHITECTURE](VNC_MCP_ARCHITECTURE.md) | VNC + MCP architecture |
| [WSL2_NETWORKING](WSL2_NETWORKING.md) | WSL2 networking guide |

## Patterns & Migration Guides

| Document | Description |
| --- | --- |
| [ASYNC_MIGRATION_GUIDE](ASYNC_MIGRATION_GUIDE.md) | Async conversion guide |
| [ASYNC_PATTERNS](ASYNC_PATTERNS.md) | Async patterns reference |
| [API_RESPONSE_MIGRATION](API_RESPONSE_MIGRATION.md) | API response standardisation |
| [LAZY_SINGLETON_MIGRATION](LAZY_SINGLETON_MIGRATION.md) | Lazy singleton pattern |
| [LAZY_SINGLETON_EXAMPLES](LAZY_SINGLETON_EXAMPLES.md) | Lazy singleton examples |
| [LOGGING_MIGRATION_GUIDE](LOGGING_MIGRATION_GUIDE.md) | Logging standardisation |
| [LOGGING_STANDARDS](LOGGING_STANDARDS.md) | Logging standards |
| [VALIDATORS_MIGRATION](VALIDATORS_MIGRATION.md) | Validator migration |
| [CONFIG_MIGRATION_CHECKLIST](CONFIG_MIGRATION_CHECKLIST.md) | Config migration checklist |
| [INITIALIZATION_PATTERN_MIGRATION](INITIALIZATION_PATTERN_MIGRATION.md) | Init pattern migration |
| [REDIS_CONSOLIDATION_MIGRATION_GUIDE](REDIS_CONSOLIDATION_MIGRATION_GUIDE.md) | Redis consolidation |

## Redis

| Document | Description |
| --- | --- |
| [REDIS_CLIENT_USAGE](REDIS_CLIENT_USAGE.md) | Redis client usage guide |
| [REDIS_CONNECTION_POOLING](REDIS_CONNECTION_POOLING.md) | Connection pooling |
| [REDIS_PERFORMANCE_OPTIMIZATION](REDIS_PERFORMANCE_OPTIMIZATION.md) | Performance tuning |

## Code Quality & Standards

| Document | Description |
| --- | --- |
| [CODE_QUALITY_ENFORCEMENT](CODE_QUALITY_ENFORCEMENT.md) | Enforcement rules |
| [CODE_QUALITY_IMPLEMENTATION](CODE_QUALITY_IMPLEMENTATION.md) | Implementation details |
| [CODE_REUSABILITY_GUIDE](CODE_REUSABILITY_GUIDE.md) | Reuse guide |
| [ERROR_CODE_CONVENTIONS](ERROR_CODE_CONVENTIONS.md) | Error code standards |
| [ERROR_MONITORING](ERROR_MONITORING.md) | Error monitoring setup |
| [ERROR_HANDLING_MIGRATION_EXAMPLE](ERROR_HANDLING_MIGRATION_EXAMPLE.md) | Error handling examples |
| [ERROR_HANDLING_REFACTORING_PLAN](ERROR_HANDLING_REFACTORING_PLAN.md) | Refactoring plan |
| [UTF8_ENFORCEMENT](UTF8_ENFORCEMENT.md) | UTF-8 encoding rules |

## Agents & AI

| Document | Description |
| --- | --- |
| [AGENT_OPTIMIZATION](AGENT_OPTIMIZATION.md) | Agent optimisation |
| [AGENT_OPTIMIZATION_SUMMARY](AGENT_OPTIMIZATION_SUMMARY.md) | Optimisation summary |
| [CLAUDE_API_OPTIMIZATION_SUITE](CLAUDE_API_OPTIMIZATION_SUITE.md) | Claude API optimisation |
| [VLLM_PROMPT_OPTIMIZATION_INTEGRATION](VLLM_PROMPT_OPTIMIZATION_INTEGRATION.md) | vLLM prompt optimisation |
| [CHROMADB_INDEXING_OPTIMIZATION](CHROMADB_INDEXING_OPTIMIZATION.md) | ChromaDB indexing |

## Infrastructure & Deployment

| Document | Description |
| --- | --- |
| [INFRASTRUCTURE_DEPLOYMENT](INFRASTRUCTURE_DEPLOYMENT.md) | Deployment guide |
| [SERVICE_MANAGEMENT](SERVICE_MANAGEMENT.md) | Service management |
| [ANSIBLE_CREDENTIAL_SECURITY](ANSIBLE_CREDENTIAL_SECURITY.md) | Ansible credential security |
| [OPENVINO_SETUP](OPENVINO_SETUP.md) | OpenVINO setup |

## Observability

| Document | Description |
| --- | --- |
| [PROMETHEUS_METRICS_USAGE](PROMETHEUS_METRICS_USAGE.md) | Prometheus metrics |
| [PROMETHEUS_GITHUB_METRICS](PROMETHEUS_GITHUB_METRICS.md) | GitHub metrics |
| [DISTRIBUTED_TRACING](DISTRIBUTED_TRACING.md) | Distributed tracing |
| [BACKEND_DEBUGGING](BACKEND_DEBUGGING.md) | Backend debugging |

## Testing

| Document | Description |
| --- | --- |
| [FRONTEND_TESTING](FRONTEND_TESTING.md) | Frontend testing guide (Pinia setup, vue-i18n, mocks) |

## Authentication & Security

| Document | Description |
| --- | --- |
| [AUTHENTICATION_RBAC](AUTHENTICATION_RBAC.md) | RBAC and user management (roles, permissions, JWT) |

## Features (2026-04-14)

New features implemented in the 2026-04-14 development session.

| Document | Description |
| --- | --- |
| [HOOKS_SYSTEM_GUIDE](HOOKS_SYSTEM_GUIDE.md) | Hook system — lifecycle event hooks for agents and workflows |
| [../api/USAGE_METERING_API](../api/USAGE_METERING_API.md) | Usage metering — LLM cost tracking, POST /usage/record, per-user cost queries |
| [PLUGIN_SDK](PLUGIN_SDK.md) | Plugin marketplace — SDK for building and publishing AutoBot plugins |
| [AutoResearch user guide](../user/guides/autoresearch-guide.md) | AutoResearch — self-improving experiment loop, prompt optimization, insights |
| Mobile Responsive UI | Chat interface, sidebar, and layout made responsive for mobile viewports (no separate doc — see issues #1804 and #4445) |

## Refactoring & Analysis

| Document | Description |
| --- | --- |
| [ROUTER_REFACTORING](ROUTER_REFACTORING.md) | Router refactoring |
| [THREAT_DETECTION_REFACTORING](THREAT_DETECTION_REFACTORING.md) | Threat detection refactoring |
| [CODE_FINGERPRINTING_REFACTORING](CODE_FINGERPRINTING_REFACTORING.md) | Code fingerprinting |
| [CODE_SMELL_REFACTORING_SUMMARY](CODE_SMELL_REFACTORING_SUMMARY.md) | Code smell summary |
| [CONSOLIDATION_PROJECT_STATUS](CONSOLIDATION_PROJECT_STATUS.md) | Consolidation status |
| [HTTP_CLIENT_CONSOLIDATION_ASSESSMENT](HTTP_CLIENT_CONSOLIDATION_ASSESSMENT.md) | HTTP client consolidation |
| [CHAT_CONVERSATION_CONSOLIDATION_ASSESSMENT](CHAT_CONVERSATION_CONSOLIDATION_ASSESSMENT.md) | Chat consolidation |

## Knowledge & Memory

| Document | Description |
| --- | --- |
| [MEMORY_STORAGE_ROUTINE](MEMORY_STORAGE_ROUTINE.md) | Memory storage routine |
| [UNIFIED_MEMORY_MANAGER_IMPLEMENTATION](UNIFIED_MEMORY_MANAGER_IMPLEMENTATION.md) | Unified memory manager |
| [CHAT_KNOWLEDGE_SERVICE_INTEGRATION](CHAT_KNOWLEDGE_SERVICE_INTEGRATION.md) | Chat-knowledge integration |
| [QUICK_REFERENCE_CHAT_KNOWLEDGE_SERVICE](QUICK_REFERENCE_CHAT_KNOWLEDGE_SERVICE.md) | Chat-knowledge quick ref |

## Miscellaneous

| Document | Description |
| --- | --- |
| [MCP_MANAGEMENT_GUIDE](MCP_MANAGEMENT_GUIDE.md) | MCP management |
| [PLUGIN_SDK](PLUGIN_SDK.md) | Plugin SDK |
| [CLAUDE_MD_OPTIMIZATION_PLAN](CLAUDE_MD_OPTIMIZATION_PLAN.md) | CLAUDE.md optimisation |
| [APPROVAL_STATUS_DESIGN_IMPROVEMENT](APPROVAL_STATUS_DESIGN_IMPROVEMENT.md) | Approval status design |
| [INSIGHTS_IMPROVEMENTS](INSIGHTS_IMPROVEMENTS.md) | Insights improvements |
| [ARCHITECTURE_COMPLIANCE_IMPLEMENTATION_REPORT](ARCHITECTURE_COMPLIANCE_IMPLEMENTATION_REPORT.md) | Compliance report |
