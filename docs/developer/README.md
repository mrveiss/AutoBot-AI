---
tags: [type/reference, status/current]
date: 2026-06-04
---

# Developer Reference — Index

All docs in `docs/developer/`. Every doc listed here; missing entry = orphan or gap.

---

## Getting Started

| Doc | What it covers |
|---|---|
| [[DEVELOPER_SETUP]] | Local dev environment setup |
| [[CLAUDE_RULES]] | Core engineering rules (check before write, reuse, etc.) |
| [[CLAUDE_WORKFLOW]] | Branch workflow, PR process, batch implementation |
| [[AUTOBOT_REFERENCE]] | IPs, service ports, playbook cheat sheet |
| [[CANONICAL_RULES]] | Canonical naming and anti-duplication rules |

---

## Backend — Patterns & How-Tos

| Doc | What it covers |
|---|---|
| [[ASYNC_PATTERNS]] | Async-first patterns; never block the event loop |
| [[ASYNC_MIGRATION_GUIDE]] | Migrating sync → async code |
| [[REDIS_CLIENT_USAGE]] | `get_redis_client` / `get_async_redis_client` usage |
| [[REDIS_CONNECTION_POOLING]] | Connection pool configuration and sizing |
| [[REDIS_CONSOLIDATION_MIGRATION_GUIDE]] | Redis database consolidation |
| [[REDIS_PERFORMANCE_OPTIMIZATION]] | Query patterns, pipeline usage, N+1 avoidance |
| [[SSOT_CONFIG_GUIDE]] | Using `autobot_shared.ssot_config` |
| [[LOGGING_STANDARDS]] | `logging.getLogger(__name__)`, no `print()` |
| [[LOGGING_MIGRATION_GUIDE]] | Migrating legacy logging patterns |
| [[ERROR_CODE_CONVENTIONS]] | Error codes, exception hierarchy |
| [[ERROR_HANDLING_MIGRATION_EXAMPLE]] | Before/after for error handling patterns |
| [[HARDCODING_PREVENTION]] | How to avoid hardcoded values |
| [[UTF8_ENFORCEMENT]] | Always `encoding='utf-8'` |
| [[PRIMITIVES]] | Core shared primitives |
| [[INITIALIZATION_PATTERN_MIGRATION]] | Singleton and lazy init patterns |
| [[LAZY_SINGLETON_MIGRATION]] | `lazy_singleton()` helper usage |
| [[LAZY_SINGLETON_EXAMPLES]] | Examples of lazy singleton pattern |
| [[VALIDATORS_MIGRATION]] | Pydantic v2 validator migration |
| [[context-overflow-protection]] | Context window monitoring and auto-summarisation |
| [[llm-fallback]] | Automatic model fallback on 429/quota errors |
| [[causal-inference]] | CausalInferenceEngine integration |

---

## Backend — Causal Reasoning

| Doc | What it covers |
|---|---|
| [[causal-inference]] | How to wire up CausalInferenceEngine |
| [[context-overflow-protection]] | Context overflow protection for LLC agents |

---

## Backend — Infrastructure

| Doc | What it covers |
|---|---|
| [[INFRASTRUCTURE_DEPLOYMENT]] | Ansible deployment overview |
| [[ANSIBLE_CREDENTIAL_SECURITY]] | Credential handling in Ansible roles |
| [[ANSIBLE_ROLE_NAMES]] | Canonical Ansible role naming |
| [[SERVICE_MANAGEMENT]] | systemd service management |
| [[CONTAINER_SECURITY]] | Docker container security requirements |
| [[PKI_CA_ROTATION]] | PKI certificate authority rotation |
| [[SINGLE_HOST_DEPLOYMENT]] | Single-server deployment guide |
| [[WSL2_NETWORKING]] | WSL2 networking quirks (mirrored mode, port reservations) |
| [[OPENVINO_SETUP]] | OpenVINO / NPU setup |

---

## Backend — Agent System

| Doc | What it covers |
|---|---|
| [[AGENT_OPTIMIZATION]] | Agent performance optimisation |
| [[HEARTBEAT_SYSTEM]] | LLC heartbeat and quota monitoring |
| [[THINKING_TOOLS_CONFIGURATION]] | Think Tool configuration |
| [[TIERED_MODEL_ROUTING]] | Routing to Opus/Sonnet/Haiku by task cost |
| [[MEMORY_STORAGE_ROUTINE]] | Agent memory storage patterns |
| [[HOOKS_SYSTEM_GUIDE]] | Hook system and event lifecycle |
| [[PROMPT_MIDDLEWARE_GUIDE]] | Prompt middleware pipeline |
| [[VLLM_PROMPT_OPTIMIZATION_INTEGRATION]] | vLLM prompt optimisation |

---

## Backend — Code Analysis & Quality

| Doc | What it covers |
|---|---|
| [[CODE_QUALITY_ENFORCEMENT]] | Pre-commit hooks, linting rules |
| [[CODE_REUSABILITY_GUIDE]] | When to extract shared code |
| [[CODE_FINGERPRINTING_REFACTORING]] | Code fingerprinting patterns |
| [[CHROMADB_INDEXING_OPTIMIZATION]] | ChromaDB index optimisation |
| [[DISTRIBUTED_TRACING]] | OpenTelemetry / distributed trace setup |
| [[ERROR_MONITORING]] | Sentry / error monitoring configuration |
| [[PROMETHEUS_METRICS_USAGE]] | Adding Prometheus metrics |
| [[PROMETHEUS_GITHUB_METRICS]] | GitHub Actions metrics in Prometheus |

---

## Backend — Chat & Knowledge

| Doc | What it covers |
|---|---|
| [[CHAT_KNOWLEDGE_SERVICE_INTEGRATION]] | Chat × knowledge service integration |
| [[QUICK_REFERENCE_CHAT_KNOWLEDGE_SERVICE]] | Quick reference for chat/knowledge API |
| [[CHAT_CONVERSATION_CONSOLIDATION_ASSESSMENT]] | Chat conversation consolidation analysis |

---

## Frontend — Patterns & How-Tos

| Doc | What it covers |
|---|---|
| [[DESIGN_SYSTEM]] | Design system overview |
| [[theming]] | CSS three-tier architecture; design tokens |
| [[COMPOSABLE_HTTP_PATTERNS]] | HTTP composable patterns |
| [[FRONTEND_COMPOSABLES]] | Composable index and usage guide |
| [[frontend-testing]] | Vitest / Playwright testing guide |
| [[frontend-type-generation]] | TypeScript type generation from backend |
| [[virtual-scrolling]] | `useVirtualList` composable |
| [[ROUTER_REGISTRY]] | Vue Router and navItems registration |
| [[ROUTER_REFACTORING]] | Router refactoring guide |
| [[NOTIFICATION_SUPPRESSION]] | Suppressing duplicate notifications |
| [[APPROVAL_STATUS_DESIGN_IMPROVEMENT]] | Approval status UI patterns |

---

## Frontend — Internationalisation

| Doc | What it covers |
|---|---|
| [[I18N_ADDING_LANGUAGE]] | Adding a new language |

---

## Plugins & Extensions

| Doc | What it covers |
|---|---|
| [[PLUGIN_SDK]] | Plugin SDK overview |
| [[PLUGIN_PUBLISHING_GUIDE]] | Publishing a plugin |
| [[plugin-boundaries]] | What belongs in a plugin vs core |
| [[plugin-vs-extension-vs-skill]] | Plugin / extension / skill — when to use which |
| [[MCP_BRIDGE_ISOLATION]] | MCP bridge isolation requirements |
| [[MCP_MANAGEMENT_GUIDE]] | Managing MCP tools |
| [[LANGCHAIN_MCP_INTEGRATION]] | LangChain × MCP integration |

---

## API & Authentication

| Doc | What it covers |
|---|---|
| [[AUTHENTICATION_RBAC]] | RBAC and JWT scope model |
| [[API_RESPONSE_MIGRATION]] | API response shape migration |
| [[ROLES]] | Role definitions |

---

## Migration Guides

| Doc | What it covers |
|---|---|
| [[CONFIG_MIGRATION_CHECKLIST]] | Config migration checklist |
| [[HTTP_CLIENT_CONSOLIDATION_ASSESSMENT]] | HTTP client consolidation |
| [[THREAT_DETECTION_REFACTORING]] | Threat detection refactoring |

---

## Assessments (status/stale — verify before using)

| Doc | Status |
|---|---|
| [[AGENT_OPTIMIZATION_SUMMARY]] | Summary of past optimisation sprint |
| [[ARCHITECTURE_COMPLIANCE_IMPLEMENTATION_REPORT]] | One-time compliance report |
| [[CODE_QUALITY_IMPLEMENTATION]] | Implementation report |
| [[CODE_SMELL_REFACTORING_SUMMARY]] | Refactoring summary |
| [[CONSOLIDATION_PROJECT_STATUS]] | Consolidation project status |
| [[INSIGHTS_IMPROVEMENTS]] | Insights improvements tracking |
| [[UNIFIED_MEMORY_MANAGER_IMPLEMENTATION]] | Implementation report |
| [[WORKTREE_SAFETY_INVESTIGATION]] | Worktree safety investigation |
| [[analytics-e2e-verification]] | Analytics E2E verification (point-in-time) |

---

## Missing Coverage (gaps — needs a doc)

- Redis schema migrations how-to
- WebSocket protocol reference (client ↔ server message shapes)
- Agent orchestration API reference
- Knowledge base ECL pipeline how-to
- NPU worker integration guide
